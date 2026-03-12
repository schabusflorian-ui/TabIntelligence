"""
Dead Letter Queue (DLQ) handling for failed Celery tasks.

Provides:
- DLQTask base class that routes failures to DLQ
- DLQ message processing and storage
- Retry mechanism with exponential backoff
"""

from uuid import UUID

from celery import Task

from src.core.logging import api_logger as logger
from src.db import crud
from src.db.session import get_db_context
from src.jobs.celery_app import celery_app


class DLQTask(Task):
    """
    Base task class that routes failures to Dead Letter Queue.

    Features:
    - Automatic retry with exponential backoff
    - After max retries, send to DLQ
    - Store failure information in database
    - Update job status to FAILED
    """

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Called when task fails after all retries exhausted.

        Routes task to DLQ and stores failure information.

        Args:
            exc: Exception that caused failure
            task_id: Celery task ID
            args: Task positional arguments
            kwargs: Task keyword arguments
            einfo: Exception info with traceback
        """
        logger.error(f"Task {task_id} failed after {self.max_retries} retries: {exc}")

        # Send to DLQ for inspection
        try:
            celery_app.send_task(
                "src.jobs.dlq.process_dlq_message",
                queue="extraction.dlq",
                kwargs={
                    "original_task_id": task_id,
                    "original_task_name": self.name,
                    "original_args": args,
                    "original_kwargs": kwargs,
                    "error": str(exc),
                    "traceback": str(einfo),
                },
            )
            logger.info(f"Task {task_id} sent to DLQ")
        except Exception as e:
            logger.error(f"Failed to send task {task_id} to DLQ: {e}")

        # Update job status in database if job_id is present
        job_id = args[0] if args else None
        if job_id:
            try:
                with get_db_context() as db:
                    crud.fail_job(db, UUID(job_id), str(exc))
                logger.info(f"Job {job_id} marked as FAILED")
            except Exception as e:
                logger.error(f"Failed to update job {job_id} after task failure: {e}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """
        Called when task is retried.

        Logs retry information for monitoring.

        Args:
            exc: Exception that triggered retry
            task_id: Celery task ID
            args: Task positional arguments
            kwargs: Task keyword arguments
            einfo: Exception info
        """
        retry_count = self.request.retries
        logger.warning(f"Task {task_id} retry {retry_count}/{self.max_retries}: {exc}")


@celery_app.task(name="src.jobs.dlq.process_dlq_message")
def process_dlq_message(
    original_task_id: str,
    original_task_name: str,
    original_args: list,
    original_kwargs: dict,
    error: str,
    traceback: str,
):
    """
    Process and store DLQ message.

    This task runs in the DLQ queue and stores failed task information
    for later inspection and potential replay.

    Args:
        original_task_id: ID of the failed task
        original_task_name: Name of the failed task
        original_args: Arguments of the failed task
        original_kwargs: Keyword arguments of the failed task
        error: Error message
        traceback: Full traceback string
    """
    logger.info(f"Processing DLQ message for task {original_task_id}")

    try:
        with get_db_context() as db:
            crud.create_dlq_entry(
                db,
                task_id=original_task_id,
                task_name=original_task_name,
                task_args=original_args,
                task_kwargs=original_kwargs,
                error=error,
                traceback=traceback,
            )
        logger.info(f"DLQ entry created for task {original_task_id}")
    except Exception as e:
        logger.error(f"Failed to create DLQ entry for task {original_task_id}: {e}")
        # Don't raise - we don't want DLQ processing to fail


@celery_app.task(name="src.jobs.dlq.replay_dlq_entry")
def replay_dlq_entry(dlq_entry_id: str):
    """
    Replay a failed task from the DLQ.

    Fetches the DLQ entry, re-enqueues the original task with the same
    arguments, and marks the DLQ entry as replayed.

    Args:
        dlq_entry_id: UUID of the DLQ entry to replay

    Returns:
        dict: Replay result with new task ID
    """
    logger.info(f"Replaying DLQ entry {dlq_entry_id}")

    try:
        with get_db_context() as db:
            dlq_entry = crud.get_dlq_entry(db, UUID(dlq_entry_id))

            if not dlq_entry:
                logger.error(f"DLQ entry {dlq_entry_id} not found")
                return {"success": False, "error": "DLQ entry not found"}

            if dlq_entry.replayed:
                logger.warning(f"DLQ entry {dlq_entry_id} already replayed")
                return {"success": False, "error": "Already replayed"}

            # Re-enqueue original task
            task = celery_app.send_task(
                dlq_entry.task_name,
                args=dlq_entry.task_args,
                kwargs=dlq_entry.task_kwargs,
                queue="extraction",
            )

            # Mark as replayed
            crud.mark_dlq_entry_replayed(db, UUID(dlq_entry_id), task.id)

            logger.info(f"DLQ entry {dlq_entry_id} replayed as task {task.id}")

            return {"success": True, "new_task_id": task.id, "original_task_id": dlq_entry.task_id}

    except Exception as e:
        logger.error(f"Failed to replay DLQ entry {dlq_entry_id}: {e}")
        return {"success": False, "error": str(e)}
