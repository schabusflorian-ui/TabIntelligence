# World-Class Database Session: Improvement Roadmap

**Current Status:** Production Ready (9/10)
**Target:** World-Class Product Experience (10/10)
**Date:** 2026-02-24

---

## Executive Summary

The current async database session implementation is **excellent and production-ready**. To achieve **world-class product experience**, we need to focus on:

1. **Testing & Quality** - Comprehensive test coverage with async patterns
2. **Observability** - Metrics, tracing, and monitoring
3. **Resilience** - Retry logic, circuit breakers, graceful degradation
4. **Performance** - Advanced optimization and query monitoring
5. **Developer Experience** - Better tooling, debugging, and error messages
6. **Operations** - Health checks, migrations, disaster recovery
7. **Documentation** - Comprehensive guides and examples

**Investment Required:** ~40-60 hours
**Impact:** Transforms from "works well" to "delightful to use and operate"

---

## 1. Testing & Quality (CRITICAL) 🔴

**Current State:** 0% test coverage for async session
**Target:** 90%+ coverage with comprehensive async tests

### 1.1 Async Session Test Suite

**Priority:** P0 (CRITICAL)
**Effort:** 8-12 hours
**Impact:** Prevents regressions, enables confident refactoring

**File:** `tests/unit/test_async_session.py`

```python
"""
Comprehensive async session tests.
"""
import pytest
from sqlalchemy import text, select
from sqlalchemy.exc import SQLAlchemyError

from src.db.session import (
    AsyncSessionLocal,
    get_db,
    get_db_context,
    get_async_database_url,
    init_db,
    close_db,
)
from src.db.models import ExtractionJob


@pytest.mark.asyncio
class TestAsyncDatabaseURL:
    """Test URL conversion logic."""

    async def test_convert_sync_to_async(self):
        """PostgreSQL URL converted to asyncpg."""
        url = "postgresql://user:pass@localhost:5432/db"
        result = get_async_database_url(url)
        assert result == "postgresql+asyncpg://user:pass@localhost:5432/db"

    async def test_already_async_url_unchanged(self):
        """Already async URL not modified."""
        url = "postgresql+asyncpg://user:pass@localhost:5432/db"
        result = get_async_database_url(url)
        assert result == url

    async def test_invalid_url_raises_error(self):
        """Invalid URL raises ValueError."""
        with pytest.raises(ValueError, match="Invalid database URL"):
            get_async_database_url("mysql://localhost/db")


@pytest.mark.asyncio
class TestAsyncSessionLifecycle:
    """Test session creation, usage, and cleanup."""

    async def test_session_creation(self, async_db):
        """Session can be created."""
        async with AsyncSessionLocal() as session:
            assert session is not None
            assert session.is_active

    async def test_session_executes_query(self, async_db):
        """Session executes queries successfully."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1 as value"))
            assert result.scalar() == 1

    async def test_session_automatic_commit(self, async_db):
        """Session commits automatically on success."""
        async with AsyncSessionLocal() as session:
            job = ExtractionJob(
                file_id="test-123",
                status="pending"
            )
            session.add(job)

        # Verify committed by querying in new session
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ExtractionJob).where(
                    ExtractionJob.file_id == "test-123"
                )
            )
            found = result.scalar_one_or_none()
            assert found is not None
            assert found.status == "pending"

    async def test_session_automatic_rollback_on_error(self, async_db):
        """Session rolls back on error."""
        with pytest.raises(SQLAlchemyError):
            async with AsyncSessionLocal() as session:
                job = ExtractionJob(
                    file_id="test-456",
                    status="pending"
                )
                session.add(job)
                # Force error
                await session.execute(text("SELECT * FROM nonexistent_table"))

        # Verify rolled back
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ExtractionJob).where(
                    ExtractionJob.file_id == "test-456"
                )
            )
            found = result.scalar_one_or_none()
            assert found is None  # Not committed

    async def test_session_cleanup_on_exception(self, async_db):
        """Session cleaned up even on exception."""
        session_id = None
        try:
            async with AsyncSessionLocal() as session:
                session_id = id(session)
                raise Exception("Test error")
        except Exception:
            pass

        # Session should be closed (can't verify directly, but no leak)
        assert session_id is not None


@pytest.mark.asyncio
class TestFastAPIDependency:
    """Test get_db() FastAPI dependency."""

    async def test_get_db_yields_session(self, async_db):
        """get_db() yields valid session."""
        async for db in get_db():
            assert db is not None
            assert db.is_active
            break  # Only need first yield

    async def test_get_db_commits_on_success(self, async_db):
        """get_db() commits automatically."""
        async for db in get_db():
            job = ExtractionJob(
                file_id="test-fastapi-1",
                status="pending"
            )
            db.add(job)
            break

        # Verify committed
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ExtractionJob).where(
                    ExtractionJob.file_id == "test-fastapi-1"
                )
            )
            assert result.scalar_one_or_none() is not None

    async def test_get_db_rolls_back_on_error(self, async_db):
        """get_db() rolls back on error."""
        with pytest.raises(Exception):
            async for db in get_db():
                job = ExtractionJob(
                    file_id="test-fastapi-2",
                    status="pending"
                )
                db.add(job)
                raise Exception("Test error")

        # Verify rolled back
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ExtractionJob).where(
                    ExtractionJob.file_id == "test-fastapi-2"
                )
            )
            assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
class TestContextManager:
    """Test get_db_context() for background tasks."""

    async def test_context_manager_commits(self, async_db):
        """Context manager commits on success."""
        async with get_db_context() as db:
            job = ExtractionJob(
                file_id="test-context-1",
                status="pending"
            )
            db.add(job)

        # Verify committed
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ExtractionJob).where(
                    ExtractionJob.file_id == "test-context-1"
                )
            )
            assert result.scalar_one_or_none() is not None

    async def test_context_manager_rolls_back_on_error(self, async_db):
        """Context manager rolls back on error."""
        with pytest.raises(Exception):
            async with get_db_context() as db:
                job = ExtractionJob(
                    file_id="test-context-2",
                    status="pending"
                )
                db.add(job)
                raise Exception("Test error")

        # Verify rolled back
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ExtractionJob).where(
                    ExtractionJob.file_id == "test-context-2"
                )
            )
            assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
class TestDatabaseUtilities:
    """Test init_db() and close_db()."""

    async def test_init_db_creates_tables(self):
        """init_db() creates all tables."""
        await init_db()
        # Tables should exist
        async with AsyncSessionLocal() as session:
            result = await session.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ))
            tables = [row[0] for row in result]
            assert 'extraction_jobs' in tables
            assert 'files' in tables

    async def test_close_db_closes_connections(self):
        """close_db() closes all connections."""
        # Create session to open connection
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))

        # Close all connections
        await close_db()

        # Can still create new sessions after close
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
```

