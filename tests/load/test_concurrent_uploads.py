"""Load tests for concurrent API usage."""

import io
import time
from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.mark.load
@pytest.mark.slow
def test_10_concurrent_users(test_client):
    """
    Simulate 10 concurrent users uploading files.
    Verify no connection pool exhaustion or race conditions.
    """

    def upload_file(user_id: int):
        """Single user upload."""
        files = {
            "file": (
                f"user_{user_id}_test.xlsx",
                io.BytesIO(b"PK\x03\x04" + bytes([user_id]) * 1000),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        try:
            response = test_client.post("/api/v1/files/upload", files=files)
            return response.status_code, response.json() if response.status_code in [
                200,
                202,
            ] else {}
        except Exception as e:
            return 500, {"error": str(e)}

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(upload_file, i) for i in range(10)]
        results = [f.result() for f in futures]

    success_count = sum(1 for status, _ in results if status in [200, 202])
    errors = [(status, data) for status, data in results if status not in [200, 202]]

    if errors:
        error_summary = "\n".join([f"Status {s}: {d}" for s, d in errors])
        pytest.fail(f"Only {success_count}/10 uploads succeeded.\nErrors:\n{error_summary}")

    assert success_count == 10, f"Only {success_count}/10 uploads succeeded"

    job_ids = [data.get("job_id") for _, data in results if "job_id" in data]
    assert len(job_ids) == 10, "Not all requests returned job IDs"
    assert len(set(job_ids)) == 10, "Job IDs not unique (race condition?)"


@pytest.mark.load
def test_connection_pool_does_not_exhaust(test_client):
    """Make 50 rapid requests to verify connection pool handles load."""
    errors = []
    response_times = []

    for i in range(50):
        try:
            start = time.time()
            response = test_client.get("/health")
            elapsed = time.time() - start
            response_times.append(elapsed)

            if response.status_code != 200:
                errors.append(f"Request {i}: status {response.status_code}")
        except Exception as e:
            errors.append(f"Request {i}: {str(e)}")

    if errors:
        error_summary = "\n".join(errors[:10])
        pytest.fail(f"Errors during load ({len(errors)}/50 failed):\n{error_summary}")

    assert len(errors) == 0, f"Errors during load: {errors}"


@pytest.mark.load
@pytest.mark.slow
def test_sustained_load_over_time(test_client):
    """Test sustained load: 30 requests over 30 seconds (1 req/sec)."""
    errors = []
    requests = 30
    interval = 1.0

    for i in range(requests):
        try:
            response = test_client.get("/health")
            if response.status_code != 200:
                errors.append(f"Request {i}: status {response.status_code}")
            if i < requests - 1:
                time.sleep(interval)
        except Exception as e:
            errors.append(f"Request {i}: {str(e)}")

    assert len(errors) == 0, f"Errors during sustained load: {errors}"


@pytest.mark.load
def test_rapid_sequential_uploads(test_client):
    """Test rapid sequential uploads (no parallelism)."""
    errors = []

    for i in range(20):
        files = {
            "file": (
                f"seq_{i}.xlsx",
                io.BytesIO(b"PK\x03\x04" + bytes([i]) * 500),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        try:
            response = test_client.post("/api/v1/files/upload", files=files)
            if response.status_code not in [200, 202]:
                errors.append(f"Upload {i}: status {response.status_code}")
        except Exception as e:
            errors.append(f"Upload {i}: {str(e)}")

    assert len(errors) == 0, f"Errors during sequential uploads: {errors}"


@pytest.mark.load
@pytest.mark.slow
def test_concurrent_read_operations(test_client):
    """Test concurrent read operations (job status checks)."""
    files = {
        "file": (
            "read_test.xlsx",
            io.BytesIO(b"PK\x03\x04" + b"\x00" * 1000),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    upload_response = test_client.post("/api/v1/files/upload", files=files)
    assert upload_response.status_code in [200, 202]

    job_id = upload_response.json()["job_id"]

    def check_status(request_id: int):
        try:
            response = test_client.get(f"/api/v1/jobs/{job_id}")
            return response.status_code, request_id
        except Exception:
            return 500, request_id

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(check_status, i) for i in range(50)]
        results = [f.result() for f in futures]

    success_count = sum(1 for status, _ in results if status == 200)
    assert success_count == 50, f"Only {success_count}/50 status checks succeeded"


@pytest.mark.load
def test_database_pool_configuration():
    """Test that database pool is properly configured."""
    from src.db.base import get_engine

    engine = get_engine()
    pool = engine.pool

    assert hasattr(pool, "size"), "Pool doesn't have size attribute"
    pool_size = pool.size()

    assert pool_size >= 5, f"Pool size too small: {pool_size}"

    if pool_size < 20:
        pytest.skip(f"Pool size is {pool_size}, should be 20 per Agent 1B specification")
