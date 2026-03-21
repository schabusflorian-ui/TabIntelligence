# Phase 1 Retrospective
**Completed: March 19, 2026**

## Executive Summary

Phase 1 delivered a working MVP for financial data extraction from Excel files. The system processes uploads through a 5-stage AI-powered pipeline, maps line items to a 312-item canonical taxonomy, validates results against accounting rules, and presents structured financial statements in a web UI.

**Final metrics:**
- 2,555 tests passing (6 skipped, 3 xfail)
- 87.77% code coverage (target: 80%)
- 50 API endpoints across 8 routers
- 312 taxonomy items across 6 categories with 1,358 aliases
- 15 database tables, 18 Alembic migrations
- 12 frontend pages, 16 reusable JS components

---

## What Worked Well

### Registry Pattern for Extraction Pipeline
The 5-stage pipeline (parsing → triage → mapping → validation → enhanced_mapping) uses a self-registering stage pattern. Adding or modifying stages requires no changes to the orchestrator. The `StageExecutor` handles retry, timeout, and checkpoints consistently across all stages.

### Lineage & Provenance Tracking
Every extracted value carries full provenance: source cells, parsing metadata, mapping method + confidence, validation results, and enhanced mapping reasoning. `LineageEvent` records enable stage-by-stage debugging. This foundation is critical for Phase 2 cell-level tracking.

### Fact Table Design
The `ExtractionFact` denormalized table (one row per job × canonical_name × period) enables efficient analytics queries without parsing nested JSON. Portfolio comparison, cross-entity analysis, and trend charts all query this table directly.

### Taxonomy Governance (Late Phase 1)
`TaxonomySuggestion`, `TaxonomyChangelog`, `LearnedAlias`, and deprecation support were added in Phases 2-3 of the taxonomy work. These provide the governance scaffolding needed for Phase 2's taxonomy overhaul.

### Structured Statement Hierarchy
Replacing the flat line-item listing with a hierarchical statement view (parent/child canonical names, subtotal computation, reconciliation checks) significantly improved the usefulness of extraction results.

### Test Infrastructure
Module-level mocks in `conftest.py` (boto3, celery, redis, kombu, botocore) allow the full test suite to run without external services. Three test client variants (auth-bypassed, SQLite in-memory, unauthenticated) cover different scenarios cleanly.

---

## What Didn't Work Well

### Taxonomy Mapping Accuracy
The mapping stage relies heavily on Claude for non-trivial matches. When the label is semantically close to an alias but not an exact match, the system sends it to the LLM — expensive and sometimes inaccurate. The `_is_close_match()` function in `crud.py` uses exact normalized string comparison only, with a bug where `_normalize_for_comparison()` returns a method reference instead of a string (line 3417).

### No Cell-Level Persistence
The parsing stage extracts cell references, formulas, and formatting — but `persist_extraction_facts()` discards all of this, keeping only `sheet_name` and `row_index`. This makes it impossible to trace a canonical value back to its exact source cell, or to build a spreadsheet overlay view.

### Async Test Fragility
Three async tests fail intermittently on Python 3.11 due to event loop attachment issues. These are now marked `xfail` but represent genuine async session management complexity that needs resolution if the system moves to fully async operations.

### Taxonomy Coverage for Debt Fund
The taxonomy has strong coverage for standard financial statements (IS/BS/CF) but weak coverage for debt-fund-specific instruments. The `debt_schedule` category has only 29 items and the `project_finance` category has 13 — insufficient for real debt fund analysis (CLO terminology, facility types, credit ratios).

### No Rigorous Accuracy Benchmarking
The benchmark scripts track accuracy as correct/total but don't compute precision, recall, or F1. No value extraction accuracy measurement exists. No per-stage error attribution. No automated regression detection in CI.

---

## Key Architectural Decisions (ADRs)

| ADR | Decision | Rationale |
|-----|----------|-----------|
| 001 | API key authentication (not OAuth) | Simple, appropriate for B2B API; API keys with hashing and expiration |
| 002 | `src/db/` as single canonical DB location | Removed `src/database/` to eliminate confusion and duplicate code |
| 003 | SSL verification bypass for S3/MinIO dev | MinIO self-signed certs; disabled via `verify=False` in dev only |
| 004 | Lineage events in same transaction as facts | Ensures lineage consistency; uses best-effort fallback if lineage fails |
| 005 | Stage retry with exponential backoff | Transient LLM failures retry 3x; permanent errors skip stage and continue |

---

## Known Technical Debt

| Item | Location | Severity | Notes |
|------|----------|----------|-------|
| `_normalize_for_comparison` bug | `src/db/crud.py:3417` | Medium | Returns method reference instead of string |
| Historical validation not implemented | `src/validation/accounting_validator.py` | Low | TODO for cross-period checks when data available |
| No cell-level persistence | `src/db/crud.py:1583` | High | `persist_extraction_facts` discards `source_cells` |
| Correction feedback doesn't create LearnedAlias | `src/db/crud.py:1893` | Medium | Only creates EntityPattern, misses cross-entity learning |
| 3 async xfail tests | Various | Low | Event loop attachment on Python 3.11 |
| `load` mark not registered in pytest | `tests/load/` | Trivial | Add to pyproject.toml markers |

---

## Metrics Snapshot

### Test Suite
```
2,555 passed | 6 skipped | 3 xfailed | 0 failed
Coverage: 87.77% (target: 80%)
Duration: ~77 seconds
```

### Codebase
```
src/         10,408 lines (Python)
tests/       ~45,000 lines
static/js/   ~8,000 lines (JavaScript)
templates/   ~500 lines (HTML)
scripts/     28 utility scripts
docs/        52 documentation files (including demo package)
```

### Demo Documentation Package
```
docs/demo/   6 files
  product-overview.html    — Self-contained HTML product pitch (Meridian design system)
  architecture-diagrams.md — 5 Mermaid diagrams (system, pipeline, ER, quality, taxonomy)
  data-flow-diagrams.md    — 4 Mermaid diagrams (lifecycle, learning loop, security, deployment)
  feature-catalog.md       — Features by persona + 50+ endpoint reference
  roadmap.md               — Product roadmap with Gantt chart (2025–2027)
  demo-walkthrough.md      — 20-minute guided demo script
```

### Database
```
15 models | 18 migrations | 10+ indexes
312 taxonomy items | 1,358 aliases | 6 categories
```

---

## Phase 2 Priorities

1. **Taxonomy Overhaul** — Fix matching accuracy (fuzzy + embeddings), fill coverage gaps (debt-fund terminology), improve governance (impact preview, bulk ops, health metrics)
2. **Cell-Level Tracking** — Persist cell references, build reverse lookup, enable correction-to-cell tracing
3. **Excel Interaction UX** — Research in-app spreadsheet view vs. Excel add-in; build Source View tab
4. **Accuracy Benchmarking** — Gold standard datasets, precision/recall/F1 engine, regression detection, CI integration
