"""
CRUD (Create, Read, Update, Delete) operations for DebtFund database.

All operations use explicit transaction management and proper error handling.
This is the canonical location per Week 2 strategy.
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone

from src.db.models import Entity, File, ExtractionJob, JobStatusEnum, LineageEvent, DLQEntry, EntityPattern
from src.core.logging import database_logger as logger
from src.core.exceptions import DatabaseError


# ============================================================================
# ENTITY OPERATIONS
# ============================================================================

def create_entity(
    db: Session,
    name: str,
    industry: Optional[str] = None,
) -> Entity:
    """
    Create a new entity.

    Args:
        db: Database session
        name: Entity name
        industry: Optional industry classification

    Returns:
        Entity: Created entity record
    """
    try:
        entity = Entity(name=name, industry=industry)
        db.add(entity)
        db.commit()
        db.refresh(entity)
        logger.info(f"Entity created: id={entity.id}, name={name}")
        return entity
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to create entity: {str(e)}")
        raise DatabaseError(
            f"Failed to create entity: {str(e)}",
            operation="create",
            table="entities"
        )


def get_entity(db: Session, entity_id: UUID) -> Optional[Entity]:
    """Get entity by ID."""
    try:
        return db.query(Entity).filter(Entity.id == entity_id).first()
    except SQLAlchemyError as e:
        logger.error(f"Failed to get entity {entity_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to get entity: {str(e)}",
            operation="read",
            table="entities"
        )


def list_entities(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> List[Entity]:
    """List entities with pagination."""
    try:
        return (
            db.query(Entity)
            .order_by(Entity.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"Failed to list entities: {str(e)}")
        raise DatabaseError(
            f"Failed to list entities: {str(e)}",
            operation="read",
            table="entities"
        )


def update_entity(
    db: Session,
    entity_id: UUID,
    name: Optional[str] = None,
    industry: Optional[str] = None,
) -> Entity:
    """Update an entity's name and/or industry."""
    try:
        entity = db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            raise DatabaseError(
                f"Entity {entity_id} not found",
                operation="update",
                table="entities"
            )
        if name is not None:
            entity.name = name
        if industry is not None:
            entity.industry = industry
        db.commit()
        db.refresh(entity)
        logger.info(f"Entity {entity_id} updated")
        return entity
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to update entity {entity_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to update entity: {str(e)}",
            operation="update",
            table="entities"
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
            f"Failed to delete entity: {str(e)}",
            operation="delete",
            table="entities"
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
        raise DatabaseError(
            f"Failed to look up file: {str(e)}",
            operation="read",
            table="files"
        )


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
        raise DatabaseError(
            f"Failed to create file: {str(e)}",
            operation="create",
            table="files"
        )


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
        raise DatabaseError(
            f"Failed to get file: {str(e)}",
            operation="read",
            table="files"
        )


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
        return (
            db.query(File)
            .order_by(File.uploaded_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    except SQLAlchemyError as e:
        logger.error(f"Failed to list files: {str(e)}")
        raise DatabaseError(
            f"Failed to list files: {str(e)}",
            operation="read",
            table="files"
        )


def update_file_s3_key(
    db: Session,
    file_id: UUID,
    s3_key: str
) -> File:
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
            raise DatabaseError(
                f"File {file_id} not found",
                operation="update",
                table="files"
            )

        file.s3_key = s3_key
        db.commit()
        db.refresh(file)

        logger.info(f"File {file_id} updated with s3_key: {s3_key}")
        return file
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to update file {file_id} with s3_key: {str(e)}")
        raise DatabaseError(
            f"Failed to update file: {str(e)}",
            operation="update",
            table="files"
        )


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
            f"Failed to create job: {str(e)}",
            operation="create",
            table="extraction_jobs"
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
            .options(joinedload(ExtractionJob.file))
            .filter(ExtractionJob.job_id == job_id)
            .first()
        )
    except SQLAlchemyError as e:
        logger.error(f"Failed to get job {job_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to get job: {str(e)}",
            operation="read",
            table="extraction_jobs"
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
                f"Job {job_id} not found",
                operation="update",
                table="extraction_jobs"
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
            f"Failed to update job: {str(e)}",
            operation="update",
            table="extraction_jobs"
        )


def complete_job(
    db: Session,
    job_id: UUID,
    result: dict,
    tokens_used: int,
    cost_usd: float,
) -> ExtractionJob:
    """
    Mark job as completed with results.

    Args:
        db: Database session
        job_id: Job UUID
        result: Extraction result dictionary
        tokens_used: Number of tokens consumed
        cost_usd: Cost in USD

    Returns:
        ExtractionJob: Updated job record

    Raises:
        DatabaseError: If update fails or job not found
    """
    try:
        job = db.query(ExtractionJob).filter(ExtractionJob.job_id == job_id).first()
        if not job:
            raise DatabaseError(
                f"Job {job_id} not found",
                operation="update",
                table="extraction_jobs"
            )

        job.status = JobStatusEnum.COMPLETED
        job.progress_percent = 100
        job.result = result
        job.tokens_used = tokens_used
        job.cost_usd = cost_usd
        job.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(job)

        logger.info(f"Job {job_id} completed: tokens={tokens_used}, cost=${cost_usd:.4f}")
        return job
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to complete job {job_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to complete job: {str(e)}",
            operation="update",
            table="extraction_jobs"
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
                f"Job {job_id} not found",
                operation="update",
                table="extraction_jobs"
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
            f"Failed to update job: {str(e)}",
            operation="update",
            table="extraction_jobs"
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
        query = db.query(ExtractionJob).options(joinedload(ExtractionJob.file))

        if status:
            query = query.filter(ExtractionJob.status == status)

        query = query.order_by(ExtractionJob.created_at.desc()).offset(offset).limit(limit)

        return query.all()
    except SQLAlchemyError as e:
        logger.error(f"Failed to list jobs: {str(e)}")
        raise DatabaseError(
            f"Failed to list jobs: {str(e)}",
            operation="read",
            table="extraction_jobs"
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
            f"Failed to create lineage event: {str(e)}",
            operation="create",
            table="lineage_events"
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
            f"Failed to get lineage: {str(e)}",
            operation="read",
            table="lineage_events"
        )


# ============================================================================
# ENTITY PATTERN OPERATIONS
# ============================================================================

def get_entity_patterns(
    db: Session,
    entity_id: UUID,
    min_confidence: float = 0.0,
    limit: int = 100,
) -> List[EntityPattern]:
    """
    Get learned patterns for an entity, ordered by confidence descending.

    Args:
        db: Database session
        entity_id: Entity UUID
        min_confidence: Minimum confidence threshold (default 0.0)
        limit: Maximum patterns to return

    Returns:
        List of EntityPattern records
    """
    try:
        query = (
            db.query(EntityPattern)
            .filter(EntityPattern.entity_id == entity_id)
            .filter(EntityPattern.confidence >= min_confidence)
            .order_by(EntityPattern.confidence.desc())
            .limit(limit)
        )
        return query.all()
    except SQLAlchemyError as e:
        logger.error(f"Failed to get entity patterns for {entity_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to get entity patterns: {str(e)}",
            operation="read",
            table="entity_patterns"
        )


def upsert_entity_pattern(
    db: Session,
    entity_id: UUID,
    original_label: str,
    canonical_name: str,
    confidence: float,
    created_by: str = "claude",
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
    """
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
            table="entity_patterns"
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
    count = 0
    for m in mappings:
        confidence = m.get("confidence", 0)
        canonical = m.get("canonical_name", "")
        label = m.get("original_label", "")

        if confidence < min_confidence or canonical == "unmapped" or not label:
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
            f"Failed to create DLQ entry: {str(e)}",
            operation="create",
            table="dlq_entries"
        )


def get_dlq_entry(db: Session, dlq_id: UUID) -> Optional[DLQEntry]:
    """Get a DLQ entry by ID."""
    try:
        return db.query(DLQEntry).filter(DLQEntry.dlq_id == dlq_id).first()
    except SQLAlchemyError as e:
        logger.error(f"Failed to get DLQ entry {dlq_id}: {str(e)}")
        raise DatabaseError(
            f"Failed to get DLQ entry: {str(e)}",
            operation="read",
            table="dlq_entries"
        )


def list_dlq_entries(
    db: Session,
    limit: int = 100,
    offset: int = 0,
    only_unreplayed: bool = False
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
            f"Failed to list DLQ entries: {str(e)}",
            operation="read",
            table="dlq_entries"
        )


def mark_dlq_entry_replayed(
    db: Session,
    dlq_id: UUID,
    new_task_id: str
) -> DLQEntry:
    """Mark a DLQ entry as replayed with the new task ID."""
    try:
        dlq_entry = db.query(DLQEntry).filter(DLQEntry.dlq_id == dlq_id).first()
        if not dlq_entry:
            raise DatabaseError(
                f"DLQ entry {dlq_id} not found",
                operation="update",
                table="dlq_entries"
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
            f"Failed to update DLQ entry: {str(e)}",
            operation="update",
            table="dlq_entries"
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
            f"Failed to delete DLQ entry: {str(e)}",
            operation="delete",
            table="dlq_entries"
        )
