"""
SQLAlchemy base configuration and engine utilities.

Provides Base class and utility functions for database operations.
"""

from sqlalchemy.orm import DeclarativeBase

from src.core.logging import database_logger as logger
from src.db.session import get_sync_engine


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


def get_engine():
    """
    Get synchronous SQLAlchemy engine.

    This is an alias for get_sync_engine() for backward compatibility.

    Returns:
        Engine: SQLAlchemy synchronous engine
    """
    return get_sync_engine()


def create_tables():
    """
    Create all tables defined in models.

    This is idempotent - safe to call multiple times.
    Tables that already exist will not be recreated.
    """
    engine = get_sync_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")


def drop_tables():
    """
    Drop all tables (USE WITH CAUTION - for testing only).

    This will delete all data in the database.
    Only use in development or testing environments.
    """
    engine = get_sync_engine()
    Base.metadata.drop_all(bind=engine)
    logger.warning("All database tables dropped")


__all__ = ["Base", "get_engine", "create_tables", "drop_tables"]