**Fixtures needed in `tests/conftest.py`:**

```python
@pytest.fixture
async def async_db():
    """Async database fixture with rollback."""
    from src.db.session import AsyncSessionLocal, init_db

    # Initialize database
    await init_db()

    # Provide session
    async with AsyncSessionLocal() as session:
        yield session
        # Rollback after test
        await session.rollback()
```

### 1.2 Integration Tests

**Priority:** P0 (CRITICAL)
**Effort:** 4-6 hours

**File:** `tests/integration/test_database_integration.py`

```python
"""
Test database integration with API and background tasks.
"""
import pytest
from httpx import AsyncClient

from src.api.main import app
from src.db.session import get_db_context
from src.db.models import ExtractionJob


@pytest.mark.asyncio
class TestAPIIntegration:
    """Test database integration in API endpoints."""

    async def test_api_creates_job_in_database(self, async_client):
        """API endpoint creates job in database."""
        response = await async_client.post(
            "/api/v1/files/upload",
            files={"file": ("test.xlsx", b"test data", "application/vnd.ms-excel")}
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        # Verify job in database
        async with get_db_context() as db:
            result = await db.execute(
                select(ExtractionJob).where(
                    ExtractionJob.job_id == job_id
                )
            )
            job = result.scalar_one()
            assert job.status == "pending"

    async def test_concurrent_requests_use_separate_sessions(self, async_client):
        """Concurrent API requests use separate database sessions."""
        import asyncio

        # Send 10 concurrent requests
        tasks = [
            async_client.post(
                "/api/v1/files/upload",
                files={"file": (f"test{i}.xlsx", b"test data", "application/vnd.ms-excel")}
            )
            for i in range(10)
        ]

        responses = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r.status_code == 200 for r in responses)

        # All jobs should be in database
        job_ids = [r.json()["job_id"] for r in responses]
        async with get_db_context() as db:
            result = await db.execute(
                select(ExtractionJob).where(
                    ExtractionJob.job_id.in_(job_ids)
                )
            )
            jobs = result.scalars().all()
            assert len(jobs) == 10
```

### 1.3 Performance Tests

**Priority:** P1 (HIGH)
**Effort:** 4-6 hours

**File:** `tests/performance/test_db_performance.py`

```python
"""
Performance tests for database operations.
"""
import pytest
import asyncio
import time

from src.db.session import AsyncSessionLocal
from src.db.models import ExtractionJob


@pytest.mark.asyncio
class TestConnectionPool:
    """Test connection pool performance."""

    async def test_pool_handles_concurrent_sessions(self):
        """Connection pool handles 50 concurrent sessions."""
        async def create_session():
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("SELECT 1"))
                await asyncio.sleep(0.1)  # Simulate work
                return result.scalar()

        start = time.time()
        results = await asyncio.gather(*[create_session() for _ in range(50)])
        duration = time.time() - start

        assert all(r == 1 for r in results)
        assert duration < 5.0  # Should complete in under 5 seconds

    async def test_query_performance_baseline(self, async_db):
        """Establish baseline query performance."""
        # Insert 1000 jobs
        jobs = [
            ExtractionJob(file_id=f"perf-test-{i}", status="pending")
            for i in range(1000)
        ]
        async_db.add_all(jobs)
        await async_db.commit()

        # Query performance
        start = time.time()
        result = await async_db.execute(
            select(ExtractionJob).where(
                ExtractionJob.status == "pending"
            )
        )
        jobs = result.scalars().all()
        duration = time.time() - start

        assert len(jobs) == 1000
        assert duration < 0.5  # Should be very fast
```

