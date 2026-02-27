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

from src.db.models import File, ExtractionJob, JobStatusEnum, LineageEvent
from src.core.logging import database_logger as logger
from src.core.exceptions import DatabaseError


# ============================================================================
# FILE OPERATIONS
# ============================================================================

def create_file(
    db: Session,
    filename: str,
    file_size: int,
    s3_key: Optional[str] = None,
    entity_id: Optional[UUID] = None,
) -> File:
    """
    Create a new file record.

    Args:
        db: Database session
        filename: Original filename
        file_size: File size in bytes
        s3_key: S3/MinIO object key (optional)
        entity_id: Entity linking ID (optional)

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
