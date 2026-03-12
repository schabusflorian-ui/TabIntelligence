# DebtFund Developer Guide

A practical guide for working in the DebtFund codebase. Read this before making changes.

## Project Structure

```
src/
├── api/                  # FastAPI endpoints (routers, schemas, middleware)
│   ├── main.py           # App creation, middleware, router registration
│   ├── files.py          # File upload (POST /api/v1/files/upload)
│   ├── jobs.py           # Job management (list, status, export, retry, review, lineage, diff)
│   ├── entities.py       # Entity CRUD
│   ├── corrections.py    # User corrections, pattern management, learned aliases
│   ├── health.py         # Kubernetes probes (liveness, readiness, db health)
│   ├── dlq.py            # Dead-letter queue admin
│   ├── taxonomy.py       # Taxonomy browsing and search
│   ├── analytics.py      # Portfolio analytics, entity financials, trends
│   ├── schemas.py        # All Pydantic request/response models
│   ├── metrics.py        # Prometheus metrics middleware
│   ├── rate_limit.py     # slowapi rate limiter config
│   └── middleware.py      # Request ID middleware
├── auth/                 # API key auth
│   ├── dependencies.py   # FastAPI dependencies: get_current_api_key, require_entity_scope
│   └── models.py         # APIKey SQLAlchemy model
├── core/                 # Shared infrastructure
│   ├── config.py         # Pydantic Settings (env vars → typed config)
│   ├── logging.py        # Structured logging setup
│   └── exceptions.py     # Exception hierarchy (DatabaseError, FileStorageError, etc.)
├── db/                   # Database layer (single canonical location)
│   ├── session.py        # Session factories (see "Database Sessions" below)
│   ├── models.py         # 8 SQLAlchemy models + ExtractionFact, LearnedAlias, DLQEntry
│   ├── crud.py           # All database operations (~2100 lines)
│   ├── base.py           # Base model, create_tables()
│   └── query_helpers.py  # Reusable query builders
├── extraction/           # 5-stage AI extraction pipeline
│   ├── orchestrator.py   # Pipeline runner (extract() entry point)
│   ├── base.py           # ExtractionStage ABC, PipelineContext
│   ├── registry.py       # Stage registry pattern
│   ├── stage_executor.py # Stage execution with retry/timeout
│   ├── taxonomy_loader.py # Loads data/taxonomy.json, alias lookup
│   ├── period_parser.py  # Financial period detection and normalization
│   ├── section_detector.py # Excel sheet section detection
│   ├── stages/           # Individual stage implementations
│   │   ├── parsing.py        # Stage 1: Excel → structured representation
│   │   ├── triage.py         # Stage 2: Sheet classification
│   │   ├── mapping.py        # Stage 3: Label → canonical name mapping
│   │   ├── validation.py     # Stage 4: Accounting validation rules
│   │   └── enhanced_mapping.py # Stage 5: Re-map low-confidence items
│   └── prompts/templates/ # Claude prompt templates (v1)
├── validation/           # Financial data quality engines
│   ├── accounting_validator.py # Cross-item accounting rules
│   ├── completeness_scorer.py  # Statement type detection (IS, BS, CF)
│   ├── quality_scorer.py       # Composite quality grade (A–F)
│   ├── lifecycle_detector.py   # Entity lifecycle detection
│   └── time_series_validator.py # Period-over-period consistency
├── jobs/                 # Background processing
│   ├── celery_app.py     # Celery config (Redis broker)
│   ├── tasks.py          # run_extraction_task (downloads from S3, runs pipeline)
│   └── dlq.py            # Dead-letter queue routing
├── lineage/              # Provenance tracking
│   ├── tracker.py        # LineageTracker (emit events per stage)
│   └── differ.py         # ExtractionDiffer (compare two job results)
└── storage/
    └── s3.py             # S3/MinIO client (upload, download, presign)
```

## Quick Start

```bash
# 1. Clone and install
git clone <repo> && cd DebtFund
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Start infrastructure
docker compose up -d   # PostgreSQL, Redis, MinIO

# 3. Run migrations
alembic upgrade head

# 4. Seed development data (optional)
python scripts/db_seed.py

# 5. Run the API server
uvicorn src.api.main:app --reload

# 6. Run tests
pytest tests/ --ignore=tests/e2e --ignore=tests/load -q

# 7. Start Celery worker (for async extraction)
./scripts/start_worker.sh
```

Required env vars: `ANTHROPIC_API_KEY` (for extraction). Everything else has dev defaults.

## Database Sessions

`src/db/session.py` provides 4 session helpers. Using the wrong one causes subtle bugs.

| Helper | Use When | Wraps Exceptions? |
|--------|----------|-------------------|
| `get_db()` | FastAPI sync endpoints (`Depends(get_db)`) | **NO** — intentional, see below |
| `get_db_sync()` | Non-FastAPI sync code (scripts, Celery tasks) | Yes → `DatabaseError` |
| `get_db_context()` | Alias for `get_db_sync()` (backward compat) | Yes → `DatabaseError` |
| `get_db_async()` | Async code | Yes → `DatabaseError` |

**Why `get_db()` doesn't wrap exceptions:** FastAPI/Starlette re-throws `HTTPException` back into dependency generator cleanup via `.throw()`. If `get_db()` caught all exceptions, it would wrap legitimate HTTP errors in `DatabaseError`, breaking error responses. This is the most common pitfall for new contributors.