**Success Criteria:**
- ✅ 90%+ test coverage for session module
- ✅ All async patterns tested
- ✅ Error scenarios covered
- ✅ Integration tests with API
- ✅ Performance baselines established

---

## 2. Observability & Monitoring (HIGH) 🟡

**Current State:** Basic logging only
**Target:** Full observability with metrics, tracing, and monitoring

### 2.1 Database Metrics

**Priority:** P0 (CRITICAL)
**Effort:** 8-12 hours

**File:** `src/db/metrics.py`

```python
"""
Database metrics collection and monitoring.
"""
from prometheus_client import Counter, Histogram, Gauge
import time
from functools import wraps
from contextlib import asynccontextmanager

# Connection pool metrics
db_pool_size = Gauge(
    'db_pool_size',
    'Current size of database connection pool'
)

db_pool_overflow = Gauge(
    'db_pool_overflow',
    'Current overflow connections in use'
)

db_pool_checked_out = Gauge(
    'db_pool_checked_out',
    'Number of connections currently checked out'
)

# Query metrics
db_queries_total = Counter(
    'db_queries_total',
    'Total number of database queries',
    ['operation', 'status']
)

db_query_duration = Histogram(
    'db_query_duration_seconds',
    'Database query duration in seconds',
    ['operation']
)

db_connection_errors = Counter(
    'db_connection_errors_total',
    'Total database connection errors',
    ['error_type']
)

# Transaction metrics
db_transactions_total = Counter(
    'db_transactions_total',
    'Total database transactions',
    ['status']  # committed, rolled_back
)

db_transaction_duration = Histogram(
    'db_transaction_duration_seconds',
    'Database transaction duration in seconds',
    ['status']
)


@asynccontextmanager
async def track_db_operation(operation: str):
    """
    Context manager to track database operation metrics.

    Usage:
        async with track_db_operation("insert_job"):
            await session.execute(...)
    """
    start = time.time()
    status = "success"

    try:
        yield
    except Exception as e:
        status = "error"
        db_connection_errors.labels(
            error_type=type(e).__name__
        ).inc()
        raise
    finally:
        duration = time.time() - start
        db_queries_total.labels(
            operation=operation,
            status=status
        ).inc()
        db_query_duration.labels(
            operation=operation
        ).observe(duration)


def update_pool_metrics(engine):
    """Update connection pool metrics from engine."""
    pool = engine.pool
    db_pool_size.set(pool.size())
    db_pool_overflow.set(pool.overflow())
    db_pool_checked_out.set(pool.checkedout())
```

**Enhanced session with metrics:**

```python
# In src/db/session.py
from src.db.metrics import (
    track_db_operation,
    db_transactions_total,
    db_transaction_duration,
    update_pool_metrics
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency with metrics tracking."""
    start = time.time()
    status = "committed"

    async with AsyncSessionLocal() as session:
        try:
            logger.debug("Database session created")
            yield session
            await session.commit()
            logger.debug("Database session committed")
        except Exception as e:
            status = "rolled_back"
            logger.error(f"Database session error: {str(e)}")
            await session.rollback()
            logger.debug("Database session rolled back")
            raise DatabaseError(
                f"Database session error: {str(e)}",
                operation="session_transaction",
            )
        finally:
            duration = time.time() - start
            db_transactions_total.labels(status=status).inc()
            db_transaction_duration.labels(status=status).observe(duration)
            await session.close()
            logger.debug("Database session closed")

            # Update pool metrics periodically
            update_pool_metrics(engine)
```

### 2.2 Distributed Tracing

**Priority:** P1 (HIGH)
**Effort:** 6-8 hours

**File:** `src/db/tracing.py`

```python
"""
Distributed tracing for database operations.
"""
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

tracer = trace.get_tracer(__name__)


def instrument_database():
    """Initialize database instrumentation."""
    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        service="debtfund-database",
    )


async def get_db_with_tracing() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency with tracing."""
    with tracer.start_as_current_span("database.session") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.connection_string", "localhost:5432/emi")

        async with AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                await session.rollback()
                raise
            finally:
                await session.close()
```

### 2.3 Query Logging & Slow Query Detection

**Priority:** P1 (HIGH)
**Effort:** 4-6 hours

```python
"""
Slow query detection and logging.
"""
import logging
from sqlalchemy import event
from sqlalchemy.engine import Engine

slow_query_logger = logging.getLogger("debtfund.database.slow_queries")
SLOW_QUERY_THRESHOLD = 1.0  # seconds


@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Record query start time."""
    conn.info.setdefault('query_start_time', []).append(time.time())


@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Log slow queries."""
    total_time = time.time() - conn.info['query_start_time'].pop()

    if total_time > SLOW_QUERY_THRESHOLD:
        slow_query_logger.warning(
            f"Slow query detected ({total_time:.2f}s): {statement[:200]}"
        )

        # Emit metric
        db_slow_queries_total.labels(
            duration_bucket=f"{int(total_time)}s"
        ).inc()
```

