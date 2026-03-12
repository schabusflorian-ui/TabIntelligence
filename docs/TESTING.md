# Testing Guide

## Running Tests

```bash
# Full suite (excludes e2e and load by default via pyproject.toml)
pytest tests/ -q

# With coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Single file or test
pytest tests/unit/test_crud.py
pytest tests/unit/test_crud.py::test_create_file

# Specific directory
pytest tests/unit/ -q
pytest tests/integration/ -q

# E2E tests (require Docker services running)
pytest tests/e2e/ -q
# Or use the helper script:
./scripts/e2e.sh         # Mock Claude (fast, free)
./scripts/e2e.sh real    # Real Claude API (requires ANTHROPIC_API_KEY)
```

**Coverage threshold:** 80% minimum (enforced in CI via `pyproject.toml`).

## Test Fixtures

### Three Test Clients

The most important thing to understand is that there are **three different test clients**, each for a different purpose:

| Fixture | Auth | Database | Use For |
|---------|------|----------|---------|
| `test_client` | Bypassed | Real PostgreSQL | Tests that need real DB behavior (rarely used) |
| `test_client_with_db` | Bypassed | SQLite in-memory | **Most endpoint tests** — fast, isolated |
| `unauthenticated_client` | NOT bypassed | SQLite in-memory | Testing 401/403 responses |

**Use `test_client_with_db` for almost everything.** It gives you auth bypass + isolated SQLite so tests don't interfere with each other.

```python
def test_list_jobs(test_client_with_db):
    response = test_client_with_db.get("/api/v1/jobs/")
    assert response.status_code == 200

def test_requires_auth(unauthenticated_client):
    response = unauthenticated_client.get("/api/v1/jobs/")
    assert response.status_code == 401
```

### Database Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `test_db` | function | Fresh SQLite in-memory engine + tables, recreated per test |
| `db_session` | function | SQLAlchemy Session from `test_db` |
| `sample_file` | function | Pre-created File record (test_model.xlsx, 50KB) |
| `sample_job` | function | Pre-created ExtractionJob linked to `sample_file` |

```python
def test_crud_operation(db_session, sample_file):
    # db_session already has sample_file in it
    result = crud.get_file(db_session, sample_file.file_id)
    assert result.filename == "test_model.xlsx"
```

### Claude Mock Fixtures

Tests never call the real Claude API. The mock system routes responses based on prompt content:

| Fixture | Description |
|---------|-------------|
| `mock_claude_client` | Smart router — returns parsing/triage/mapping response based on prompt keywords |
| `mock_anthropic` | Patches `get_claude_client` everywhere to use `mock_claude_client` |
| `mock_claude_parsing_response` | Stage 1 canned response |
| `mock_claude_triage_response` | Stage 2 canned response |
| `mock_claude_mapping_response` | Stage 3 canned response |
| `mock_excel_to_structured_repr` | Simulates Excel parsing without openpyxl |
| `mock_structured_to_markdown` | Converts structured data to markdown |

### Auth Fixtures

| Fixture | Description |
|---------|-------------|
| `mock_api_key` | APIKey with `id=None` (avoids FK violations on audit_logs) |

Auth bypass works via FastAPI dependency override:
```python
app.dependency_overrides[get_current_api_key] = lambda: mock_api_key
```

### Excel Fixtures

Located in `tests/fixtures/`:

| File | Description |
|------|-------------|
| `sample_model.xlsx` | Basic 3-statement model |
| `realistic_model.xlsx` | 8-sheet mid-market LBO (~$250M revenue, 5 periods) |
| `messy_startup.xlsx` | Messy startup with irregular formatting |

Generate more with `python scripts/create_*.py`.

## Module-Level Mocks

`tests/conftest.py` mocks these modules **at import time** (before any `src/` imports):

- `boto3` — S3 client (put_object, get_object, head_bucket)
- `botocore.exceptions` — Real exception classes preserved
- `celery` — Mock Celery app with Task base class
- `redis`, `kombu` — Stub mocks

