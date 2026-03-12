"""Tests for job retry endpoint (POST /api/v1/jobs/{job_id}/retry)."""
import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4


class TestRetryEndpoint:
    """Test POST /api/v1/jobs/{job_id}/retry."""

    def test_retry_failed_job(self, test_client_with_db, test_db):
        """Successfully retries a failed job."""
        from src.db import crud

        session = test_db()
        try:
            file = crud.create_file(
                session, filename="test.xlsx", file_size=1024, s3_key="uploads/test.xlsx"
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)
            crud.fail_job(session, job.job_id, "Claude API timeout")
            job_id = str(job.job_id)
        finally:
            session.close()

        # Mock Celery task (no longer need S3 mock -- retry just passes s3_key)
        mock_task_result = MagicMock()
        mock_task_result.id = "retry-task-123"

        with patch("src.api.jobs.run_extraction_task") as mock_task:
            mock_task.delay.return_value = mock_task_result

            response = test_client_with_db.post(f"/api/v1/jobs/{job_id}/retry")

        assert response.status_code == 200
        data = response.json()
        assert data["original_job_id"] == job_id
        assert data["new_job_id"] != job_id  # New job created
        assert data["status"] == "processing"
        assert data["message"] == "Re-extraction started"

        # Verify task was called with s3_key, not file_bytes
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args
        assert call_kwargs.kwargs.get("s3_key") == "uploads/test.xlsx" or \
               (call_kwargs.args and len(call_kwargs.args) > 1 and "uploads" in str(call_kwargs))

    def test_retry_pending_job_rejected(self, test_client_with_db, test_db):
        """Cannot retry a job that isn't failed."""
        from src.db import crud

        session = test_db()
        try:
            file = crud.create_file(session, filename="test.xlsx", file_size=1024)
            job = crud.create_extraction_job(session, file_id=file.file_id)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.post(f"/api/v1/jobs/{job_id}/retry")
        assert response.status_code == 409
        assert "failed" in response.json()["detail"].lower()

    def test_retry_completed_job_rejected(self, test_client_with_db, test_db):
        """Cannot retry a completed job."""
        from src.db import crud

        session = test_db()
        try:
            file = crud.create_file(session, filename="test.xlsx", file_size=1024)
            job = crud.create_extraction_job(session, file_id=file.file_id)
            crud.complete_job(session, job.job_id, result={"data": "test"}, tokens_used=100, cost_usd=0.01)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.post(f"/api/v1/jobs/{job_id}/retry")
        assert response.status_code == 409

    def test_retry_job_not_found(self, test_client_with_db):
        """Returns 404 for nonexistent job."""
        fake_id = str(uuid4())
        response = test_client_with_db.post(f"/api/v1/jobs/{fake_id}/retry")
        assert response.status_code == 404

    def test_retry_invalid_job_id(self, test_client_with_db):
        """Returns 400 for invalid job_id format."""
        response = test_client_with_db.post("/api/v1/jobs/not-a-uuid/retry")
        assert response.status_code == 400

    def test_retry_requires_auth(self, unauthenticated_client):
        """Returns 401 without authentication."""
        fake_id = str(uuid4())
        response = unauthenticated_client.post(f"/api/v1/jobs/{fake_id}/retry")
        assert response.status_code in (401, 403)

    def test_retry_with_checkpoint_resumes(self, test_client_with_db, test_db):
        """Retry of a job with checkpoint data should pass resume_from_stage."""
        from src.db import crud

        session = test_db()
        try:
            file = crud.create_file(
                session, filename="test.xlsx", file_size=1024, s3_key="uploads/test.xlsx"
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)

            # Simulate checkpoint: parsing and triage completed before failure
            job.result = {
                "_stage_results": {
                    "parsing": {"tokens": 500, "parsed": {"sheets": []}},
                    "triage": {"tokens": 100, "triage": []},
                },
                "_last_completed_stage": "triage",
            }
            session.commit()

            crud.fail_job(session, job.job_id, "mapping stage Claude API error")
            job_id = str(job.job_id)
        finally:
            session.close()

        mock_task_result = MagicMock()
        mock_task_result.id = "resume-task-456"

        with patch("src.api.jobs.run_extraction_task") as mock_task:
            mock_task.delay.return_value = mock_task_result
            response = test_client_with_db.post(f"/api/v1/jobs/{job_id}/retry")

        assert response.status_code == 200
        data = response.json()
        assert data["resumed_from"] == "mapping"
        assert set(data["reused_stages"]) == {"parsing", "triage"}

        # Verify task was called with resume_from_stage
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["resume_from_stage"] == "mapping"

    def test_retry_without_checkpoint_starts_fresh(self, test_client_with_db, test_db):
        """Retry of a job without checkpoint data should start from scratch."""
        from src.db import crud

        session = test_db()
        try:
            file = crud.create_file(
                session, filename="test.xlsx", file_size=1024, s3_key="uploads/test.xlsx"
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)
            crud.fail_job(session, job.job_id, "parsing failed immediately")
            job_id = str(job.job_id)
        finally:
            session.close()

        mock_task_result = MagicMock()
        mock_task_result.id = "fresh-task-789"

        with patch("src.api.jobs.run_extraction_task") as mock_task:
            mock_task.delay.return_value = mock_task_result
            response = test_client_with_db.post(f"/api/v1/jobs/{job_id}/retry")

        assert response.status_code == 200
        data = response.json()
        assert "resumed_from" not in data

        # Verify task was called without resume_from_stage
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs.get("resume_from_stage") is None

    def test_retry_checkpoint_seeded_on_new_job(self, test_client_with_db, test_db):
        """New job should have checkpoint data copied from failed job."""
        from src.db import crud

        session = test_db()
        try:
            file = crud.create_file(
                session, filename="test.xlsx", file_size=1024, s3_key="uploads/test.xlsx"
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)
            job.result = {
                "_stage_results": {
                    "parsing": {"tokens": 500},
                },
                "_last_completed_stage": "parsing",
            }
            session.commit()
            crud.fail_job(session, job.job_id, "triage failed")
            job_id = str(job.job_id)
        finally:
            session.close()

        mock_task_result = MagicMock()
        mock_task_result.id = "seeded-task-101"

        with patch("src.api.jobs.run_extraction_task") as mock_task:
            mock_task.delay.return_value = mock_task_result
            response = test_client_with_db.post(f"/api/v1/jobs/{job_id}/retry")

        assert response.status_code == 200
        new_job_id = response.json()["new_job_id"]

        # Verify the new job has checkpoint data seeded
        session2 = test_db()
        try:
            from uuid import UUID
            new_job = crud.get_job(session2, UUID(new_job_id))
            assert new_job.result is not None
            assert "parsing" in new_job.result.get("_stage_results", {})
        finally:
            session2.close()
