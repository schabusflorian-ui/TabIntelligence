"""Tests for job listing endpoint (GET /api/v1/jobs)."""
import pytest
from uuid import uuid4


class TestJobListing:
    """Test GET /api/v1/jobs endpoint."""

    def test_list_jobs_empty(self, test_client_with_db):
        """Returns empty list when no jobs exist."""
        response = test_client_with_db.get("/api/v1/jobs")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["jobs"] == []
        assert data["limit"] == 50
        assert data["offset"] == 0

    def test_list_jobs_with_data(self, test_client_with_db, test_db):
        """Returns jobs when they exist."""
        from src.db import crud

        session = test_db()
        try:
            file = crud.create_file(session, filename="test.xlsx", file_size=1024)
            crud.create_extraction_job(session, file_id=file.file_id)
            crud.create_extraction_job(session, file_id=file.file_id)
        finally:
            session.close()

        response = test_client_with_db.get("/api/v1/jobs")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["jobs"]) == 2
        # Most recent first
        assert data["jobs"][0]["status"] == "pending"
        assert data["jobs"][0]["filename"] == "test.xlsx"

    def test_list_jobs_filter_by_status(self, test_client_with_db, test_db):
        """Filters jobs by status."""
        from src.db import crud
        from src.db.models import JobStatusEnum

        session = test_db()
        try:
            file = crud.create_file(session, filename="test.xlsx", file_size=1024)
            job1 = crud.create_extraction_job(session, file_id=file.file_id)
            job2 = crud.create_extraction_job(session, file_id=file.file_id)
            crud.fail_job(session, job2.job_id, "test error")
        finally:
            session.close()

        response = test_client_with_db.get("/api/v1/jobs?status=failed")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["jobs"][0]["status"] == "failed"

    def test_list_jobs_invalid_status(self, test_client_with_db):
        """Returns 400 for invalid status filter."""
        response = test_client_with_db.get("/api/v1/jobs?status=invalid")
        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]

    def test_list_jobs_pagination(self, test_client_with_db, test_db):
        """Respects limit and offset parameters."""
        from src.db import crud

        session = test_db()
        try:
            file = crud.create_file(session, filename="test.xlsx", file_size=1024)
            for _ in range(5):
                crud.create_extraction_job(session, file_id=file.file_id)
        finally:
            session.close()

        response = test_client_with_db.get("/api/v1/jobs?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["limit"] == 2
        assert data["offset"] == 0

        response2 = test_client_with_db.get("/api/v1/jobs?limit=2&offset=2")
        data2 = response2.json()
        assert data2["count"] == 2
        assert data2["offset"] == 2

    def test_list_jobs_includes_timestamps(self, test_client_with_db, test_db):
        """Job items include created_at and updated_at."""
        from src.db import crud

        session = test_db()
        try:
            file = crud.create_file(session, filename="test.xlsx", file_size=1024)
            crud.create_extraction_job(session, file_id=file.file_id)
        finally:
            session.close()

        response = test_client_with_db.get("/api/v1/jobs")
        data = response.json()
        job = data["jobs"][0]
        assert "created_at" in job
        assert "updated_at" in job
        assert job["created_at"] is not None

    def test_list_jobs_requires_auth(self, unauthenticated_client):
        """Returns 401 without authentication."""
        response = unauthenticated_client.get("/api/v1/jobs")
        assert response.status_code in (401, 403)
