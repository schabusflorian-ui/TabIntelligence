"""Database models and session management (Week 2 canonical location)."""

from src.db.base import Base, create_tables, drop_tables, get_engine
from src.db.models import (
    AuditLog,
    DLQEntry,
    Entity,
    EntityPattern,
    ExtractionFact,
    ExtractionJob,
    File,
    JobStatusEnum,
    LearnedAlias,
    LineageEvent,
    Taxonomy,
)
from src.db.session import (
    async_engine,
    get_db,
    get_db_async,
    get_db_context,
    get_db_dependency,
    get_db_sync,
    get_sync_engine,
)
from src.db import crud  # noqa: E402 — must be after models to avoid circular import
# NOTE: APIKey (src.auth.models) is registered with Base.metadata when src.auth is imported
# by the app. Do NOT import it here — it causes circular imports.

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
