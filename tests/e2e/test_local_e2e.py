"""
Local end-to-end tests — full API flow without Docker.

Uses FastAPI TestClient + SQLite + mocked Claude + synchronous Celery.
Exercises: upload → extraction pipeline → job completion → result validation.

Run:
    pytest tests/e2e/test_local_e2e.py -v
"""

import asyncio
import concurrent.futures
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_model.xlsx"


@pytest.fixture
def e2e_client(test_db, mock_anthropic, mock_api_key):
    """
    Full E2E client wiring:
    - SQLite in-memory DB (shared between API and Celery task)
    - Mocked Claude (all 5 stages return canned responses)
    - Celery task runs synchronously via asyncio.run()
    - Auth bypassed with mock API key
    """
    from src.api.main import app
    from src.auth.dependencies import get_current_api_key
    from src.db.session import get_db

    # --- DB override for FastAPI dependency injection ---
    def override_get_db():
        db = test_db()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_api_key] = lambda: mock_api_key

    # --- DB context manager for Celery task (tasks.py uses get_db_context) ---
    @contextmanager
    def test_db_context():
        db = test_db()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    # --- Mock S3 client for upload endpoint (S3 upload) and task (S3 download) ---
    # Store uploaded bytes keyed by s3_key so the task can download them.
    _s3_store: dict[str, bytes] = {}

    mock_s3 = MagicMock()
    mock_s3.generate_s3_key.side_effect = lambda file_id, filename, prefix="uploads": (
        f"uploads/{file_id}_{filename}"
    )
    mock_s3.ensure_bucket_exists.return_value = None

    def _mock_upload(file_bytes, s3_key, **kwargs):
        _s3_store[s3_key] = file_bytes
        return s3_key

    mock_s3.upload_file.side_effect = _mock_upload

    def _mock_download(s3_key):
        return _s3_store.get(s3_key, b"fallback-bytes")

    mock_s3.download_file.side_effect = _mock_download

    # --- Synchronous Celery task execution ---
    # Run in a separate thread to avoid "asyncio.run() inside running loop" error.
    # This mirrors what the real Celery worker does (separate process/thread).
    def mock_delay(job_id, s3_key, entity_id=None):
        from src.jobs.tasks import async_extraction_wrapper

        def _run():
            asyncio.run(async_extraction_wrapper(job_id, s3_key, entity_id))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run)
            future.result(timeout=60)  # Wait up to 60s

        result = MagicMock()
        result.id = "mock-task-id"
        return result

    with (
        patch("src.api.files.run_extraction_task") as mock_files_task,
        patch("src.api.jobs.run_extraction_task") as mock_jobs_task,
        patch("src.api.main.get_s3_client", return_value=mock_s3),
        patch("src.api.files.get_s3_client", return_value=mock_s3),
        patch("src.storage.s3.get_s3_client", return_value=mock_s3),
        patch("src.jobs.tasks.get_db_context", test_db_context),
    ):
        mock_files_task.delay = mock_delay
        mock_jobs_task.delay = mock_delay

        client = TestClient(app, raise_server_exceptions=False)
        yield client

    app.dependency_overrides.clear()


def _upload_file(client, path=FIXTURE_PATH):
    """Helper: upload an Excel file and return the response."""
    with open(path, "rb") as f:
        return client.post(
            "/api/v1/files/upload",
            files={
                "file": (
                    "sample_model.xlsx",
                    f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_upload_returns_job_id(e2e_client):
    """Upload creates File + Job records and returns IDs."""
    resp = _upload_file(e2e_client)
    assert resp.status_code == 200, f"Upload failed: {resp.text}"

    data = resp.json()
    assert "file_id" in data
    assert "job_id" in data
    assert data["status"] == "processing"
    assert data["message"] == "Extraction started"


def test_full_extraction_completes(e2e_client):
    """Upload triggers synchronous extraction; job completes with full result."""
    # Upload (extraction runs synchronously via patched delay)
    resp = _upload_file(e2e_client)
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    job_id = resp.json()["job_id"]

    # Job should already be completed (ran synchronously)
    resp = e2e_client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200, f"Job fetch failed: {resp.text}"

    job = resp.json()
    assert job["status"] == "completed", (
        f"Expected completed, got {job['status']}. Error: {job.get('error')}"
    )

    result = job["result"]
    assert result is not None

    # Validate full result structure
    assert "sheets" in result
    assert "line_items" in result
    assert "tokens_used" in result
    assert "cost_usd" in result
    assert "triage" in result
    assert "validation" in result
    assert "lineage_summary" in result

    # Validate content
    assert len(result["sheets"]) >= 1
    assert len(result["line_items"]) == 3  # Revenue, COGS, Gross Profit
    assert result["tokens_used"] > 0
    assert result["cost_usd"] > 0

    # Validate canonical names from mapping
    canonical_names = {li["canonical_name"] for li in result["line_items"]}
    assert canonical_names == {"revenue", "cogs", "gross_profit"}

    # Validate all 5 stages produced lineage events
    summary = result["lineage_summary"]
    assert summary["total_events"] == 5
    assert sorted(summary["stages"]) == [1, 2, 3, 4, 5]


def test_deduplication_via_api(e2e_client):
    """Upload same file twice — second returns duplicate status."""
    resp1 = _upload_file(e2e_client)
    assert resp1.status_code == 200

    resp2 = _upload_file(e2e_client)
    assert resp2.status_code == 200

    data2 = resp2.json()
    assert data2["status"] == "duplicate"
    assert "already uploaded" in data2["message"].lower()


def test_invalid_file_rejected(e2e_client):
    """Non-Excel file should be rejected with 400."""
    resp = e2e_client.post(
        "/api/v1/files/upload",
        files={"file": ("bad_file.txt", b"not excel", "text/plain")},
    )
    assert resp.status_code == 400
    assert "Excel" in resp.text


def test_job_not_found(e2e_client):
    """Nonexistent job ID returns 404."""
    resp = e2e_client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
