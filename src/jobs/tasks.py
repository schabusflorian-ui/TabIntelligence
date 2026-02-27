"""
Celery tasks for DebtFund extraction pipeline.
"""
import asyncio
from typing import Optional
from uuid import UUID

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

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
    autoretry_for=(Exception,),  # Auto-retry on exceptions
    max_retries=3,  # Retry up to 3 times before DLQ
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

    This is the Celery task wrapper that runs the async extraction orchestrator.
    Uses asyncio.run() to bridge the sync Celery task with async extraction code.

    Args:
        job_id: UUID of the extraction job
        file_bytes: Raw Excel file bytes
        entity_id: Optional entity ID for context

    Returns:
        Extraction result dictionary
    """
    logger.info(f"Celery task started: job_id={job_id}")

    # Extract trace context from Celery headers for distributed tracing
    propagator = TraceContextTextMapPropagator()
    ctx = propagator.extract(carrier=self.request.headers or {})

    try:
        # Bridge sync Celery task with async extraction using asyncio.run()
        # Run within trace context to maintain distributed tracing
        with trace.use_span(trace.get_current_span(), end_on_exit=False):
            result = asyncio.run(
                async_extraction_wrapper(job_id, file_bytes, entity_id)
            )

        logger.info(f"Celery task completed: job_id={job_id}")
        return result

    except SoftTimeLimitExceeded:
        logger.warning(f"Task soft time limit exceeded: job_id={job_id}")
        with get_db_context() as db:
            crud.fail_job(
                db,
                UUID(job_id),
                "Extraction timeout: exceeded 5 minute soft limit"
            )
        raise

    except Exception as e:
        logger.error(f"Celery task failed: job_id={job_id}, error={str(e)}")
        log_exception(logger, e, {"job_id": job_id})
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
        with get_db_context() as db:
            crud.fail_job(db, job_uuid, f"LINEAGE INCOMPLETE: {str(e)}")
        logger.critical(f"Lineage incomplete for job {job_id}: {str(e)}")
        log_exception(logger, e, {"job_id": job_id})
        raise

    except ClaudeAPIError as e:
        with get_db_context() as db:
            crud.fail_job(db, job_uuid, f"Claude API error: {str(e)}")
        logger.error(f"Claude API error for job {job_id}: {str(e)}")
        raise

    except ExtractionError as e:
        with get_db_context() as db:
            crud.fail_job(db, job_uuid, f"Extraction error: {str(e)}")
        logger.error(f"Extraction error for job {job_id}: {str(e)}")
        raise

    except Exception as e:
        with get_db_context() as db:
            crud.fail_job(db, job_uuid, f"Unexpected error: {str(e)}")
        logger.error(f"Unexpected error for job {job_id}: {str(e)}")
        raise
