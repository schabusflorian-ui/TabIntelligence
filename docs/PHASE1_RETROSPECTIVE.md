# Phase 1 Retrospective

## Overview

Phase 1 ran from project inception through late February 2026, delivering a working MVP: a 5-stage extraction pipeline, 350+ item taxonomy, entity management, corrections workflow, structured financial statement output, and comprehensive test coverage. The system can upload Excel financial models, extract data using Claude, map line items to a canonical taxonomy, validate against accounting rules, and present structured results via a REST API and web dashboard.

**Final Phase 1 metrics**: 428 tests passing, 74% coverage, 10 Alembic migrations, 21 SQLAlchemy models, 5 ADRs.

---

## What Worked

### Registry-Based Stage Architecture
The 5-stage extraction pipeline (Parsing, Triage, Mapping, Validation, Enhanced Mapping) uses a registry pattern where each stage is independently testable, retryable, and can evolve without touching others. This proved critical when tuning individual stages for accuracy — changes to mapping logic never broke parsing or validation.

### Lineage Tracking
Every extraction produces a complete audit trail via `LineageEvent` records. Each stage writes what it did, what changed, and why. This made debugging extraction failures straightforward and gave confidence to refactor stages knowing we could trace any regression to its source.

### Fact Table Design
Decomposing extraction results into `ExtractionFact` rows (one per canonical_name/period/value) rather than relying solely on the JSON blob in `ExtractionJob.result` was a pivotal decision. It enabled SQL-based analytics, cross-entity comparison, validation queries, and the later derivation engine — none of which would have been practical against nested JSON.

### Taxonomy Governance Foundation
The `Taxonomy` model with `canonical_name`, `aliases`, `parent_canonical`, and `validation_rules` proved extensible enough to support everything Phase 2 demanded: learned aliases, auto-promotion, gap detection, versioning, and diff. The governance workflow (suggest → review → accept/reject → changelog) works end-to-end.

### Testing Architecture
The three-client pattern (`test_client`, `test_client_with_db`, `unauthenticated_client`) with module-level mocks for external services (boto3, celery, redis) gave us fast, isolated tests that caught real bugs without requiring infrastructure. The Claude mock router that returns stage-specific responses based on prompt keywords was particularly effective.

---

## What Didn't Work

### Async Test Fragility
Three async tests consistently fail on Python 3.11 due to event loop attachment issues (`asyncpg` sessions cannot be bound to a test event loop that differs from the one running the application). We marked these as `xfail` rather than investing in a complex async test harness. The sync path (used by all API endpoints) is fully tested.

### Taxonomy Mapping Accuracy Gaps
Phase 1's taxonomy had systematic problems: alias conflicts (same alias pointing to multiple canonicals), missing UK/IFRS terminology, and no priority-aware disambiguation. Benchmark accuracy on diverse fixtures ranged from 55% to 100%. This was the single biggest gap driving Phase 2's taxonomy overhaul.

### No Cell-Level Persistence
The extraction pipeline produces cell references in provenance metadata (`provenance.source_cells`), but Phase 1 never persisted these in queryable form. Corrections couldn't trace back to source cells, and there was no way to build a "click cell → see mapping" experience. This required a new `cell_mappings` table and pipeline changes in Phase 2.

### JSON Blob Coupling
Early code relied heavily on `ExtractionJob.result` (a large JSON blob) for both reading and mutating extraction results. Corrections had to deep-copy the blob, find items by label string matching, mutate, then reassign. This was fragile and slow. The fact table partially solved this, but the correction workflow still operates on the JSON blob for backward compatibility.

---

## Architectural Decisions (ADRs 001-005)

| ADR | Decision | Rationale |
|-----|----------|-----------|
| **001** | API authentication + CORS + rate limiting + file size limits | Production security — endpoints were completely exposed |
| **002** | Consolidate `src/database/` into `src/db/` | Two DB modules with conflicting pool configs; single canonical location |
| **003** | Enable SSL verification for S3 connections | `verify=False` was a critical security vulnerability |
| **004** | Transactional lineage persistence | Async/sync mismatch caused partial lineage data on errors |
| **005** | Standardized retry logic across all extraction stages | Only Stage 1 had retries; transient Claude failures wasted cost in later stages |

All five ADRs addressed foundational issues that would have blocked production deployment. The pattern of documenting decisions as ADRs (rather than inline comments) proved valuable for onboarding and future reference.

---

## Known Technical Debt

### Addressed in Phase 2
- **Taxonomy alias conflicts** — resolved in taxonomy v3.4.0-3.5.0 with 40+ alias fixes
- **`_normalize_for_comparison()` bug** in crud.py — returned method reference instead of string; fixed with rapidfuzz integration (B1.1)
- **No fuzzy matching** — exact-match only; replaced with `rapidfuzz` token_sort_ratio scoring

### Remaining
- **Historical time-series validation** (`src/validation/accounting_validator.py:138`) — TODO for when multi-period historical data is available; currently validates single-period only
- **JSON blob correction workflow** — `apply_correction_to_result()` still deep-copies and mutates `ExtractionJob.result` JSON; should eventually operate on `ExtractionFact` rows directly
- **Async session support** — `get_db_async()` exists but is only used by background tasks; the main API is sync-only via `get_db()`

---

## Key Metrics at Phase 1 Close

| Metric | Value |
|--------|-------|
| Test count | 428 passing, 3 xfail (async), 6 skipped |
| Coverage | 74% |
| Models | 21 SQLAlchemy (2.0 syntax) |
| Migrations | 10 Alembic |
| Taxonomy items | 312 across 5 categories |
| API endpoints | ~25 |
| Extraction stages | 5 (parsing, triage, mapping, validation, enhanced mapping) |
| ADRs | 5 |

---

## Lessons Learned

1. **Taxonomy is the product.** The quality of extraction output is bounded by taxonomy coverage and alias accuracy. Investing in taxonomy governance infrastructure pays for itself immediately.

2. **Benchmark early.** We didn't have rigorous accuracy benchmarks until Phase 2. If we'd measured per-fixture accuracy from the start, we'd have caught alias conflicts and coverage gaps weeks earlier.

3. **Sync-first was the right call.** FastAPI supports async, but our database access patterns (short-lived queries, no streaming) don't benefit from it. The sync path is simpler, easier to test, and has no event loop issues.

4. **Module-level mocks before imports.** Mocking boto3/celery/redis at the module level in `conftest.py` (before any application imports) prevents import-time side effects and makes the test suite runnable without infrastructure.

5. **ADRs > comments.** Writing 5 ADRs took less time than the debugging sessions that preceded them. They serve as the authoritative record of "why" for decisions that would otherwise be forgotten.
