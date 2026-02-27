"""
Database session management with both async and sync support.

This is the canonical session management per Week 2 strategy.
Provides session factories for both FastAPI (async) and Alembic (sync).
"""
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings
from src.core.exceptions import DatabaseError
from src.core.logging import database_logger as logger

settings = get_settings()


# ============================================================================
# ASYNC SESSION (for FastAPI and async operations)
# ============================================================================

# Create async engine
async_engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.is_development,
    pool_pre_ping=True,
    pool_size=20,           # Increased from 10 for production load
    max_overflow=40,        # Increased from 20 (total 60 connections)
    pool_recycle=3600,      # Recycle connections after 1 hour
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_db_async() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.

    Usage in async functions:
        async with get_db_async() as db:
            result = await db.execute(select(Entity))
            entities = result.scalars().all()

    Yields:
        AsyncSession: SQLAlchemy async database session

    Raises:
        DatabaseError: If database operation fails
    """
    async with AsyncSessionLocal() as session:
        try:
            logger.debug("Async database session created")
            yield session
            await session.commit()
            logger.debug("Async database session committed")
        except Exception as e:
            await session.rollback()
            logger.error(f"Async database session error: {str(e)}")
            raise DatabaseError(f"Async database operation failed: {str(e)}")
        finally:
            await session.close()
            logger.debug("Async database session closed")


async def get_db_dependency() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for async database sessions.

    Usage in FastAPI endpoints:
        @app.get("/entities")
        async def get_entities(db: AsyncSession = Depends(get_db_dependency)):
            result = await db.execute(select(Entity))
            return result.scalars().all()

    Yields:
        AsyncSession: SQLAlchemy async database session

    Raises:
        DatabaseError: If database operation fails
    """
    async with get_db_async() as session:
        yield session


# ============================================================================
# SYNC SESSION (for Alembic migrations and tests)
# ============================================================================

def get_sync_engine(database_url: str = None):
    """
    Get synchronous SQLAlchemy engine for Alembic migrations.

    Args:
        database_url: Optional database URL override

    Returns:
        Engine: SQLAlchemy synchronous engine
    """
    url = database_url or settings.database_url
    return create_engine(
        url,
        echo=settings.is_development,
        pool_pre_ping=True,
        pool_size=20,           # Match async engine config
        max_overflow=40,        # Match async engine config (total 60 connections)
        pool_recycle=3600,      # Recycle connections after 1 hour
    )


# Sync session factory
SyncSessionLocal = sessionmaker(
    bind=get_sync_engine(),
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@contextmanager
def get_db_sync() -> Generator[Session, None, None]:
    """
    Sync context manager for database sessions (for Alembic and tests).

    Usage in migrations or sync code:
        with get_db_sync() as db:
            entity = Entity(name="Test Corp")
            db.add(entity)
            # Automatic commit on exit

    Yields:
        Session: SQLAlchemy synchronous database session

    Raises:
        DatabaseError: If database operation fails
    """
    session = SyncSessionLocal()
    try:
        logger.debug("Sync database session created")
        yield session
        session.commit()
        logger.debug("Sync database session committed")
    except Exception as e:
        session.rollback()
        logger.error(f"Sync database session error: {str(e)}")
        raise DatabaseError(f"Sync database operation failed: {str(e)}")
    finally:
        session.close()
        logger.debug("Sync database session closed")


def get_db_context():
    """
    Alias for get_db_sync() for backward compatibility.

    This is used by the lineage tracker and other legacy code.
    """
    return get_db_sync()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for sync database sessions.

    Unlike get_db_sync(), this does NOT wrap non-database exceptions
    in DatabaseError. This is important because FastAPI/Starlette throws
    HTTPExceptions back into dependency generators during cleanup.
    """
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
