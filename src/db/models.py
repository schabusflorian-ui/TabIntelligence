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
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base  # noqa: F401 — re-exported for backward compat
from src.taxonomy_constants import VALID_CATEGORIES

# ============================================================================
# ENUMS
# ============================================================================


class JobStatusEnum(str, PyEnum):
    """Job status enumeration."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


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

    __table_args__ = (
        CheckConstraint(
            "fiscal_year_end IS NULL OR (fiscal_year_end >= 1 AND fiscal_year_end <= 12)",
            name="ck_entity_fiscal_year_end",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), index=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    fiscal_year_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    default_currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    reporting_standard: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    entity_patterns: Mapped[List["EntityPattern"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    api_keys: Mapped[List["APIKey"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
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
            name="ck_taxonomy_typical_sign",
        ),
        CheckConstraint(
            "category IN (" + ", ".join(f"'{c}'" for c in VALID_CATEGORIES) + ")",
            name="ck_taxonomy_category",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    aliases: Mapped[Optional[list]] = mapped_column(JSON)  # List of alias strings
    definition: Mapped[Optional[str]] = mapped_column(Text)
    typical_sign: Mapped[Optional[str]] = mapped_column(String(10))
    parent_canonical: Mapped[Optional[str]] = mapped_column(String(100))
    validation_rules: Mapped[Optional[dict]] = mapped_column(JSON)
    deprecated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    deprecated_redirect: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

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
            "confidence >= 0.0 AND confidence <= 1.0", name="ck_entity_patterns_confidence"
        ),
        CheckConstraint(
            "created_by IN ('claude', 'user_correction')", name="ck_entity_patterns_created_by"
        ),
        Index("ix_entity_patterns_entity_id_original_label", "entity_id", "original_label"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    original_label: Mapped[str] = mapped_column(String(500), index=True)
    canonical_name: Mapped[str] = mapped_column(String(100), index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(precision=5, scale=4))
    occurrence_count: Mapped[int] = mapped_column(Integer, server_default="1")
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    entity: Mapped[Optional["Entity"]] = relationship(back_populates="entity_patterns")

    def __repr__(self):
        return (
            f"<EntityPattern(original='{self.original_label}',"
            f" canonical='{self.canonical_name}',"
            f" confidence={self.confidence})>"
        )


class LearnedAlias(Base):
    """
    Learned aliases discovered from high-confidence Claude mappings.

    When Claude maps a label to a canonical name with high confidence and
    the label is not already in the taxonomy, it's recorded here. After
    sufficient occurrences across different entities, aliases can be
    promoted to the canonical taxonomy.
    """

    __tablename__ = "learned_aliases"

    __table_args__ = (
        UniqueConstraint("canonical_name", "alias_text", name="uq_learned_aliases_canonical_alias"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_name: Mapped[str] = mapped_column(String(100), index=True)
    alias_text: Mapped[str] = mapped_column(String(500), index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, server_default="1")
    source_entities: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    promoted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    archived_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return (
            f"<LearnedAlias(canonical='{self.canonical_name}', "
            f"alias='{self.alias_text}', count={self.occurrence_count})>"
        )


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

    file_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
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
        PG_UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    extraction_jobs: Mapped[List["ExtractionJob"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
    entity: Mapped[Optional["Entity"]] = relationship(foreign_keys=[entity_id])

    def __repr__(self):
        return f"<File(file_id={self.file_id}, filename='{self.filename}')>"


class ExtractionJob(Base):
    """
    Extraction job tracking and results.

    Replaces the in-memory jobs dictionary with persistent storage.
    Tracks job status, progress, results, and costs.
    """

    __tablename__ = "extraction_jobs"

    __table_args__ = (
        Index("ix_extraction_jobs_status_created_at", "status", "created_at"),
        Index("ix_extraction_jobs_updated_at", "updated_at"),
    )

    job_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    file_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("files.file_id", ondelete="CASCADE")
    )

    # Job status tracking
    status: Mapped[JobStatusEnum] = mapped_column(
        Enum(JobStatusEnum), default=JobStatusEnum.PENDING, index=True
    )
    current_stage: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # "parsing", "triage", "mapping"
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)

    # Extraction results
    result: Mapped[Optional[dict]] = mapped_column(JSON)  # Full ExtractionResult as JSON
    error: Mapped[Optional[str]] = mapped_column(String(2000))  # Error message if failed

    # Cost tracking
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float)

    # Quality
    quality_grade: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)

    # Taxonomy tracking
    taxonomy_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    taxonomy_checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    file: Mapped["File"] = relationship(back_populates="extraction_jobs")
    lineage_events: Mapped[List["LineageEvent"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    correction_history: Mapped[List["CorrectionHistory"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
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

    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("extraction_jobs.job_id", ondelete="CASCADE"), index=True
    )

    stage_name: Mapped[str] = mapped_column(String(50))  # "parsing", "triage", "mapping"
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
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

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    action: Mapped[str] = mapped_column(
        String(50), index=True
    )  # "upload", "extract", "view", "revoke_key"
    resource_type: Mapped[str] = mapped_column(
        String(50), index=True
    )  # "file", "job", "api_key", "entity"
    resource_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )
    api_key_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
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


# ============================================================================
# DLQ (Dead Letter Queue)
# ============================================================================


class DLQEntry(Base):
    """
    Dead Letter Queue entry for failed Celery tasks.

    Records task failures for inspection and replay.
    Prevents data loss when tasks fail after all retries.
    """

    __tablename__ = "dlq_entries"

    dlq_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[str] = mapped_column(String(255), index=True)  # Celery task ID
    task_name: Mapped[str] = mapped_column(String(255))
    task_args: Mapped[Optional[dict]] = mapped_column(JSON)
    task_kwargs: Mapped[Optional[dict]] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(Text)
    traceback: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    replayed: Mapped[int] = mapped_column(Integer, default=0)
    replayed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    replayed_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self):
        return (
            f"<DLQEntry(dlq_id={self.dlq_id}, task_id='{self.task_id}', replayed={self.replayed})>"
        )


# ============================================================================
# EXTRACTION FACT TABLE
# ============================================================================


class ExtractionFact(Base):
    """
    Decomposed extraction result: one row per (job, canonical_name, period).

    Enables efficient querying of individual extracted values across jobs,
    entities, periods, and canonical names. Populated from line_items after
    extraction completes.
    """

    __tablename__ = "extraction_facts"

    __table_args__ = (
        Index("ix_fact_entity_canonical_period", "entity_id", "canonical_name", "period"),
        Index("ix_fact_job_canonical", "job_id", "canonical_name"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("extraction_jobs.job_id", ondelete="CASCADE"), index=True
    )
    entity_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    canonical_name: Mapped[str] = mapped_column(String(100), index=True)
    original_label: Mapped[Optional[str]] = mapped_column(String(500))
    period: Mapped[str] = mapped_column(String(50), index=True)
    period_normalized: Mapped[Optional[str]] = mapped_column(String(50))
    value: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=4))
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sheet_name: Mapped[Optional[str]] = mapped_column(String(255))
    row_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hierarchy_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mapping_method: Mapped[Optional[str]] = mapped_column(String(50))
    taxonomy_category: Mapped[Optional[str]] = mapped_column(String(50))
    validation_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    currency_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    source_unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    source_scale: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return (
            f"<ExtractionFact(job_id={self.job_id}, canonical='{self.canonical_name}', "
            f"period='{self.period}', value={self.value})>"
        )


# ============================================================================
# CORRECTION HISTORY
# ============================================================================


class CorrectionHistory(Base):
    """
    Tracks corrections applied to extraction job results.

    Each row records one line_item correction (old canonical -> new canonical)
    applied to a specific job. Stores a snapshot of the old line_item for undo.
    """

    __tablename__ = "correction_history"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("extraction_jobs.job_id", ondelete="CASCADE"), index=True
    )
    entity_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    original_label: Mapped[str] = mapped_column(String(500))
    sheet: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    old_canonical_name: Mapped[str] = mapped_column(String(100))
    new_canonical_name: Mapped[str] = mapped_column(String(100))
    old_confidence: Mapped[float] = mapped_column(Float)
    new_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    old_line_item_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    reverted: Mapped[bool] = mapped_column(Boolean, default=False)
    reverted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    job: Mapped["ExtractionJob"] = relationship(back_populates="correction_history")

    def __repr__(self):
        return (
            f"<CorrectionHistory(id={self.id}, job_id={self.job_id}, "
            f"'{self.old_canonical_name}' -> '{self.new_canonical_name}')>"
        )


class TaxonomyVersion(Base):
    """
    Tracks taxonomy.json versions applied to the database.

    Records version, item count, and content checksum for audit trail
    and backward compatibility.
    """

    __tablename__ = "taxonomy_versions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    version: Mapped[str] = mapped_column(String(20))
    item_count: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))  # SHA-256
    categories: Mapped[dict] = mapped_column(JSON)  # {"income_statement": 54, ...}
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    applied_by: Mapped[Optional[str]] = mapped_column(String(100))

    def __repr__(self):
        return f"<TaxonomyVersion(version='{self.version}', items={self.item_count})>"


class UnmappedLabelAggregate(Base):
    """
    Tracks unmapped labels across entities for taxonomy gap analysis.

    Each row represents a unique (label_normalized, entity_id) pair.
    Populated during fact persistence when canonical_name == 'unmapped'.
    """

    __tablename__ = "unmapped_label_aggregates"

    __table_args__ = (
        UniqueConstraint("label_normalized", "entity_id", name="uq_unmapped_label_entity"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    label_normalized: Mapped[str] = mapped_column(String(500), index=True)
    original_labels: Mapped[list] = mapped_column(JSON, default=list)
    entity_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    occurrence_count: Mapped[int] = mapped_column(Integer, server_default="1")
    last_seen_job_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    sheet_names: Mapped[list] = mapped_column(JSON, default=list)
    taxonomy_category_hint: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return (
            f"<UnmappedLabelAggregate(label='{self.label_normalized}', "
            f"count={self.occurrence_count})>"
        )


# ============================================================================
# FX RATE CACHE
# ============================================================================


class FxRateCache(Base):
    """Cached FX exchange rates for currency normalization."""

    __tablename__ = "fx_rate_cache"

    __table_args__ = (
        UniqueConstraint("from_currency", "to_currency", "rate_date", name="uq_fx_rate"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    from_currency: Mapped[str] = mapped_column(String(3), index=True)
    to_currency: Mapped[str] = mapped_column(String(3), index=True)
    rate_date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    rate: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8))
    source: Mapped[str] = mapped_column(String(50), server_default="alpha_vantage")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<FxRateCache({self.from_currency}/{self.to_currency} {self.rate_date}: {self.rate})>"


# ============================================================================
# QUALITY SNAPSHOT
# ============================================================================


class QualitySnapshot(Base):
    """Point-in-time quality grade snapshot per entity."""

    __tablename__ = "quality_snapshots"

    __table_args__ = (
        Index("ix_quality_snapshot_entity_date", "entity_id", "snapshot_date"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    snapshot_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    avg_confidence: Mapped[float] = mapped_column(Float)
    quality_grade: Mapped[str] = mapped_column(String(2))
    total_facts: Mapped[int] = mapped_column(Integer)
    total_jobs: Mapped[int] = mapped_column(Integer)
    unmapped_label_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<QualitySnapshot(entity={self.entity_id}, date={self.snapshot_date}, grade={self.quality_grade})>"


# ============================================================================
# TAXONOMY SUGGESTIONS
# ============================================================================


class TaxonomySuggestion(Base):
    """
    Taxonomy improvement suggestions generated from frequently unmapped labels.

    Surfaces commonly unmapped labels as candidates for taxonomy updates:
    - new_alias: label is close to an existing canonical name, suggest adding as alias
    - new_item: label has no close match, suggest adding as new taxonomy item
    - fix_conflict: label maps to multiple canonical names ambiguously
    """

    __tablename__ = "taxonomy_suggestions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    suggestion_type: Mapped[str] = mapped_column(String(20))  # "new_alias", "new_item", "fix_conflict"
    canonical_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # null for "new_item"
    suggested_text: Mapped[str] = mapped_column(String(500))
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_jobs: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # list of job IDs
    status: Mapped[str] = mapped_column(String(20), default="pending")  # "pending", "accepted", "rejected"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    def __repr__(self):
        return (
            f"<TaxonomySuggestion(type='{self.suggestion_type}', "
            f"text='{self.suggested_text}', status='{self.status}')>"
        )


# ============================================================================
# TAXONOMY CHANGELOG
# ============================================================================


class TaxonomyChangelog(Base):
    """
    Changelog entry for taxonomy field changes.

    Records every modification to a taxonomy item for audit trail
    and governance. Tracks who changed what, when, and the old/new values.
    """

    __tablename__ = "taxonomy_changelog"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_name: Mapped[str] = mapped_column(String(200))
    field_name: Mapped[str] = mapped_column(String(100))
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str] = mapped_column(String(100))
    taxonomy_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    def __repr__(self):
        return (
            f"<TaxonomyChangelog(canonical='{self.canonical_name}', "
            f"field='{self.field_name}', by='{self.changed_by}')>"
        )


# NOTE: APIKey (src.auth.models) is registered with Base.metadata when
# src.auth is imported by the app. Do NOT import it here — circular import.


