"""
Celery tasks for DebtFund extraction pipeline.

Job failure handling strategy:
- During retries: job stays in PROCESSING (no premature FAILED marking)
- After all retries exhausted: DLQTask.on_failure() marks job as FAILED and routes to DLQ
- SoftTimeLimitExceeded: marked FAILED immediately (not retryable)
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


@celery_app.task(
    bind=True,
    base=DLQTask,
    name='debtfund.extraction.run',
    autoretry_for=(Exception,),
    max_retries=3,
    acks_late=True,
)
def run_extraction_task(
    self,
    job_id: str,
    file_bytes: bytes,
    entity_id: Optional[str] = None
) -> dict:
    """
    Background task for extraction pipeline.

    Uses asyncio.run() to bridge the sync Celery task with async extraction code.
    Job failure is handled by DLQTask.on_failure() after all retries are exhausted.
    """
    logger.info(
        f"Celery task started: job_id={job_id}, "
        f"attempt={self.request.retries + 1}/{self.max_retries + 1}"
    )

    try:
        result = asyncio.run(
            async_extraction_wrapper(job_id, file_bytes, entity_id)
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
        # Log but don't mark as FAILED - Celery will retry via autoretry_for.
        # DLQTask.on_failure() handles final failure after all retries exhausted.
        logger.error(
            f"Celery task attempt {self.request.retries + 1} failed: "
            f"job_id={job_id}, error={str(e)}"
        )
        raise


async def async_extraction_wrapper(
    job_id: str,
    file_bytes: bytes,
    entity_id: Optional[str]
) -> dict:
    """
    Async wrapper that orchestrates the extraction pipeline.

    This function handles:
    1. Updating job status to PROCESSING
    2. Running the async extraction orchestrator
    3. Updating job status to COMPLETED or FAILED

    Args:
        job_id: UUID of the extraction job
        file_bytes: Raw Excel file bytes
        entity_id: Optional entity ID

    Returns:
        Extraction result dictionary
    """
    from src.extraction.orchestrator import extract
    from src.core.exceptions import ExtractionError, ClaudeAPIError, LineageIncompleteError

    job_uuid = UUID(job_id)

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

        # Run extraction pipeline (outside transaction - long operation)
        result = await extract(file_bytes, file_id_str, entity_id, job_id=job_id)

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
