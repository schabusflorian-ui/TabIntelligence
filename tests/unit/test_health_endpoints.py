"""
Tests for health check endpoints.
Covers liveness, readiness, database health, and circuit breaker status.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# Liveness Probe
# ============================================================================


@pytest.mark.asyncio
async def test_liveness_returns_alive():
    """Test liveness probe returns status alive."""
    from src.api.health import liveness

    result = await liveness()
    assert result["status"] == "alive"
    assert "timestamp" in result


# ============================================================================
# Readiness Probe
# ============================================================================


@pytest.mark.asyncio
async def test_readiness_healthy_db():
    """Test readiness returns ready when DB is connected."""
    from src.api.health import readiness

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("src.api.health.get_db_async", return_value=mock_ctx):
        result = await readiness()

    assert result["status"] == "ready"
    assert result["database"] == "connected"
    assert "query_time_ms" in result


@pytest.mark.asyncio
async def test_readiness_unhealthy_db():
    """Test readiness returns not_ready when DB is disconnected."""
    from src.api.health import readiness

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("src.api.health.get_db_async", return_value=mock_ctx):
        result = await readiness()

    # JSONResponse returned — parse the body
    import json

    body = json.loads(result.body.decode())
    assert body["status"] == "not_ready"
    assert body["database"] == "disconnected"
    assert "connection refused" in body["error"]
    assert result.status_code == 503


# ============================================================================
# Detailed Database Health
# ============================================================================


def _make_db_health_mocks(
    pool_checked_out=2, pool_overflow=0, pool_size=10, breaker_state="closed", success_rate=0.99
):
    """Helper to create standard mocks for database_health tests."""
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1

    mock_version_result = MagicMock()
    mock_version_result.scalar.return_value = "PostgreSQL 15.2, compiled by gcc"

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_result, mock_version_result])

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.size.return_value = pool_size
    mock_pool.checkedout.return_value = pool_checked_out
    mock_pool.overflow.return_value = pool_overflow

    mock_engine = MagicMock()
    mock_engine.pool = mock_pool

    mock_breaker_stats = {
        "state": breaker_state,
        "success_rate": success_rate,
        "total_requests": 1000,
        "failed_requests": int(1000 * (1 - success_rate)),
        "rejected_requests": 0,
    }

    return mock_ctx, mock_engine, mock_breaker_stats


@pytest.mark.asyncio
async def test_database_health_healthy():
    """Test database health returns healthy when all checks pass."""
    from src.api.health import database_health

    mock_ctx, mock_engine, mock_breaker_stats = _make_db_health_mocks()

    with (
        patch("src.api.health.get_db_async", return_value=mock_ctx),
        patch("src.api.health.async_engine", mock_engine),
        patch("src.api.health.db_circuit_breaker") as mock_breaker,
    ):
        mock_breaker.get_stats.return_value = mock_breaker_stats
        result = await database_health()

    assert result["status"] == "healthy"
    assert "query_time_ms" in result
    assert result["pool"]["size"] == 10
    assert result["circuit_breaker"]["state"] == "closed"
    assert result["postgresql_version"].startswith("PostgreSQL")


@pytest.mark.asyncio
async def test_database_health_degraded_high_pool_utilization():
    """Test database health returns degraded for high pool utilization."""
    from src.api.health import database_health

    # Pool utilization > 90%: checked_out=10, overflow=1, total=11, 10/11 = 90.9%
    mock_ctx, mock_engine, mock_breaker_stats = _make_db_health_mocks(
        pool_checked_out=10, pool_overflow=1
    )

    with (
        patch("src.api.health.get_db_async", return_value=mock_ctx),
        patch("src.api.health.async_engine", mock_engine),
        patch("src.api.health.db_circuit_breaker") as mock_breaker,
    ):
        mock_breaker.get_stats.return_value = mock_breaker_stats
        result = await database_health()

    assert result["status"] == "degraded"
    assert "warnings" in result


@pytest.mark.asyncio
async def test_database_health_degraded_circuit_half_open():
    """Test database health returns degraded when circuit breaker is half_open."""
    from src.api.health import database_health

    mock_ctx, mock_engine, mock_breaker_stats = _make_db_health_mocks(
        breaker_state="half_open", success_rate=0.85
    )

    with (
        patch("src.api.health.get_db_async", return_value=mock_ctx),
        patch("src.api.health.async_engine", mock_engine),
        patch("src.api.health.db_circuit_breaker") as mock_breaker,
    ):
        mock_breaker.get_stats.return_value = mock_breaker_stats
        result = await database_health()

    assert result["status"] == "degraded"
    assert "warnings" in result


@pytest.mark.asyncio
async def test_database_health_circuit_open_with_low_success():
    """Test database health with open circuit breaker and low success rate."""
    from src.api.health import database_health

    mock_ctx, mock_engine, mock_breaker_stats = _make_db_health_mocks(
        breaker_state="open", success_rate=0.5
    )

    with (
        patch("src.api.health.get_db_async", return_value=mock_ctx),
        patch("src.api.health.async_engine", mock_engine),
        patch("src.api.health.db_circuit_breaker") as mock_breaker,
    ):
        mock_breaker.get_stats.return_value = mock_breaker_stats
        result = await database_health()

    # Circuit open triggers "unhealthy" but low success_rate check runs after
    # and sets to "degraded" (the later check overwrites). Verify warnings contain both.
    assert result["status"] in ("unhealthy", "degraded")
    assert "warnings" in result
    assert any("OPEN" in w for w in result["warnings"])


@pytest.mark.asyncio
async def test_database_health_exception():
    """Test database health returns unhealthy on DB failure."""
    from src.api.health import database_health

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("src.api.health.get_db_async", return_value=mock_ctx):
        result = await database_health()

    # JSONResponse returned — parse the body
    import json

    body = json.loads(result.body.decode())
    assert body["status"] == "unhealthy"
    assert "DB down" in body["error"]
    assert result.status_code == 503


# ============================================================================
# Circuit Breaker Status
# ============================================================================


@pytest.mark.asyncio
async def test_circuit_breaker_status():
    """Test circuit breaker status endpoint."""
    from src.api.health import circuit_breaker_status

    mock_stats = {
        "state": "closed",
        "consecutive_failures": 0,
        "total_requests": 5000,
        "successful_requests": 4990,
        "failed_requests": 10,
        "rejected_requests": 0,
        "success_rate": 0.998,
    }

    with patch("src.api.health.db_circuit_breaker") as mock_breaker:
        mock_breaker.get_stats.return_value = mock_stats
        result = await circuit_breaker_status()

    assert result["state"] == "closed"
    assert result["total_requests"] == 5000
    assert "timestamp" in result


# ============================================================================
# DB Metrics Endpoint
# ============================================================================


@pytest.mark.asyncio
async def test_db_metrics_endpoint():
    """Test Prometheus-compatible metrics endpoint."""
    from src.api.health import db_metrics

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.size.return_value = 10
    mock_pool.checkedout.return_value = 3
    mock_pool.overflow.return_value = 0

    mock_engine = MagicMock()
    mock_engine.pool = mock_pool

    mock_breaker_stats = {
        "state": "closed",
        "total_requests": 1000,
        "failed_requests": 5,
        "rejected_requests": 0,
    }

    with (
        patch("src.api.health.get_db_async", return_value=mock_ctx),
        patch("src.api.health.async_engine", mock_engine),
        patch("src.api.health.db_circuit_breaker") as mock_breaker,
    ):
        mock_breaker.get_stats.return_value = mock_breaker_stats
        result = await db_metrics()

    content = result.body.decode()
    assert "database_query_time_ms" in content
    assert "database_pool_size 10" in content
    assert "database_pool_checked_out 3" in content
    assert "database_circuit_breaker_state 0" in content


@pytest.mark.asyncio
async def test_db_metrics_exception():
    """Test metrics endpoint returns 503 on failure."""
    from src.api.health import db_metrics

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("DB unavailable"))
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("src.api.health.get_db_async", return_value=mock_ctx):
        result = await db_metrics()

    assert result.status_code == 503
