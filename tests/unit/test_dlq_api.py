"""Tests for DLQ admin API endpoints."""
import pytest
from uuid import uuid4

from src.db import crud


class TestListDLQ:
    """Test GET /api/v1/admin/dlq/ endpoint."""

    def test_list_dlq_empty(self, test_client_with_db):
        resp = test_client_with_db.get("/api/v1/admin/dlq/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    def test_list_dlq_with_entries(self, test_client_with_db, db_session):
        crud.create_dlq_entry(
            db_session,
            task_id="task-1",
            task_name="debtfund.extraction.run",
            task_args=["arg1"],
            task_kwargs={"key": "value"},
            error="Test error",
            traceback="Traceback...",
        )

        resp = test_client_with_db.get("/api/v1/admin/dlq/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["entries"][0]["task_name"] == "debtfund.extraction.run"

    def test_list_dlq_only_unreplayed(self, test_client_with_db, db_session):
        entry = crud.create_dlq_entry(
            db_session,
            task_id="task-1",
            task_name="test.task",
            task_args=[],
            task_kwargs={},
            error="Error",
            traceback="",
        )
        # Mark one as replayed
        crud.mark_dlq_entry_replayed(db_session, entry.dlq_id, "new-task-1")

        # Create another unreplayed entry
        crud.create_dlq_entry(
            db_session,
            task_id="task-2",
            task_name="test.task",
            task_args=[],
            task_kwargs={},
            error="Error 2",
            traceback="",
        )

        resp = test_client_with_db.get("/api/v1/admin/dlq/?only_unreplayed=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["entries"][0]["task_id"] == "task-2"


class TestGetDLQ:
    """Test GET /api/v1/admin/dlq/{dlq_id} endpoint."""

    def test_get_dlq_not_found(self, test_client_with_db):
        fake_id = str(uuid4())
        resp = test_client_with_db.get(f"/api/v1/admin/dlq/{fake_id}")
        assert resp.status_code == 404

    def test_get_dlq_invalid_uuid(self, test_client_with_db):
        resp = test_client_with_db.get("/api/v1/admin/dlq/bad-uuid")
        assert resp.status_code == 400

    def test_get_dlq_success(self, test_client_with_db, db_session):
        entry = crud.create_dlq_entry(
            db_session,
            task_id="task-1",
            task_name="debtfund.extraction.run",
            task_args=["arg1"],
            task_kwargs={"key": "value"},
            error="Test error",
            traceback="Full traceback here",
        )

        resp = test_client_with_db.get(f"/api/v1/admin/dlq/{entry.dlq_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_name"] == "debtfund.extraction.run"
        assert data["error"] == "Test error"
        assert data["traceback"] == "Full traceback here"
        assert data["task_args"] == ["arg1"]


class TestDeleteDLQ:
    """Test DELETE /api/v1/admin/dlq/{dlq_id} endpoint."""

    def test_delete_dlq_not_found(self, test_client_with_db):
        fake_id = str(uuid4())
        resp = test_client_with_db.delete(f"/api/v1/admin/dlq/{fake_id}")
        assert resp.status_code == 404

    def test_delete_dlq_success(self, test_client_with_db, db_session):
        entry = crud.create_dlq_entry(
            db_session,
            task_id="task-1",
            task_name="test.task",
            task_args=[],
            task_kwargs={},
            error="Error",
            traceback="",
        )

        resp = test_client_with_db.delete(f"/api/v1/admin/dlq/{entry.dlq_id}")
        assert resp.status_code == 204

        # Verify it's gone
        resp2 = test_client_with_db.get(f"/api/v1/admin/dlq/{entry.dlq_id}")
        assert resp2.status_code == 404


class TestReplayDLQ:
    """Test POST /api/v1/admin/dlq/{dlq_id}/replay endpoint."""

    def test_replay_not_found(self, test_client_with_db):
        fake_id = str(uuid4())
        resp = test_client_with_db.post(f"/api/v1/admin/dlq/{fake_id}/replay")
        assert resp.status_code == 404

    def test_replay_invalid_uuid(self, test_client_with_db):
        resp = test_client_with_db.post("/api/v1/admin/dlq/bad-uuid/replay")
        assert resp.status_code == 400
