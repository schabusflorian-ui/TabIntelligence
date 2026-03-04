"""
Celery tasks for DebtFund extraction pipeline.

Job failure handling strategy:
- During retries: job stays in PROCESSING (no premature FAILED marking)
- After all retries exhausted: DLQTask.on_failure() marks job as FAILED and routes to DLQ
- SoftTimeLimitExceeded: marked FAILED immediately (not retryable)
- Code bugs (KeyError, TypeError, ValueError, AttributeError) fail immediately to DLQ
"""
import asyncio
from typing import Optional
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded

from src.jobs.celery_app import celery_app
from src.jobs.dlq import DLQTask
from src.db.session import get_db_context
from src.db import crud
from src.db.models import JobStatusEnum
from src.core.logging import api_logger as logger, log_exception
from src.core.exceptions import ClaudeAPIError, RateLimitError

# Import anthropic exceptions with fallback for test environments where
# anthropic may be mocked at module level.
try:
    from anthropic import APIStatusError, APIConnectionError, APITimeoutError
    _TRANSIENT_EXCEPTIONS: tuple = (
        ClaudeAPIError, RateLimitError,
        APIConnectionError, APITimeoutError, APIStatusError,
        ConnectionError, TimeoutError,
    )
except (ImportError, AttributeError):
    _TRANSIENT_EXCEPTIONS = (
        ClaudeAPIError, RateLimitError,
        ConnectionError, TimeoutError,
    )


@celery_app.task(
    bind=True,
    base=DLQTask,
    name='debtfund.extraction.run',
    autoretry_for=_TRANSIENT_EXCEPTIONS,
    max_retries=3,
    acks_late=True,
)
def run_extraction_task(
    self,
    job_id: str,
    s3_key: str,
    entity_id: Optional[str] = None
) -> dict:
    """
    Background task for extraction pipeline.

    Downloads file from S3 using the provided key, then runs extraction.
    Uses asyncio.run() to bridge the sync Celery task with async extraction code.
    Job failure is handled by DLQTask.on_failure() after all retries are exhausted.
    """
    logger.info(
        f"Celery task started: job_id={job_id}, s3_key={s3_key}, "
        f"attempt={self.request.retries + 1}/{self.max_retries + 1}"
    )

    try:
        result = asyncio.run(
            async_extraction_wrapper(job_id, s3_key, entity_id)
        )
        logger.info(f"Celery task completed: job_id={job_id}")
        return result

    except SoftTimeLimitExceeded:
        # Timeouts are not retryable - mark FAILED immediately
        logger.warning(f"Task soft time limit exceeded: job_id={job_id}")
        with get_db_context() as db:
            crud.fail_job(
                db,
                UUID(job_id),
                "Extraction timeout: exceeded 5 minute soft limit"
            )
        raise

    except Exception as e:
        # Log but don't mark as FAILED - Celery will retry via autoretry_for
        # for transient errors. Code bugs (KeyError, TypeError, etc.) are NOT
        # in autoretry_for and will go straight to DLQ via on_failure().
        logger.error(
            f"Celery task attempt {self.request.retries + 1} failed: "
            f"job_id={job_id}, error={str(e)}"
        )
        raise


async def async_extraction_wrapper(
    job_id: str,
    s3_key: str,
    entity_id: Optional[str]
) -> dict:
    """
    Async wrapper that orchestrates the extraction pipeline.

    This function handles:
    1. Downloading the file from S3
    2. Updating job status to PROCESSING
    3. Running the async extraction orchestrator with progress callbacks
    4. Updating job status to COMPLETED or FAILED

    Args:
        job_id: UUID of the extraction job
        s3_key: S3 object key to download the file from
        entity_id: Optional entity ID

    Returns:
        Extraction result dictionary
    """
    from src.extraction.orchestrator import extract
    from src.core.exceptions import ExtractionError, ClaudeAPIError, LineageIncompleteError
    from src.storage.s3 import get_s3_client

    job_uuid = UUID(job_id)

    # Download file from S3
    s3_client = get_s3_client()
    file_bytes = s3_client.download_file(s3_key)

    def update_progress(stage_name: str, progress_percent: int):
        """Update job progress in DB after each stage completes."""
        try:
            with get_db_context() as db:
                crud.update_job_status(
                    db, job_uuid, JobStatusEnum.PROCESSING,
                    current_stage=stage_name,
                    progress_percent=progress_percent
                )
        except Exception as e:
            logger.warning(f"Could not update progress for job {job_id}: {e}")

    try:
        # Update to PROCESSING status
        with get_db_context() as db:
            job = crud.get_job(db, job_uuid)
            if job is None:
                raise ValueError(f"Job {job_id} not found")
            file_id_str = str(job.file_id)

            crud.update_job_status(
                db,
                job_uuid,
                JobStatusEnum.PROCESSING,
                current_stage="parsing",
                progress_percent=10
            )

        logger.info(f"Starting extraction for job: {job_id}")

        # Run extraction pipeline with progress callback
        result = await extract(
            file_bytes, file_id_str, entity_id,
            job_id=job_id, progress_callback=update_progress,
        )

        # Mark as completed
        with get_db_context() as db:
            crud.complete_job(
                db,
                job_uuid,
                result=result,
                tokens_used=result.get("tokens_used", 0),
                cost_usd=result.get("cost_usd", 0.0)
            )

        logger.info(f"Extraction completed successfully for job: {job_id}")
        return result

    except LineageIncompleteError as e:
        # Log with context but don't mark FAILED here - DLQTask.on_failure() handles that
        logger.critical(f"Lineage incomplete for job {job_id}: {str(e)}")
        log_exception(logger, e, {"job_id": job_id})
        raise

    except ClaudeAPIError as e:
        logger.error(f"Claude API error for job {job_id}: {str(e)}")
        raise

    except ExtractionError as e:
        logger.error(f"Extraction error for job {job_id}: {str(e)}")
        raise

    except Exception as e:
        logger.error(f"Unexpected error for job {job_id}: {str(e)}")
        raise