This prevents tests from requiring running S3/Redis/Celery services. **These mocks are global** — you cannot un-mock them in individual tests.

## Writing Tests

### Basic endpoint test

```python
def test_create_entity(test_client_with_db):
    response = test_client_with_db.post(
        "/api/v1/entities/",
        json={"name": "Acme Corp", "industry": "Technology"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Acme Corp"
```

### Testing error paths

```python
def test_invalid_uuid_returns_400(test_client_with_db):
    response = test_client_with_db.get("/api/v1/jobs/not-a-uuid")
    assert response.status_code == 400

def test_missing_job_returns_404(test_client_with_db):
    response = test_client_with_db.get(
        f"/api/v1/jobs/00000000-0000-0000-0000-000000000099"
    )
    assert response.status_code == 404
```

### Testing with database records

```python
def test_job_status(test_client_with_db, db_session, sample_job):
    response = test_client_with_db.get(f"/api/v1/jobs/{sample_job.job_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"
```

### Mocking specific dependencies

```python
from unittest.mock import patch, MagicMock

def test_upload_s3_failure(test_client_with_db):
    with patch("src.api.files.get_s3_client") as mock_s3:
        mock_s3.return_value.upload_file.side_effect = Exception("S3 down")
        response = test_client_with_db.post(
            "/api/v1/files/upload",
            files={"file": ("test.xlsx", b"PK...", "application/vnd.openxmlformats...")},
        )
        assert response.status_code == 500
```

**Important:** Patch where the function is **imported**, not where it's **defined**:
- Upload endpoint imports `get_s3_client` in `src/api/files.py` → patch `src.api.files.get_s3_client`
- Retry endpoint uses it in `src/api/jobs.py` → patch `src.api.jobs.run_extraction_task`

### Testing extraction stages

```python
import pytest

@pytest.mark.asyncio
async def test_parsing_stage(mock_anthropic, mock_excel_to_structured_repr):
    from src.extraction.stages.parsing import ParsingStage
    from src.extraction.base import PipelineContext

    context = PipelineContext(
        file_bytes=b"fake excel bytes",
        file_id="test-file-id",
    )
    stage = ParsingStage()
    result = await stage.execute(context)
    assert "sheets" in result
```

## Test Organization

```
tests/
├── conftest.py           # All fixtures and module-level mocks
├── unit/                 # Fast, isolated tests (~80 files)
│   ├── test_crud.py          # Database CRUD operations
│   ├── test_orchestrator.py  # Pipeline orchestration
│   ├── test_e2e_pipeline.py  # All 5 stages end-to-end (mocked Claude)
│   ├── test_entities.py      # Entity API endpoints
│   ├── test_corrections.py   # Correction endpoints
│   └── ...
├── integration/          # Tests that exercise multiple layers
│   ├── test_api_endpoints.py
│   ├── test_api_security.py
│   └── test_extraction_e2e.py
├── e2e/                  # Full system tests (require Docker)
│   ├── test_real_claude.py   # Tests with real Claude API
│   └── test_local_e2e.py
├── load/                 # Stress tests
│   └── test_concurrent_uploads.py
└── fixtures/             # Test data (Excel files, expected JSON)
```

## Common Issues

**"Cannot find table" errors:** You're using `test_client` (real PostgreSQL) but the test database doesn't have tables. Use `test_client_with_db` instead.

**"FK violation on audit_logs":** The `mock_api_key` fixture sets `id=None` to avoid this. If you create a real APIKey in a test, ensure the `audit_logs` table exists.

**Async test failures on Python 3.11:** Event loop attachment issues with `pytest-asyncio`. Use `@pytest.mark.asyncio` and ensure `asyncio_mode = "auto"` in `pyproject.toml`.

**Mock patch targets:** After the router consolidation, patches must target the new locations:
- `src.api.files.get_s3_client` (not `src.api.main.get_s3_client`)
- `src.api.files.run_extraction_task` (for upload)
- `src.api.jobs.run_extraction_task` (for retry)
