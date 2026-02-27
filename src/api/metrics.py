"""
Prometheus metrics for DebtFund API.

Defines application-level metrics and a middleware to collect HTTP request data.
Exposes a /metrics endpoint for Prometheus scraping.
"""
import time
from typing import Callable

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.logging import api_logger as logger


# ============================================================================
# METRIC DEFINITIONS
# ============================================================================

# HTTP request metrics
http_requests_total = Counter(
    "debtfund_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "debtfund_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

http_requests_in_progress = Gauge(
    "debtfund_http_requests_in_progress",
    "Number of HTTP requests currently being processed",
    ["method"],
)

# Extraction job metrics
extraction_jobs_total = Counter(
    "debtfund_extraction_jobs_total",
    "Total extraction jobs by status",
    ["status"],
)

extraction_duration_seconds = Histogram(
    "debtfund_extraction_duration_seconds",
    "Extraction pipeline duration in seconds",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

# File upload metrics
file_uploads_total = Counter(
    "debtfund_file_uploads_total",
    "Total file uploads",
)

file_upload_bytes = Histogram(
    "debtfund_file_upload_bytes",
    "File upload size in bytes",
    buckets=[10_000, 100_000, 500_000, 1_000_000, 5_000_000, 10_000_000, 50_000_000, 100_000_000],
)

# Database metrics
db_query_duration_seconds = Histogram(
    "debtfund_db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)


# ============================================================================
# MIDDLEWARE
# ============================================================================

def _normalize_path(path: str) -> str:
    """
    Normalize URL path to prevent cardinality explosion.

    Replaces UUIDs and numeric IDs with placeholders.
    """
    import re
    # Replace UUIDs
    path = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{id}",
        path,
    )
    # Replace numeric IDs in path segments
    path = re.sub(r"/\d+(?=/|$)", "/{id}", path)
    return path


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to collect HTTP request metrics for Prometheus.

    Tracks request count, duration, and in-progress requests.
    Skips metrics collection for the /metrics endpoint itself.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip metrics endpoint to avoid self-referential counting
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        path = _normalize_path(request.url.path)

        http_requests_in_progress.labels(method=method).inc()
        start_time = time.time()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            duration = time.time() - start_time
            http_requests_in_progress.labels(method=method).dec()
            http_requests_total.labels(
                method=method, endpoint=path, status_code=status_code
            ).inc()
            http_request_duration_seconds.labels(
                method=method, endpoint=path
            ).observe(duration)

        return response


# ============================================================================
# ENDPOINT
# ============================================================================

async def metrics_endpoint(request: Request) -> Response:
    """
    Prometheus metrics endpoint.

    Returns all collected metrics in Prometheus exposition format.
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
