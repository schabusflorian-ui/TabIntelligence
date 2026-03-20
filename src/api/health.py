"""
Health check endpoints for monitoring and orchestration.

Provides:
- Liveness probe: Is the service running?
- Readiness probe: Can the service handle requests?
- Detailed database health: Connection pool and query performance
- Stale job detection: Find jobs stuck in PENDING/PROCESSING

These endpoints are used by Kubernetes and monitoring systems to
determine service health and route traffic accordingly.
"""

import time
from datetime import datetime, timedelta
from typing import Any, Dict

from fastapi import APIRouter, Depends, Response
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_api_key
from src.core.config import get_settings
from src.core.logging import api_logger as logger
from src.db.resilience import db_circuit_breaker
from src.db.session import async_engine, get_db, get_db_async
from src.storage.s3 import get_s3_client

router = APIRouter(prefix="/health", tags=["health"])


# ============================================================================
# Root Health Check (moved from main.py)
# ============================================================================


@router.get("", status_code=200)
async def health(db: Session = Depends(get_db)):
    """
    Comprehensive health check with component status.

    Returns status of all dependent services (database, S3).
    Returns 200 if healthy, 503 if any critical component is down.
    """
    from datetime import timezone as tz

    checks: Dict[str, Any] = {
        "status": "healthy",
        "version": get_settings().app_version,
        "timestamp": datetime.now(tz.utc).isoformat(),
        "components": {},
    }

    # Database check
    try:
        start = time.time()
        db.execute(text("SELECT 1"))
        latency_ms = round((time.time() - start) * 1000, 2)
        checks["components"]["database"] = {"status": "up", "latency_ms": latency_ms}
    except Exception as e:
        checks["status"] = "degraded"
        checks["components"]["database"] = {"status": "down", "error": str(e)}

    # S3/MinIO check
    try:
        s3_settings = get_settings()
        s3_client = get_s3_client(s3_settings)
        s3_client.ensure_bucket_exists()
        checks["components"]["s3"] = {"status": "up", "bucket": s3_settings.s3_bucket}
    except Exception as e:
        checks["components"]["s3"] = {"status": "down", "error": str(e)}

    status_code = 200 if checks["status"] == "healthy" else 503
    return JSONResponse(content=checks, status_code=status_code)


# ============================================================================
# Liveness Probe
# ============================================================================


