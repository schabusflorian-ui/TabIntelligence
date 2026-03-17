"""
CRUD (Create, Read, Update, Delete) operations for DebtFund database.

All operations use explicit transaction management and proper error handling.
This is the canonical location per Week 2 strategy.
"""

import copy
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func as sa_func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from src.core.exceptions import DatabaseError
from src.core.logging import database_logger as logger
from src.db.models import (
    CorrectionHistory,
    DLQEntry,
    Entity,
    EntityPattern,
    ExtractionFact,
    ExtractionJob,
    File,
    JobStatusEnum,
    LearnedAlias,
    LineageEvent,
    UnmappedLabelAggregate,
)

# ============================================================================
# ENTITY OPERATIONS
# ============================================================================


def create_entity(
    db: Session,
    name: str,
    industry: Optional[str] = None,
    fiscal_year_end: Optional[int] = None,
    default_currency: Optional[str] = None,
    reporting_standard: Optional[str] = None,
) -> Entity:
    """
    Create a new entity.

    Args:
        db: Database session
        name: Entity name
        industry: Optional industry classification
        fiscal_year_end: Optional fiscal year end month (1-12)
        default_currency: Optional ISO 4217 currency code
        reporting_standard: Optional reporting standard (GAAP, IFRS, etc.)

    Returns:
        Entity: Created entity record
    """
    try:
        entity = Entity(
            name=name,
            industry=industry,
            fiscal_year_end=fiscal_year_end,
            default_currency=default_currency,
            reporting_standard=reporting_standard,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        logger.info(f"Entity created: id={entity.id}, name={name}")
        return entity
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to create entity: {str(e)}")
        raise DatabaseError(
            f"Failed to create entity: {str(e)}", operation="create", table="entities"
        )


def get_entity(db: Session, entity_id: UUID) -> Optional[Entity]:
    """Get entity by ID."""
    try:
        return db.query(Entity).filter(Entity.id == entity_id).first()
    except SQLAlchemyError as e:
        logger.error(f"Failed to get entity {entity_id}: {str(e)}")
        raise DatabaseError(f"Failed to get entity: {str(e)}", operation="read", table="entities")


def list_entities(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> List[Entity]:
    """List entities with pagination."""
    try:
        return db.query(Entity).order_by(Entity.created_at.desc()).offset(offset).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error(f"Failed to list entities: {str(e)}")
        raise DatabaseError(
            f"Failed to list entities: {str(e)}", operation="read", table="entities"
        )


def update_entity(
    db: Session,
    entity_id: UUID,
    name: Optional[str] = None,
    industry: Optional[str] = None,
    fiscal_year_end: Optional[int] = None,
    default_currency: Optional[str] = None,
    reporting_standard: Optional[str] = None,
) -> Entity:
    """Update an entity's fields."""
    try:
        entity = db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            raise DatabaseError(
                f"Entity {entity_id} not found", operation="update", table="entities"
            )
        if name is not None:
            entity.name = name
        if industry is not None:
            entity.industry = industry
        if fiscal_year_end is not None:
            entity.fiscal_year_end = fiscal_year_end
        if default_currency is not None:
            entity.default_currency = default_currency
        if reporting_standard is not None:
            entity.reporting_standard = reporting_standard
        db.commit()
        db.refresh(entity)
        logger.info(f"Entity {entity_id} updated")
        return entity
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to update entity {entity_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to update entity: {str(e)}", operation="update", table="entities"
        )


def delete_entity(db: Session, entity_id: UUID) -> bool:
    """Delete an entity. Returns True if deleted, False if not found."""
    try:
        entity = db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            return False
        db.delete(entity)
        db.commit()
        logger.info(f"Entity {entity_id} deleted")
        return True
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to delete entity {entity_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to delete entity: {str(e)}", operation="delete", table="entities"
        )


# ============================================================================
# FILE OPERATIONS
# ============================================================================


def get_file_by_hash(db: Session, content_hash: str) -> Optional[File]:
    """
    Look up file by content hash for deduplication.

    Args:
        db: Database session
        content_hash: SHA-256 hex digest

    Returns:
        File or None if no match
    """
    try:
        return db.query(File).filter(File.content_hash == content_hash).first()
    except SQLAlchemyError as e:
        logger.error(f"Failed to look up file by hash: {str(e)}")
        raise DatabaseError(f"Failed to look up file: {str(e)}", operation="read", table="files")


def create_file(
    db: Session,
    filename: str,
    file_size: int,
    s3_key: Optional[str] = None,
    entity_id: Optional[UUID] = None,
    content_hash: Optional[str] = None,
) -> File:
    """
    Create a new file record.

    Args:
        db: Database session
        filename: Original filename
        file_size: File size in bytes
        s3_key: S3/MinIO object key (optional)
        entity_id: Entity linking ID (optional)
        content_hash: SHA-256 hex digest of file content (optional)

    Returns:
        File: Created file record

    Raises:
        DatabaseError: If creation fails
    """
    try:
        file = File(
            filename=filename,
            file_size=file_size,
            s3_key=s3_key,
            entity_id=entity_id,
            content_hash=content_hash,
        )
        db.add(file)
        db.commit()
        db.refresh(file)
        logger.info(f"File created: file_id={file.file_id}, filename={filename}")
        return file
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to create file: {str(e)}")
        raise DatabaseError(f"Failed to create file: {str(e)}", operation="create", table="files")


def get_file(db: Session, file_id: UUID) -> Optional[File]:
    """
    Get file by ID.

    Args:
        db: Database session
        file_id: File UUID

    Returns:
        File or None if not found

    Raises:
        DatabaseError: If query fails
    """
    try:
        return db.query(File).filter(File.file_id == file_id).first()
    except SQLAlchemyError as e:
        logger.error(f"Failed to get file {file_id}: {str(e)}")
        raise DatabaseError(f"Failed to get file: {str(e)}", operation="read", table="files")


def list_files(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> List[File]:
    """
    List files ordered by upload date (newest first).

    Args:
        db: Database session
        limit: Maximum number of files to return
        offset: Number of files to skip

    Returns:
        List[File]: List of file records
    """
    try:
        return db.query(File).order_by(File.uploaded_at.desc()).offset(offset).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error(f"Failed to list files: {str(e)}")
        raise DatabaseError(f"Failed to list files: {str(e)}", operation="read", table="files")


def update_file_s3_key(db: Session, file_id: UUID, s3_key: str) -> File:
    """
    Update file record with S3 key after upload.

    Args:
        db: Database session
        file_id: File UUID
        s3_key: S3 object key

    Returns:
        File: Updated file record

    Raises:
        DatabaseError: If update fails or file not found
    """
    try:
        file = db.query(File).filter(File.file_id == file_id).first()
        if not file:
            raise DatabaseError(f"File {file_id} not found", operation="update", table="files")

        file.s3_key = s3_key
        db.commit()
        db.refresh(file)

        logger.info(f"File {file_id} updated with s3_key: {s3_key}")
        return file
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to update file {file_id} with s3_key: {str(e)}")
        raise DatabaseError(f"Failed to update file: {str(e)}", operation="update", table="files")


# ============================================================================
# EXTRACTION JOB OPERATIONS
# ============================================================================


def create_extraction_job(
    db: Session,
    file_id: UUID,
    job_id: Optional[UUID] = None,
) -> ExtractionJob:
    """
    Create a new extraction job.

    Args:
        db: Database session
        file_id: File UUID to process
        job_id: Optional explicit job ID (for backwards compatibility)

    Returns:
        ExtractionJob: Created job record

    Raises:
        DatabaseError: If creation fails
    """
    try:
        job = ExtractionJob(
            job_id=job_id,  # Allow explicit job_id if provided
            file_id=file_id,
            status=JobStatusEnum.PENDING,
            progress_percent=0,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        logger.info(f"Extraction job created: job_id={job.job_id}, file_id={file_id}")
        return job
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to create extraction job: {str(e)}")
        raise DatabaseError(
            f"Failed to create job: {str(e)}", operation="create", table="extraction_jobs"
        )


def get_job(db: Session, job_id: UUID) -> Optional[ExtractionJob]:
    """
    Get extraction job by ID with file relationship.

    Uses eager loading to prevent N+1 query issues.

    Args:
        db: Database session
        job_id: Job UUID

    Returns:
        ExtractionJob or None if not found

    Raises:
        DatabaseError: If query fails
    """
    try:
        return (
            db.query(ExtractionJob)
            .options(joinedload(ExtractionJob.file).joinedload(File.entity))
            .filter(ExtractionJob.job_id == job_id)
            .first()
        )
    except SQLAlchemyError as e:
        logger.error(f"Failed to get job {job_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to get job: {str(e)}", operation="read", table="extraction_jobs"
        )


def update_job_status(
    db: Session,
    job_id: UUID,
    status: JobStatusEnum,
    current_stage: Optional[str] = None,
    progress_percent: Optional[int] = None,
    error: Optional[str] = None,
) -> ExtractionJob:
    """
    Update job status and progress.

    Args:
        db: Database session
        job_id: Job UUID
        status: New job status
        current_stage: Current extraction stage (optional)
        progress_percent: Progress percentage (optional)
        error: Error message (optional)

    Returns:
        ExtractionJob: Updated job record

    Raises:
        DatabaseError: If update fails or job not found
    """
    try:
        job = db.query(ExtractionJob).filter(ExtractionJob.job_id == job_id).first()
        if not job:
            raise DatabaseError(
                f"Job {job_id} not found", operation="update", table="extraction_jobs"
            )

        job.status = status
        if current_stage is not None:
            job.current_stage = current_stage
        if progress_percent is not None:
            job.progress_percent = progress_percent
        if error is not None:
            job.error = error

        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)

        logger.debug(f"Job {job_id} status updated: {status.value}")
        return job
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to update job {job_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to update job: {str(e)}", operation="update", table="extraction_jobs"
        )


def complete_job(
    db: Session,
    job_id: UUID,
    result: dict,
    tokens_used: int,
    cost_usd: float,
    quality_grade: Optional[str] = None,
) -> ExtractionJob:
    """
    Mark job as completed (or NEEDS_REVIEW if quality gate fails).

    Args:
        db: Database session
        job_id: Job UUID
        result: Extraction result dictionary
        tokens_used: Number of tokens consumed
        cost_usd: Cost in USD
        quality_grade: Letter grade from quality scorer (A/B/C/D/F)

    Returns:
        ExtractionJob: Updated job record

    Raises:
        DatabaseError: If update fails or job not found
    """
    try:
        job = db.query(ExtractionJob).filter(ExtractionJob.job_id == job_id).first()
        if not job:
            raise DatabaseError(
                f"Job {job_id} not found", operation="update", table="extraction_jobs"
            )

        # Quality gate: F grade -> NEEDS_REVIEW instead of COMPLETED
        quality_gate = (result.get("quality") or {}).get("quality_gate", {})
        if not quality_gate.get("passed", True):
            job.status = JobStatusEnum.NEEDS_REVIEW
        else:
            job.status = JobStatusEnum.COMPLETED

        job.progress_percent = 100
        job.result = result
        job.tokens_used = tokens_used
        job.cost_usd = cost_usd
        job.quality_grade = quality_grade
        job.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(job)

        logger.info(
            f"Job {job_id} {job.status.value}: "
            f"tokens={tokens_used}, cost=${cost_usd:.4f}, grade={quality_grade}"
        )
        return job
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to complete job {job_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to complete job: {str(e)}", operation="update", table="extraction_jobs"
        )


def review_job(
    db: Session,
    job_id: UUID,
    decision: str,
    reason: Optional[str] = None,
) -> ExtractionJob:
    """
    Review a NEEDS_REVIEW job: approve transitions to COMPLETED, reject to FAILED.

    Raises:
        DatabaseError: If job not found or not in NEEDS_REVIEW status.
    """
    try:
        job = db.query(ExtractionJob).filter(ExtractionJob.job_id == job_id).first()
        if not job:
            raise DatabaseError(
                f"Job {job_id} not found",
                operation="update",
                table="extraction_jobs",
            )

        if job.status != JobStatusEnum.NEEDS_REVIEW:
            raise DatabaseError(
                f"Job {job_id} is not in NEEDS_REVIEW status (current: {job.status.value})",
                operation="update",
                table="extraction_jobs",
            )

        if decision == "approve":
            job.status = JobStatusEnum.COMPLETED
        else:
            job.status = JobStatusEnum.FAILED
            job.error = f"Rejected: {reason}" if reason else "Rejected by reviewer"

        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)

        logger.info(f"Job {job_id} reviewed: decision={decision}, new_status={job.status.value}")
        return job
    except DatabaseError:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise DatabaseError(
            f"Failed to review job: {str(e)}",
            operation="update",
            table="extraction_jobs",
        )


def fail_job(
    db: Session,
    job_id: UUID,
    error: str,
) -> ExtractionJob:
    """
    Mark job as failed with error message.

    Args:
        db: Database session
        job_id: Job UUID
        error: Error message

    Returns:
        ExtractionJob: Updated job record

    Raises:
        DatabaseError: If update fails or job not found
    """
    try:
        job = db.query(ExtractionJob).filter(ExtractionJob.job_id == job_id).first()
        if not job:
            raise DatabaseError(
                f"Job {job_id} not found", operation="update", table="extraction_jobs"
            )

        job.status = JobStatusEnum.FAILED
        job.error = error[:2000]  # Truncate to column limit
        job.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(job)

        logger.warning(f"Job {job_id} failed: {error[:100]}...")
        return job
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to mark job {job_id} as failed: {str(e)}")
        raise DatabaseError(
            f"Failed to update job: {str(e)}", operation="update", table="extraction_jobs"
        )


def update_job_partial_result(
    db: Session,
    job_id: UUID,
    stage_name: str,
    stage_result: dict,
) -> ExtractionJob:
    """Save partial stage results to job.result for checkpoint/resume.

    Stores results under ``_stage_results`` keyed by stage name.
    """
    try:
        job = db.query(ExtractionJob).filter(ExtractionJob.job_id == job_id).first()
        if not job:
            raise DatabaseError(
                f"Job {job_id} not found",
                operation="update",
                table="extraction_jobs",
            )

        current = copy.deepcopy(job.result) if job.result else {}
        stage_results = current.get("_stage_results", {})
        stage_results[stage_name] = stage_result
        current["_stage_results"] = stage_results
        current["_last_completed_stage"] = stage_name

        job.result = current
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)

        logger.debug(f"Job {job_id} partial result saved: stage={stage_name}")
        return job
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to save partial result for job {job_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to save partial result: {str(e)}",
            operation="update",
            table="extraction_jobs",
        )


def list_jobs(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    status: Optional[JobStatusEnum] = None,
) -> List[ExtractionJob]:
    """
    List extraction jobs with optional filtering.

    Args:
        db: Database session
        limit: Maximum number of jobs to return (default 50)
        offset: Number of jobs to skip (default 0)
        status: Filter by job status (optional)

    Returns:
        List[ExtractionJob]: List of jobs

    Raises:
        DatabaseError: If query fails
    """
    try:
        query = db.query(ExtractionJob).options(
            joinedload(ExtractionJob.file).joinedload(File.entity)
        )

        if status:
            query = query.filter(ExtractionJob.status == status)

        query = query.order_by(ExtractionJob.created_at.desc()).offset(offset).limit(limit)

        return query.all()
    except SQLAlchemyError as e:
        logger.error(f"Failed to list jobs: {str(e)}")
        raise DatabaseError(
            f"Failed to list jobs: {str(e)}", operation="read", table="extraction_jobs"
        )


def get_entity_jobs(
    db: Session,
    entity_id: UUID,
    limit: int = 50,
    offset: int = 0,
    status: Optional[JobStatusEnum] = None,
) -> List[ExtractionJob]:
    """Get extraction jobs for a specific entity via File.entity_id join."""
    try:
        query = (
            db.query(ExtractionJob)
            .join(File, ExtractionJob.file_id == File.file_id)
            .filter(File.entity_id == entity_id)
            .options(joinedload(ExtractionJob.file).joinedload(File.entity))
        )
        if status:
            query = query.filter(ExtractionJob.status == status)

        return (
            query.order_by(ExtractionJob.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"Failed to get entity jobs: {str(e)}")
        raise DatabaseError(
            f"Failed to get entity jobs: {str(e)}",
            operation="read",
            table="extraction_jobs",
        )


# ============================================================================
# LINEAGE EVENT OPERATIONS
# ============================================================================


def create_lineage_event(
    db: Session,
    job_id: UUID,
    stage_name: str,
    data: Optional[dict] = None,
) -> LineageEvent:
    """
    Create a lineage event for a job stage.

    Args:
        db: Database session
        job_id: Job UUID
        stage_name: Stage name (e.g., "parsing", "triage", "mapping")
        data: Stage-specific metadata (optional)

    Returns:
        LineageEvent: Created event record

    Raises:
        DatabaseError: If creation fails
    """
    try:
        event = LineageEvent(
            job_id=job_id,
            stage_name=stage_name,
            data=data,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        logger.debug(f"Lineage event created: job_id={job_id}, stage={stage_name}")
        return event
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to create lineage event: {str(e)}")
        raise DatabaseError(
            f"Failed to create lineage event: {str(e)}", operation="create", table="lineage_events"
        )


def get_job_lineage(db: Session, job_id: UUID) -> List[LineageEvent]:
    """
    Get all lineage events for a job, ordered by timestamp.

    Args:
        db: Database session
        job_id: Job UUID

    Returns:
        List[LineageEvent]: List of lineage events

    Raises:
        DatabaseError: If query fails
    """
    try:
        return (
            db.query(LineageEvent)
            .filter(LineageEvent.job_id == job_id)
            .order_by(LineageEvent.timestamp.asc())
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"Failed to get lineage for job {job_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to get lineage: {str(e)}", operation="read", table="lineage_events"
        )


# ============================================================================
# ENTITY PATTERN OPERATIONS
# ============================================================================


def get_entity_patterns(
    db: Session,
    entity_id: UUID,
    min_confidence: float = 0.0,
    limit: int = 100,
    active_only: bool = True,
) -> List[EntityPattern]:
    """
    Get learned patterns for an entity, ordered by confidence descending.

    Args:
        db: Database session
        entity_id: Entity UUID
        min_confidence: Minimum confidence threshold (default 0.0)
        limit: Maximum patterns to return
        active_only: If True, only return active patterns (default True)

    Returns:
        List of EntityPattern records
    """
    try:
        query = (
            db.query(EntityPattern)
            .filter(EntityPattern.entity_id == entity_id)
            .filter(EntityPattern.confidence >= min_confidence)
        )
        if active_only:
            query = query.filter(EntityPattern.is_active == True)
        query = query.order_by(EntityPattern.confidence.desc()).limit(limit)
        return query.all()
    except SQLAlchemyError as e:
        logger.error(f"Failed to get entity patterns for {entity_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to get entity patterns: {str(e)}", operation="read", table="entity_patterns"
        )


def upsert_entity_pattern(
    db: Session,
    entity_id: UUID,
    original_label: str,
    canonical_name: str,
    confidence: float,
    created_by: str = "claude",
    flush_only: bool = False,
) -> EntityPattern:
    """
    Create or update an entity pattern (upsert by entity_id + original_label).

    If a pattern already exists for this entity/label pair:
    - Updates confidence if new confidence is higher
    - Increments occurrence_count
    - Updates last_seen timestamp

    Args:
        db: Database session
        entity_id: Entity UUID
        original_label: Raw label from document
        canonical_name: Mapped canonical name
        confidence: Confidence score (0.0-1.0)
        created_by: Source ('claude' or 'user_correction')

    Returns:
        EntityPattern: Created or updated record

    Raises:
        ValueError: If canonical_name is not a valid taxonomy item
    """
    from src.extraction.taxonomy_loader import get_all_canonical_names

    if canonical_name not in get_all_canonical_names():
        raise ValueError(f"Invalid canonical_name: '{canonical_name}'")

    try:
        existing = (
            db.query(EntityPattern)
            .filter(
                EntityPattern.entity_id == entity_id,
                EntityPattern.original_label == original_label,
            )
            .first()
        )

        if existing:
            if confidence > float(existing.confidence):
                existing.confidence = confidence  # type: ignore[assignment]
                existing.canonical_name = canonical_name
            existing.occurrence_count += 1
            existing.last_seen = datetime.now(timezone.utc)
            if flush_only:
                db.flush()
            else:
                db.commit()
                db.refresh(existing)
            return existing

        pattern = EntityPattern(
            entity_id=entity_id,
            original_label=original_label,
            canonical_name=canonical_name,
            confidence=confidence,
            created_by=created_by,
            last_seen=datetime.now(timezone.utc),
        )
        db.add(pattern)
        if flush_only:
            db.flush()
        else:
            db.commit()
            db.refresh(pattern)
        logger.debug(
            f"Entity pattern created: entity={entity_id}, "
            f"'{original_label}' -> '{canonical_name}' ({confidence:.2f})"
        )
        return pattern

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to upsert entity pattern: {str(e)}")
        raise DatabaseError(
            f"Failed to upsert entity pattern: {str(e)}",
            operation="upsert",
            table="entity_patterns",
        )


def bulk_upsert_entity_patterns(
    db: Session,
    entity_id: UUID,
    mappings: List[dict],
    min_confidence: float = 0.8,
    created_by: str = "claude",
) -> int:
    """
    Bulk upsert entity patterns from extraction mappings.

    Only persists mappings above the confidence threshold.

    Args:
        db: Database session
        entity_id: Entity UUID
        mappings: List of mapping dicts with original_label, canonical_name, confidence
        min_confidence: Minimum confidence to persist (default 0.8)
        created_by: Source identifier

    Returns:
        Number of patterns upserted
    """
    from src.extraction.taxonomy_loader import get_all_canonical_names

    valid_names = get_all_canonical_names()
    count = 0
    for m in mappings:
        confidence = m.get("confidence", 0)
        canonical = m.get("canonical_name", "")
        label = m.get("original_label", "")

        if confidence < min_confidence or canonical == "unmapped" or not label:
            continue
        if canonical not in valid_names:
            logger.warning(f"Skipping invalid canonical '{canonical}' for entity {entity_id}")
            continue

        upsert_entity_pattern(
            db=db,
            entity_id=entity_id,
            original_label=label,
            canonical_name=canonical,
            confidence=confidence,
            created_by=created_by,
        )
        count += 1

    logger.info(f"Bulk upserted {count} entity patterns for entity {entity_id}")
    return count


def delete_entity_pattern(db: Session, pattern_id: UUID) -> bool:
    """Delete an entity pattern. Returns True if deleted, False if not found."""
    try:
        pattern = db.query(EntityPattern).filter(EntityPattern.id == pattern_id).first()
        if not pattern:
            return False
        db.delete(pattern)
        db.commit()
        logger.info(f"Entity pattern {pattern_id} deleted")
        return True
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to delete entity pattern {pattern_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to delete entity pattern: {str(e)}",
            operation="delete",
            table="entity_patterns",
        )


# ============================================================================
# DLQ OPERATIONS
# ============================================================================


def create_dlq_entry(
    db: Session,
    task_id: str,
    task_name: str,
    task_args: list,
    task_kwargs: dict,
    error: str,
    traceback: str,
) -> DLQEntry:
    """
    Create a Dead Letter Queue entry for a failed task.

    Args:
        db: Database session
        task_id: Celery task ID
        task_name: Task name
        task_args: Task positional arguments
        task_kwargs: Task keyword arguments
        error: Error message
        traceback: Full traceback string

    Returns:
        Created DLQ entry
    """
    try:
        dlq_entry = DLQEntry(
            task_id=task_id,
            task_name=task_name,
            task_args=task_args,
            task_kwargs=task_kwargs,
            error=error,
            traceback=traceback,
        )
        db.add(dlq_entry)
        db.commit()
        db.refresh(dlq_entry)

        logger.info(f"DLQ entry created: dlq_id={dlq_entry.dlq_id}, task_id={task_id}")
        return dlq_entry

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to create DLQ entry for task {task_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to create DLQ entry: {str(e)}", operation="create", table="dlq_entries"
        )


def get_dlq_entry(db: Session, dlq_id: UUID) -> Optional[DLQEntry]:
    """Get a DLQ entry by ID."""
    try:
        return db.query(DLQEntry).filter(DLQEntry.dlq_id == dlq_id).first()
    except SQLAlchemyError as e:
        logger.error(f"Failed to get DLQ entry {dlq_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to get DLQ entry: {str(e)}", operation="read", table="dlq_entries"
        )


def list_dlq_entries(
    db: Session, limit: int = 100, offset: int = 0, only_unreplayed: bool = False
) -> List[DLQEntry]:
    """List DLQ entries with pagination."""
    try:
        query = db.query(DLQEntry).order_by(DLQEntry.created_at.desc())
        if only_unreplayed:
            query = query.filter(DLQEntry.replayed == 0)
        return query.limit(limit).offset(offset).all()
    except SQLAlchemyError as e:
        logger.error(f"Failed to list DLQ entries: {str(e)}")
        raise DatabaseError(
            f"Failed to list DLQ entries: {str(e)}", operation="read", table="dlq_entries"
        )


def mark_dlq_entry_replayed(db: Session, dlq_id: UUID, new_task_id: str) -> DLQEntry:
    """Mark a DLQ entry as replayed with the new task ID."""
    try:
        dlq_entry = db.query(DLQEntry).filter(DLQEntry.dlq_id == dlq_id).first()
        if not dlq_entry:
            raise DatabaseError(
                f"DLQ entry {dlq_id} not found", operation="update", table="dlq_entries"
            )
        dlq_entry.replayed += 1
        dlq_entry.replayed_at = datetime.now(timezone.utc)
        dlq_entry.replayed_task_id = new_task_id
        db.commit()
        db.refresh(dlq_entry)
        logger.info(f"DLQ entry {dlq_id} marked as replayed (task {new_task_id})")
        return dlq_entry
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to mark DLQ entry {dlq_id} as replayed: {str(e)}")
        raise DatabaseError(
            f"Failed to update DLQ entry: {str(e)}", operation="update", table="dlq_entries"
        )


def delete_dlq_entry(db: Session, dlq_id: UUID) -> bool:
    """Delete a DLQ entry. Returns True if deleted, False if not found."""
    try:
        dlq_entry = db.query(DLQEntry).filter(DLQEntry.dlq_id == dlq_id).first()
        if not dlq_entry:
            return False
        db.delete(dlq_entry)
        db.commit()
        logger.info(f"DLQ entry {dlq_id} deleted")
        return True
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to delete DLQ entry {dlq_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to delete DLQ entry: {str(e)}", operation="delete", table="dlq_entries"
        )


# ============================================================================
# PATTERN INTELLIGENCE OPERATIONS
# ============================================================================


def compute_effective_confidence(
    base_confidence: float,
    last_seen: Optional[datetime],
    created_by: str = "claude",
) -> float:
    """
    Compute effective confidence with time-based decay.

    User corrections are exempt from decay. Claude-generated patterns
    lose up to 30% confidence per year since last seen, with a floor at 0.5.

    Args:
        base_confidence: Stored confidence value (0.0-1.0)
        last_seen: Timestamp of last pattern match
        created_by: Pattern source ('claude' or 'user_correction')

    Returns:
        Effective confidence after decay
    """
    if created_by == "user_correction":
        return float(base_confidence)

    if last_seen is None:
        return float(base_confidence)

    now = datetime.now(timezone.utc)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    days_since = (now - last_seen).days
    decay_factor = max(0.5, 1.0 - (days_since / 365) * 0.3)
    return float(base_confidence) * decay_factor


def resolve_pattern_conflicts(db: Session, entity_id: UUID) -> int:
    """
    Resolve conflicts where multiple patterns map the same label to different canonicals.

    Resolution priority:
    1. user_correction wins over claude
    2. Higher occurrence_count wins
    3. More recent last_seen wins as tiebreaker

    Args:
        db: Database session
        entity_id: Entity UUID

    Returns:
        Number of patterns deactivated
    """
    try:
        # Get all active patterns for this entity
        patterns = (
            db.query(EntityPattern)
            .filter(
                EntityPattern.entity_id == entity_id,
                EntityPattern.is_active == True,
            )
            .all()
        )

        # Group by original_label
        from collections import defaultdict

        label_groups: dict[str, list[EntityPattern]] = defaultdict(list)
        for p in patterns:
            label_groups[p.original_label].append(p)

        deactivated = 0
        for label, group in label_groups.items():
            if len(group) <= 1:
                continue

            # Sort: user_correction first, then by occurrence_count desc, then by last_seen desc
            def sort_key(p: EntityPattern):
                is_user = 1 if p.created_by == "user_correction" else 0
                occ = p.occurrence_count or 0
                seen = p.last_seen or datetime.min.replace(tzinfo=timezone.utc)
                if seen.tzinfo is None:
                    seen = seen.replace(tzinfo=timezone.utc)
                return (is_user, occ, seen)

            group.sort(key=sort_key, reverse=True)

            # Winner is first; deactivate the rest
            for p in group[1:]:
                p.is_active = False
                deactivated += 1

        if deactivated:
            db.commit()
            logger.info(
                f"Resolved pattern conflicts for entity {entity_id}: "
                f"{deactivated} patterns deactivated"
            )

        return deactivated

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to resolve pattern conflicts: {str(e)}")
        raise DatabaseError(
            f"Failed to resolve pattern conflicts: {str(e)}",
            operation="update",
            table="entity_patterns",
        )


def update_pattern_confidence_from_validation(
    db: Session,
    entity_id: UUID,
    failed_canonicals: set,
    passed_canonicals: set,
) -> dict:
    """
    Adjust pattern confidence based on validation results.

    Pattern-mapped items that fail validation get confidence reduced.
    Items that pass get a small confidence boost (reinforcement).
    User corrections are exempt from adjustments.

    Args:
        db: Database session
        entity_id: Entity UUID
        failed_canonicals: Set of canonical names that failed validation
        passed_canonicals: Set of canonical names that passed validation

    Returns:
        Dict with 'reduced' and 'boosted' counts
    """
    try:
        patterns = (
            db.query(EntityPattern)
            .filter(
                EntityPattern.entity_id == entity_id,
                EntityPattern.is_active == True,
                EntityPattern.created_by == "claude",
            )
            .all()
        )

        reduced = 0
        boosted = 0

        for p in patterns:
            if p.canonical_name in failed_canonicals:
                new_conf = max(0.1, float(p.confidence) - 0.1)
                p.confidence = new_conf  # type: ignore[assignment]
                reduced += 1
            elif p.canonical_name in passed_canonicals:
                new_conf = min(1.0, float(p.confidence) + 0.02)
                p.confidence = new_conf  # type: ignore[assignment]
                boosted += 1

        if reduced or boosted:
            db.commit()
            logger.info(
                f"Validation feedback for entity {entity_id}: {reduced} reduced, {boosted} boosted"
            )

        return {"reduced": reduced, "boosted": boosted}

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to update pattern confidence from validation: {str(e)}")
        raise DatabaseError(
            f"Failed to update pattern confidence: {str(e)}",
            operation="update",
            table="entity_patterns",
        )


def get_industry_patterns(
    db: Session,
    industry: str,
    exclude_entity_id: UUID,
    min_confidence: float = 0.8,
    limit: int = 50,
) -> List[EntityPattern]:
    """
    Get patterns from other entities in the same industry.

    Used to bootstrap pattern hints for new entities by loading
    patterns from entities with the same industry classification.

    Args:
        db: Database session
        industry: Industry classification string
        exclude_entity_id: Entity to exclude (avoid self-matching)
        min_confidence: Minimum confidence threshold
        limit: Maximum patterns to return

    Returns:
        List of EntityPattern records from other entities in the industry
    """
    try:
        return (
            db.query(EntityPattern)
            .join(Entity, EntityPattern.entity_id == Entity.id)
            .filter(
                Entity.industry == industry,
                EntityPattern.entity_id != exclude_entity_id,
                EntityPattern.confidence >= min_confidence,
                EntityPattern.is_active == True,
            )
            .order_by(EntityPattern.confidence.desc())
            .limit(limit)
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"Failed to get industry patterns for {industry}: {str(e)}")
        raise DatabaseError(
            f"Failed to get industry patterns: {str(e)}", operation="read", table="entity_patterns"
        )


# ============================================================================
# LEARNED ALIAS OPERATIONS
# ============================================================================


def record_learned_alias(
    db: Session,
    canonical_name: str,
    alias_text: str,
    entity_id: str,
) -> Optional[LearnedAlias]:
    """
    Record a learned alias from a high-confidence mapping.

    Upserts by (canonical_name, alias_text). Increments occurrence_count
    and appends entity_id to source_entities if not already present.

    Args:
        db: Database session
        canonical_name: Canonical taxonomy name
        alias_text: The discovered alias text
        entity_id: Entity where alias was discovered

    Returns:
        Created or updated LearnedAlias record, or None if canonical_name is invalid
    """
    from src.extraction.taxonomy_loader import get_all_canonical_names

    if canonical_name not in get_all_canonical_names():
        logger.warning(f"Skipping learned alias for invalid canonical '{canonical_name}'")
        return None

    try:
        existing = (
            db.query(LearnedAlias)
            .filter(
                LearnedAlias.canonical_name == canonical_name,
                LearnedAlias.alias_text == alias_text,
            )
            .first()
        )

        if existing:
            existing.occurrence_count += 1
            sources = list(existing.source_entities or [])
            if entity_id not in sources:
                sources.append(entity_id)
                existing.source_entities = sources
            db.commit()
            db.refresh(existing)
            return existing

        alias = LearnedAlias(
            canonical_name=canonical_name,
            alias_text=alias_text,
            occurrence_count=1,
            source_entities=[entity_id],
        )
        db.add(alias)
        db.commit()
        db.refresh(alias)
        logger.debug(f"Learned alias recorded: '{alias_text}' -> {canonical_name}")
        return alias

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to record learned alias: {str(e)}")
        raise DatabaseError(
            f"Failed to record learned alias: {str(e)}", operation="upsert", table="learned_aliases"
        )


def get_learned_aliases(
    db: Session,
    promoted: Optional[bool] = None,
    min_occurrences: int = 1,
    limit: int = 100,
) -> List[LearnedAlias]:
    """
    List learned aliases with optional filters.

    Args:
        db: Database session
        promoted: Filter by promoted status (None = all)
        min_occurrences: Minimum occurrence count
        limit: Maximum records to return

    Returns:
        List of LearnedAlias records
    """
    try:
        query = db.query(LearnedAlias).filter(LearnedAlias.occurrence_count >= min_occurrences)
        if promoted is not None:
            query = query.filter(LearnedAlias.promoted == promoted)
        return query.order_by(LearnedAlias.occurrence_count.desc()).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error(f"Failed to get learned aliases: {str(e)}")
        raise DatabaseError(
            f"Failed to get learned aliases: {str(e)}", operation="read", table="learned_aliases"
        )


def promote_learned_alias(db: Session, alias_id: UUID) -> Optional[LearnedAlias]:
    """
    Mark a learned alias as promoted.

    Args:
        db: Database session
        alias_id: LearnedAlias UUID

    Returns:
        Updated LearnedAlias or None if not found
    """
    try:
        alias = db.query(LearnedAlias).filter(LearnedAlias.id == alias_id).first()
        if not alias:
            return None
        alias.promoted = True
        db.commit()
        db.refresh(alias)
        logger.info(f"Learned alias promoted: '{alias.alias_text}' -> {alias.canonical_name}")
        try:
            from src.extraction.taxonomy_loader import invalidate_promoted_cache

            invalidate_promoted_cache()
        except ImportError:
            pass
        return alias
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to promote learned alias {alias_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to promote learned alias: {str(e)}",
            operation="update",
            table="learned_aliases",
        )


def get_promoted_aliases_for_lookup(db: Session) -> List[dict]:
    """Return promoted aliases as {alias_text, canonical_name} dicts for taxonomy merge.

    Used by taxonomy_loader to merge promoted learned aliases into the alias lookup.
    Returns empty list on failure (graceful degradation).
    """
    try:
        aliases = db.query(LearnedAlias).filter(LearnedAlias.promoted == True).all()
        return [{"alias_text": a.alias_text, "canonical_name": a.canonical_name} for a in aliases]
    except SQLAlchemyError as e:
        logger.error(f"Failed to get promoted aliases for lookup: {str(e)}")
        return []


def get_promotable_aliases(
    db: Session,
    min_occurrences: int = 3,
) -> List[LearnedAlias]:
    """
    Get aliases eligible for promotion to taxonomy.

    Aliases must have been seen across enough different entities
    and not yet promoted.

    Args:
        db: Database session
        min_occurrences: Minimum occurrence count for eligibility

    Returns:
        List of LearnedAlias records eligible for promotion
    """
    try:
        return (
            db.query(LearnedAlias)
            .filter(
                LearnedAlias.promoted == False,
                LearnedAlias.occurrence_count >= min_occurrences,
            )
            .order_by(LearnedAlias.occurrence_count.desc())
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"Failed to get promotable aliases: {str(e)}")
        raise DatabaseError(
            f"Failed to get promotable aliases: {str(e)}", operation="read", table="learned_aliases"
        )


# ============================================================================
# EXTRACTION FACT OPERATIONS
# ============================================================================


def persist_extraction_facts(
    db: Session,
    job_id: UUID,
    entity_id: Optional[UUID],
    line_items: List[dict],
    validation_lookup: Optional[dict] = None,
) -> int:
    """Decompose line_items into (canonical_name, period, value) facts and bulk insert.

    Args:
        db: Database session
        job_id: ExtractionJob UUID
        entity_id: Optional Entity UUID
        line_items: List of dicts with canonical_name, original_label, values, confidence, etc.
        validation_lookup: Optional dict {canonical_name: {passed: bool, ...}} from item_validation

    Returns:
        Number of facts persisted
    """
    from decimal import Decimal, InvalidOperation

    facts = []
    unmapped_labels = []
    for item in line_items:
        canonical = item.get("canonical_name")
        if not canonical:
            continue

        # Collect unmapped labels for taxonomy gap tracking
        if canonical == "unmapped":
            label = (item.get("original_label") or "").strip()
            if label:
                unmapped_labels.append({
                    "original_label": label,
                    "label_normalized": label.lower().strip(),
                    "sheet_name": item.get("sheet_name") or item.get("sheet"),
                    "taxonomy_category_hint": item.get("taxonomy_category"),
                })
            continue

        values = item.get("values", {})
        if not isinstance(values, dict):
            continue

        for period, value in values.items():
            if value is None:
                continue
            try:
                dec_value = Decimal(str(value))
            except (InvalidOperation, ValueError, TypeError):
                logger.warning(f"Skipping malformed value for {canonical}/{period}: {value}")
                continue

            validation_passed = None
            if validation_lookup and canonical in validation_lookup:
                validation_passed = validation_lookup[canonical].get("passed")

            facts.append(
                ExtractionFact(
                    job_id=job_id,
                    entity_id=entity_id,
                    canonical_name=canonical,
                    original_label=item.get("original_label"),
                    period=str(period),
                    period_normalized=item.get("period_normalized", {}).get(str(period))
                    if isinstance(item.get("period_normalized"), dict)
                    else None,
                    value=dec_value,
                    confidence=item.get("confidence"),
                    sheet_name=item.get("sheet_name"),
                    row_index=item.get("row_index"),
                    hierarchy_level=item.get("hierarchy_level"),
                    mapping_method=item.get("method"),
                    taxonomy_category=item.get("taxonomy_category"),
                    validation_passed=validation_passed,
                    currency_code=item.get("currency_code"),
                    source_unit=item.get("source_unit"),
                    source_scale=item.get("source_scale"),
                )
            )

    if not facts and not unmapped_labels:
        return 0

    fact_count = 0
    try:
        if facts:
            db.bulk_save_objects(facts)
            db.commit()
            fact_count = len(facts)
            logger.info(f"Persisted {fact_count} extraction facts for job {job_id}")
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to persist extraction facts: {str(e)}")
        raise DatabaseError(
            f"Failed to persist extraction facts: {str(e)}",
            operation="create",
            table="extraction_facts",
        )

    # Best-effort unmapped label tracking
    if unmapped_labels:
        try:
            _persist_unmapped_labels(db, job_id, entity_id, unmapped_labels)
        except Exception as e:
            logger.warning(f"Could not persist unmapped labels: {e}")

    return fact_count


def _persist_unmapped_labels(
    db: Session,
    job_id: UUID,
    entity_id: Optional[UUID],
    unmapped_labels: List[dict],
) -> None:
    """Upsert unmapped label aggregates for taxonomy gap analysis."""
    for label_info in unmapped_labels:
        existing = (
            db.query(UnmappedLabelAggregate)
            .filter(
                UnmappedLabelAggregate.label_normalized == label_info["label_normalized"],
                UnmappedLabelAggregate.entity_id == entity_id,
            )
            .first()
        )

        if existing:
            existing.occurrence_count += 1
            existing.last_seen_job_id = job_id
            if label_info["original_label"] not in (existing.original_labels or []):
                existing.original_labels = (existing.original_labels or []) + [
                    label_info["original_label"]
                ]
            sheet = label_info.get("sheet_name")
            if sheet and sheet not in (existing.sheet_names or []):
                existing.sheet_names = (existing.sheet_names or []) + [sheet]
        else:
            db.add(
                UnmappedLabelAggregate(
                    label_normalized=label_info["label_normalized"],
                    original_labels=[label_info["original_label"]],
                    entity_id=entity_id,
                    occurrence_count=1,
                    last_seen_job_id=job_id,
                    sheet_names=[label_info["sheet_name"]] if label_info.get("sheet_name") else [],
                    taxonomy_category_hint=label_info.get("taxonomy_category_hint"),
                )
            )

    db.commit()
    logger.info(
        f"Persisted {len(unmapped_labels)} unmapped label records for job {job_id}"
    )


def get_unmapped_label_aggregation(
    db: Session,
    min_occurrences: int = 1,
    min_entities: int = 1,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Aggregate unmapped labels across entities for taxonomy gap analysis.

    Returns labels sorted by total occurrence count descending,
    filtered by minimum occurrences and minimum entity count.
    """
    # Subquery: group by label, aggregate counts
    subquery = (
        db.query(
            UnmappedLabelAggregate.label_normalized,
            sa_func.sum(UnmappedLabelAggregate.occurrence_count).label("total_occurrences"),
            sa_func.count(sa_func.distinct(UnmappedLabelAggregate.entity_id)).label("entity_count"),
        )
        .group_by(UnmappedLabelAggregate.label_normalized)
        .having(sa_func.sum(UnmappedLabelAggregate.occurrence_count) >= min_occurrences)
        .having(sa_func.count(sa_func.distinct(UnmappedLabelAggregate.entity_id)) >= min_entities)
        .order_by(sa_func.sum(UnmappedLabelAggregate.occurrence_count).desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Count total matching labels (for pagination)
    total_query = (
        db.query(sa_func.count(sa_func.distinct(UnmappedLabelAggregate.label_normalized)))
        .group_by(UnmappedLabelAggregate.label_normalized)
        .having(sa_func.sum(UnmappedLabelAggregate.occurrence_count) >= min_occurrences)
        .having(sa_func.count(sa_func.distinct(UnmappedLabelAggregate.entity_id)) >= min_entities)
    )
    total = total_query.count()

    # For each label, fetch detail rows
    labels = []
    for row in subquery:
        label_norm = row[0]
        detail_rows = (
            db.query(UnmappedLabelAggregate)
            .filter(UnmappedLabelAggregate.label_normalized == label_norm)
            .all()
        )

        all_variants: list[str] = []
        all_entity_ids: list[str] = []
        all_sheets: list[str] = []
        category_hint = None
        for d in detail_rows:
            all_variants.extend(d.original_labels or [])
            if d.entity_id:
                all_entity_ids.append(str(d.entity_id))
            all_sheets.extend(d.sheet_names or [])
            if d.taxonomy_category_hint and not category_hint:
                category_hint = d.taxonomy_category_hint

        labels.append({
            "label_normalized": label_norm,
            "original_variants": sorted(set(all_variants)),
            "total_occurrences": int(row[1]),
            "entity_count": int(row[2]),
            "entity_ids": sorted(set(all_entity_ids)),
            "sheet_names": sorted(set(all_sheets)),
            "taxonomy_category_hint": category_hint,
        })

    return {
        "labels": labels,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def query_extraction_facts(
    db: Session,
    entity_id: Optional[UUID] = None,
    canonical_name: Optional[str] = None,
    period: Optional[str] = None,
    job_id: Optional[UUID] = None,
    min_confidence: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[ExtractionFact]:
    """Query extraction facts with optional filters.

    Args:
        db: Database session
        entity_id: Filter by entity
        canonical_name: Filter by canonical name
        period: Filter by period
        job_id: Filter by job
        min_confidence: Minimum confidence threshold
        limit: Max results (default 100, capped at 1000)
        offset: Pagination offset

    Returns:
        List of ExtractionFact records
    """
    limit = min(limit, 1000)
    try:
        query = db.query(ExtractionFact)
        if entity_id:
            query = query.filter(ExtractionFact.entity_id == entity_id)
        if canonical_name:
            query = query.filter(ExtractionFact.canonical_name == canonical_name)
        if period:
            query = query.filter(ExtractionFact.period == period)
        if job_id:
            query = query.filter(ExtractionFact.job_id == job_id)
        if min_confidence is not None:
            query = query.filter(ExtractionFact.confidence >= min_confidence)

        return query.order_by(ExtractionFact.created_at.desc()).offset(offset).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error(f"Failed to query extraction facts: {str(e)}")
        raise DatabaseError(
            f"Failed to query extraction facts: {str(e)}",
            operation="read",
            table="extraction_facts",
        )


# ============================================================================
# CORRECTION HISTORY OPERATIONS
# ============================================================================


def _build_line_item_index(line_items: list) -> dict:
    """Build a lookup index from line_items for O(1) matching by original_label.

    Returns dict mapping original_label -> list of (index, item) tuples.
    """
    from collections import defaultdict

    index = defaultdict(list)
    for idx, item in enumerate(line_items):
        label = item.get("original_label")
        if label:
            index[label].append((idx, item))
    return dict(index)


def _find_matching_line_items(
    line_items: list,
    original_label: str,
    sheet: Optional[str] = None,
    _index: Optional[dict] = None,
) -> list:
    """Find line_items matching original_label (and optionally sheet).

    Args:
        _index: Pre-built index from _build_line_item_index() for O(1) lookup.
                 If None, falls back to linear scan.

    Returns list of (index, item) tuples.
    """
    if _index is not None:
        candidates = _index.get(original_label, [])
    else:
        candidates = [
            (idx, item)
            for idx, item in enumerate(line_items)
            if item.get("original_label") == original_label
        ]

    if sheet is None:
        return candidates
    return [(idx, item) for idx, item in candidates if item.get("sheet") == sheet]


def update_extraction_facts_for_correction(
    db: Session,
    job_id: UUID,
    original_label: str,
    old_canonical_name: str,
    new_canonical_name: str,
    confidence: float = 1.0,
    mapping_method: str = "user_correction",
) -> int:
    """Update ExtractionFact rows when a correction is applied or undone.

    Args:
        confidence: Value to set (1.0 for apply, original value for undo).
        mapping_method: Value to set ("user_correction" for apply, original for undo).

    Returns count of facts updated.
    """
    try:
        facts = (
            db.query(ExtractionFact)
            .filter(
                ExtractionFact.job_id == job_id,
                ExtractionFact.canonical_name == old_canonical_name,
                ExtractionFact.original_label == original_label,
            )
            .all()
        )
        for fact in facts:
            fact.canonical_name = new_canonical_name
            fact.confidence = confidence
            fact.mapping_method = mapping_method
        return len(facts)
    except SQLAlchemyError as e:
        logger.warning(f"Could not update extraction facts for correction: {e}")
        return 0


def apply_correction_to_result(
    db: Session,
    job_id: UUID,
    corrections: list,
    created_by: str = "user_correction",
) -> dict:
    """Apply corrections to job.result line_items, create history records,
    update EntityPatterns, and update ExtractionFact rows.

    Args:
        db: Database session
        job_id: Job UUID
        corrections: List of dicts with keys: original_label, new_canonical_name, sheet (optional)
        created_by: Source identifier

    Returns:
        dict with keys: diffs, patterns_created, patterns_updated, facts_updated, warnings
    """
    try:
        # Lock the job row to prevent concurrent lost updates
        job = (
            db.query(ExtractionJob)
            .options(joinedload(ExtractionJob.file))
            .filter(ExtractionJob.job_id == job_id)
            .with_for_update()
            .first()
        )
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to load job: {e}", operation="read", table="extraction_jobs")

    if not job:
        raise DatabaseError("Job not found", operation="read", table="extraction_jobs")

    if not job.result or "line_items" not in job.result:
        raise DatabaseError(
            "Job has no result to correct", operation="update", table="extraction_jobs"
        )

    entity_id = job.file.entity_id if job.file else None
    if not entity_id:
        raise DatabaseError(
            "Corrections require an entity association", operation="update", table="extraction_jobs"
        )

    # Deep copy the result so mutations are isolated from the ORM instance
    modified_result = copy.deepcopy(job.result)
    line_items = modified_result["line_items"]
    line_item_index = _build_line_item_index(line_items)
    diffs = []
    patterns_created = 0
    patterns_updated = 0
    facts_updated = 0
    warnings = []

    try:
        for correction in corrections:
            original_label = correction["original_label"]
            new_canonical = correction["new_canonical_name"]
            sheet = correction.get("sheet")

            matches = _find_matching_line_items(
                line_items, original_label, sheet, _index=line_item_index
            )

            if not matches:
                warnings.append(f"Label '{original_label}' not found in job result")
                continue

            for idx, item in matches:
                old_canonical = item.get("canonical_name", "unmapped")
                old_confidence = item.get("confidence", 0.0)

                if old_canonical == new_canonical:
                    warnings.append(
                        f"No change needed for '{original_label}' (already '{new_canonical}')"
                    )
                    continue

                # Snapshot before mutation
                snapshot = copy.deepcopy(item)

                # Mutate line_item in our copy
                item["canonical_name"] = new_canonical
                item["confidence"] = 1.0
                if "provenance" not in item:
                    item["provenance"] = {}
                item["provenance"]["mapping"] = {
                    "method": created_by,
                    "stage": "correction",
                    "taxonomy_category": item.get("provenance", {})
                    .get("mapping", {})
                    .get("taxonomy_category", "unknown"),
                    "reasoning": f"User correction: {old_canonical} -> {new_canonical}",
                }

                # Create history record
                history = CorrectionHistory(
                    job_id=job_id,
                    entity_id=entity_id,
                    original_label=original_label,
                    sheet=item.get("sheet"),
                    old_canonical_name=old_canonical,
                    new_canonical_name=new_canonical,
                    old_confidence=old_confidence,
                    new_confidence=1.0,
                    old_line_item_snapshot=snapshot,
                )
                db.add(history)

                # Upsert entity pattern for future extractions
                existing_pattern = (
                    db.query(EntityPattern)
                    .filter(
                        EntityPattern.entity_id == entity_id,
                        EntityPattern.original_label == original_label,
                    )
                    .first()
                )

                upsert_entity_pattern(
                    db=db,
                    entity_id=entity_id,
                    original_label=original_label,
                    canonical_name=new_canonical,
                    confidence=1.0,
                    created_by=created_by,
                    flush_only=True,
                )

                if existing_pattern:
                    patterns_updated += 1
                else:
                    patterns_created += 1

                # Update extraction facts
                facts_updated += update_extraction_facts_for_correction(
                    db, job_id, original_label, old_canonical, new_canonical
                )

                diffs.append(
                    {
                        "original_label": original_label,
                        "sheet": item.get("sheet"),
                        "row": item.get("row"),
                        "old_canonical_name": old_canonical,
                        "new_canonical_name": new_canonical,
                        "old_confidence": old_confidence,
                        "new_confidence": 1.0,
                    }
                )

        # Assign the modified result back to the job
        job.result = modified_result
        flag_modified(job, "result")
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

    except SQLAlchemyError as e:
        db.rollback()
        raise DatabaseError(
            f"Failed to apply corrections: {e}",
            operation="update",
            table="extraction_jobs",
        )

    return {
        "diffs": diffs,
        "patterns_created": patterns_created,
        "patterns_updated": patterns_updated,
        "facts_updated": facts_updated,
        "warnings": warnings,
    }


def preview_corrections(
    db: Session,
    job_id: UUID,
    corrections: list,
) -> dict:
    """Preview what corrections would change without persisting.

    Returns:
        dict with keys: diffs, warnings
    """
    try:
        job = db.query(ExtractionJob).filter(ExtractionJob.job_id == job_id).first()
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to load job: {e}", operation="read", table="extraction_jobs")

    if not job:
        raise DatabaseError("Job not found", operation="read", table="extraction_jobs")

    if not job.result or "line_items" not in job.result:
        raise DatabaseError(
            "Job has no result to preview", operation="read", table="extraction_jobs"
        )

    line_items = job.result["line_items"]
    line_item_index = _build_line_item_index(line_items)
    diffs = []
    warnings = []

    for correction in corrections:
        original_label = correction["original_label"]
        new_canonical = correction["new_canonical_name"]
        sheet = correction.get("sheet")

        matches = _find_matching_line_items(
            line_items, original_label, sheet, _index=line_item_index
        )

        if not matches:
            warnings.append(f"Label '{original_label}' not found in job result")
            continue

        for _idx, item in matches:
            old_canonical = item.get("canonical_name", "unmapped")
            old_confidence = item.get("confidence", 0.0)

            if old_canonical == new_canonical:
                warnings.append(
                    f"No change needed for '{original_label}' (already '{new_canonical}')"
                )
                continue

            diffs.append(
                {
                    "original_label": original_label,
                    "sheet": item.get("sheet"),
                    "row": item.get("row"),
                    "old_canonical_name": old_canonical,
                    "new_canonical_name": new_canonical,
                    "old_confidence": old_confidence,
                    "new_confidence": 1.0,
                }
            )

    return {"diffs": diffs, "warnings": warnings}


def undo_correction(
    db: Session,
    correction_id: UUID,
) -> CorrectionHistory:
    """Revert a single correction by restoring old_line_item_snapshot into job.result.

    Returns the updated CorrectionHistory record.

    Raises:
        DatabaseError: If correction not found, already reverted, or DB error.
    """
    try:
        correction = (
            db.query(CorrectionHistory).filter(CorrectionHistory.id == correction_id).first()
        )
    except SQLAlchemyError as e:
        raise DatabaseError(
            f"Failed to load correction: {e}", operation="read", table="correction_history"
        )

    if not correction:
        raise DatabaseError("Correction not found", operation="read", table="correction_history")

    if correction.reverted:
        raise DatabaseError(
            "Correction already reverted", operation="update", table="correction_history"
        )

    # Reject undo if another non-reverted correction exists for the same
    # label+sheet on this job. Restoring this snapshot would silently
    # overwrite the other correction's changes (data corruption).
    try:
        sheet_filter = (
            CorrectionHistory.sheet == correction.sheet
            if correction.sheet
            else CorrectionHistory.sheet.is_(None)
        )
        other_active = (
            db.query(CorrectionHistory)
            .filter(
                CorrectionHistory.job_id == correction.job_id,
                CorrectionHistory.original_label == correction.original_label,
                sheet_filter,
                CorrectionHistory.reverted == False,  # noqa: E712
                CorrectionHistory.id != correction.id,
            )
            .first()
        )
    except SQLAlchemyError as e:
        raise DatabaseError(
            f"Failed to check correction ordering: {e}",
            operation="read",
            table="correction_history",
        )

    if other_active:
        raise DatabaseError(
            f"Cannot undo: another active correction for '{correction.original_label}' "
            f"exists (id={other_active.id}). Undo the most recent correction first.",
            operation="update",
            table="correction_history",
        )

    try:
        job = db.query(ExtractionJob).filter(ExtractionJob.job_id == correction.job_id).first()
        if not job or not job.result or "line_items" not in job.result:
            raise DatabaseError(
                "Job result not available for undo", operation="update", table="extraction_jobs"
            )

        line_items = job.result["line_items"]
        snapshot = correction.old_line_item_snapshot

        if snapshot:
            # Find the line_item and replace with snapshot
            matches = _find_matching_line_items(
                line_items,
                correction.original_label,
                correction.sheet,
            )
            if matches:
                idx, _ = matches[0]
                line_items[idx] = copy.deepcopy(snapshot)
            else:
                raise DatabaseError(
                    f"Label '{correction.original_label}' not found in job result for undo",
                    operation="update",
                    table="extraction_jobs",
                )
        else:
            # No snapshot - restore just canonical_name and confidence
            matches = _find_matching_line_items(
                line_items,
                correction.original_label,
                correction.sheet,
            )
            if matches:
                idx, item = matches[0]
                item["canonical_name"] = correction.old_canonical_name
                item["confidence"] = correction.old_confidence
            else:
                raise DatabaseError(
                    f"Label '{correction.original_label}' not found in job result for undo",
                    operation="update",
                    table="extraction_jobs",
                )

        flag_modified(job, "result")

        # Restore extraction facts with original confidence/method
        old_method = None
        if correction.old_line_item_snapshot:
            prov = correction.old_line_item_snapshot.get("provenance", {})
            old_method = prov.get("mapping", {}).get("method")
        update_extraction_facts_for_correction(
            db,
            correction.job_id,
            correction.original_label,
            correction.new_canonical_name,
            correction.old_canonical_name,
            confidence=correction.old_confidence,
            mapping_method=old_method,  # type: ignore[arg-type]
        )

        correction.reverted = True
        correction.reverted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(correction)

    except DatabaseError:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise DatabaseError(
            f"Failed to undo correction: {e}",
            operation="update",
            table="correction_history",
        )

    return correction


def get_correction_history(
    db: Session,
    job_id: UUID,
    include_reverted: bool = True,
    offset: int = 0,
    limit: int = 100,
) -> tuple:
    """Return correction history for a job, ordered by created_at desc.

    Returns:
        (items, total_count) tuple for pagination.
    """
    try:
        query = db.query(CorrectionHistory).filter(CorrectionHistory.job_id == job_id)
        if not include_reverted:
            query = query.filter(CorrectionHistory.reverted == False)  # noqa: E712
        total = query.count()
        items = (
            query.order_by(CorrectionHistory.created_at.desc()).offset(offset).limit(limit).all()
        )
        return items, total
    except SQLAlchemyError as e:
        raise DatabaseError(
            f"Failed to get correction history: {e}",
            operation="read",
            table="correction_history",
        )


# ============================================================================
# ANALYTICS QUERY OPERATIONS
# ============================================================================

from sqlalchemy import Date, cast


def get_entity_financials(
    db: Session,
    entity_id: UUID,
    canonical_names: Optional[List[str]] = None,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    statement_type: Optional[str] = None,
) -> List[ExtractionFact]:
    """Query financial facts for an entity, grouped by canonical_name.

    Returns raw ExtractionFact rows; caller groups by canonical_name/period.
    Only returns the latest fact per (canonical_name, period) — i.e. the
    most recent job's value.
    """
    try:
        query = db.query(ExtractionFact).filter(ExtractionFact.entity_id == entity_id)
        if canonical_names:
            query = query.filter(ExtractionFact.canonical_name.in_(canonical_names))
        if period_start:
            query = query.filter(ExtractionFact.period >= period_start)
        if period_end:
            query = query.filter(ExtractionFact.period <= period_end)
        if statement_type:
            query = query.filter(ExtractionFact.taxonomy_category == statement_type)

        return query.order_by(
            ExtractionFact.canonical_name,
            ExtractionFact.period,
            ExtractionFact.created_at.desc(),
        ).all()
    except SQLAlchemyError as e:
        logger.error(f"Failed to get entity financials: {e}")
        raise DatabaseError(
            f"Failed to get entity financials: {e}",
            operation="read",
            table="extraction_facts",
        )


def get_cross_entity_comparison(
    db: Session,
    entity_ids: List[UUID],
    canonical_names: List[str],
    period: Optional[str] = None,
    period_normalized: Optional[str] = None,
    year: Optional[int] = None,
) -> List[ExtractionFact]:
    """Get facts for comparing multiple entities.

    Supports three matching modes:
    - period: exact raw period string match
    - period_normalized: match on normalized period (e.g. FY2024)
    - year: match any fact whose normalized period contains this year
    """
    try:
        query = db.query(ExtractionFact).filter(
            ExtractionFact.entity_id.in_(entity_ids),
            ExtractionFact.canonical_name.in_(canonical_names),
        )

        if period:
            query = query.filter(ExtractionFact.period == period)
        elif period_normalized:
            query = query.filter(ExtractionFact.period_normalized == period_normalized)
        elif year:
            query = query.filter(ExtractionFact.period_normalized.like(f"%{year}%"))

        return query.order_by(ExtractionFact.canonical_name, ExtractionFact.entity_id).all()
    except SQLAlchemyError as e:
        logger.error(f"Failed to get cross-entity comparison: {e}")
        raise DatabaseError(
            f"Failed to get cross-entity comparison: {e}",
            operation="read",
            table="extraction_facts",
        )


def get_facts_for_anomaly_detection(
    db: Session,
    canonical_names: List[str],
    period_normalized: Optional[str] = None,
    year: Optional[int] = None,
    entity_ids: Optional[List[UUID]] = None,
) -> List[ExtractionFact]:
    """Get facts for cross-entity anomaly detection.

    Returns facts grouped by (canonical_name, period_normalized) across entities.
    """
    try:
        query = db.query(ExtractionFact).filter(
            ExtractionFact.canonical_name.in_(canonical_names),
            ExtractionFact.entity_id.isnot(None),
        )

        if period_normalized:
            query = query.filter(ExtractionFact.period_normalized == period_normalized)
        elif year:
            query = query.filter(ExtractionFact.period_normalized.like(f"%{year}%"))

        if entity_ids:
            query = query.filter(ExtractionFact.entity_id.in_(entity_ids))

        return (
            query.order_by(
                ExtractionFact.canonical_name,
                ExtractionFact.period_normalized,
                ExtractionFact.entity_id,
            )
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"Failed to get facts for anomaly detection: {e}")
        raise DatabaseError(
            f"Failed to get facts for anomaly detection: {e}",
            operation="read",
            table="extraction_facts",
        )


def get_portfolio_summary(
    db: Session,
    entity_ids: Optional[List[UUID]] = None,
    period: Optional[str] = None,
) -> dict:
    """Aggregate portfolio stats using SQL-level aggregation.

    Returns dict with total_entities, total_jobs, total_facts,
    avg_confidence, quality_distribution.
    """
    try:
        # Total entities
        entity_query = db.query(sa_func.count(Entity.id))
        if entity_ids:
            entity_query = entity_query.filter(Entity.id.in_(entity_ids))
        total_entities = entity_query.scalar() or 0

        # Total jobs and quality distribution
        job_query = db.query(ExtractionJob)
        if entity_ids:
            job_query = job_query.join(File, ExtractionJob.file_id == File.file_id).filter(
                File.entity_id.in_(entity_ids)
            )
        total_jobs = job_query.count()

        # Quality distribution
        quality_rows = (
            db.query(
                ExtractionJob.quality_grade,
                sa_func.count(ExtractionJob.job_id),
            )
            .filter(ExtractionJob.quality_grade.isnot(None))
            .group_by(ExtractionJob.quality_grade)
            .all()
        )
        quality_distribution = [{"grade": grade, "count": count} for grade, count in quality_rows]

        # Facts stats
        facts_query = db.query(ExtractionFact)
        if entity_ids:
            facts_query = facts_query.filter(ExtractionFact.entity_id.in_(entity_ids))
        if period:
            facts_query = facts_query.filter(ExtractionFact.period == period)

        total_facts = facts_query.count()
        avg_confidence = db.query(sa_func.avg(ExtractionFact.confidence)).filter(
            ExtractionFact.confidence.isnot(None)
        )
        if entity_ids:
            avg_confidence = avg_confidence.filter(ExtractionFact.entity_id.in_(entity_ids))
        if period:
            avg_confidence = avg_confidence.filter(ExtractionFact.period == period)
        avg_conf_val = avg_confidence.scalar()

        return {
            "total_entities": total_entities,
            "total_jobs": total_jobs,
            "total_facts": total_facts,
            "avg_confidence": round(float(avg_conf_val), 4) if avg_conf_val else None,
            "quality_distribution": quality_distribution,
        }
    except SQLAlchemyError as e:
        logger.error(f"Failed to get portfolio summary: {e}")
        raise DatabaseError(
            f"Failed to get portfolio summary: {e}",
            operation="read",
            table="extraction_facts",
        )


def get_entity_trends(
    db: Session,
    entity_id: UUID,
    canonical_name: str,
) -> List[ExtractionFact]:
    """Get all facts for a specific entity + canonical_name, ordered by period.

    Caller computes YoY changes.
    """
    try:
        return (
            db.query(ExtractionFact)
            .filter(
                ExtractionFact.entity_id == entity_id,
                ExtractionFact.canonical_name == canonical_name,
            )
            .order_by(ExtractionFact.period)
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"Failed to get entity trends: {e}")
        raise DatabaseError(
            f"Failed to get entity trends: {e}",
            operation="read",
            table="extraction_facts",
        )


def get_taxonomy_coverage(db: Session) -> dict:
    """Compute taxonomy coverage stats using SQL aggregation.

    Returns total_taxonomy_items, items_ever_mapped, most_common,
    never_mapped, coverage_pct.
    """
    from src.db.models import Taxonomy

    try:
        # Total taxonomy items
        total_taxonomy = db.query(sa_func.count(Taxonomy.id)).scalar() or 0

        # Distinct canonical names ever mapped in facts
        mapped_names_query = db.query(ExtractionFact.canonical_name).distinct().all()
        mapped_names = {row[0] for row in mapped_names_query}

        # Most common mapped items (top 20)
        most_common_rows = (
            db.query(
                ExtractionFact.canonical_name,
                ExtractionFact.taxonomy_category,
                sa_func.count(ExtractionFact.id).label("times_mapped"),
                sa_func.avg(ExtractionFact.confidence).label("avg_conf"),
            )
            .group_by(ExtractionFact.canonical_name, ExtractionFact.taxonomy_category)
            .order_by(sa_func.count(ExtractionFact.id).desc())
            .limit(20)
            .all()
        )

        most_common = [
            {
                "canonical_name": row[0],
                "category": row[1] or "unknown",
                "times_mapped": row[2],
                "avg_confidence": round(float(row[3]), 4) if row[3] else None,
            }
            for row in most_common_rows
        ]

        # Never-mapped taxonomy items
        all_taxonomy_names = {row[0] for row in db.query(Taxonomy.canonical_name).all()}
        never_mapped = sorted(all_taxonomy_names - mapped_names)

        coverage_pct = (
            round(len(mapped_names) / total_taxonomy * 100, 2) if total_taxonomy > 0 else 0.0
        )

        return {
            "total_taxonomy_items": total_taxonomy,
            "items_ever_mapped": len(mapped_names),
            "coverage_pct": coverage_pct,
            "most_common": most_common,
            "never_mapped": never_mapped,
        }
    except SQLAlchemyError as e:
        logger.error(f"Failed to get taxonomy coverage: {e}")
        raise DatabaseError(
            f"Failed to get taxonomy coverage: {e}",
            operation="read",
            table="extraction_facts",
        )


def get_cost_analytics(
    db: Session,
    entity_id: Optional[UUID] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    """Compute cost analytics across jobs using SQL-level aggregation.

    Returns total_cost, total_jobs, avg_cost_per_job,
    cost_by_entity, cost_trend_daily.
    """
    try:
        # Build shared filter conditions
        base_filters = [ExtractionJob.cost_usd.isnot(None)]
        if date_from:
            base_filters.append(ExtractionJob.created_at >= datetime.fromisoformat(date_from))  # type: ignore[arg-type]
        if date_to:
            base_filters.append(ExtractionJob.created_at <= datetime.fromisoformat(date_to))  # type: ignore[arg-type]

        # --- Totals query ---
        totals_query = db.query(
            sa_func.coalesce(sa_func.sum(ExtractionJob.cost_usd), 0.0),
            sa_func.count(ExtractionJob.job_id),
            sa_func.coalesce(sa_func.avg(ExtractionJob.cost_usd), 0.0),
        ).filter(*base_filters)
        if entity_id:
            totals_query = totals_query.join(File, ExtractionJob.file_id == File.file_id).filter(
                File.entity_id == entity_id
            )
        totals_row = totals_query.one()
        total_cost = float(totals_row[0])
        total_jobs = int(totals_row[1])
        avg_cost = float(totals_row[2])

        # --- Cost by entity query ---
        entity_query = (
            db.query(
                File.entity_id,
                Entity.name,
                sa_func.sum(ExtractionJob.cost_usd),
                sa_func.count(ExtractionJob.job_id),
            )
            .join(File, ExtractionJob.file_id == File.file_id)
            .outerjoin(Entity, File.entity_id == Entity.id)
            .filter(*base_filters)
            .filter(File.entity_id.isnot(None))
        )
        if entity_id:
            entity_query = entity_query.filter(File.entity_id == entity_id)
        entity_query = entity_query.group_by(File.entity_id, Entity.name)

        cost_by_entity = [
            {
                "entity_id": str(eid),
                "entity_name": ename,
                "total_cost": round(float(tcost), 4),
                "job_count": int(jcount),
            }
            for eid, ename, tcost, jcount in entity_query.all()
        ]

        # --- Daily trend query ---
        daily_query = db.query(
            cast(ExtractionJob.created_at, Date).label("day"),
            sa_func.sum(ExtractionJob.cost_usd),
            sa_func.count(ExtractionJob.job_id),
        ).filter(*base_filters)
        if entity_id:
            daily_query = daily_query.join(File, ExtractionJob.file_id == File.file_id).filter(
                File.entity_id == entity_id
            )
        daily_query = daily_query.group_by("day").order_by("day")

        cost_trend_daily = [
            {
                "date": str(day),
                "cost": round(float(dcost), 4),
                "job_count": int(dcount),
            }
            for day, dcost, dcount in daily_query.all()
        ]

        return {
            "total_cost": round(total_cost, 4),
            "total_jobs": total_jobs,
            "avg_cost_per_job": round(avg_cost, 4),
            "cost_by_entity": cost_by_entity,
            "cost_trend_daily": cost_trend_daily,
        }
    except SQLAlchemyError as e:
        logger.error(f"Failed to get cost analytics: {e}")
        raise DatabaseError(
            f"Failed to get cost analytics: {e}",
            operation="read",
            table="extraction_jobs",
        )


# ============================================================================
# STRUCTURED STATEMENT & MULTI-PERIOD COMPARISON (Phase 7)
# ============================================================================


def get_structured_statement(
    db: Session,
    entity_id: UUID,
    category: str,
) -> dict:
    """Build a hierarchical structured statement for an entity and category.

    Queries ExtractionFact by entity_id + taxonomy_category, loads the
    taxonomy hierarchy for the category, groups by canonical_name + period,
    and nests into a parent->children tree with computed subtotals.

    Returns dict with keys: entity_name, category, periods, items, total_items.
    """
    from src.extraction.taxonomy_loader import load_taxonomy_json

    # 1. Load entity
    entity = get_entity(db, entity_id)

    # 2. Query facts for this entity + category
    try:
        facts = (
            db.query(ExtractionFact)
            .filter(
                ExtractionFact.entity_id == entity_id,
                ExtractionFact.taxonomy_category == category,
            )
            .order_by(
                ExtractionFact.canonical_name,
                ExtractionFact.period,
                ExtractionFact.created_at.desc(),
            )
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"Failed to get structured statement: {e}")
        raise DatabaseError(
            f"Failed to get structured statement: {e}",
            operation="read",
            table="extraction_facts",
        )

    # 3. Group facts: canonical_name -> {period -> value} (latest per pair)
    from collections import defaultdict

    grouped: dict = defaultdict(dict)
    all_periods: set = set()
    for f in facts:
        if f.period not in grouped[f.canonical_name]:
            grouped[f.canonical_name][f.period] = float(f.value)
            all_periods.add(f.period)

    sorted_periods = sorted(all_periods)

    # 4. Load taxonomy hierarchy for this category
    taxonomy_data = load_taxonomy_json()
    category_items = taxonomy_data.get("categories", {}).get(category, [])

    # Build lookup: canonical_name -> taxonomy item
    tax_lookup: dict = {}
    for item in category_items:
        tax_lookup[item["canonical_name"]] = item

    # 5. Build flat line items (only items with data or parent items)
    line_items: dict = {}  # canonical_name -> item dict

    # First pass: create items for all facts
    for cn, period_values in grouped.items():
        tax_item = tax_lookup.get(cn, {})
        line_items[cn] = {
            "canonical_name": cn,
            "display_name": tax_item.get("display_name", cn.replace("_", " ").title()),
            "hierarchy_level": 0,
            "is_subtotal": False,
            "parent_canonical": tax_item.get("parent_canonical"),
            "values": period_values,
            "children": [],
        }

    # Determine hierarchy levels from parent_canonical chains
    def _get_level(cn: str, visited: set | None = None) -> int:
        if visited is None:
            visited = set()
        if cn in visited:
            return 0
        visited.add(cn)
        item = tax_lookup.get(cn, {})
        parent = item.get("parent_canonical")
        if not parent or parent not in tax_lookup:
            return 0
        return _get_level(parent, visited) + 1

    for cn in line_items:
        line_items[cn]["hierarchy_level"] = _get_level(cn)

    # 6. Build parent->children tree
    # Ensure parent items exist even if they have no direct facts
    parents_to_add = set()
    for cn, item_data in list(line_items.items()):
        parent = item_data.get("parent_canonical")
        if parent and parent not in line_items:
            parents_to_add.add(parent)

    for parent_cn in parents_to_add:
        tax_item = tax_lookup.get(parent_cn, {})
        line_items[parent_cn] = {
            "canonical_name": parent_cn,
            "display_name": tax_item.get("display_name", parent_cn.replace("_", " ").title()),
            "hierarchy_level": _get_level(parent_cn),
            "is_subtotal": True,
            "parent_canonical": tax_item.get("parent_canonical"),
            "values": {},
            "children": [],
        }

    # Nest children under parents
    root_items = []
    for cn, item_data in line_items.items():
        parent = item_data.get("parent_canonical")
        if parent and parent in line_items:
            line_items[parent]["children"].append(item_data)
            line_items[parent]["is_subtotal"] = True
        else:
            root_items.append(item_data)

    # 7. Compute subtotals for parent items (sum of children)
    def _compute_subtotals(item: dict) -> None:
        if not item["children"]:
            return
        for child in item["children"]:
            _compute_subtotals(child)
        # Only compute subtotal if parent has no direct values
        if not item["values"]:
            subtotal_values: dict = {}
            for p in sorted_periods:
                total = 0.0
                has_any = False
                for child in item["children"]:
                    if p in child["values"]:
                        total += child["values"][p]
                        has_any = True
                if has_any:
                    subtotal_values[p] = total
            item["values"] = subtotal_values

    for item in root_items:
        _compute_subtotals(item)

    # Count total items (including nested)
    def _count_items(items: list) -> int:
        count = 0
        for item in items:
            count += 1
            count += _count_items(item.get("children", []))
        return count

    total = _count_items(root_items)

    return {
        "entity_name": entity.name if entity else None,
        "category": category,
        "periods": sorted_periods,
        "items": root_items,
        "total_items": total,
    }


def get_multi_period_comparison(
    db: Session,
    entity_id: UUID,
    canonical_names: List[str],
    periods: List[str],
) -> dict:
    """Compare specific line items across multiple periods with deltas.

    Returns dict with keys: entity_name, canonical_names, periods, items.
    Each item has values (per period) and deltas (absolute/pct between adjacent periods).
    """
    entity = get_entity(db, entity_id)

    try:
        facts = (
            db.query(ExtractionFact)
            .filter(
                ExtractionFact.entity_id == entity_id,
                ExtractionFact.canonical_name.in_(canonical_names),
                ExtractionFact.period.in_(periods),
            )
            .order_by(
                ExtractionFact.canonical_name,
                ExtractionFact.period,
                ExtractionFact.created_at.desc(),
            )
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"Failed to get multi-period comparison: {e}")
        raise DatabaseError(
            f"Failed to get multi-period comparison: {e}",
            operation="read",
            table="extraction_facts",
        )

    # Group: canonical_name -> {period -> value} (latest per pair)
    from collections import defaultdict

    grouped: dict = defaultdict(dict)
    category_lookup: dict = {}
    for f in facts:
        if f.period not in grouped[f.canonical_name]:
            grouped[f.canonical_name][f.period] = float(f.value)
        if f.canonical_name not in category_lookup and f.taxonomy_category:
            category_lookup[f.canonical_name] = f.taxonomy_category

    # Build display_name lookup from taxonomy
    from src.extraction.taxonomy_loader import get_all_taxonomy_items

    display_lookup: dict = {}
    for item in get_all_taxonomy_items():
        display_lookup[item["canonical_name"]] = item.get("display_name")

    sorted_periods = sorted(periods)

    items = []
    for cn in canonical_names:
        period_values = grouped.get(cn, {})

        values = []
        for p in sorted_periods:
            val = period_values.get(p)
            values.append({"period": p, "value": val})

        # Compute deltas between adjacent periods
        deltas = []
        for i in range(len(sorted_periods) - 1):
            from_p = sorted_periods[i]
            to_p = sorted_periods[i + 1]
            from_val = period_values.get(from_p)
            to_val = period_values.get(to_p)

            abs_change = None
            pct_change = None
            if from_val is not None and to_val is not None:
                abs_change = to_val - from_val
                if from_val != 0:
                    pct_change = round((abs_change / abs(from_val)) * 100, 2)

            deltas.append({
                "from_period": from_p,
                "to_period": to_p,
                "absolute_change": abs_change,
                "pct_change": pct_change,
            })

        items.append({
            "canonical_name": cn,
            "display_name": display_lookup.get(cn),
            "taxonomy_category": category_lookup.get(cn),
            "values": values,
            "deltas": deltas,
        })

    return {
        "entity_name": entity.name if entity else None,
        "canonical_names": canonical_names,
        "periods": sorted_periods,
        "items": items,
    }


# ============================================================================
# INTELLIGENCE LAYER: CONFIDENCE CALIBRATION
# ============================================================================


def get_confidence_calibration(db: Session) -> dict:
    """Compute confidence calibration data.

    Buckets all ExtractionFact predictions by confidence into 10 bins,
    then checks CorrectionHistory to determine which were subsequently
    corrected (i.e. "incorrect").

    Returns:
        dict with keys: buckets, total_facts, total_corrections
    """
    try:
        # Get all facts with confidence values
        facts = (
            db.query(ExtractionFact)
            .filter(ExtractionFact.confidence.isnot(None))
            .all()
        )

        # Get all non-reverted corrections: build set of (job_id, canonical_name)
        corrections = (
            db.query(CorrectionHistory)
            .filter(CorrectionHistory.reverted == False)  # noqa: E712
            .all()
        )
        corrected_keys = set()
        for c in corrections:
            corrected_keys.add((str(c.job_id), c.old_canonical_name))

        total_corrections = len(corrections)

        # Initialize 10 buckets
        buckets = []
        for i in range(10):
            bin_start = round(i * 0.1, 1)
            bin_end = round((i + 1) * 0.1, 1)
            buckets.append({
                "bin_start": bin_start,
                "bin_end": bin_end,
                "total_predictions": 0,
                "correct_predictions": 0,
            })

        # Assign each fact to a bucket
        for fact in facts:
            conf = fact.confidence
            if conf is None:
                continue
            # Determine bucket index (0-9)
            bucket_idx = min(int(conf * 10), 9)

            buckets[bucket_idx]["total_predictions"] += 1

            # A fact is "correct" if it was NOT subsequently corrected for that job
            fact_key = (str(fact.job_id), fact.canonical_name)
            if fact_key not in corrected_keys:
                buckets[bucket_idx]["correct_predictions"] += 1

        # Compute accuracy per bucket
        for b in buckets:
            if b["total_predictions"] > 0:
                b["accuracy"] = round(
                    b["correct_predictions"] / b["total_predictions"], 4
                )
            else:
                b["accuracy"] = None

        return {
            "buckets": buckets,
            "total_facts": len(facts),
            "total_corrections": total_corrections,
        }
    except SQLAlchemyError as e:
        logger.error(f"Failed to get confidence calibration: {e}")
        raise DatabaseError(
            f"Failed to get confidence calibration: {e}",
            operation="read",
            table="extraction_facts",
        )


# ============================================================================
# INTELLIGENCE LAYER: AUTO-PROMOTION
# ============================================================================


def check_auto_promotions(db: Session) -> int:
    """Auto-promote learned aliases that meet promotion criteria.

    Criteria: occurrence_count >= 5, len(source_entities) >= 3, not yet promoted.

    Returns:
        Number of aliases promoted.
    """
    try:
        candidates = (
            db.query(LearnedAlias)
            .filter(
                LearnedAlias.promoted == False,  # noqa: E712
                LearnedAlias.occurrence_count >= 5,
            )
            .all()
        )

        promoted_count = 0
        for alias in candidates:
            source_entities = alias.source_entities or []
            if len(source_entities) >= 3:
                alias.promoted = True
                promoted_count += 1

        if promoted_count > 0:
            db.commit()
            logger.info(f"Auto-promoted {promoted_count} learned aliases")
            # Invalidate taxonomy cache
            try:
                from src.extraction.taxonomy_loader import invalidate_promoted_cache

                invalidate_promoted_cache()
            except ImportError:
                pass

        return promoted_count

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to check auto-promotions: {e}")
        raise DatabaseError(
            f"Failed to check auto-promotions: {e}",
            operation="update",
            table="learned_aliases",
        )


# ============================================================================
# Quality Trending
# ============================================================================


def create_quality_snapshot(
    db: Session,
    entity_id: UUID,
    snapshot_date: str,
    avg_confidence: float,
    quality_grade: str,
    total_facts: int,
    total_jobs: int,
    unmapped_label_count: int = 0,
) -> "QualitySnapshot":
    """Create a quality snapshot record for an entity."""
    from src.db.models import QualitySnapshot

    snapshot = QualitySnapshot(
        entity_id=entity_id,
        snapshot_date=snapshot_date,
        avg_confidence=avg_confidence,
        quality_grade=quality_grade,
        total_facts=total_facts,
        total_jobs=total_jobs,
        unmapped_label_count=unmapped_label_count,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def get_quality_trend(
    db: Session,
    entity_id: UUID,
    limit: int = 30,
) -> list[dict]:
    """Get quality snapshots for an entity, ordered by date descending."""
    from src.db.models import QualitySnapshot

    snapshots = (
        db.query(QualitySnapshot)
        .filter(QualitySnapshot.entity_id == entity_id)
        .order_by(QualitySnapshot.snapshot_date.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "snapshot_date": s.snapshot_date,
            "avg_confidence": s.avg_confidence,
            "quality_grade": s.quality_grade,
            "total_facts": s.total_facts,
            "total_jobs": s.total_jobs,
            "unmapped_label_count": s.unmapped_label_count,
        }
        for s in snapshots
    ]
