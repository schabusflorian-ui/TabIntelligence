"""Tests for DLQ admin endpoints (GET/DELETE /api/v1/admin/dlq)."""
import pytest
from uuid import uuid4


class TestDLQList:
    """Test GET /api/v1/admin/dlq."""

    def test_list_dlq_empty(self, test_client_with_db):
        response = test_client_with_db.get("/api/v1/admin/dlq/")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["entries"] == []

    def test_list_dlq_with_entries(self, test_client_with_db, test_db):
        from src.db import crud

        session = test_db()
        try:
            crud.create_dlq_entry(
                session,
                task_id="task-abc-123",
                task_name="debtfund.extraction.run",
                task_args=["job-id-1"],
                task_kwargs={"entity_id": None},
                error="Claude API timeout",
                traceback="Traceback...",
            )
            crud.create_dlq_entry(
                session,
                task_id="task-def-456",
                task_name="debtfund.extraction.run",
                task_args=["job-id-2"],
                task_kwargs={},
                error="Rate limit exceeded",
                traceback="Traceback...",
            )
        finally:
            session.close()

        response = test_client_with_db.get("/api/v1/admin/dlq/")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["entries"][0]["task_name"] == "debtfund.extraction.run"

    def test_list_dlq_only_unreplayed(self, test_client_with_db, test_db):
        from src.db import crud

        session = test_db()
        try:
            entry1 = crud.create_dlq_entry(
                session,
                task_id="task-1",
                task_name="test.task",
                task_args=[],
                task_kwargs={},
                error="error1",
                traceback="tb1",
            )
            entry2 = crud.create_dlq_entry(
                session,
                task_id="task-2",
                task_name="test.task",
                task_args=[],
                task_kwargs={},
                error="error2",
                traceback="tb2",
            )
            # Mark entry1 as replayed
            crud.mark_dlq_entry_replayed(session, entry1.dlq_id, "new-task-1")
        finally:
            session.close()

        response = test_client_with_db.get("/api/v1/admin/dlq/?only_unreplayed=true")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["entries"][0]["task_id"] == "task-2"


class TestDLQGetDetail:
    """Test GET /api/v1/admin/dlq/{dlq_id}."""

    def test_get_dlq_entry(self, test_client_with_db, test_db):
        from src.db import crud

        session = test_db()
        try:
            entry = crud.create_dlq_entry(
                session,
                task_id="task-xyz",
                task_name="debtfund.extraction.run",
                task_args=["job-123"],
                task_kwargs={"entity_id": "ent-456"},
                error="Something went wrong",
                traceback="File ...\n  line 42\nRuntimeError: boom",
            )
            dlq_id = str(entry.dlq_id)
        finally:
            session.close()

        response = test_client_with_db.get(f"/api/v1/admin/dlq/{dlq_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-xyz"
        assert data["error"] == "Something went wrong"
        assert "RuntimeError" in data["traceback"]
        assert data["task_args"] == ["job-123"]

    def test_get_dlq_entry_not_found(self, test_client_with_db):
        fake_id = str(uuid4())
        response = test_client_with_db.get(f"/api/v1/admin/dlq/{fake_id}")
        assert response.status_code == 404

    def test_get_dlq_entry_invalid_id(self, test_client_with_db):
        response = test_client_with_db.get("/api/v1/admin/dlq/not-a-uuid")
        assert response.status_code == 400


class TestDLQDelete:
    """Test DELETE /api/v1/admin/dlq/{dlq_id}."""

    def test_delete_dlq_entry(self, test_client_with_db, test_db):
        from src.db import crud

        session = test_db()
        try:
            entry = crud.create_dlq_entry(
                session,
                task_id="task-del",
                task_name="test.task",
                task_args=[],
                task_kwargs={},
                error="error",
                traceback="tb",
            )
            dlq_id = str(entry.dlq_id)
        finally:
            session.close()

        response = test_client_with_db.delete(f"/api/v1/admin/dlq/{dlq_id}")
        assert response.status_code == 204

        # Verify it's gone
        response2 = test_client_with_db.get(f"/api/v1/admin/dlq/{dlq_id}")
        assert response2.status_code == 404

    def test_delete_dlq_entry_not_found(self, test_client_with_db):
        fake_id = str(uuid4())
        response = test_client_with_db.delete(f"/api/v1/admin/dlq/{fake_id}")
        assert response.status_code == 404


class TestDLQAuth:
    """Test DLQ endpoints require authentication."""

    def test_list_requires_auth(self, unauthenticated_client):
        response = unauthenticated_client.get("/api/v1/admin/dlq/")
        assert response.status_code in (401, 403)