**Success Criteria:**
- ✅ Prometheus metrics exported
- ✅ Connection pool metrics tracked
- ✅ Query duration histograms
- ✅ Distributed tracing integrated
- ✅ Slow query detection active
- ✅ Grafana dashboards created

---

## 3. Resilience & Reliability (HIGH) 🟡

**Current State:** Basic error handling
**Target:** Production-grade resilience with retry, circuit breakers, graceful degradation

### 3.1 Retry Logic with Exponential Backoff

**Priority:** P0 (CRITICAL)
**Effort:** 4-6 hours

**File:** `src/db/resilience.py`

```python
"""
Database resilience patterns.
"""
import asyncio
from functools import wraps
from typing import TypeVar, Callable
import logging

from sqlalchemy.exc import OperationalError, TimeoutError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


def with_db_retry(
    max_attempts: int = 3,
    min_wait: float = 1,
    max_wait: float = 10,
):
    """
    Decorator to retry database operations with exponential backoff.

    Usage:
        @with_db_retry(max_attempts=3)
        async def get_job(db, job_id):
            return await db.execute(select(Job).where(Job.id == job_id))
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(min=min_wait, max=max_wait),
        retry=retry_if_exception_type((OperationalError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


async def execute_with_retry(
    session: AsyncSession,
    operation: Callable,
    *args,
    max_retries: int = 3,
    **kwargs
) -> T:
    """
    Execute database operation with automatic retry.

    Args:
        session: Database session
        operation: Async function to execute
        max_retries: Maximum retry attempts

    Returns:
        Operation result

    Example:
        result = await execute_with_retry(
            session,
            lambda s: s.execute(select(Job)),
            max_retries=3
        )
    """
    for attempt in range(max_retries):
        try:
            return await operation(session, *args, **kwargs)
        except (OperationalError, TimeoutError) as e:
            if attempt == max_retries - 1:
                logger.error(f"Database operation failed after {max_retries} attempts: {e}")
                raise

            wait_time = min(2 ** attempt, 10)  # Exponential backoff, max 10s
            logger.warning(
                f"Database operation failed (attempt {attempt + 1}/{max_retries}), "
                f"retrying in {wait_time}s: {e}"
            )
            await asyncio.sleep(wait_time)
```

### 3.2 Circuit Breaker Pattern

**Priority:** P1 (HIGH)
**Effort:** 6-8 hours

```python
"""
Circuit breaker for database connections.
"""
from enum import Enum
from datetime import datetime, timedelta
import asyncio


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failures detected, stop requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class DatabaseCircuitBreaker:
    """
    Circuit breaker for database operations.

    Prevents cascading failures by stopping requests to unhealthy database.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self.state = CircuitState.CLOSED
        self.failures = 0
        self.successes = 0
        self.last_failure_time = None

    async def call(self, operation: Callable) -> T:
        """Execute operation with circuit breaker protection."""
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if (datetime.now() - self.last_failure_time).seconds >= self.recovery_timeout:
                logger.info("Circuit breaker: entering HALF_OPEN state")
                self.state = CircuitState.HALF_OPEN
            else:
                raise DatabaseError(
                    "Circuit breaker is OPEN - database unavailable",
                    operation="circuit_breaker"
                )

        try:
            result = await operation()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        """Handle successful operation."""
        self.failures = 0

        if self.state == CircuitState.HALF_OPEN:
            self.successes += 1
            if self.successes >= self.success_threshold:
                logger.info("Circuit breaker: entering CLOSED state (recovered)")
                self.state = CircuitState.CLOSED
                self.successes = 0

    def _on_failure(self):
        """Handle failed operation."""
        self.failures += 1
        self.last_failure_time = datetime.now()
        self.successes = 0

        if self.failures >= self.failure_threshold:
            logger.error(
                f"Circuit breaker: entering OPEN state "
                f"({self.failures} consecutive failures)"
            )
            self.state = CircuitState.OPEN


# Global circuit breaker instance
db_circuit_breaker = DatabaseCircuitBreaker()
```

### 3.3 Health Checks

**Priority:** P0 (CRITICAL)
**Effort:** 2-4 hours

**File:** `src/api/health.py`

```python
"""
Database health check endpoints.
"""
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from src.db.session import get_db_context

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/liveness")
async def liveness():
    """
    Liveness probe - is the service running?

    Returns 200 if service is up (doesn't check database).
    """
    return {"status": "alive"}


@router.get("/readiness")
async def readiness():
    """
    Readiness probe - is the service ready to handle requests?

    Returns 200 if database is accessible, 503 otherwise.
    """
    try:
        async with get_db_context() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        return Response(
            content={"status": "not_ready", "error": str(e)},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@router.get("/health/database")
async def database_health():
    """
    Detailed database health check.

    Returns connection pool status and query performance.
    """
    try:
        from src.db.session import engine

        start = time.time()
        async with get_db_context() as db:
            await db.execute(text("SELECT 1"))
        query_time = time.time() - start

        pool = engine.pool

        return {
            "status": "healthy",
            "query_time_ms": round(query_time * 1000, 2),
            "pool": {
                "size": pool.size(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "total_connections": pool.size() + pool.overflow(),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        return Response(
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
```

