"""
Tests for upload endpoint bug fixes:
- Fix 1: Transactional upload (S3 first, then DB)
- Fix 2: Deduplication race condition (IntegrityError handling)
- Fix 3: Celery enqueue failure returns 503
- Fix 4: Task receives s3_key instead of file_bytes
"""
import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4


class TestUploadS3FailureNoOrphanedRecords:
    """Fix 1: If S3 upload fails, no DB records should be created."""

    def test_s3_failure_returns_500_no_orphan_db_records(self, test_client_with_db, test_db):
        """When S3 upload fails, endpoint returns 500 and no File/Job records exist."""
        from src.core.exceptions import FileStorageError

        mock_s3 = MagicMock()
        mock_s3.generate_s3_key.return_value = "uploads/test-key.xlsx"
        mock_s3.upload_file.side_effect = FileStorageError("S3 connection refused")

        with patch("src.api.main.get_s3_client", return_value=mock_s3):
            response = test_client_with_db.post(
                "/api/v1/files/upload",
                files={"file": ("test.xlsx", b"fake excel content", "application/vnd.ms-excel")},
            )

        assert response.status_code == 500
        assert "Storage error" in response.json()["detail"]

        # Verify no orphaned DB records were created
        from src.db import crud
        session = test_db()
        try:
            files = crud.list_files(session, limit=100)
            assert len(files) == 0, "No File records should exist after S3 failure"
        finally:
            session.close()


class TestCeleryEnqueueFailureReturns503:
    """Fix 3: If Celery enqueue fails, endpoint returns 503."""

    def test_celery_enqueue_failure_returns_503(self, test_client_with_db, test_db):
        """When Redis/Celery is down, upload returns 503 and marks job FAILED."""
        from src.db.models import JobStatusEnum

        mock_s3 = MagicMock()
        mock_s3.generate_s3_key.return_value = "uploads/test-key.xlsx"
        mock_s3.upload_file.return_value = "uploads/test-key.xlsx"

        mock_task = MagicMock()
        mock_task.delay.side_effect = ConnectionError("Redis connection refused")

        with patch("src.api.main.get_s3_client", return_value=mock_s3), \
             patch("src.api.main.run_extraction_task", mock_task):
            response = test_client_with_db.post(
                "/api/v1/files/upload",
                files={"file": ("test.xlsx", b"fake excel content", "application/vnd.ms-excel")},
            )

        assert response.status_code == 503
        assert "Task queue unavailable" in response.json()["detail"]

        # Verify the job was marked as FAILED
        from src.db import crud
        session = test_db()
        try:
            from src.db.models import ExtractionJob
            jobs = session.query(ExtractionJob).all()
            assert len(jobs) == 1, "One job should exist"
            assert jobs[0].status == JobStatusEnum.FAILED
            assert "Task queue unavailable" in jobs[0].error
        finally:
            session.close()


class TestTaskReceivesS3Key:
    """Fix 4: Task receives s3_key instead of file_bytes."""

    def test_task_called_with_s3_key_not_file_bytes(self, test_client_with_db):
        """Verify the Celery task is called with s3_key, not file_bytes."""
        mock_s3 = MagicMock()
        mock_s3.generate_s3_key.return_value = "uploads/2024/01/test-key.xlsx"
        mock_s3.upload_file.return_value = "uploads/2024/01/test-key.xlsx"

        mock_task = MagicMock()
        mock_result = MagicMock()
        mock_result.id = "test-task-id"
        mock_task.delay.return_value = mock_result

        with patch("src.api.main.get_s3_client", return_value=mock_s3), \
             patch("src.api.main.run_extraction_task", mock_task):
            response = test_client_with_db.post(
                "/api/v1/files/upload",
                files={"file": ("test.xlsx", b"fake excel content", "application/vnd.ms-excel")},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"
        assert data["s3_key"] == "uploads/2024/01/test-key.xlsx"

        # Verify task was called with s3_key (string), not file_bytes
        mock_task.delay.assert_called_once()
        call_args = mock_task.delay.call_args
        # Check that s3_key was passed (as keyword arg)
        assert "s3_key" in call_args.kwargs
        assert call_args.kwargs["s3_key"] == "uploads/2024/01/test-key.xlsx"
        # Ensure file_bytes was NOT passed
        assert "file_bytes" not in call_args.kwargs


class TestRetryPassesS3Key:
    """Verify the retry endpoint passes s3_key to the task."""

    def test_retry_passes_s3_key_to_task(self, test_client_with_db, test_db):
        """Retry endpoint should pass s3_key, not download and pass file_bytes."""
        from src.db import crud

        session = test_db()
        try:
            file = crud.create_file(
                session, filename="test.xlsx", file_size=1024, s3_key="uploads/original.xlsx"
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)
            crud.fail_job(session, job.job_id, "Some error")
            job_id = str(job.job_id)
        finally:
            session.close()

        mock_task_result = MagicMock()
        mock_task_result.id = "retry-task-456"

        with patch("src.api.main.run_extraction_task") as mock_task:
            mock_task.delay.return_value = mock_task_result
            response = test_client_with_db.post(f"/api/v1/jobs/{job_id}/retry")

        assert response.status_code == 200

        # Verify task was called with s3_key
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args
        assert call_kwargs.kwargs.get("s3_key") == "uploads/original.xlsx"
        # Verify file_bytes was NOT passed
        assert "file_bytes" not in call_kwargs.kwargs
