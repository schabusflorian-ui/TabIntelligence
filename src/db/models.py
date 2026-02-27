"""
SQLAlchemy 2.0 ORM models for DebtFund database.

This is the canonical location for database models per Week 2 strategy.
Uses modern SQLAlchemy 2.0 declarative syntax with Mapped and mapped_column.

Models:
- Entity: Company/asset entities being tracked
- Taxonomy: Canonical financial line items
- EntityPattern: Learned entity-specific label mappings
- File: Uploaded Excel files
- ExtractionJob: Job tracking and results
- LineageEvent: Stage-by-stage lineage tracking
"""
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum as PyEnum
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# ============================================================================
# ENUMS
# ============================================================================


class JobStatusEnum(str, PyEnum):
    """Job status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================================
# ENTITY MODELS
# ============================================================================


class Entity(Base):
    """
    Company or asset entity being analyzed.

    Represents a tracked entity (company, fund, asset, etc.) in the system.
    Each entity can have multiple files and entity-specific learned patterns.
    """
    __tablename__ = "entities"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # Relationships
    entity_patterns: Mapped[List["EntityPattern"]] = relationship(
        back_populates="entity",
        cascade="all, delete-orphan"
    )
    api_keys: Mapped[List["APIKey"]] = relationship(
        back_populates="entity",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Entity(id={self.id}, name='{self.name}')>"


# ============================================================================
# TAXONOMY MODELS
# ============================================================================


class Taxonomy(Base):
    """
    Canonical financial line items taxonomy.

    Represents the master list of standardized financial line items.
    Used for mapping extracted labels to canonical names.
    """
    __tablename__ = "taxonomy"

    __table_args__ = (
        CheckConstraint(
            "typical_sign IN ('positive', 'negative', 'varies') OR typical_sign IS NULL",
            name='ck_taxonomy_typical_sign'
        ),
        CheckConstraint(
            "category IN ('income_statement', 'balance_sheet', 'cash_flow', "
            "'debt_schedule', 'depreciation_amortization', 'working_capital', "
            "'assumptions', 'metrics')",
            name='ck_taxonomy_category'
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    canonical_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True
    )
    category: Mapped[str] = mapped_column(String(50), index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    aliases: Mapped[Optional[list]] = mapped_column(JSON)  # List of alias strings
    definition: Mapped[Optional[str]] = mapped_column(Text)
    typical_sign: Mapped[Optional[str]] = mapped_column(String(10))
    parent_canonical: Mapped[Optional[str]] = mapped_column(String(100))
    validation_rules: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    def __repr__(self):
        return f"<Taxonomy(canonical_name='{self.canonical_name}', category='{self.category}')>"


class EntityPattern(Base):
    """
    Entity-specific learned label-to-canonical mappings.

    Stores patterns learned from user corrections and successful mappings.
    Used to improve accuracy for entity-specific naming conventions.
    """
    __tablename__ = "entity_patterns"

    __table_args__ = (
        CheckConstraint(
            'confidence >= 0.0 AND confidence <= 1.0',
            name='ck_entity_patterns_confidence'
        ),
        CheckConstraint(
            "created_by IN ('claude', 'user_correction')",
            name='ck_entity_patterns_created_by'
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    entity_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        index=True
    )
    original_label: Mapped[str] = mapped_column(String(500), index=True)
    canonical_name: Mapped[str] = mapped_column(String(100), index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(precision=5, scale=4))
    occurrence_count: Mapped[int] = mapped_column(Integer, server_default="1")
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # Relationships
    entity: Mapped[Optional["Entity"]] = relationship(back_populates="entity_patterns")

    def __repr__(self):
        return f"<EntityPattern(original='{self.original_label}', canonical='{self.canonical_name}', confidence={self.confidence})>"


# ============================================================================
# FILE & JOB MODELS
# ============================================================================


class File(Base):
    """
    Uploaded Excel file metadata.

    Tracks files uploaded by users for financial model extraction.
    Each file can have multiple extraction jobs.
    """
    __tablename__ = "files"

    file_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer)  # Size in bytes
    s3_key: Mapped[Optional[str]] = mapped_column(String(512))  # S3/MinIO object key
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64),  # SHA-256 hex digest
        index=True,
        unique=True,
        nullable=True,
    )
    entity_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        index=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    extraction_jobs: Mapped[List["ExtractionJob"]] = relationship(
        back_populates="file",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<File(file_id={self.file_id}, filename='{self.filename}')>"


class ExtractionJob(Base):
    """
    Extraction job tracking and results.

    Replaces the in-memory jobs dictionary with persistent storage.
    Tracks job status, progress, results, and costs.
    """
    __tablename__ = "extraction_jobs"

    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    file_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("files.file_id", ondelete="CASCADE")
    )

    # Job status tracking
    status: Mapped[JobStatusEnum] = mapped_column(
        Enum(JobStatusEnum),
        default=JobStatusEnum.PENDING,
        index=True
    )
    current_stage: Mapped[Optional[str]] = mapped_column(String(50))  # "parsing", "triage", "mapping"
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)

    # Extraction results
    result: Mapped[Optional[dict]] = mapped_column(JSON)  # Full ExtractionResult as JSON
    error: Mapped[Optional[str]] = mapped_column(String(2000))  # Error message if failed

    # Cost tracking
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    file: Mapped["File"] = relationship(back_populates="extraction_jobs")
    lineage_events: Mapped[List["LineageEvent"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<ExtractionJob(job_id={self.job_id}, status={self.status.value})>"


# ============================================================================
# LINEAGE MODELS
# ============================================================================


class LineageEvent(Base):
    """
    Lineage event tracking for extraction stages.

    Records each stage of the extraction pipeline with metadata.
    Enables full audit trail and debugging.
    """
    __tablename__ = "lineage_events"

    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("extraction_jobs.job_id", ondelete="CASCADE"),
        index=True
    )

    stage_name: Mapped[str] = mapped_column(String(50))  # "parsing", "triage", "mapping"
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    data: Mapped[Optional[dict]] = mapped_column(JSON)  # Stage-specific metadata

    # Relationships
    job: Mapped["ExtractionJob"] = relationship(back_populates="lineage_events")

    def __repr__(self):
        return f"<LineageEvent(event_id={self.event_id}, stage='{self.stage_name}')>"


# ============================================================================
# AUDIT MODELS
# ============================================================================


class AuditLog(Base):
    """
    Audit log for compliance tracking.

    Records all significant actions performed through the API.
    Provides complete audit trail for regulatory compliance.
    """
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )
    action: Mapped[str] = mapped_column(String(50), index=True)  # "upload", "extract", "view", "revoke_key"
    resource_type: Mapped[str] = mapped_column(String(50), index=True)  # "file", "job", "api_key", "entity"
    resource_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True
    )
    api_key_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))  # IPv6 max length
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    details: Mapped[Optional[dict]] = mapped_column(JSON)  # Additional context
    status_code: Mapped[Optional[int]] = mapped_column(Integer)  # HTTP response status

    def __repr__(self):
        return (
            f"<AuditLog(id={self.id}, action='{self.action}', "
            f"resource_type='{self.resource_type}', resource_id={self.resource_id})>"
        )


# Late import to register APIKey with Base metadata (avoids circular imports)
from src.auth.models import APIKey  # noqa: E402, F401
