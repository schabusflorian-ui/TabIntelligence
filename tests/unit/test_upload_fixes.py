"""
Tests for upload endpoint bug fixes:
- Fix 1: Transactional upload (S3 first, then DB)
- Fix 2: Deduplication race condition (IntegrityError handling)
- Fix 3: Celery enqueue failure returns 503
- Fix 4: Task receives s3_key instead of file_bytes
"""

from unittest.mock import MagicMock, patch

# Valid XLSX magic bytes (ZIP header) so uploads pass magic-byte validation
_FAKE_XLSX = b"PK\x03\x04" + b"\x00" * 100


class TestUploadS3FailureGracefulDegradation:
    """Fix 1: If S3 upload fails, upload proceeds without storage (graceful degradation)."""

    def test_s3_failure_proceeds_without_storage(self, test_client_with_db, test_db):
        """When S3 upload fails, endpoint returns 200 with s3_key=None."""
        from src.core.exceptions import FileStorageError

        mock_s3 = MagicMock()
        mock_s3.generate_s3_key.return_value = "uploads/test-key.xlsx"
        mock_s3.upload_file.side_effect = FileStorageError("S3 connection refused")

        with patch("src.api.files.get_s3_client", return_value=mock_s3):
            response = test_client_with_db.post(
                "/api/v1/files/upload",
                files={"file": ("test.xlsx", _FAKE_XLSX, "application/vnd.ms-excel")},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["s3_key"] is None  # Graceful degradation: no S3 key

        # File and job records should still be created
        from src.db import crud

        session = test_db()
        try:
            files = crud.list_files(session, limit=100)
            assert len(files) == 1, "File record should exist despite S3 failure"
            assert files[0].s3_key is None
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

        with (
            patch("src.api.files.get_s3_client", return_value=mock_s3),
            patch("src.api.files.run_extraction_task", mock_task),
        ):
            response = test_client_with_db.post(
                "/api/v1/files/upload",
                files={"file": ("test.xlsx", _FAKE_XLSX, "application/vnd.ms-excel")},
            )

        assert response.status_code == 503
        assert "Task queue unavailable" in response.json()["detail"]

        # Verify the job was marked as FAILED
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

        with (
            patch("src.api.files.get_s3_client", return_value=mock_s3),
            patch("src.api.files.run_extraction_task", mock_task),
        ):
            response = test_client_with_db.post(
                "/api/v1/files/upload",
                files={"file": ("test.xlsx", _FAKE_XLSX, "application/vnd.ms-excel")},
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

        with patch("src.api.jobs.run_extraction_task") as mock_task:
            mock_task.delay.return_value = mock_task_result
            response = test_client_with_db.post(f"/api/v1/jobs/{job_id}/retry")

        assert response.status_code == 200

        # Verify task was called with s3_key
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args
        assert call_kwargs.kwargs.get("s3_key") == "uploads/original.xlsx"
        # Verify file_bytes was NOT passed
        assert "file_bytes" not in call_kwargs.kwargs


class TestQualityGradeAndNeedsReview:
    """Test quality_grade persistence and NEEDS_REVIEW status."""

    def test_complete_job_stores_quality_grade(self, test_client_with_db, test_db):
        """complete_job should store quality_grade on the ExtractionJob."""
        from src.db import crud

        session = test_db()
        try:
            file = crud.create_file(
                session, filename="test.xlsx", file_size=1024, s3_key="uploads/test.xlsx"
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)

            result = {
                "quality": {
                    "letter_grade": "B",
                    "numeric_score": 0.82,
                    "quality_gate": {"passed": True},
                },
            }
            crud.complete_job(
                session,
                job.job_id,
                result=result,
                tokens_used=500,
                cost_usd=0.01,
                quality_grade="B",
            )

            updated = crud.get_job(session, job.job_id)
            assert updated.quality_grade == "B"
            assert updated.status.value == "completed"
        finally:
            session.close()

    def test_complete_job_needs_review_on_gate_fail(self, test_client_with_db, test_db):
        """complete_job should set NEEDS_REVIEW when quality gate fails."""
        from src.db import crud
        from src.db.models import JobStatusEnum

        session = test_db()
        try:
            file = crud.create_file(
                session, filename="test.xlsx", file_size=1024, s3_key="uploads/test.xlsx"
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)

            result = {
                "quality": {
                    "letter_grade": "F",
                    "numeric_score": 0.25,
                    "quality_gate": {"passed": False, "reason": "Grade F"},
                },
            }
            crud.complete_job(
                session,
                job.job_id,
                result=result,
                tokens_used=500,
                cost_usd=0.01,
                quality_grade="F",
            )

            updated = crud.get_job(session, job.job_id)
            assert updated.status == JobStatusEnum.NEEDS_REVIEW
            assert updated.quality_grade == "F"
        finally:
            session.close()

    def test_complete_job_completed_when_gate_passes(self, test_client_with_db, test_db):
        """complete_job should set COMPLETED when quality gate passes."""
        from src.db import crud
        from src.db.models import JobStatusEnum

        session = test_db()
        try:
            file = crud.create_file(
                session, filename="test.xlsx", file_size=1024, s3_key="uploads/test.xlsx"
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)

            result = {
                "quality": {
                    "letter_grade": "A",
                    "numeric_score": 0.95,
                    "quality_gate": {"passed": True},
                },
            }
            crud.complete_job(
                session,
                job.job_id,
                result=result,
                tokens_used=500,
                cost_usd=0.01,
                quality_grade="A",
            )

            updated = crud.get_job(session, job.job_id)
            assert updated.status == JobStatusEnum.COMPLETED
        finally:
            session.close()

    def test_complete_job_no_quality_gate_defaults_completed(self, test_client_with_db, test_db):
        """Without quality_gate in result, job should still be COMPLETED."""
        from src.db import crud
        from src.db.models import JobStatusEnum

        session = test_db()
        try:
            file = crud.create_file(
                session, filename="test.xlsx", file_size=1024, s3_key="uploads/test.xlsx"
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)

            result = {"quality": {"letter_grade": "C"}}
            crud.complete_job(session, job.job_id, result=result, tokens_used=100, cost_usd=0.001)

            updated = crud.get_job(session, job.job_id)
            assert updated.status == JobStatusEnum.COMPLETED
        finally:
            session.close()
