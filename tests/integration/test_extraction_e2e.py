"""End-to-end extraction pipeline test."""
import pytest
import time
import io
from pathlib import Path

from src.db.session import get_db_context
from src.db import crud
from src.db.models import JobStatusEnum


@pytest.mark.integration
@pytest.mark.slow
def test_full_extraction_pipeline(test_client, sample_excel_file):
    """
    Test complete extraction flow:
    1. Upload file
    2. Poll job status until complete
    3. Verify lineage events saved
    4. Verify database records
    """
    files = {
        "file": (
            "financial_model.xlsx",
            sample_excel_file,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    }
    upload_response = test_client.post("/api/v1/files/upload", files=files)

    assert upload_response.status_code in [200, 202]
    data = upload_response.json()
    assert "job_id" in data
    assert "file_id" in data

    job_id = data["job_id"]

    # Step 2: Poll job status (max 5 minutes)
    max_wait = 300
    poll_interval = 5
    elapsed = 0
    job_complete = False
    final_status = None

    while elapsed < max_wait:
        status_response = test_client.get(f"/api/v1/jobs/{job_id}")
        assert status_response.status_code == 200

        status_data = status_response.json()
        job_status = status_data["status"]

        if job_status in ["completed", "failed"]:
            job_complete = True
            final_status = job_status

            if job_status == "failed":
                error_msg = status_data.get("error", "Unknown error")
                pytest.fail(f"Job failed: {error_msg}")
            break

        time.sleep(poll_interval)
        elapsed += poll_interval

    assert job_complete, f"Job did not complete within {max_wait}s"
    assert final_status == "completed"

    # Step 3: Verify lineage events saved
    with get_db_context() as db:
        from uuid import UUID

        lineage_events = crud.get_job_lineage(db, UUID(job_id))
        assert len(lineage_events) > 0, "No lineage events found"

        stages = {event.stage_name for event in lineage_events}
        has_stage_1 = any("stage_1" in s or "parsing" in s for s in stages)
        assert has_stage_1, f"No stage 1 lineage found. Stages: {stages}"


@pytest.mark.integration
def test_upload_creates_database_records(test_client, sample_excel_file):
    """Test that file upload creates proper database records."""
    files = {
        "file": (
            "test_model.xlsx",
            sample_excel_file,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    }
    upload_response = test_client.post("/api/v1/files/upload", files=files)

    assert upload_response.status_code in [200, 202]
    data = upload_response.json()

    job_id = data["job_id"]
    file_id = data["file_id"]

    with get_db_context() as db:
        from uuid import UUID

        db_file = crud.get_file(db, UUID(file_id))
        assert db_file is not None
        assert db_file.filename == "test_model.xlsx"
        assert db_file.file_size > 0

        db_job = crud.get_job(db, UUID(job_id))
        assert db_job is not None
        assert db_job.file_id == UUID(file_id)
        assert db_job.status in [JobStatusEnum.PENDING, JobStatusEnum.PROCESSING, JobStatusEnum.COMPLETED]


@pytest.mark.integration
def test_job_status_endpoint(test_client, sample_excel_file):
    """Test job status endpoint returns correct structure."""
    files = {
        "file": (
            "status_test.xlsx",
            sample_excel_file,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    }
    upload_response = test_client.post("/api/v1/files/upload", files=files)
    job_id = upload_response.json()["job_id"]

    status_response = test_client.get(f"/api/v1/jobs/{job_id}")
    assert status_response.status_code == 200

    status_data = status_response.json()
    assert "job_id" in status_data
    assert "file_id" in status_data
    assert "status" in status_data
    assert "current_stage" in status_data
    assert "progress_percent" in status_data
    assert isinstance(status_data["progress_percent"], (int, type(None)))


@pytest.mark.integration
def test_invalid_job_id_returns_404(test_client):
    """Test that invalid job ID returns 404."""
    response = test_client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.integration
def test_malformed_job_id_returns_400(test_client):
    """Test that malformed job ID returns 400."""
    response = test_client.get("/api/v1/jobs/not-a-uuid")
    assert response.status_code == 400


@pytest.fixture
def sample_excel_file():
    """Create or load a minimal valid Excel file for testing."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_model.xlsx"
    if fixture_path.exists():
        with open(fixture_path, "rb") as f:
            return io.BytesIO(f.read())

    excel_header = b"PK\x03\x04\x14\x00\x00\x00\x08\x00"
    minimal_xlsx = excel_header + b"\x00" * 1000
    return io.BytesIO(minimal_xlsx)
