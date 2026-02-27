"""Tests for lineage drilldown endpoint (GET /api/v1/jobs/{job_id}/lineage)."""
import pytest
from uuid import uuid4


class TestLineageEndpoint:
    """Test GET /api/v1/jobs/{job_id}/lineage."""

    def test_lineage_empty(self, test_client_with_db, test_db):
        """Returns empty events list for a job with no lineage."""
        from src.db import crud

        session = test_db()
        try:
            file = crud.create_file(session, filename="test.xlsx", file_size=1024)
            job = crud.create_extraction_job(session, file_id=file.file_id)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.get(f"/api/v1/jobs/{job_id}/lineage")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["events_count"] == 0
        assert data["events"] == []

    def test_lineage_with_events(self, test_client_with_db, test_db):
        """Returns lineage events for a job."""
        from src.db import crud

        session = test_db()
        try:
            file = crud.create_file(session, filename="test.xlsx", file_size=1024)
            job = crud.create_extraction_job(session, file_id=file.file_id)
            job_id = str(job.job_id)

            crud.create_lineage_event(
                session, job_id=job.job_id, stage_name="parsing",
                data={"tokens": 500, "duration_ms": 1200}
            )
            crud.create_lineage_event(
                session, job_id=job.job_id, stage_name="triage",
                data={"tokens": 300, "sheets_processed": 3}
            )
            crud.create_lineage_event(
                session, job_id=job.job_id, stage_name="mapping",
                data={"tokens": 800, "items_mapped": 25}
            )
        finally:
            session.close()

        response = test_client_with_db.get(f"/api/v1/jobs/{job_id}/lineage")
        assert response.status_code == 200
        data = response.json()
        assert data["events_count"] == 3
        stages = [e["stage_name"] for e in data["events"]]
        assert "parsing" in stages
        assert "triage" in stages
        assert "mapping" in stages
        # Each event has data
        for event in data["events"]:
            assert "event_id" in event
            assert "timestamp" in event
            assert event["data"] is not None

    def test_lineage_job_not_found(self, test_client_with_db):
        """Returns 404 for nonexistent job."""
        fake_id = str(uuid4())
        response = test_client_with_db.get(f"/api/v1/jobs/{fake_id}/lineage")
        assert response.status_code == 404

    def test_lineage_invalid_job_id(self, test_client_with_db):
        """Returns 400 for invalid job_id format."""
        response = test_client_with_db.get("/api/v1/jobs/not-a-uuid/lineage")
        assert response.status_code == 400

    def test_lineage_requires_auth(self, unauthenticated_client):
        """Returns 401 without authentication."""
        fake_id = str(uuid4())
        response = unauthenticated_client.get(f"/api/v1/jobs/{fake_id}/lineage")
        assert response.status_code in (401, 403)
