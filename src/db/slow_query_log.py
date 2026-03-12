"""
Slow query logging via SQLAlchemy event listeners.

Attaches to SQLAlchemy Engine events to measure and log query execution time.
Queries exceeding the threshold are logged as warnings with full statement details.

Usage:
    from src.db.slow_query_log import attach_slow_query_logging
    attach_slow_query_logging(engine, threshold_ms=100)
"""

import time

from sqlalchemy import event
from sqlalchemy.engine import Engine

from src.core.logging import database_logger as logger

# Try importing Prometheus metric (optional - don't fail if not available)
try:
    from src.api.metrics import db_query_duration_seconds

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


def attach_slow_query_logging(
    engine: Engine,
    threshold_ms: float = 100.0,
) -> None:
    """
    Attach slow query logging event listeners to a SQLAlchemy engine.

    Args:
        engine: SQLAlchemy Engine instance
        threshold_ms: Log queries slower than this threshold (milliseconds)
    """

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("query_start_time", []).append(time.time())

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        start_times = conn.info.get("query_start_time")
        if not start_times:
            return

        total_time = time.time() - start_times.pop()
        total_ms = total_time * 1000

        # Record Prometheus metric if available
        if METRICS_AVAILABLE:
            operation = _classify_operation(statement)
            db_query_duration_seconds.labels(operation=operation).observe(total_time)

        # Log slow queries
        if total_ms > threshold_ms:
            # Truncate long statements for readability
            stmt_preview = statement[:500] + "..." if len(statement) > 500 else statement
            logger.warning(
                "Slow query detected",
                extra={
                    "duration_ms": round(total_ms, 2),
                    "threshold_ms": threshold_ms,
                    "statement": stmt_preview,
                    "executemany": executemany,
                },
            )

    logger.info(f"Slow query logging attached (threshold: {threshold_ms}ms)")


def _classify_operation(statement: str) -> str:
    """Classify SQL statement into operation type for metrics labels."""
    stmt_upper = statement.strip().upper()
    if stmt_upper.startswith("SELECT"):
        return "select"
    elif stmt_upper.startswith("INSERT"):
        return "insert"
    elif stmt_upper.startswith("UPDATE"):
        return "update"
    elif stmt_upper.startswith("DELETE"):
        return "delete"
    else:
        return "other"