```python
# In a FastAPI endpoint — use get_db():
@router.get("/items")
def list_items(db: Session = Depends(get_db)):
    return crud.list_items(db)

# In a script or Celery task — use get_db_sync():
with get_db_sync() as db:
    crud.do_something(db)
```

## Extraction Pipeline

The pipeline runs 5 stages sequentially via `orchestrator.extract()`:

```
Excel File → [Stage 1: Parsing] → [Stage 2: Triage] → [Stage 3: Mapping]
           → [Stage 4: Validation] → [Stage 5: Enhanced Mapping] → ExtractionResult
```

**How stages work:**

1. Each stage extends `ExtractionStage` (in `base.py`) with an `async execute(context)` method
2. Stages register themselves in `StageRegistry` (in `registry.py`)
3. `PipelineContext` carries shared state between stages — call `context.get_result("parsing")` to read a prior stage's output
4. The orchestrator handles checkpointing: if a job fails at Stage 3, retry resumes from Stage 3 using saved results

**Stage responsibilities:**

| Stage | File | What It Does |
|-------|------|-------------|
| 1. Parsing | `stages/parsing.py` | Excel → structured representation (sheets, rows, columns) |
| 2. Triage | `stages/triage.py` | Classify sheets (IS, BS, CF, skip) |
| 3. Mapping | `stages/mapping.py` | Map labels → canonical taxonomy names (Claude + pattern shortcircuit) |
| 4. Validation | `stages/validation.py` | Apply accounting rules, cross-item checks |
| 5. Enhanced Mapping | `stages/enhanced_mapping.py` | Re-map low-confidence items with validation feedback |

**Adding a new stage:**
1. Create `src/extraction/stages/my_stage.py` extending `ExtractionStage`
2. Set `stage_number` to define ordering
3. Register it in `src/extraction/stages/__init__.py`
4. Update `STAGE_ORDER` in `src/api/jobs.py`

## Key Patterns

### Authentication

Every mutation endpoint requires an API key via `Depends(get_current_api_key)`. Entity-scoped endpoints use `Depends(require_entity_scope)` which additionally checks the key's `entity_id` matches the target.

```python
# Any authenticated user:
@router.get("/jobs/")
def list_jobs(api_key: APIKey = Depends(get_current_api_key)):
    ...

# Must have access to the specific entity:
@router.get("/entities/{entity_id}")
def get_entity(entity_id: str, api_key: APIKey = Depends(require_entity_scope)):
    ...
```

In tests, bypass auth with: `app.dependency_overrides[get_current_api_key] = lambda: mock_api_key`

### Lineage Tracking

Every data transformation emits a lineage event via `LineageTracker`. This is not optional — lineage is fundamental to the product's value proposition.

```python
tracker = LineageTracker(job_id=job_id)
lineage_id = tracker.emit(
    stage="mapping",
    event_type="label_mapped",
    input_lineage_id=parent_id,
    metadata={"original": "Rev", "canonical": "revenue"}
)
tracker.save_to_db()
```

### Entity Patterns (Learning Loop)

When a label is mapped (by Claude or user correction), an `EntityPattern` is created linking `(entity_id, original_label) → canonical_name`. On future extractions for the same entity, Stage 3 checks patterns first and shortcircuits the Claude call if a high-confidence match exists.

### Content Hash Deduplication

File uploads compute a SHA-256 hash. If the same bytes are uploaded again, the existing file record and job_id are returned — no duplicate extraction runs.

## Configuration

All config lives in `src/core/config.py` via Pydantic Settings. Override with env vars:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://emi:emi_dev@localhost:5432/emi` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker |
| `ANTHROPIC_API_KEY` | (required) | Claude API key |
| `S3_ENDPOINT` | `http://localhost:9000` | MinIO/S3 endpoint |
| `S3_BUCKET` | `debtfund-files` | Storage bucket |
| `CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Model for extraction |
| `MAX_FILE_SIZE_MB` | `50` | Upload limit |
| `QUALITY_GATE_MIN_GRADE` | `F` | Minimum grade to pass (A/B/C/D/F) |

## Common Tasks

### Add a new API endpoint

1. Choose the appropriate router file in `src/api/`
2. Add a Pydantic schema to `src/api/schemas.py` if needed
3. Add CRUD operations to `src/db/crud.py` if needed
4. Write the endpoint with auth, rate limiting, UUID validation, and error handling
5. Write tests using `test_client_with_db` fixture

### Add a taxonomy item

1. Edit `data/taxonomy.json` — add to the appropriate category
2. Include: `canonical_name`, `display_name`, `aliases`, `definition`, `typical_sign`, `parent_canonical`
3. Run `python scripts/validate_taxonomy.py` to check validity
4. If adding validation rules, update `src/validation/accounting_validator.py`

### Run a benchmark

```bash
# Single file
python scripts/benchmark_extraction.py tests/fixtures/realistic_model.xlsx

# All fixtures, save results
python scripts/benchmark_extraction.py --fixture-dir tests/fixtures/ --save
```

### Reset the database

```bash
./scripts/db_reset.sh          # Drop and recreate
./scripts/db_reset.sh --seed   # Drop, recreate, seed sample data
```

### Write a new migration

```bash
alembic revision --autogenerate -m "add_my_column"
# Review the generated file in alembic/versions/
alembic upgrade head
```
