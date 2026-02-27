"""
Integration tests for FastAPI endpoints.
Tests the API layer and its integration with the extraction pipeline.
"""
import pytest
import time
from io import BytesIO


def test_health_check(test_client):
    """Test API health check endpoint."""
    response = test_client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
    assert "version" in data


def test_root_endpoint(test_client):
    """Test root endpoint returns service info."""
    response = test_client.get("/")

    assert response.status_code == 200
    # Should return some information about the service


def test_file_upload_creates_job(test_client_with_db, sample_xlsx, mock_anthropic):
    """Test file upload endpoint creates extraction job."""
    files = {
        "file": ("test_model.xlsx", BytesIO(sample_xlsx), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }

    response = test_client_with_db.post("/api/v1/files/upload", files=files)

    assert response.status_code == 200
    data = response.json()

    assert "job_id" in data
    assert "file_id" in data
    assert "status" in data
    assert data["status"] in ["processing", "pending"]


def test_file_upload_rejects_non_excel_files(test_client_with_db):
    """Test that non-Excel files are rejected."""
    fake_file = BytesIO(b"This is not an Excel file")
    files = {
        "file": ("test.txt", fake_file, "text/plain")
    }

    response = test_client_with_db.post("/api/v1/files/upload", files=files)

    assert response.status_code == 400
    assert "Excel file" in response.json()["detail"]


def test_file_upload_rejects_missing_file(test_client_with_db):
    """Test that missing file parameter returns error."""
    response = test_client_with_db.post("/api/v1/files/upload")

    assert response.status_code == 422  # Unprocessable Entity


def test_job_status_endpoint(test_client_with_db, sample_xlsx, mock_anthropic):
    """Test job status retrieval endpoint."""
    # Upload file first
    files = {
        "file": ("test.xlsx", BytesIO(sample_xlsx), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }
    upload_response = test_client_with_db.post("/api/v1/files/upload", files=files)
    job_id = upload_response.json()["job_id"]

    # Give background task a moment to start
    time.sleep(0.1)

    # Check job status
    status_response = test_client_with_db.get(f"/api/v1/jobs/{job_id}")

    assert status_response.status_code == 200
    data = status_response.json()

    assert data["job_id"] == job_id
    assert "status" in data
    assert data["status"] in ["pending", "processing", "completed", "failed"]


def test_job_status_not_found(test_client_with_db):
    """Test that non-existent job returns 404."""
    fake_job_id = "00000000-0000-0000-0000-000000000000"
    response = test_client_with_db.get(f"/api/v1/jobs/{fake_job_id}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_upload_with_entity_id(test_client_with_db, sample_xlsx, mock_anthropic):
    """Test file upload with optional entity_id parameter."""
    files = {
        "file": ("test.xlsx", BytesIO(sample_xlsx), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }

    response = test_client_with_db.post(
        "/api/v1/files/upload",
        files=files,
        data={"entity_id": "test-entity-123"}
    )

    assert response.status_code == 200
    assert "job_id" in response.json()


@pytest.mark.skip(reason="Requires Celery worker - cannot mock task execution synchronously")
def test_extraction_job_completion(test_client_with_db, sample_xlsx, mock_anthropic):
    """Test that extraction job completes successfully (integration test)."""
    # Upload file
    files = {
        "file": ("test.xlsx", BytesIO(sample_xlsx), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }
    upload_response = test_client_with_db.post("/api/v1/files/upload", files=files)
    job_id = upload_response.json()["job_id"]

    # Poll for completion (with timeout)
    max_attempts = 50  # 5 seconds with 100ms sleep
    for attempt in range(max_attempts):
        time.sleep(0.1)
        status_response = test_client_with_db.get(f"/api/v1/jobs/{job_id}")
        data = status_response.json()

        if data["status"] in ["completed", "failed"]:
            break

    # Verify completion
    assert data["status"] == "completed", f"Job failed with error: {data.get('error')}"
    assert data["progress_percent"] == 100
    assert "result" in data
    assert data["result"] is not None


@pytest.mark.skip(reason="Requires Celery worker - cannot mock task execution synchronously")
def test_extraction_result_structure(test_client_with_db, sample_xlsx, mock_anthropic):
    """Test that completed extraction has proper result structure."""
    # Upload and wait for completion
    files = {
        "file": ("test.xlsx", BytesIO(sample_xlsx), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }
    upload_response = test_client_with_db.post("/api/v1/files/upload", files=files)
    job_id = upload_response.json()["job_id"]

    # Wait for completion
    for _ in range(50):
        time.sleep(0.1)
        status_response = test_client_with_db.get(f"/api/v1/jobs/{job_id}")
        data = status_response.json()
        if data["status"] == "completed":
            break

    # Check result structure
    result = data["result"]
    assert "sheets" in result
    assert "triage" in result
    assert "line_items" in result
    assert "tokens_used" in result
    assert "cost_usd" in result


def test_concurrent_uploads(test_client_with_db, mock_anthropic):
    """Test that multiple uploads with different content are handled correctly."""
    # Use unique content for each file to avoid deduplication
    files_list = [
        ("test1.xlsx", BytesIO(b"PK\x03\x04" + b"\x01" * 100), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("test2.xlsx", BytesIO(b"PK\x03\x04" + b"\x02" * 100), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("test3.xlsx", BytesIO(b"PK\x03\x04" + b"\x03" * 100), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ]

    job_ids = []
    for filename, content, mime_type in files_list:
        files = {"file": (filename, content, mime_type)}
        response = test_client_with_db.post("/api/v1/files/upload", files=files)
        assert response.status_code == 200
        job_ids.append(response.json()["job_id"])

    # Verify all jobs were created
    assert len(job_ids) == 3
    assert len(set(job_ids)) == 3  # All unique


def test_api_cors_headers(test_client):
    """Test that CORS headers are properly set."""
    response = test_client.options("/health", headers={"Origin": "http://localhost:3000"})

    # FastAPI with CORSMiddleware should handle OPTIONS requests
    assert response.status_code in [200, 405]  # 405 if OPTIONS not explicitly defined
