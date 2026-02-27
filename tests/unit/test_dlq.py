"""
Tests for Dead Letter Queue (DLQ) handling.

Note: process_dlq_message and replay_dlq_entry are Celery-decorated tasks
which become MagicMocks due to the module-level Celery mock in conftest.
We test the DLQTask class methods directly since they ARE testable.
"""
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4


class TestDLQTaskOnFailure:
    """Test DLQTask.on_failure routes failures to DLQ and updates job status."""

    def _make_task(self):
        """Create a DLQTask instance for testing."""
        from src.jobs.dlq import DLQTask
        task = DLQTask()
        task.name = "debtfund.extraction.run"
        task.max_retries = 3
        return task

    def test_on_failure_sends_to_dlq_and_updates_job(self):
        """Test that failed tasks are sent to DLQ and job is marked failed."""
        task = self._make_task()

        exc = ValueError("extraction failed")
        task_id = "task-123"
        job_id = str(uuid4())
        args = [job_id]
        einfo = MagicMock(__str__=lambda self: "traceback info")

        mock_db = MagicMock()

        with patch("src.jobs.dlq.celery_app") as mock_celery, \
             patch("src.jobs.dlq.get_db_context") as mock_db_ctx, \
             patch("src.jobs.dlq.crud") as mock_crud:

            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            task.on_failure(exc, task_id, args, {}, einfo)

            # Should send to DLQ
            mock_celery.send_task.assert_called_once()
            call_args = mock_celery.send_task.call_args
            assert call_args[0][0] == 'src.jobs.dlq.process_dlq_message'
            assert call_args[1]['queue'] == 'extraction.dlq'
            assert call_args[1]['kwargs']['original_task_id'] == task_id
            assert call_args[1]['kwargs']['error'] == "extraction failed"

            # Should mark job as failed
            mock_crud.fail_job.assert_called_once()

    def test_on_failure_handles_dlq_send_error(self):
        """Test on_failure handles DLQ send errors gracefully."""
        task = self._make_task()
        job_id = str(uuid4())

        mock_db = MagicMock()

        with patch("src.jobs.dlq.celery_app") as mock_celery, \
             patch("src.jobs.dlq.get_db_context") as mock_db_ctx, \
             patch("src.jobs.dlq.crud"):

            mock_celery.send_task.side_effect = Exception("Redis down")
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            # Should not raise despite DLQ send failure
            task.on_failure(ValueError("err"), "tid", [job_id], {}, MagicMock())

    def test_on_failure_handles_db_update_error(self):
        """Test on_failure handles DB update errors gracefully."""
        task = self._make_task()
        job_id = str(uuid4())

        with patch("src.jobs.dlq.celery_app"), \
             patch("src.jobs.dlq.get_db_context") as mock_db_ctx:

            mock_db_ctx.return_value.__enter__ = MagicMock(
                side_effect=Exception("DB connection lost")
            )
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            # Should not raise despite DB error
            task.on_failure(ValueError("err"), "tid", [job_id], {}, MagicMock())

    def test_on_failure_no_job_id_skips_db_update(self):
        """Test on_failure skips DB update when no job_id in args."""
        task = self._make_task()

        with patch("src.jobs.dlq.celery_app"), \
             patch("src.jobs.dlq.crud") as mock_crud:

            task.on_failure(ValueError("err"), "tid", [], {}, MagicMock())

        mock_crud.fail_job.assert_not_called()


class TestDLQTaskOnRetry:
    """Test DLQTask.on_retry logging."""

    def test_on_retry_logs_without_error(self):
        """Test on_retry executes without raising."""
        from src.jobs.dlq import DLQTask

        task = DLQTask()
        task.max_retries = 3
        task.request = MagicMock()
        task.request.retries = 2

        # Should not raise
        task.on_retry(ValueError("transient"), "tid", [], {}, MagicMock())