@router.get("/liveness", status_code=200)
async def liveness():
    """
    Liveness probe - is the service alive?

    Returns 200 if the service is running. Does not check database connectivity.
    This endpoint is used by Kubernetes to determine if the container should be restarted.

    Use this for:
    - Kubernetes liveness probe
    - Uptime monitoring
    - Basic health check

    Returns:
        dict: Status information

    Example response:
        {
            "status": "alive",
            "timestamp": "2026-02-24T12:00:00"
        }
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================================================
# Readiness Probe
# ============================================================================


@router.get("/readiness")
async def readiness():
    """
    Readiness probe - is the service ready to handle requests?

    Returns 200 if database is accessible, 503 otherwise.
    This endpoint is used by Kubernetes to determine if traffic should be routed to this instance.

    Use this for:
    - Kubernetes readiness probe
    - Load balancer health checks
    - Deployment verification

    Returns:
        Response: 200 if ready, 503 if not ready

    Example response (ready):
        {
            "status": "ready",
            "database": "connected",
            "timestamp": "2026-02-24T12:00:00"
        }

    Example response (not ready):
        {
            "status": "not_ready",
            "database": "disconnected",
            "error": "could not connect to server",
            "timestamp": "2026-02-24T12:00:00"
        }
    """
    try:
        # Quick database connectivity check
        start = time.time()
        async with get_db_async() as db:
            await db.execute(text("SELECT 1"))
        query_time = (time.time() - start) * 1000  # Convert to ms

        logger.debug(f"Readiness check passed ({query_time:.2f}ms)")

        return {
            "status": "ready",
            "database": "connected",
            "query_time_ms": round(query_time, 2),
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Readiness check failed: {e}")

        return JSONResponse(
            content={
                "status": "not_ready",
                "database": "disconnected",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# ============================================================================
# Detailed Database Health
# ============================================================================


@router.get("/database")
async def database_health(_api_key=Depends(get_current_api_key)) -> Dict[str, Any]:
    """
    Detailed database health check with connection pool status.

    Returns comprehensive information about database health including:
    - Query performance
    - Connection pool utilization
    - Circuit breaker state

    Use this for:
    - Monitoring dashboards
    - Performance debugging
    - Capacity planning

    Returns:
        dict: Detailed health information

    Example response (healthy):
        {
            "status": "healthy",
            "query_time_ms": 12.5,
            "pool": {
                "size": 10,
                "checked_out": 2,
                "overflow": 0,
                "total_connections": 10
            },
            "circuit_breaker": {
                "state": "closed",
                "success_rate": 0.99
            },
            "timestamp": "2026-02-24T12:00:00"
        }

    Example response (degraded):
        {
            "status": "degraded",
            "reason": "High connection pool utilization",
            "query_time_ms": 1250.0,
            "pool": {
                "size": 10,
                "checked_out": 18,
                "overflow": 8,
                "total_connections": 18
            },
            "circuit_breaker": {
                "state": "half_open",
                "success_rate": 0.75
            },
            "timestamp": "2026-02-24T12:00:00"
        }
    """
    try:
        # Measure query performance
        start = time.time()
        async with get_db_async() as db:
            # Test basic query
            result = await db.execute(text("SELECT 1"))
            result.scalar()

            # Get PostgreSQL version for verification
            version_result = await db.execute(text("SELECT version()"))
            pg_version = version_result.scalar()

        query_time = (time.time() - start) * 1000  # Convert to ms

        # Get connection pool status
        pool = async_engine.pool
        pool_info = {
            "size": pool.size(),  # type: ignore[attr-defined]
            "checked_out": pool.checkedout(),  # type: ignore[attr-defined]
            "overflow": pool.overflow(),  # type: ignore[attr-defined]
            "total_connections": pool.size() + pool.overflow(),  # type: ignore[attr-defined]
        }

        # Get circuit breaker stats
        breaker_stats = db_circuit_breaker.get_stats()
        circuit_info = {
            "state": breaker_stats["state"],
            "success_rate": breaker_stats["success_rate"],
            "total_requests": breaker_stats["total_requests"],
            "failed_requests": breaker_stats["failed_requests"],
        }

        # Determine overall health status
        status = "healthy"
        warnings = []

        # Check query performance
        if query_time > 1000:  # > 1 second
            status = "degraded"
            warnings.append(f"Slow query performance ({query_time:.0f}ms)")
        elif query_time > 500:  # > 500ms
            warnings.append(f"Elevated query latency ({query_time:.0f}ms)")

        # Check connection pool utilization
        pool_utilization = pool_info["checked_out"] / pool_info["total_connections"]
        if pool_utilization > 0.9:  # > 90%
            status = "degraded"
            warnings.append(f"High connection pool utilization ({pool_utilization:.0%})")
        elif pool_utilization > 0.75:  # > 75%
            warnings.append(f"Elevated connection pool utilization ({pool_utilization:.0%})")

        # Check circuit breaker
        if circuit_info["state"] == "open":
            status = "unhealthy"
            warnings.append("Circuit breaker is OPEN")
        elif circuit_info["state"] == "half_open":
            status = "degraded"
            warnings.append("Circuit breaker is HALF_OPEN (recovering)")

        # Check success rate
        if circuit_info["success_rate"] < 0.9:  # < 90%
            status = "degraded"
            warnings.append(f"Low success rate ({circuit_info['success_rate']:.0%})")

        response = {
            "status": status,
            "query_time_ms": round(query_time, 2),
            "pool": pool_info,
            "circuit_breaker": circuit_info,
            "postgresql_version": pg_version.split(",")[0] if pg_version else "unknown",
            "timestamp": datetime.utcnow().isoformat(),
        }

        if warnings:
            response["warnings"] = warnings

        logger.info(f"Database health check: {status} ({len(warnings)} warnings)")

        return response

    except Exception as e:
        logger.error(f"Database health check failed: {e}")

        return JSONResponse(  # type: ignore[return-value]
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# ============================================================================
# Circuit Breaker Status
# ============================================================================


@router.get("/circuit-breaker")
async def circuit_breaker_status(_api_key=Depends(get_current_api_key)):
    """
    Get circuit breaker status and statistics.

    Returns detailed information about the circuit breaker state,
    useful for monitoring and debugging.

    Returns:
        dict: Circuit breaker statistics

    Example response:
        {
            "state": "closed",
            "consecutive_failures": 0,
            "total_requests": 12500,
            "successful_requests": 12450,
            "failed_requests": 50,
            "rejected_requests": 0,
            "success_rate": 0.996,
            "last_state_change": "2026-02-24T10:30:00"
        }
    """
    stats = db_circuit_breaker.get_stats()
    return {
        **stats,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================================================
# Metrics Endpoint (Prometheus-compatible)
# ============================================================================


@router.get("/db-metrics", include_in_schema=False)
async def db_metrics(_api_key=Depends(get_current_api_key)):
    """
    Prometheus-compatible metrics endpoint.

    Returns metrics in Prometheus text format for scraping.
    This is used by monitoring systems to collect time-series data.

    Returns:
        str: Metrics in Prometheus format

    Example output:
        # HELP database_query_time_ms Database query time in milliseconds
        # TYPE database_query_time_ms gauge
        database_query_time_ms 12.5

        # HELP database_pool_size Database connection pool size
        # TYPE database_pool_size gauge
        database_pool_size 10
    """
    try:
        # Quick health check
        start = time.time()
        async with get_db_async() as db:
            await db.execute(text("SELECT 1"))
        query_time = (time.time() - start) * 1000

        # Get pool info
        pool = async_engine.pool
        pool_size = pool.size()  # type: ignore[attr-defined]
        pool_checked_out = pool.checkedout()  # type: ignore[attr-defined]
        pool_overflow = pool.overflow()  # type: ignore[attr-defined]

        # Get circuit breaker stats
        breaker_stats = db_circuit_breaker.get_stats()

        breaker_state = (
            0
            if breaker_stats["state"] == "closed"
            else 1
            if breaker_stats["state"] == "half_open"
            else 2
        )

        # Format as Prometheus metrics
        metrics_output = f"""# HELP database_query_time_ms Database query time in milliseconds
