"""Job management API endpoints (lineage, retry)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from src.db.session import get_db
from src.db import crud
from src.db.models import JobStatusEnum
from src.auth.dependencies import get_current_api_key
from src.core.exceptions import DatabaseError
from src.core.logging import api_logger as logger

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/{job_id}/lineage")
def get_job_lineage(
    job_id: str,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get lineage events for a job, showing the full extraction audit trail."""
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    try:
        job = crud.get_job(db, job_uuid)
        if not job:
            raise HTTPException(404, "Job not found")

        events = crud.get_job_lineage(db, job_uuid)
        return {
            "job_id": job_id,
            "status": job.status.value,
            "events_count": len(events),
            "events": [
                {
                    "event_id": str(e.event_id),
                    "stage_name": e.stage_name,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    "data": e.data,
                }
                for e in events
            ],
        }
    except DatabaseError as e:
        logger.error(f"Database error getting lineage: {str(e)}")
        raise HTTPException(500, "Database error getting lineage")


@router.post("/{job_id}/retry")
def retry_job(
    job_id: str,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Retry a failed extraction job by re-enqueuing the Celery task."""
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    try:
        job = crud.get_job(db, job_uuid)
        if not job:
            raise HTTPException(404, "Job not found")

        if job.status != JobStatusEnum.FAILED:
            raise HTTPException(
                409,
                f"Only failed jobs can be retried (current status: {job.status.value})"
            )

        # Download original file from S3 to re-process
        from src.core.config import get_settings
        from src.storage.s3 import get_s3_client

        file = crud.get_file(db, job.file_id)
        if not file or not file.s3_key:
            raise HTTPException(422, "Original file not available for retry")

        settings = get_settings()
        s3_client = get_s3_client(settings)
        file_bytes = s3_client.download_file(file.s3_key)

        # Create a new job for the retry
        new_job = crud.create_extraction_job(db, file_id=file.file_id)

        # Enqueue Celery task
        from src.jobs.tasks import run_extraction_task

        entity_id = str(file.entity_id) if file.entity_id else None
        task = run_extraction_task.delay(
            job_id=str(new_job.job_id),
            file_bytes=file_bytes,
            entity_id=entity_id,
        )

        logger.info(
            f"Job {job_id} retried as new job {new_job.job_id}, task_id={task.id}"
        )

        return {
            "original_job_id": job_id,
            "new_job_id": str(new_job.job_id),
            "task_id": task.id,
            "status": "retrying",
        }

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"Database error retrying job: {str(e)}")
        raise HTTPException(500, "Database error retrying job")
    except Exception as e:
        logger.error(f"Failed to retry job {job_id}: {str(e)}")
        raise HTTPException(500, f"Retry failed: {str(e)}")
