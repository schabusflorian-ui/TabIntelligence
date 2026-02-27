"""
SQLAlchemy async database setup for DebtFund.
Provides base model class and async session management.
"""
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine
)
from sqlalchemy.orm import DeclarativeBase
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from src.core.config import get_settings
from src.core.logging import database_logger as logger

# Base class for all models
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass

# Global engine and session factory
_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_async_engine() -> AsyncEngine:
    """
    Get or create async database engine.
    Uses asyncpg driver for PostgreSQL.
    """
    global _engine

    if _engine is None:
        settings = get_settings()

        # Convert postgresql:// to postgresql+asyncpg://
        db_url = settings.database_url.replace(
            "postgresql://",
            "postgresql+asyncpg://"
        )

        _engine = create_async_engine(
            db_url,
            echo=settings.debug,  # Log SQL in debug mode
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before using
        )

        logger.info(f"Database engine created: {db_url.split('@')[1]}")

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create async session factory."""
    global _async_session_factory

    if _async_session_factory is None:
        engine = get_async_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("Async session factory created")

    return _async_session_factory


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.

    Usage:
        async with get_async_session() as session:
            result = await session.execute(query)
            await session.commit()
    """
    factory = get_session_factory()
    session = factory()

    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db():
    """Initialize database - create all tables."""
    engine = get_async_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized - all tables created")


async def dispose_db():
    """Dispose database engine - cleanup on shutdown."""
    global _engine, _async_session_factory

    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database engine disposed")