**Success Criteria:**
- ✅ Retry logic with exponential backoff
- ✅ Circuit breaker prevents cascading failures
- ✅ Health check endpoints (liveness, readiness)
- ✅ Graceful degradation on database unavailability
- ✅ Connection pool monitoring

---

## 4. Performance Optimization (MEDIUM) 🟢

**Current State:** Good baseline performance
**Target:** Optimized for high throughput and low latency

### 4.1 Connection Pool Tuning

**Priority:** P1 (HIGH)
**Effort:** 2-4 hours

**File:** `src/core/config.py` (add settings)

```python
# Database connection pool settings
database_pool_size: int = Field(
    default=10,
    description="Database connection pool size"
)

database_pool_max_overflow: int = Field(
    default=20,
    description="Maximum overflow connections"
)

database_pool_recycle: int = Field(
    default=3600,
    description="Connection recycle time in seconds"
)

database_pool_timeout: int = Field(
    default=30,
    description="Connection timeout in seconds"
)

database_statement_timeout: int = Field(
    default=30000,  # 30 seconds
    description="Statement timeout in milliseconds"
)
```

**Enhanced engine creation:**

```python
# In src/db/session.py
engine = create_async_engine(
    async_database_url,
    echo=settings.is_development,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_pool_max_overflow,
    pool_recycle=settings.database_pool_recycle,
    pool_pre_ping=True,
    pool_timeout=settings.database_pool_timeout,
    connect_args={
        "server_settings": {
            "application_name": "debtfund",
            "statement_timeout": str(settings.database_statement_timeout),
        },
        "command_timeout": 60,
    },
)
```

### 4.2 Query Optimization & Monitoring

**Priority:** P2 (MEDIUM)
**Effort:** 4-6 hours

```python
"""
Query optimization utilities.
"""
from sqlalchemy import event
from sqlalchemy.engine import Engine


class QueryStats:
    """Track query statistics for optimization."""

    def __init__(self):
        self.query_counts = {}
        self.slow_queries = []

    def record_query(self, statement: str, duration: float):
        """Record query execution."""
        # Track query frequency
        query_hash = hash(statement[:100])
        self.query_counts[query_hash] = self.query_counts.get(query_hash, 0) + 1

        # Track slow queries
        if duration > 1.0:
            self.slow_queries.append({
                'statement': statement[:500],
                'duration': duration,
                'count': self.query_counts[query_hash],
            })

    def get_most_frequent_queries(self, limit: int = 10):
        """Get most frequently executed queries."""
        return sorted(
            self.query_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]

    def get_optimization_suggestions(self):
        """Suggest query optimizations."""
        suggestions = []

        # Frequent queries without indexes
        for query, count in self.get_most_frequent_queries():
            if count > 100:
                suggestions.append(f"Consider adding index for frequent query (executed {count} times)")

        # Slow queries
        if self.slow_queries:
            suggestions.append(f"Found {len(self.slow_queries)} slow queries - review and optimize")

        return suggestions
```

### 4.3 Read Replicas Support

**Priority:** P2 (MEDIUM)
**Effort:** 6-8 hours

```python
"""
Read replica support for scaling read operations.
"""
from sqlalchemy.ext.asyncio import create_async_engine

# Primary database (write operations)
primary_engine = create_async_engine(settings.database_url, ...)

# Read replicas (read operations)
replica_engines = [
    create_async_engine(url, ...)
    for url in settings.database_replica_urls
]


class DatabaseRouter:
    """Route queries to primary or replicas."""

    def __init__(self):
        self.replica_index = 0

    def get_read_engine(self):
        """Get next replica engine (round-robin)."""
        if not replica_engines:
            return primary_engine

        engine = replica_engines[self.replica_index]
        self.replica_index = (self.replica_index + 1) % len(replica_engines)
        return engine

    def get_write_engine(self):
        """Get primary engine for writes."""
        return primary_engine
```

**Success Criteria:**
- ✅ Configurable connection pool settings
- ✅ Statement timeout enforced
- ✅ Query statistics tracked
- ✅ Optimization suggestions generated
- ✅ Read replica support (optional)

---

## 5. Developer Experience (MEDIUM) 🟢

**Current State:** Good docstrings and error messages
**Target:** Exceptional developer experience with tooling and debugging

### 5.1 Enhanced Error Messages

**Priority:** P1 (HIGH)
**Effort:** 3-4 hours

