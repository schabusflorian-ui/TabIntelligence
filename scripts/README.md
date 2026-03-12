# Scripts

Utility scripts for development, testing, and operations.

## Database Management

| Script | Description |
|--------|-------------|
| `db_reset.sh` | Drop and recreate all tables via Alembic. Use `--seed` to populate with sample data. **Destroys all data.** |
| `db_seed.py` | Seed development database with sample entities, files, jobs, and API keys. |
| `safe_migrate.py` | Safe Alembic migration with pre-flight checks and rollback. Modes: `--check`, `--upgrade`, `--rollback`, `--backup` |
| `init_e2e_db.py` | Initialize E2E test database with a deterministic API key. |

```bash
# Typical workflow:
./scripts/db_reset.sh --seed       # Fresh start with sample data
python scripts/safe_migrate.py --check   # Verify migration state
python scripts/safe_migrate.py --upgrade # Apply pending migrations
```

## Test Fixture Generators

All scripts create Excel files in `tests/fixtures/`.

| Script | Output | Description |
|--------|--------|-------------|
| `create_test_model.py` | `sample_model.xlsx` | Basic 3-statement model |
| `create_realistic_model.py` | `realistic_model.xlsx` | 8-sheet mid-market LBO (~$250M revenue, 5 periods) |
| `create_saas_startup.py` | `saas_startup.xlsx` | Series B SaaS model (P&L, BS, SaaS Metrics, Headcount) |
| `create_seed_burn.py` | `seed_burn.xlsx` | Pre-revenue monthly burn model (12 months) |
| `create_european_model.py` | `european_model.xlsx` | European mid-market IFRS model |
| `create_edge_cases.py` | `edge_cases.xlsx` | Structural edge cases (combined IS+BS, quarterly, sensitivities) |
| `create_large_model.py` | `large_model.xlsx` | Large corporate model (12 sheets, ~200 items) |
| `create_messy_fixture.py` | `messy_startup.xlsx` | Realistic messy startup with irregular formatting |

```bash
python scripts/create_realistic_model.py
```

## Benchmarking

| Script | Description |
|--------|-------------|
| `benchmark_extraction.py` | Run full 5-stage pipeline benchmark. Reports timing, token usage, cost, and accuracy. Requires `ANTHROPIC_API_KEY`. |
| `regression_tracker.py` | Compare benchmark results against baselines to detect accuracy regressions. |

```bash
# Single file
python scripts/benchmark_extraction.py tests/fixtures/realistic_model.xlsx

# All fixtures, save results
python scripts/benchmark_extraction.py --fixture-dir tests/fixtures/ --save

# Check for regressions
python scripts/regression_tracker.py \
    --results-dir data/benchmark_results/ \
    --baselines-dir data/benchmark_baselines/
```

## Taxonomy Tools

| Script | Description |
|--------|-------------|
| `validate_taxonomy.py` | Validate `data/taxonomy.json` — checks schema, orphans, duplicates, formula syntax |
| `enhance_taxonomy_phase1.py` | Add OCR variants, format examples, industry tags |
| `enhance_taxonomy_phase2.py` | Add cross-item validation, confidence scoring, misspellings |
| `enhance_taxonomy_phase3.py` | Add industry metrics, GAAP/IFRS context, regulatory |
| `enhance_taxonomy_unified.py` | Combined Phases 1-3 applied to categories structure |

```bash
python scripts/validate_taxonomy.py
```

## Development Utilities

| Script | Description |
|--------|-------------|
| `start_worker.sh` | Start Celery worker for async extraction processing |
| `e2e.sh` | Run E2E tests. Modes: (default) mock Claude, `real` for real API, `clean` to tear down |
| `poc_guided_extraction.py` | Proof-of-concept guided extraction with Claude (standalone) |
| `verify_week1.sh` | Week 1 verification suite |

```bash
./scripts/start_worker.sh    # Start Celery worker
./scripts/e2e.sh             # Mock Claude E2E
./scripts/e2e.sh real        # Real Claude E2E
./scripts/e2e.sh clean       # Clean up Docker containers
```
