"""
DebtFund - API Server
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from src.api.rate_limit import limiter
from src.core.config import get_settings
from src.core.exceptions import FileStorageError
from src.core.logging import api_logger as logger
from src.core.logging import setup_logging

# Tracing is optional (Week 3 feature) - don't block if not installed
try:
    from src.core.tracing import instrument_fastapi, setup_tracing

    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    logger.warning("OpenTelemetry not installed - tracing disabled (install for Week 3)")
# Initialize logging
# Use JSON format in production for machine-parseable logs
import os

from src.api.analytics import router as analytics_router
from src.api.corrections import router as corrections_router
from src.api.dlq import router as dlq_router
from src.api.entities import router as entities_router
from src.api.files import router as files_router
from src.api.health import router as health_router
from src.api.jobs import router as jobs_router
from src.api.metrics import MetricsMiddleware, metrics_endpoint
from src.api.middleware import RequestIDMiddleware
from src.api.middleware.security_headers import SecurityHeadersMiddleware
from src.api.taxonomy import router as taxonomy_router
from src.db.session import get_db
from src.storage.s3 import get_s3_client

use_json_logging = os.getenv("LOG_FORMAT", "plain").lower() == "json"
setup_logging(level="INFO", use_json=use_json_logging)


# ============================================================================
# Lifespan context manager (replaces deprecated @app.on_event)
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    # --- STARTUP ---
    from src.db.base import create_tables

    # Initialize distributed tracing (optional)
    if TRACING_AVAILABLE:
        setup_tracing(service_name="debtfund-api")
        instrument_fastapi(app)
        logger.info("Distributed tracing initialized")
    else:
        logger.info("Distributed tracing disabled (OpenTelemetry not installed)")

    # Initialize database tables (supplement to alembic)
    create_tables()
    logger.info("Database initialized successfully")

    # Attach slow query logging to sync engine
    from src.db.session import get_sync_engine
    from src.db.slow_query_log import attach_slow_query_logging

    attach_slow_query_logging(get_sync_engine(), threshold_ms=100)
    logger.info("Slow query logging enabled (threshold: 100ms)")

    # Ensure S3 bucket exists
    try:
        settings = get_settings()
        s3_client = get_s3_client(settings)
        s3_client.ensure_bucket_exists()
        logger.info(f"S3 bucket '{settings.s3_bucket}' ready")
    except FileStorageError as e:
        logger.error(f"S3 bucket initialization failed: {str(e)}")
        logger.warning("Application starting without S3 storage")

    logger.info("DebtFund API server started")
    yield

    # --- SHUTDOWN ---
    logger.info("DebtFund API server shutting down...")
    from src.db.session import async_engine, get_sync_engine

    try:
        await async_engine.dispose()
        get_sync_engine().dispose()
        logger.info("Database connections closed")
    except Exception as e:
        logger.warning(f"Error closing database connections: {e}")
    logger.info("DebtFund API server stopped")


_settings = get_settings()

_openapi_tags = [
    {"name": "entities", "description": "Company/asset entity CRUD and pattern management."},
    {"name": "jobs", "description": "Extraction job lifecycle: submit, poll, export, retry, review."},
    {"name": "files", "description": "Upload Excel models (.xlsx/.xls) for extraction."},
    {"name": "taxonomy", "description": "Browse/search the 297-item canonical financial taxonomy."},
    {"name": "analytics", "description": "Cross-entity comparison, portfolio summary, structured statements."},
    {"name": "corrections", "description": "User corrections that train entity-specific patterns."},
    {"name": "admin-dlq", "description": "Dead-letter queue for failed extraction jobs."},
    {"name": "health", "description": "Liveness/readiness probes and component health checks."},
]

app = FastAPI(
    title="DebtFund",
    version=_settings.app_version,
    description="**DebtFund** — Guided hybrid extraction platform for financial models. "
    "Extracts structured line items from Excel using Claude AI, maps to canonical taxonomy.",
    openapi_tags=_openapi_tags,
    contact={"name": "DebtFund", "email": "support@debtfund.example.com"},
    license_info={"name": "Proprietary"},
    lifespan=lifespan,
)

logger.info("DebtFund API module loaded")

# Attach shared rate limiter to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)

# Add request ID middleware for correlation tracking
app.add_middleware(RequestIDMiddleware)

# Add security response headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Add Prometheus metrics middleware
app.add_middleware(MetricsMiddleware)

# Prometheus metrics endpoint — protected by auth in production
# In production, prefer network-level protection (e.g. internal-only port).
# The endpoint is still hidden from OpenAPI schema.
app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)

# Kubernetes-style health probes (liveness, readiness, database health)
app.include_router(health_router)

# Taxonomy browsing and search endpoints
app.include_router(taxonomy_router)

# Entity CRUD endpoints
app.include_router(entities_router)

# File browsing and upload endpoints
app.include_router(files_router)

# Job management endpoints (list, status, export, retry, review, lineage)
app.include_router(jobs_router)

# DLQ admin endpoints
app.include_router(dlq_router)

# User correction and entity pattern endpoints
app.include_router(corrections_router)

# Analytics endpoints (cross-entity, portfolio, trends, coverage, costs)
app.include_router(analytics_router)

# Serve frontend static files
_static_dir = Path(__file__).parent.parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
async def root():
    """Root endpoint — serves frontend UI if available, otherwise returns service info."""
    index = _static_dir / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return {
        "service": "DebtFund - Excel Model Intelligence",
        "version": _settings.app_version,
        "status": "operational",
    }


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    """
    Comprehensive health check with component status.

    Returns status of all dependent services (database, S3).
    Returns 200 if healthy, 503 if any critical component is down.
    """
    import time
    from datetime import datetime
    from datetime import timezone as tz

    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    checks = {
        "status": "healthy",
        "version": _settings.app_version,
        "timestamp": datetime.now(tz.utc).isoformat(),
        "components": {},
    }

    # Database check
    try:
        start = time.time()
        db.execute(text("SELECT 1"))
        latency_ms = round((time.time() - start) * 1000, 2)
        checks["components"]["database"] = {"status": "up", "latency_ms": latency_ms}  # type: ignore[index]
    except Exception as e:
        checks["status"] = "degraded"
        checks["components"]["database"] = {"status": "down", "error": str(e)}  # type: ignore[index]

    # S3/MinIO check
    try:
        s3_settings = get_settings()
        s3_client = get_s3_client(s3_settings)
        s3_client.ensure_bucket_exists()
        checks["components"]["s3"] = {"status": "up", "bucket": s3_settings.s3_bucket}  # type: ignore[index]
    except Exception as e:
        checks["components"]["s3"] = {"status": "down", "error": str(e)}  # type: ignore[index]

    status_code = 200 if checks["status"] == "healthy" else 503
    return JSONResponse(content=checks, status_code=status_code)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
