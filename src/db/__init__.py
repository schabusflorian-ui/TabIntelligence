"""Database models and session management (Week 2 canonical location)."""

from src.db.base import Base, get_engine, create_tables, drop_tables
from src.db.models import (
    Entity,
    Taxonomy,
    EntityPattern,
    LearnedAlias,
    File,
    ExtractionJob,
    LineageEvent,
    AuditLog,
    DLQEntry,
    ExtractionFact,
    JobStatusEnum,
)
from src.db.session import (
    get_db_async,
    get_db_dependency,
    get_db_sync,
    get_db_context,
    get_db,
    async_engine,
    get_sync_engine,
)
from src.db import crud

__all__ = [
    # Base and utilities
    "Base",
    "get_engine",
    "create_tables",
    "drop_tables",
    # Models
    "Entity",
    "Taxonomy",
    "EntityPattern",
    "LearnedAlias",
    "File",
    "ExtractionJob",
    "LineageEvent",
    "AuditLog",
    "DLQEntry",
    "ExtractionFact",
    "JobStatusEnum",
    # Session management
    "get_db_async",
    "get_db_dependency",
    "get_db_sync",
    "get_db_context",
    "get_db",
    "async_engine",
    "get_sync_engine",
    # CRUD operations
    "crud",
]