```python
"""
Enhanced database error messages with context and suggestions.
"""
from sqlalchemy.exc import IntegrityError, OperationalError
from src.core.exceptions import DatabaseError


class EnhancedDatabaseError(DatabaseError):
    """Database error with helpful context and suggestions."""

    def __init__(
        self,
        message: str,
        operation: str,
        original_error: Exception = None,
        context: dict = None,
        suggestions: list = None,
    ):
        super().__init__(message, operation)
        self.original_error = original_error
        self.context = context or {}
        self.suggestions = suggestions or []

    def __str__(self):
        """Format error with context and suggestions."""
        parts = [f"Database error in {self.operation}: {self.args[0]}"]

        if self.context:
            parts.append("\nContext:")
            for key, value in self.context.items():
                parts.append(f"  {key}: {value}")

        if self.suggestions:
            parts.append("\nSuggestions:")
            for suggestion in self.suggestions:
                parts.append(f"  - {suggestion}")

        if self.original_error:
            parts.append(f"\nOriginal error: {type(self.original_error).__name__}: {self.original_error}")

        return "\n".join(parts)


def enhance_database_error(error: Exception, operation: str, **context) -> EnhancedDatabaseError:
    """Convert SQLAlchemy error to enhanced error with suggestions."""
    suggestions = []

    if isinstance(error, IntegrityError):
        if "unique constraint" in str(error).lower():
            suggestions.append("This record already exists. Use update instead of insert.")
            suggestions.append("Check if a record with this ID or unique field already exists.")
        elif "foreign key constraint" in str(error).lower():
            suggestions.append("Referenced record does not exist. Create parent record first.")
            suggestions.append("Verify that foreign key references valid existing record.")
        elif "not null constraint" in str(error).lower():
            suggestions.append("Required field is missing. Check that all required fields are provided.")

    elif isinstance(error, OperationalError):
        if "could not connect" in str(error).lower():
            suggestions.append("Database server is not running or unreachable.")
            suggestions.append("Check DATABASE_URL environment variable.")
            suggestions.append("Verify PostgreSQL is running: docker-compose ps")
        elif "timeout" in str(error).lower():
            suggestions.append("Query took too long. Consider adding indexes.")
            suggestions.append("Check slow query logs for optimization opportunities.")

    return EnhancedDatabaseError(
        message=str(error),
        operation=operation,
        original_error=error,
        context=context,
        suggestions=suggestions,
    )


# Usage in session.py
try:
    await session.commit()
except Exception as e:
    enhanced_error = enhance_database_error(
        e,
        operation="session_commit",
        session_id=id(session),
        timestamp=datetime.utcnow().isoformat(),
    )
    logger.error(str(enhanced_error))
    raise enhanced_error
```

### 5.2 Database CLI Tool

**Priority:** P2 (MEDIUM)
**Effort:** 4-6 hours

**File:** `scripts/db_cli.py`

```python
"""
Database CLI tool for common operations.

Usage:
    python scripts/db_cli.py health
    python scripts/db_cli.py pool-status
    python scripts/db_cli.py slow-queries
    python scripts/db_cli.py migrate
"""
import click
import asyncio
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def cli():
    """Database CLI tool."""
    pass


@cli.command()
def health():
    """Check database health."""
    async def check():
        from src.db.session import get_db_context
        from sqlalchemy import text

        try:
            async with get_db_context() as db:
                result = await db.execute(text("SELECT version()"))
                version = result.scalar()

            console.print(f"✅ Database is healthy", style="green")
            console.print(f"PostgreSQL version: {version.split(',')[0]}")
        except Exception as e:
            console.print(f"❌ Database is unhealthy: {e}", style="red")

    asyncio.run(check())


@cli.command()
def pool_status():
    """Show connection pool status."""
    from src.db.session import engine

    pool = engine.pool

    table = Table(title="Connection Pool Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Pool Size", str(pool.size()))
    table.add_row("Checked Out", str(pool.checkedout()))
    table.add_row("Overflow", str(pool.overflow()))
    table.add_row("Total Connections", str(pool.size() + pool.overflow()))

    console.print(table)


@cli.command()
def slow_queries():
    """Show slow query statistics."""
    # Would integrate with query stats
    console.print("Slow query analysis coming soon...")


if __name__ == "__main__":
    cli()
```

### 5.3 Type-Safe Query Builders

**Priority:** P2 (MEDIUM)
**Effort:** 6-8 hours

```python
"""
Type-safe query builders for common operations.
"""
from typing import Generic, TypeVar, Type, List
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar('T')


class Repository(Generic[T]):
    """
    Generic repository for type-safe database operations.

    Usage:
        job_repo = Repository(ExtractionJob)
        job = await job_repo.get_by_id(session, "job-123")
        all_jobs = await job_repo.get_all(session)
    """

    def __init__(self, model: Type[T]):
        self.model = model

    async def get_by_id(self, session: AsyncSession, id: str) -> T | None:
        """Get record by ID."""
        result = await session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        session: AsyncSession,
        limit: int = 100,
        offset: int = 0
    ) -> List[T]:
        """Get all records with pagination."""
        result = await session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def create(self, session: AsyncSession, **kwargs) -> T:
        """Create new record."""
        instance = self.model(**kwargs)
        session.add(instance)
        await session.flush()
        return instance

    async def update(
        self,
        session: AsyncSession,
        id: str,
        **kwargs
    ) -> T | None:
        """Update record."""
        await session.execute(
            update(self.model)
            .where(self.model.id == id)
            .values(**kwargs)
        )
        return await self.get_by_id(session, id)

    async def delete(self, session: AsyncSession, id: str) -> bool:
        """Delete record."""
        result = await session.execute(
            delete(self.model).where(self.model.id == id)
        )
        return result.rowcount > 0
```

**Success Criteria:**
- ✅ Enhanced error messages with suggestions
- ✅ CLI tool for database operations
- ✅ Type-safe repository pattern
- ✅ Rich console output for debugging
- ✅ Query builder utilities

---

## 6. Production Operations (HIGH) 🟡

**Current State:** Basic init_db() and close_db()
**Target:** Full operational excellence

### 6.1 Migration Management

**Priority:** P0 (CRITICAL)
**Effort:** Already exists (Alembic), enhance with safety checks

```python
"""
Safe migration utilities.
"""
import asyncio
from alembic import command
from alembic.config import Config


async def check_migration_safety(revision: str) -> dict:
    """
    Check if migration is safe to run.

    Returns warnings about:
    - Table locks
    - Data loss potential
    - Downtime requirements
    """
    warnings = []

    # Parse migration script
    # Check for:
    # - DROP TABLE
    # - DROP COLUMN
    # - ALTER COLUMN (type change)
    # - CREATE UNIQUE INDEX (requires table lock)

    return {
        "safe": len(warnings) == 0,
        "warnings": warnings,
    }


async def migrate_with_backup(backup_path: str = None):
    """Run migrations with automatic backup."""
    # 1. Create backup
    # 2. Run migrations
    # 3. Verify migration
    # 4. If failed, restore backup
    pass
```

### 6.2 Backup & Restore

**Priority:** P1 (HIGH)
**Effort:** 4-6 hours

```python
"""
Database backup and restore utilities.
"""
import subprocess
from datetime import datetime


async def create_backup(output_path: str = None) -> str:
    """
    Create PostgreSQL backup.

    Returns path to backup file.
    """
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"backups/debtfund_{timestamp}.sql"

    # pg_dump command
    cmd = [
        "pg_dump",
        "-h", settings.db_host,
        "-U", settings.db_user,
        "-d", settings.db_name,
        "-f", output_path,
        "--clean",  # Include DROP statements
        "--if-exists",  # Use IF EXISTS
    ]

    subprocess.run(cmd, check=True)
    logger.info(f"Database backup created: {output_path}")

    return output_path


async def restore_backup(backup_path: str):
    """Restore database from backup."""
    cmd = [
        "psql",
        "-h", settings.db_host,
        "-U", settings.db_user,
        "-d", settings.db_name,
        "-f", backup_path,
    ]

    subprocess.run(cmd, check=True)
    logger.info(f"Database restored from: {backup_path}")
```

### 6.3 Connection Leak Detection

**Priority:** P1 (HIGH)
**Effort:** 3-4 hours

```python
"""
Detect and prevent connection leaks.
"""
import weakref
from collections import defaultdict


class ConnectionLeakDetector:
    """Track connection usage and detect leaks."""

    def __init__(self):
        self.connections = weakref.WeakValueDictionary()
        self.creation_stacks = {}
        self.active_count = defaultdict(int)

    def track_connection(self, conn_id: int, stack_trace: str):
        """Track new connection creation."""
        self.creation_stacks[conn_id] = {
            'stack': stack_trace,
            'created_at': datetime.now(),
        }
        self.active_count[stack_trace] += 1

    def release_connection(self, conn_id: int):
        """Track connection release."""
        if conn_id in self.creation_stacks:
            stack = self.creation_stacks[conn_id]['stack']
            self.active_count[stack] -= 1
            del self.creation_stacks[conn_id]

    def detect_leaks(self, threshold_minutes: int = 5) -> list:
        """Find connections open longer than threshold."""
        leaks = []
        now = datetime.now()

        for conn_id, info in self.creation_stacks.items():
            age_minutes = (now - info['created_at']).seconds / 60
            if age_minutes > threshold_minutes:
                leaks.append({
                    'connection_id': conn_id,
                    'age_minutes': age_minutes,
                    'stack': info['stack'],
                })

        return leaks
```

**Success Criteria:**
- ✅ Safe migration checks
- ✅ Automated backup/restore
- ✅ Connection leak detection
- ✅ Migration verification
- ✅ Rollback capabilities

---

## 7. Documentation & Examples (MEDIUM) 🟢

**Current State:** Good inline docstrings
**Target:** Comprehensive guides and patterns

### 7.1 Usage Guide

**Priority:** P2 (MEDIUM)
**Effort:** 4-6 hours

**File:** `docs/guides/DATABASE_USAGE_GUIDE.md`

```markdown
# Database Usage Guide

## Quick Start

### Basic Session Usage

```python
from src.db.session import get_db_context
from src.db.models import ExtractionJob

