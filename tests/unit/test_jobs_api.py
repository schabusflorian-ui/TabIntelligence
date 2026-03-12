"""Tests for job management API endpoints (lineage, retry)."""

from uuid import uuid4

from src.db import crud


class TestJobLineage:
    """Test GET /api/v1/jobs/{job_id}/lineage endpoint."""

    def test_lineage_not_found(self, test_client_with_db):
        fake_id = str(uuid4())
        resp = test_client_with_db.get(f"/api/v1/jobs/{fake_id}/lineage")
        assert resp.status_code == 404

    def test_lineage_invalid_uuid(self, test_client_with_db):
        resp = test_client_with_db.get("/api/v1/jobs/bad-id/lineage")
        assert resp.status_code == 400

    def test_lineage_empty_events(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="test.xlsx", file_size=100)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        resp = test_client_with_db.get(f"/api/v1/jobs/{job.job_id}/lineage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == str(job.job_id)
        assert data["events_count"] == 0
        assert data["events"] == []

    def test_lineage_with_events(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="test.xlsx", file_size=100)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)
        crud.create_lineage_event(
            db_session,
            job_id=job.job_id,
            stage_name="stage_1_parsing",
            data={"tokens": 100},
        )
        crud.create_lineage_event(
            db_session,
            job_id=job.job_id,
            stage_name="stage_2_triage",
            data={"tokens": 50},
        )

        resp = test_client_with_db.get(f"/api/v1/jobs/{job.job_id}/lineage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events_count"] == 2
        stages = [e["stage_name"] for e in data["events"]]
        assert "stage_1_parsing" in stages
        assert "stage_2_triage" in stages


class TestJobRetry:
    """Test POST /api/v1/jobs/{job_id}/retry endpoint."""

    def test_retry_not_found(self, test_client_with_db):
        fake_id = str(uuid4())
        resp = test_client_with_db.post(f"/api/v1/jobs/{fake_id}/retry")
        assert resp.status_code == 404

    def test_retry_invalid_uuid(self, test_client_with_db):
        resp = test_client_with_db.post("/api/v1/jobs/bad-id/retry")
        assert resp.status_code == 400

    def test_retry_non_failed_job(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="test.xlsx", file_size=100)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)
        # Job is in PENDING status by default

        resp = test_client_with_db.post(f"/api/v1/jobs/{job.job_id}/retry")
        assert resp.status_code == 409
        assert "failed" in resp.json()["detail"].lower()
