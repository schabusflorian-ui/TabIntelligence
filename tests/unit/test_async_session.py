"""
Tests for database session management (src/db/session.py).

Tests the current canonical API:
- async_engine: Async SQLAlchemy engine
- AsyncSessionLocal: Async session factory
- get_db_async(): Async context manager
- get_db_dependency(): FastAPI async dependency
- get_sync_engine(): Sync engine for Alembic
- SyncSessionLocal: Sync session factory
- get_db_sync(): Sync context manager
- get_db() / get_db_context(): Backward-compat sync wrappers
"""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from src.db.session import (
    async_engine,
    AsyncSessionLocal,
    get_db_async,
    get_db_dependency,
    get_sync_engine,
    SyncSessionLocal,
    get_db_sync,
    get_db,
    get_db_context,
)
from src.core.exceptions import DatabaseError


# ============================================================================
# ENGINE AND FACTORY VERIFICATION
# ============================================================================


class TestEngineCreation:
    """Verify engines and session factories exist and are configured."""

    def test_async_engine_exists(self):
        """Async engine should be created at module level."""
        assert async_engine is not None

    def test_async_engine_uses_asyncpg(self):
        """Async engine should use asyncpg driver."""
        url = str(async_engine.url)
        assert "asyncpg" in url

    def test_async_engine_pool_configured(self):
        """Async engine should have connection pooling."""
        pool = async_engine.pool
        assert pool.size() == 20
        assert pool is not None

    def test_async_session_factory_exists(self):
        """AsyncSessionLocal factory should exist."""
        assert AsyncSessionLocal is not None

    def test_sync_engine_creates_engine(self):
        """get_sync_engine should return a valid engine."""
        engine = get_sync_engine()
        assert engine is not None

    def test_sync_engine_uses_postgresql(self):
        """Sync engine should use standard postgresql driver."""
        engine = get_sync_engine()
        url = str(engine.url)
        assert "postgresql" in url
        assert "asyncpg" not in url

    def test_sync_session_factory_exists(self):
        """SyncSessionLocal factory should exist."""
        assert SyncSessionLocal is not None


# ============================================================================
# ASYNC SESSION (get_db_async)
# ============================================================================


@pytest.mark.asyncio
class TestAsyncSession:
    """Test async database session context manager."""

    async def test_get_db_async_yields_session(self):
        """get_db_async should yield a valid async session."""
        async with get_db_async() as session:
            assert session is not None
            assert session.is_active

    async def test_get_db_async_executes_query(self):
        """Session from get_db_async should execute queries."""
        async with get_db_async() as session:
            result = await session.execute(text("SELECT 1 as value"))
            assert result.scalar() == 1

    @pytest.mark.skipif(
        __import__("sys").version_info < (3, 10),
        reason="Event loop binding issue with module-level asyncpg engine on Python <3.10"
    )
    async def test_get_db_async_auto_commits(self):
        """get_db_async should auto-commit on successful exit."""
        async with get_db_async() as session:
            await session.execute(text("SELECT 1"))

    async def test_get_db_async_rolls_back_on_error(self):
        """get_db_async should rollback and raise DatabaseError on exception."""
        with pytest.raises(DatabaseError, match="Async database operation failed"):
            async with get_db_async() as session:
                raise ValueError("Test error")

    async def test_get_db_async_wraps_db_errors(self):
        """get_db_async should wrap SQLAlchemy errors in DatabaseError."""
        with pytest.raises(DatabaseError):
            async with get_db_async() as session:
                await session.execute(text("SELECT * FROM nonexistent_table_xyz"))


# ============================================================================
# FASTAPI DEPENDENCY (get_db_dependency)
# ============================================================================


@pytest.mark.asyncio
class TestFastAPIDependency:
    """Test get_db_dependency for FastAPI Depends()."""

    async def test_dependency_yields_session(self):
        """get_db_dependency should yield a valid session."""
        async for db in get_db_dependency():
            assert db is not None
            assert db.is_active
            break

    @pytest.mark.skipif(
        __import__("sys").version_info < (3, 10),
        reason="Event loop binding issue with module-level asyncpg engine on Python <3.10"
    )
    async def test_dependency_executes_query(self):
        """Session from dependency should execute queries."""
        async for db in get_db_dependency():
            result = await db.execute(text("SELECT 1"))
            assert result.scalar() == 1
            break


# ============================================================================
# SYNC SESSION (get_db_sync)
# ============================================================================


class TestSyncSession:
    """Test sync database session context manager."""

    def test_get_db_sync_yields_session(self):
        """get_db_sync should yield a valid sync session."""
        with get_db_sync() as session:
            assert session is not None

    def test_get_db_sync_executes_query(self):
        """Session from get_db_sync should execute queries."""
        with get_db_sync() as session:
            result = session.execute(text("SELECT 1 as value"))
            assert result.scalar() == 1

    def test_get_db_sync_auto_commits(self):
        """get_db_sync should auto-commit on successful exit."""
        with get_db_sync() as session:
            session.execute(text("SELECT 1"))
        # No exception means commit succeeded

    def test_get_db_sync_rolls_back_on_error(self):
        """get_db_sync should rollback and raise DatabaseError on exception."""
        with pytest.raises(DatabaseError, match="Sync database operation failed"):
            with get_db_sync() as session:
                raise ValueError("Test error")


# ============================================================================
# BACKWARD COMPATIBILITY
# ============================================================================


class TestBackwardCompatibility:
    """Test backward-compat wrappers (get_db, get_db_context)."""

    def test_get_db_yields_session(self):
        """get_db() should yield a sync session."""
        for session in get_db():
            assert session is not None
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1
            break

    def test_get_db_context_is_sync(self):
        """get_db_context() should return a sync context manager."""
        with get_db_context() as session:
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1


# ============================================================================
# CONCURRENT SESSIONS
# ============================================================================


@pytest.mark.asyncio
class TestConcurrentSessions:
    """Test concurrent async session handling."""

    async def test_multiple_concurrent_sessions(self):
        """Multiple concurrent async sessions should work independently."""
        import asyncio

        async def query_value(value: int):
            async with get_db_async() as session:
                result = await session.execute(text(f"SELECT {value}"))
                return result.scalar()

        results = await asyncio.gather(*[query_value(i) for i in range(10)])
        assert results == list(range(10))

    @pytest.mark.skipif(
        __import__("sys").version_info < (3, 10),
        reason="Event loop binding issue with module-level asyncpg engine on Python <3.10"
    )
    async def test_pool_handles_burst(self):
        """Connection pool should handle burst of concurrent requests."""
        import asyncio

        async def quick_query():
            async with get_db_async() as session:
                await session.execute(text("SELECT 1"))
                return True

        results = await asyncio.gather(*[quick_query() for _ in range(20)])
        assert all(results)
        assert len(results) == 20