# In async function
async with get_db_context() as db:
    job = ExtractionJob(file_id="123", status="pending")
    db.add(job)
    # Automatic commit on exit
```

### FastAPI Integration

```python
from fastapi import Depends
from src.db.session import get_db

@app.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ExtractionJob).where(ExtractionJob.id == job_id)
    )
    return result.scalar_one_or_none()
```

## Best Practices

1. **Always use context managers** - Ensures cleanup
2. **Use repositories** - Type-safe, reusable
3. **Handle errors** - Catch specific exceptions
4. **Monitor performance** - Track slow queries
5. **Test with fixtures** - Use async test fixtures

## Common Patterns

See examples below...
```

### 7.2 Migration Guide

**File:** `docs/guides/DATABASE_MIGRATIONS.md`

```markdown
# Database Migration Guide

## Creating Migrations

```bash
# Auto-generate migration
alembic revision --autogenerate -m "Add user_id column"

# Create empty migration
alembic revision -m "Custom data migration"
```

## Running Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show current revision
alembic current
```

## Safety Checklist

Before running migrations:
- [ ] Backup database
- [ ] Review migration script
- [ ] Test in staging environment
- [ ] Plan downtime window (if needed)
- [ ] Have rollback plan ready
```

**Success Criteria:**
- ✅ Comprehensive usage guide
- ✅ Migration best practices documented
- ✅ Code examples for common patterns
- ✅ Troubleshooting guide
- ✅ Performance tuning guide

---

## Implementation Priority Matrix

| Category | Priority | Effort | Impact | When |
|----------|----------|--------|--------|------|
| **1. Testing** | P0 (CRITICAL) | 12-18h | 🔴 HIGH | Week 2 |
| **3.1 Retry Logic** | P0 (CRITICAL) | 4-6h | 🔴 HIGH | Week 2 |
| **3.3 Health Checks** | P0 (CRITICAL) | 2-4h | 🔴 HIGH | Week 2 |
| **6.1 Migration Safety** | P0 (CRITICAL) | 4-6h | 🔴 HIGH | Week 2 |
| **2.1 Metrics** | P0 (CRITICAL) | 8-12h | 🟡 MEDIUM | Week 3 |
| **3.2 Circuit Breaker** | P1 (HIGH) | 6-8h | 🟡 MEDIUM | Week 3 |
| **2.2 Tracing** | P1 (HIGH) | 6-8h | 🟡 MEDIUM | Week 3 |
| **4.1 Pool Tuning** | P1 (HIGH) | 2-4h | 🟡 MEDIUM | Week 3 |
| **5.1 Error Messages** | P1 (HIGH) | 3-4h | 🟢 LOW | Week 4 |
| **6.2 Backup/Restore** | P1 (HIGH) | 4-6h | 🟡 MEDIUM | Week 4 |
| **4.2 Query Optimization** | P2 (MEDIUM) | 4-6h | 🟢 LOW | Week 5 |
| **5.2 CLI Tool** | P2 (MEDIUM) | 4-6h | 🟢 LOW | Week 5 |
| **7. Documentation** | P2 (MEDIUM) | 8-10h | 🟢 LOW | Week 5 |

---

## Total Investment

**Week 2 (Critical):** 22-34 hours
**Week 3 (High Priority):** 22-34 hours
**Week 4-5 (Polish):** 19-26 hours

**Total:** 63-94 hours (~2-3 weeks)

---

## Success Metrics

### Code Quality
- ✅ 90%+ test coverage
- ✅ Zero known bugs
- ✅ All linting passes

### Performance
- ✅ < 50ms p95 query latency
- ✅ < 100ms p99 query latency
- ✅ 1000+ requests/second throughput

### Reliability
- ✅ 99.9% uptime
- ✅ Zero connection leaks
- ✅ Automatic recovery from failures

### Observability
- ✅ All metrics exported
- ✅ Distributed tracing enabled
- ✅ Slow query detection active
- ✅ Grafana dashboards deployed

### Operations
- ✅ Zero-downtime migrations
- ✅ Automated backups
- ✅ Health checks passing
- ✅ Runbooks documented

### Developer Experience
- ✅ < 5 minutes to understand and use
- ✅ Helpful error messages
- ✅ Type-safe APIs
- ✅ Comprehensive documentation

---

## World-Class Benchmark

Companies with world-class database infrastructure:
- **Stripe:** 99.999% uptime, comprehensive monitoring
- **Airbnb:** Auto-scaling, advanced observability
- **Netflix:** Circuit breakers, graceful degradation
- **GitHub:** Query optimization, read replicas

**Our Target:** Match these standards for our scale

---

## Next Steps

1. **Week 2:** Implement critical items (testing, retry, health)
2. **Week 3:** Add observability and resilience
3. **Week 4:** Operations and developer experience
4. **Week 5:** Documentation and polish

**Review:** Re-evaluate after Week 3 to measure impact

---

*Created: 2026-02-24*
*Last Updated: 2026-02-24*
*Status: DRAFT - Awaiting approval*