# TYPE database_query_time_ms gauge
database_query_time_ms {query_time:.2f}

# HELP database_pool_size Database connection pool size
# TYPE database_pool_size gauge
database_pool_size {pool_size}

# HELP database_pool_checked_out Database connections currently in use
# TYPE database_pool_checked_out gauge
database_pool_checked_out {pool_checked_out}

# HELP database_pool_overflow Database overflow connections in use
# TYPE database_pool_overflow gauge
database_pool_overflow {pool_overflow}

# HELP database_circuit_breaker_state Circuit breaker state (0=closed, 1=half_open, 2=open)
# TYPE database_circuit_breaker_state gauge
database_circuit_breaker_state {breaker_state}

# HELP database_requests_total Total database requests
# TYPE database_requests_total counter
database_requests_total {breaker_stats["total_requests"]}

# HELP database_requests_failed Failed database requests
# TYPE database_requests_failed counter
database_requests_failed {breaker_stats["failed_requests"]}

# HELP database_requests_rejected Rejected database requests (circuit open)
# TYPE database_requests_rejected counter
database_requests_rejected {breaker_stats["rejected_requests"]}
"""

        return Response(content=metrics_output, media_type="text/plain")

    except Exception as e:
        logger.error(f"Metrics endpoint failed: {e}")
        return Response(
            content=f"# Error collecting metrics: {e}\n",
            media_type="text/plain",
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# ============================================================================
# Stale Job Detection
# ============================================================================


@router.get("/stale-jobs")
async def stale_jobs(_api_key=Depends(get_current_api_key)):
    """
    Check for stale PENDING/PROCESSING jobs.

    Detects jobs that may be stuck:
    - PENDING jobs older than 10 minutes (should have been picked up by Celery)
    - PROCESSING jobs older than 30 minutes (typical extraction takes < 10 min)

    Use this for:
    - Monitoring dashboards
    - Alerting on stuck jobs
    - Operational debugging

    Returns:
        dict: Stale job counts and IDs

    Example response (healthy):
        {
            "status": "ok",
            "stale_pending": [],
            "stale_processing": [],
            "stale_pending_count": 0,
            "stale_processing_count": 0,
            "timestamp": "2026-03-04T12:00:00"
        }

    Example response (stale jobs found):
        {
            "status": "warning",
            "stale_pending": ["abc-123"],
            "stale_processing": ["def-456"],
            "stale_pending_count": 1,
            "stale_processing_count": 1,
            "timestamp": "2026-03-04T12:00:00"
        }
    """
    try:
        from src.db.models import ExtractionJob, JobStatusEnum
        from src.db.session import get_db_context

        now = datetime.utcnow()
        pending_cutoff = now - timedelta(minutes=10)
        processing_cutoff = now - timedelta(minutes=30)

        with get_db_context() as db:
            stale_pending = (
                db.query(ExtractionJob)
                .filter(
                    ExtractionJob.status == JobStatusEnum.PENDING,
                    ExtractionJob.created_at < pending_cutoff,
                )
                .all()
            )

            stale_processing = (
                db.query(ExtractionJob)
                .filter(
                    ExtractionJob.status == JobStatusEnum.PROCESSING,
                    ExtractionJob.updated_at < processing_cutoff,
                )
                .all()
            )

        pending_ids = [str(j.job_id) for j in stale_pending]
        processing_ids = [str(j.job_id) for j in stale_processing]

        status = "ok"
        if pending_ids or processing_ids:
            status = "warning"
            logger.warning(
                f"Stale jobs detected: {len(pending_ids)} pending, {len(processing_ids)} processing"
            )

        return {
            "status": status,
            "stale_pending": pending_ids,
            "stale_processing": processing_ids,
            "stale_pending_count": len(pending_ids),
            "stale_processing_count": len(processing_ids),
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Stale job check failed: {e}")
        return JSONResponse(
            content={
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )
