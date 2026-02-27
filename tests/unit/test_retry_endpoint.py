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

        # Mock S3 download and Celery task
        mock_s3 = MagicMock()
        mock_s3.download_file.return_value = b"fake excel bytes"

        mock_task_result = MagicMock()
        mock_task_result.id = "retry-task-123"

        with patch("src.api.main.get_s3_client", return_value=mock_s3), \
             patch("src.api.main.run_extraction_task") as mock_task:
            mock_task.delay.return_value = mock_task_result

            response = test_client_with_db.post(f"/api/v1/jobs/{job_id}/retry")

        assert response.status_code == 200
        data = response.json()
        assert data["original_job_id"] == job_id
        assert data["new_job_id"] != job_id  # New job created
        assert data["status"] == "processing"
        assert data["message"] == "Re-extraction started"

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
