# Phase 2 Review

## Overview

Phase 2 ran through March 2026 with the theme "From Prototype to Product." All 15 planned tasks (B1.1-B1.6, B2.1-B2.3, B3.1-B3.2, B4.1-B4.6) were completed across four workstreams: Taxonomy Overhaul, Cell-Level Tracking, Excel Interaction UX, and Extraction Accuracy Benchmarking. A Stage 6 Derivation Engine was also delivered as a bonus beyond the original plan.

---

## Metrics: Phase 1 vs Phase 2

| Metric | Phase 1 Close | Phase 2 Close | Delta |
|--------|--------------|--------------|-------|
| Tests | 428 passing | 2,661 passing | +522% |
| Coverage | 74% | 85.7% | +11.7pp |
| Taxonomy items | 312 | 369 | +57 |
| Taxonomy version | 2.1.0 | 3.5.0 | 4 major revisions |
| Extraction stages | 5 | 6 (+ derivation) | +1 |
| API endpoints | ~25 | 84 | +236% |
| Alembic migrations | 10 | 37 | +27 |
| Benchmark accuracy | unmeasured | 100% (227/227) | n/a |
| Frontend pages | 5 | 10 | +5 |
| Lines of code (src/) | ~15k | 32,938 | +120% |
| Lines of code (tests/) | ~12k | 50,688 | +322% |
| Git commits | 11 | 79 | +68 |

---

## Workstream B1: Taxonomy Overhaul

The biggest workstream — taxonomy was the single largest quality bottleneck in Phase 1.

### B1.1 Fuzzy Matching
Replaced exact-match `_is_close_match()` with `rapidfuzz` token_sort_ratio scoring. Fixed the `_normalize_for_comparison()` bug that returned a method reference instead of a string. This immediately improved pattern matching for entity-specific overrides.

### B1.2 Correction Feedback Loop
User corrections now create `LearnedAlias` records with 3x weighting toward auto-promotion thresholds (3 occurrences, 2 entities). Pending `TaxonomySuggestion` evidence is updated when corrections match. A single correction from 2 different entities triggers auto-promotion — the alias becomes available taxonomy-wide.

### B1.3 Embedding Pre-Filter
`sentence-transformers` (all-MiniLM-L6-v2) computes embeddings for all canonical names and aliases. The in-memory vector index sits between pattern lookup and the Claude API call in Stage 3: high similarity skips Claude entirely, medium similarity provides hints to the prompt.

### B1.4 Automated Gap Detection
`GET /taxonomy/gaps` analyzes `UnmappedLabelAggregate` with occurrence/entity thresholds. `GET /taxonomy/gaps/clusters` groups similar unmapped labels by embedding similarity. Each cluster is classified as alias_candidate, new_item_candidate, or ambiguous.

### B1.5 Taxonomy Extension
Taxonomy grew from 312 to 369 items (v2.1.0 → v3.5.0). Major additions: UK/IFRS terminology (Trade Debtors, Cash at Bank, Stocks, Share Capital), debt schedule enrichment, project finance metrics, and 40+ alias conflict fixes. Benchmarks went from 86% to 100% mapping accuracy across all 6 fixtures.

### B1.6 Governance Improvements
- **Impact preview**: `GET /taxonomy/impact-preview/{canonical_name}` shows affected facts, patterns, and entities before changes
- **Bulk operations**: `POST /taxonomy/bulk-accept`, `POST /taxonomy/bulk-add-aliases`
- **Health metrics**: `GET /taxonomy/health` returns mapping success rate, alias hit rate, coverage, suggestion backlog
- **Version snapshots**: `TaxonomyVersion.snapshot` stores full taxonomy.json content; `GET /taxonomy/versions/diff` computes items added/removed and alias changes between versions

---

## Workstream B2: Cell-Level Tracking

### B2.1 Data Model
New `cell_mappings` table with reverse lookup index: given (job_id, sheet_name, cell_ref), returns canonical_name, mapping_status, confidence, fact_id. Indexed on (job_id, sheet_name, cell_ref) and (job_id, sheet_name, row_index). Added `cell_ref` and `source_cell_refs` columns to `ExtractionFact`.

