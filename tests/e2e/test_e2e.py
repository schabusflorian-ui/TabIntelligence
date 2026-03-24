"""
End-to-end tests against the full Docker stack.

Prerequisites:
    docker compose -f docker-compose.yml -f docker-compose.e2e.yml up --build -d
    # Wait for services to be healthy, then:
    E2E_BASE_URL=http://localhost:8100 \
    E2E_API_KEY=emi_e2e_test_key_for_integration_testing \
        python -m pytest tests/e2e/ -v

Can also run standalone:
    python tests/e2e/test_e2e.py
"""

import os
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8100")
API_KEY = os.getenv("E2E_API_KEY", "emi_e2e_test_key_for_integration_testing")
FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_model.xlsx"
POLL_INTERVAL = 2  # seconds
POLL_TIMEOUT = 120  # seconds


def _headers():
    return {"Authorization": f"Bearer {API_KEY}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_health():
    """API health check - database and S3 must be up."""
    resp = requests.get(f"{BASE_URL}/health", timeout=10)
    assert resp.status_code == 200, f"Health check failed: {resp.text}"

    data = resp.json()
    assert data["status"] == "healthy", f"Unhealthy: {data}"
    assert data["components"]["database"]["status"] == "up"
    assert data["components"]["s3"]["status"] == "up"


def test_upload_and_extract():
    """Full E2E: upload Excel file -> poll job -> validate completed result."""
    assert FIXTURE_PATH.exists(), f"Test fixture missing: {FIXTURE_PATH}"

    # 1. Upload
    with open(FIXTURE_PATH, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/api/v1/files/upload",
            headers=_headers(),
            files={
                "file": (
                    "sample_model.xlsx",
                    f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            timeout=30,
        )

    assert resp.status_code == 200, f"Upload failed ({resp.status_code}): {resp.text}"
    upload = resp.json()
    assert "job_id" in upload, f"No job_id in response: {upload}"
    assert "file_id" in upload

    job_id = upload["job_id"]
    print(f"\n  Uploaded: file_id={upload['file_id']}, job_id={job_id}")

    # 2. Poll for completion
    start = time.time()
    job_data = None

    while time.time() - start < POLL_TIMEOUT:
        resp = requests.get(
            f"{BASE_URL}/api/v1/jobs/{job_id}",
            headers=_headers(),
            timeout=10,
        )
        assert resp.status_code == 200, f"Job poll failed: {resp.text}"
        job_data = resp.json()
        status = job_data["status"]

        print(
            f"  Poll: status={status}, "
            f"stage={job_data.get('current_stage')}, "
            f"progress={job_data.get('progress_percent')}%"
        )

        if status in ("completed", "failed"):
            break

        time.sleep(POLL_INTERVAL)

    # 3. Validate
    assert job_data is not None
    assert job_data["status"] == "completed", (
        f"Job did not complete within {POLL_TIMEOUT}s. "
        f"Status: {job_data['status']}, error: {job_data.get('error')}"
    )

    result = job_data.get("result")
    assert result is not None, "Completed job has no result"

    # Structural checks
    assert "sheets" in result
    assert "line_items" in result
    assert "tokens_used" in result
    assert "cost_usd" in result
    assert len(result["sheets"]) >= 1
    assert result["tokens_used"] > 0

    print(
        f"\n  Result: {len(result['sheets'])} sheets, "
        f"{len(result['line_items'])} line items, "
        f"{result['tokens_used']} tokens, ${result['cost_usd']:.4f}"
    )


def test_deduplication():
    """Upload same file twice — second should return duplicate."""
    assert FIXTURE_PATH.exists()

    file_bytes = FIXTURE_PATH.read_bytes()

    # First upload (may already exist from test_upload_and_extract)
    requests.post(
        f"{BASE_URL}/api/v1/files/upload",
        headers=_headers(),
        files={
            "file": (
                "sample_model.xlsx",
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        timeout=30,
    )

    # Second upload — should detect duplicate
    resp = requests.post(
        f"{BASE_URL}/api/v1/files/upload",
        headers=_headers(),
        files={
            "file": (
                "sample_model.xlsx",
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        timeout=30,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "duplicate", f"Expected duplicate, got: {data}"
    print(f"\n  Dedup: {data['message']}")


def test_invalid_file_rejected():
    """Non-Excel file should be rejected with 400."""
    resp = requests.post(
        f"{BASE_URL}/api/v1/files/upload",
        headers=_headers(),
        files={"file": ("not_excel.txt", b"this is not excel", "text/plain")},
        timeout=10,
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert "Excel" in resp.text


def test_invalid_job_id_returns_404():
    """Non-existent job ID should return 404."""
    resp = requests.get(
        f"{BASE_URL}/api/v1/jobs/00000000-0000-0000-0000-000000000000",
        headers=_headers(),
        timeout=10,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        ("Health check", test_health),
        ("Upload and extract", test_upload_and_extract),
        ("Deduplication", test_deduplication),
        ("Invalid file rejected", test_invalid_file_rejected),
        ("Invalid job ID returns 404", test_invalid_job_id_returns_404),
    ]

    print("=" * 60)
    print("TabIntelligence E2E Test Suite")
    print(f"Target: {BASE_URL}")
    print("=" * 60)

    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
    exit(0 if passed == len(tests) else 1)
