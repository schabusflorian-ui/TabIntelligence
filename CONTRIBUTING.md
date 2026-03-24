# Contributing to DebtFund

## Development Setup

```bash
# Clone & install
git clone <repository-url> && cd DebtFund
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Start infrastructure
docker-compose up -d    # PostgreSQL, Redis, MinIO
alembic upgrade head    # Apply migrations

# Install pre-commit hooks
pre-commit install
pre-commit install --hook-type pre-push
```

## Code Quality

### Linting & Formatting

We use [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting (configured in `pyproject.toml`):

```bash
ruff format src tests          # Format
ruff check src tests           # Lint
ruff check --fix src tests     # Auto-fix
```

Pre-commit hooks run ruff automatically on every commit. A pytest smoke test runs on `git push`.

### Testing

```bash
# Fast unit tests (excludes slow retry/backoff tests)
pytest tests/unit/ -m "not slow"      # ~10s

# Full unit suite
pytest tests/unit/                     # ~35s

# With coverage
pytest tests/unit/ --cov=src --cov-report=html

# Specific file
pytest tests/unit/test_orchestrator.py -v

# E2E tests (requires ANTHROPIC_API_KEY)
pytest tests/e2e/ -v
```

**Test markers:**
- `@pytest.mark.slow` — Tests >2s (retry/backoff with real sleeps). Excluded from pre-push smoke.
- `@pytest.mark.integration` — Tests requiring external services (DB, Redis, S3).

**Test fixtures** (in `tests/conftest.py`):
- `test_client` — Auth bypassed, no DB override (hits real PostgreSQL)
- `test_client_with_db` — Auth bypassed + SQLite in-memory
- `unauthenticated_client` — No auth bypass + SQLite in-memory (for 401 tests)

### Coverage Target

- **Overall**: 85%+
- **Critical paths**: Extraction stages, validation logic, lineage emission

## Project Structure

```
src/
├── api/               # FastAPI routers (8 routers, 50 endpoints)
│   ├── main.py        # App factory, upload endpoint, health check
│   ├── jobs.py        # Job CRUD, export, retry, lineage
│   ├── entities.py    # Entity CRUD
│   ├── corrections.py # Correction workflow, review queue
│   ├── analytics.py   # Cross-entity analytics, facts query
│   ├── health.py      # Liveness, readiness, DB health, metrics
│   ├── dlq.py         # Dead letter queue admin
│   └── metrics.py     # Prometheus metrics
├── auth/              # API key authentication
├── core/              # Config, logging, exceptions
├── db/                # SQLAlchemy models, CRUD, session, migrations
├── extraction/        # 5-stage pipeline
│   ├── stages/        # Parsing, Triage, Mapping, Validation, Enhanced Mapping
│   ├── prompts/       # Claude prompt templates
│   ├── orchestrator.py
│   └── taxonomy_loader.py
├── jobs/              # Celery tasks + DLQ
├── lineage/           # Lineage tracker + cross-extraction differ
├── storage/           # S3/MinIO file storage
└── validation/        # Accounting, completeness, quality, lifecycle
```

## Conventions

### Commit Messages

Use concise, descriptive messages focused on "why" not "what":

```
Fix stage executor retry logic for rate-limited Claude calls

Add cross-entity comparison analytics endpoint

Update taxonomy to v3.0.0 with SaaS metrics and startup aliases
```

### Branch Naming

```
feature/short-description
fix/issue-description
```

### Database Changes

Always create an Alembic migration for schema changes:

```bash
alembic revision --autogenerate -m "Add quality_grade to extraction_jobs"
alembic upgrade head
alembic downgrade -1    # Test reversibility
```

Follow SQLAlchemy 2.0 patterns (`Mapped`/`mapped_column`), not legacy `Column`.

### Adding API Endpoints

1. Add Pydantic response models to `src/api/schemas.py`
2. Add CRUD functions to `src/db/crud.py`
3. Add endpoint to the appropriate router in `src/api/`
4. All endpoints require auth: `_api_key=Depends(get_current_api_key)`
5. Add tests in `tests/unit/` or `tests/integration/`

### Extraction Pipeline

The 5-stage pipeline follows a registry pattern (`src/extraction/stages/`):
1. **Parsing** — Excel to structured repr + markdown (streaming Claude API)
2. **Triage** — Sheet classification into tiers 1-4
3. **Mapping** — Line items to canonical taxonomy (with pattern shortcircuit)
4. **Validation** — Accounting rules, cross-item checks, lifecycle detection
5. **Enhanced Mapping** — Re-map low-confidence items using validation feedback

Each stage extends `ExtractionStage` from `src/extraction/base.py`. The orchestrator runs them sequentially via `StageExecutor`.

## Documentation

Developer documentation lives in `docs/`:

| Directory | Audience | Contents |
|-----------|----------|----------|
| `docs/demo/` | Users & stakeholders | Product overview, feature catalog, roadmap, demo script, architecture & data flow diagrams |
| `docs/adr/` | Engineers | Architecture Decision Records (auth, DB consolidation, S3, lineage, retry) |
| `docs/API.md` | Engineers | API endpoint reference |
| `docs/DEVELOPER_GUIDE.md` | Engineers | Architecture overview and development workflow |
| `docs/TESTING.md` | Engineers | Test strategy, fixtures, and execution guide |

When adding significant features, update the relevant documentation — especially `docs/demo/feature-catalog.md` for user-visible features and `CHANGELOG.md` for all changes.

## Definition of Done

- [ ] Code follows existing patterns (read neighboring code first)
- [ ] Unit tests written and passing
- [ ] Full test suite green (`pytest tests/unit/`)
- [ ] No ruff lint/format errors
- [ ] Migration reversible (if schema change)
- [ ] No secrets committed (.env, API keys)