### B2.2 Pipeline Persistence
`persist_cell_mappings()` walks structured representations and line items to build the reverse index. Wired into the orchestrator after fact persistence.

### B2.3 API Endpoints
`GET /jobs/{job_id}/cells` — cell mappings with sheet/status filtering. `GET /jobs/{job_id}/cells/stats` — per-sheet mapping statistics. Integrated into the corrections workflow with optional `cell_ref` targeting.

---

## Workstream B3: Excel Interaction UX

### B3.1 Research
Evaluated FortuneSheet (MIT, free) vs Handsontable ($1,590/dev/yr) vs Office.js Excel Add-In. Chose FortuneSheet for Phase 2a (in-app view) with add-in as Phase 2b.

### B3.2 Source View Tab
New "Source View" tab in job detail page. FortuneSheet grid initialized from structured data endpoint. Cells color-coded by mapping status (green/yellow/red). Click cell to see mapping details in side panel. Cross-tab linking from Line Items tab.

---

## Workstream B4: Benchmarking

### B4.1 Gold Standard Datasets
6 gold standard fixtures with expected mappings, triage tiers, and acceptable alternatives. Covers: simple burn model, realistic multi-statement, SaaS startup, European/IFRS, edge cases (OCR artifacts, merged cells), and large 50-item model.

### B4.2 Accuracy Engine
`src/benchmarking/accuracy.py` computes precision, recall, F1, per-category and per-sheet breakdowns. Stage attribution traces errors to parsing/triage/mapping/enhanced_mapping.

### B4.3 Database Persistence
`benchmark_runs` and `benchmark_category_metrics` tables. CRUD for creating runs, querying trends, and generating category heatmaps.

### B4.4 Enhanced Regression Detection
F1/recall thresholds in `regression_tracker.py`. Taxonomy-aware regression applies looser thresholds when taxonomy version changes.

### B4.5 CI Integration
Regression check in `.github/workflows/ci.yml` runs against pre-committed baselines (no API cost). Nightly full benchmark workflow in `.github/workflows/benchmark.yml`.

### B4.6 Dashboard
`static/js/pages/benchmarks.js` — accuracy trend charts, category heatmaps, per-run drill-down with mismatch inspection.

---

## Bonus: Stage 6 Derivation Engine

Not in the original plan but delivered during Phase 2. DAG-based engine with 35 derivation rules:
- Income statement chain (gross_profit → ebitda → ebt → net_income)
- Balance sheet derived items (net_debt, net_working_capital)
- Cash flow (FCF)
- Key ratios (debt_to_ebitda, interest_coverage, margins)
- Project finance (DSCR, CFAE, loan_to_cost, covenant headroom)
- Confidence propagation with uncertainty bands
- Consistency checking (extracted vs computed values)
- Covenant breach detection

---

## What Went Well

1. **Taxonomy accuracy went from unmeasured to 100%.** The combination of alias conflict fixes, UK/IFRS terminology, embedding pre-filter, and gold standard benchmarks created a tight feedback loop.

2. **Test count grew 6x** (428 → 2,661) with coverage climbing from 74% to 86%. Every new feature shipped with tests.

3. **The derivation engine** was an unplanned addition that significantly increases the value of extraction output — users get computed metrics (margins, ratios, covenant checks) for free.

4. **Cell-level tracking** unlocked the Source View UX and enables future features like "highlight source for this number."

## What Could Be Better

1. **Normalization module is disconnected.** FX service, anomaly detection, and suggestion engine exist but aren't wired into the extraction pipeline. Period/unit normalization isn't automatic.

2. **DerivedFact table is underutilized.** The derivation engine computes metrics but only stores them in the job result JSON blob, not in the queryable `derived_facts` table.

3. **CD pipeline is placeholder.** The deploy step just echoes image tags — no actual deployment to staging or production.

4. **FX rates are static.** The `fx_service.py` has hardcoded fallback rates. No live API integration.

5. **Time-series validation is stubbed.** The TODO at `accounting_validator.py:138` means YoY reasonableness checks aren't implemented.
