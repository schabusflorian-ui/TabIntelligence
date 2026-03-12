# DebtFund — World-Class Agent Prompts

Each agent below is a self-contained session. Copy the prompt into a new Claude Code chat rooted at the DebtFund project directory. Agents are ordered by dependency — earlier agents unlock later ones.

**Current State** (March 4, 2026):
- 731 tests passing, 85% coverage
- Benchmark: 100% triage, 96.4% mapping, 100% validation, $0.44/model, ~225s
- 5-stage pipeline: Parsing → Triage → Mapping → Validation → Enhanced Mapping
- Stack: FastAPI + Celery + PostgreSQL + S3 + Claude Sonnet 4

---

## Agent A: Production-Grade Excel Parsing

### Prompt

```
You are improving the Excel parsing stage of a financial model extraction pipeline. The project is at ~/DebtFund.

## Current State

The parsing stage (`src/extraction/stages/parsing.py`, 494 lines) does two-pass openpyxl extraction:
- Pass 1 (data_only=False): Captures formulas, bold formatting, indent levels, merged regions
- Pass 2 (data_only=True, read_only=True): Captures computed values
- Merges into a structured JSON repr, converts to markdown, sends to Claude Sonnet 4 for classification

This works. Benchmark on an 8-sheet LBO model: 8/8 sheets parsed, 110 line items extracted, all values correct.

## What's Missing

1. **Merged cell reconstruction**: `_excel_to_structured_repr()` lists merged regions (e.g., "A1:C5") in metadata but does NOT propagate the merged cell's value to all cells in the region. Real financial models use merged cells extensively for section headers spanning multiple columns. When Claude sees empty cells where a merged header should be, it loses structural context.

2. **Smart chunking for large files**: Currently the entire Excel content goes to Claude in one call. A 50-sheet model with 5000 rows produces 100K+ input tokens. We need sheet-by-sheet or chunk-based processing with a merge step.

3. **Number format intelligence**: The structured repr captures `number_format` (e.g., "#,##0", "0.0%", "$#,##0") but the markdown conversion doesn't use it systematically. Financial models encode meaning in formats — percentages vs. dollars vs. ratios vs. dates. Claude should know "this column is percentages" from the format string.

4. **Hidden sheet/row detection**: openpyxl can detect `ws.sheet_state` (visible/hidden/veryHidden) and row visibility. Hidden sheets sometimes contain important source data (driver assumptions). We should flag them, not silently include/exclude.

5. **Formula dependency graph**: We extract individual formulas per cell but don't build a dependency graph. Knowing that "cell E15 = SUM(E10:E14)" tells Claude this is a subtotal. Knowing "cell D5 references Sheet2!B10" tells Claude about cross-sheet relationships. A lightweight formula parser that extracts cell references would be valuable.

## Files to Read First

- `src/extraction/stages/parsing.py` — the full parsing stage
- `src/extraction/prompts/templates/parsing.v1.txt` — the Claude prompt for parsing
- `src/extraction/base.py` — PipelineContext and ExtractionStage base class
- `src/extraction/utils.py` — extract_json() helper
- `tests/unit/test_excel_parsing.py` — existing parsing tests (25 tests)
- `tests/fixtures/realistic_model.xlsx` — the benchmark test file
- `scripts/create_realistic_model.py` — how the test fixture was generated

## Implementation Requirements

1. **Merged cell propagation**: In `_excel_to_structured_repr()`, after building the sheet data, iterate merged regions and copy the top-left cell's value/formatting to all cells in the region. Add a `is_merged: bool` flag to cells.

2. **Chunking strategy**: Add a `_should_chunk()` method that estimates token count from the structured repr. If > 50K tokens, split into per-sheet Claude calls and merge results. The parsing prompt should work on individual sheets without modification. Add a `_merge_parsed_sheets()` method that combines per-sheet Claude responses.

3. **Format-aware markdown**: In `_structured_to_markdown()`, add a "Format" column or annotation. Group consecutive percentage-formatted cells under a "% column" marker. This helps Claude distinguish "54.5" (percentage) from "54.5" (dollar amount in thousands).

4. **Hidden sheet handling**: Add `is_hidden` to structured repr (already partially done). In the markdown, prefix hidden sheets with "[HIDDEN] " so Claude can factor this into triage.

5. **Formula reference extraction**: Add `_extract_cell_references(formula: str) -> List[str]` that parses Excel formulas for cell references (A1, Sheet2!B5, named ranges). Use regex — don't need a full parser. Add `references: List[str]` to the cell dict in structured repr.

## Testing Requirements

- Add tests for merged cell propagation (create a small .xlsx with merged cells programmatically)
- Add tests for chunking threshold detection
- Add tests for formula reference extraction (test common patterns: =A1+B1, =SUM(A1:A10), =Sheet2!B5, ='Sheet Name'!A1)
- Add test for hidden sheet detection
- Run full test suite — must stay at 731+ tests, 85%+ coverage
- Do NOT run the benchmark (costs real API money)

## Constraints

- Do not change the Claude model or prompt template structure
- Do not modify the stage registry pattern
- Do not add new dependencies — openpyxl already supports everything needed
- Keep backward compatibility — existing tests must pass unchanged
- Focus on the parsing stage ONLY — do not touch other stages
```

---

## Agent B: Item-Level Lineage & Provenance

### Prompt

```
You are building item-level lineage tracking for a financial model extraction pipeline. The project is at ~/DebtFund.

## Current State

The lineage system (`src/lineage/tracker.py`, 159 lines) tracks STAGE-level events:
- 5 events per extraction (one per stage)
- Parent-child chain: Stage 1 → Stage 2 → ... → Stage 5
- Metadata: token counts, sheet counts, mapping counts (summary stats only)
- Persisted to `lineage_events` table via `crud.create_lineage_event()`

The system answers "which stages ran" but NOT "where did this specific number come from."

## The Goal

Build item-level provenance so that for ANY line item in the output, you can trace:
1. **Source**: Which Excel cell(s) the value came from (sheet, row, column, cell_ref)
2. **Parsing**: How the cell was parsed (raw value, formula, hierarchy_level assigned)
3. **Mapping**: Which canonical name it mapped to, with what confidence, by which method (alias/semantic/entity_pattern)
4. **Validation**: Which validation rules applied to it, pass/fail status
5. **Enhanced mapping**: Whether it was remapped, old vs new canonical, confidence change

## Architecture Decision

Do NOT create a new database table for item-level lineage. Instead:
- Add a `provenance` field to each line item in the extraction result JSON
- This keeps provenance co-located with the data (no join needed)
- The existing `lineage_events` table stays for stage-level tracking

Each line item in the final output should have:
```json
{
  "original_label": "Net Revenue",
  "canonical_name": "revenue",
  "confidence": 0.95,
  "values": {"FY2022A": 232000},
  "provenance": {
    "source_cells": [
      {"sheet": "Income Statement", "cell_ref": "A4", "raw_value": "Net Revenue"},
      {"sheet": "Income Statement", "cell_ref": "B4", "raw_value": 232000, "formula": "=B3*1.08"}
    ],
    "parsing": {
      "hierarchy_level": 0,
      "is_bold": true,
      "is_formula": true,
      "is_subtotal": false
    },
    "mapping": {
      "method": "alias",
      "stage": 3,
      "taxonomy_category": "income_statement",
      "reasoning": "Net Revenue is a direct alias for revenue"
    },
    "validation": {
      "rules_applied": ["must_be_positive", "revenue >= gross_profit"],
      "all_passed": true
    },
    "enhanced_mapping": null
  }
}
```

## Files to Read First

- `src/lineage/tracker.py` — current lineage tracking
- `src/extraction/orchestrator.py` — how stages chain and results aggregate
- `src/extraction/stages/parsing.py` — Stage 1 output format (the `parsed` dict)
- `src/extraction/stages/mapping.py` — Stage 3 output format (the `mappings` list)
- `src/extraction/stages/enhanced_mapping.py` — Stage 5 output format
- `src/extraction/stages/validation.py` — Stage 4, how it builds `extracted_values`
- `src/extraction/base.py` — PipelineContext
- `src/api/main.py` — export endpoint (search for "/export")
- `data/benchmark_results/20260304_200108.json` — current output format

## Implementation Plan

### Step 1: Parsing stage emits cell refs
In `parsing.py`, ensure the Claude prompt asks for `cell_ref` per row (e.g., "A4"). The structured repr already has `ref` per cell — pass this through to the parsed output. Add `source_cells` to each row in the parsed result.

### Step 2: Mapping stage records provenance
In `mapping.py`, after Claude returns mappings, attach provenance metadata:
- `method`: from Claude's response (already has this)
- `reasoning`: from Claude's response (already has this)
- `taxonomy_category`: look up from taxonomy dict
- `stage`: 3 (or 5 for enhanced)

### Step 3: Validation stage annotates items
In `validation.py`, after running checks, build a `validation_provenance` dict keyed by canonical_name listing which rules were checked and their results.

### Step 4: Orchestrator merges provenance
In `orchestrator.py`, in the final result assembly step, merge source_cells (from parsing), mapping provenance (from mapping), validation provenance (from validation), and enhanced_mapping provenance (from stage 5) into each line item's `provenance` field.

### Step 5: Export endpoint includes provenance
In `main.py` export endpoint, include `provenance` in JSON export. For CSV export, flatten key provenance fields into columns (source_sheet, source_cell, mapping_method, mapping_confidence).

### Step 6: API endpoint for single-item provenance
Add `GET /api/v1/jobs/{job_id}/lineage/{canonical_name}` that returns the full provenance chain for a specific canonical item across all periods.

## Testing

- Unit test: provenance dict structure validation
- Unit test: source_cell extraction from parsing
- Unit test: mapping provenance attachment
- Integration test: full pipeline produces provenance on each line item
- Run full suite — 731+ tests, 85%+ coverage

## Constraints

- Do NOT create new database tables
- Do NOT change the lineage_events table schema
- Provenance lives in the result JSON blob (stored in extraction_jobs.result)
- Keep backward compatibility — existing tests must pass
- Don't change the stage execution order or registry pattern
```

---

## Agent C: Orchestrator Hardening & Error Recovery

### Prompt

```
You are hardening the extraction orchestrator for production reliability. The project is at ~/DebtFund.

## Current State

The orchestrator (`src/extraction/orchestrator.py`, 268 lines) runs 5 stages sequentially. Current issues:

1. **No stage-level retry**: If Stage 3 (mapping) fails after Stages 1-2 succeed, the entire pipeline fails. Celery retries the whole job from Stage 1, wasting the Claude API calls for parsing and triage again. With 5 Claude calls at ~$0.10 each, a Stage 5 failure wastes $0.40.

2. **No checkpoint/resume**: No way to resume from a failed stage. The PipelineContext holds results in memory only — if the process dies, everything is lost.

3. **No conditional stage skipping**: All 5 stages run regardless of content. If triage says "only 2 sheets are tier 1, rest are tier 4", validation still runs on sparse data producing meaningless 100% pass rates.

4. **No timeout per stage**: The Celery soft timeout (5 min) applies to the entire job. A single slow Claude call could eat the entire budget. Per-stage timeouts would allow failing fast.

5. **Progress callback is fragile**: If the callback fails (DB connection dropped mid-extraction), it's silently caught. The frontend shows stale progress forever.

## Files to Read First

- `src/extraction/orchestrator.py` — the full orchestrator
- `src/extraction/base.py` — PipelineContext, ExtractionStage
- `src/extraction/registry.py` — stage registry
- `src/jobs/tasks.py` — Celery task wrapper
- `src/core/retry.py` — retry decorator
- `src/core/exceptions.py` — exception hierarchy
- `src/lineage/tracker.py` — lineage tracking
- `tests/unit/test_orchestrator.py` — existing orchestrator tests

## Implementation Requirements

### 1. Stage-Level Retry with Result Caching

Add a `StageExecutor` class that wraps stage execution with:
- Per-stage retry (configurable, default 2 attempts)
- Result caching: after a stage succeeds, cache its result so retries of later stages don't re-run it
- Cache storage: use PipelineContext (in-memory for now)

```python
class StageExecutor:
    async def execute_with_retry(self, stage, context, max_attempts=2):
        cached = context.get_cached_result(stage.name)
        if cached:
            return cached
        for attempt in range(1, max_attempts + 1):
            try:
                result = await stage.execute(context, attempt=attempt)
                context.cache_result(stage.name, result)
                return result
            except (RateLimitError, ClaudeAPIError) as e:
                if attempt == max_attempts:
                    raise
                await asyncio.sleep(2 ** attempt)
```

### 2. Checkpoint/Resume via Job Metadata

Store completed stage results in the extraction_jobs.result field progressively:
- After each stage completes, UPDATE the job's result with partial data
- On resume (if the job was interrupted), load existing results from DB
- Add `resume_from_stage` parameter to `extract()` function

This requires changes to:
- `orchestrator.py`: Save partial results after each stage
- `tasks.py`: Check for existing partial results on retry
- `crud.py`: Add `update_job_partial_result()` function

### 3. Conditional Stage Execution

After triage (Stage 2), check the results:
- If ALL sheets are tier 4 (skip), abort pipeline early with a "no extractable content" result
- If no tier 1-2 sheets exist, skip validation (Stage 4) since there's not enough data for meaningful cross-item checks
- Add a `should_skip()` method to each stage that receives PipelineContext and returns (skip: bool, reason: str)

### 4. Per-Stage Timeout

Add `timeout_seconds` property to ExtractionStage base class:
- Parsing: 120s (large files need time)
- Triage: 30s (small prompt, fast response)
- Mapping: 90s (many labels)
- Validation: 60s (deterministic + one Claude call)
- Enhanced Mapping: 90s (remapping + persistence)

Wrap stage execution with `asyncio.wait_for(stage.execute(...), timeout=stage.timeout_seconds)`. On timeout, raise `ExtractionError(stage=stage.name)` which triggers stage-level retry.

### 5. Progress Callback Resilience

- Add a retry wrapper around the progress callback
- If DB update fails, queue the update for later (in-memory list)
- After pipeline completes, flush any queued progress updates
- Add a `last_heartbeat` timestamp to extraction_jobs to detect stale jobs from the health endpoint

## Testing

- Test stage retry: mock Stage 3 to fail once then succeed, verify Stages 1-2 not re-run
- Test checkpoint: mock Stage 4 failure, verify partial results saved to DB
- Test conditional skip: mock triage returning all tier-4, verify Stages 3-5 skipped
- Test per-stage timeout: mock slow stage, verify timeout triggers retry
- Test progress resilience: mock DB failure in callback, verify pipeline still completes
- Run full suite — 731+ tests, 85%+ coverage

## Constraints

- Do not change the stage interface (ExtractionStage.execute signature)
- Do not add new database tables
- Preserve the lineage chain (all stages must still emit lineage events, even skipped ones with "skipped" metadata)
- Keep the registry pattern
- Don't change Claude prompts or API calls
```

---

## Agent D: Frontend — Professional Results Experience

### Prompt

```
You are building a professional-grade frontend for a financial model extraction platform. The project is at ~/DebtFund.

## Current State

The frontend is vanilla JS (`static/app.js`, 343 lines) + HTML (`static/index.html`, 112 lines) + CSS (`static/styles.css`). It has:
- Drag-and-drop file upload
- Polling-based progress bar with stage names
- Results display with 3 tabs: Line Items (sortable table), Triage, Validation
- JSON/CSV export buttons
- API key management (localStorage)

It works but is basic — no filtering, no pagination, no lineage visualization, no interactive validation explorer.

## The Goal

Transform the frontend into a professional results experience WITHOUT introducing a build system or JS framework. Stay with vanilla JS but make it excellent.

## Files to Read First

- `static/index.html` — current HTML structure
- `static/app.js` — current JS (343 lines)
- `static/styles.css` — current styles
- `src/api/main.py` — API endpoints (search for @app.get and @app.post to understand available data)
- `data/benchmark_results/20260304_200108.json` — sample extraction result (what data is available)
- `src/api/schemas.py` — response schemas

## Implementation Requirements

### 1. Results Table Overhaul

Replace the current line items table with a professional data table:
- **Column visibility**: Toggle columns on/off (sheet, label, canonical, confidence, values per period)
- **Filtering**: Text filter per column (search box in header), confidence range slider
- **Pagination**: Show 50 items per page with prev/next, total count
- **Grouping**: Group by sheet (collapsible sections), or group by canonical category
- **Cell formatting**: Values formatted as currency ($1,234,567), percentages (54.5%), or plain numbers based on canonical type
- **Confidence visualization**: Color-coded badges (green >=0.8, yellow >=0.5, red <0.5) + tooltip showing reasoning
- **Row expansion**: Click a row to expand and show provenance details (source cells, mapping method, validation status) — only if provenance data exists in the API response

### 2. Triage Visualization

Replace the triage table with a visual sheet map:
- **Card layout**: Each sheet as a card showing name, tier badge (color-coded), decision, confidence, row count
- **Sortable**: By tier, by confidence, alphabetical
- **Tier summary bar**: Horizontal stacked bar showing count per tier (e.g., "3 High | 3 Medium | 1 Low | 1 Skip")

### 3. Validation Dashboard

Replace the validation content div with an interactive dashboard:
- **Overall gauge**: Circular gauge showing overall confidence (0-100%)
- **Period breakdown**: Table showing pass/fail per period with drill-down
- **Flag inspector**: Click a flag to see details (rule, actual vs expected, Claude's reasoning, suggested fix)
- **Flag severity badges**: Error (red), Warning (yellow), Info (blue)

### 4. Summary Statistics Enhancement

Expand the 5 summary stats to include:
- **Cost breakdown**: Input tokens cost + Output tokens cost (use Claude Sonnet pricing: $3/M input, $15/M output)
- **Processing time breakdown**: Per-stage duration if available in the result
- **Mapping coverage**: X of Y labels mapped (with confidence distribution histogram)

### 5. Export Enhancements

- Add Excel export button (calls future `/api/v1/jobs/{job_id}/export?format=xlsx` endpoint — show disabled with "Coming soon" tooltip for now)
- Add "Copy to clipboard" for individual values
- Add "Download validation report" button

### 6. Job History

Add a "Recent Jobs" sidebar/panel:
- Fetch from `GET /api/v1/jobs/` endpoint
- Show job ID (truncated), filename, status, timestamp
- Click to load results for any completed job
- Color-code by status: green (completed), red (failed), yellow (processing)
- Auto-refresh processing jobs

### 7. Dark Mode

Add a dark/light mode toggle:
- Respect system preference (prefers-color-scheme)
- Store preference in localStorage
- Use CSS custom properties for all colors

## Design Principles

- **No build system**: Pure HTML/CSS/JS, no npm, no bundlers, no frameworks
- **Progressive enhancement**: Everything works without JS (basic HTML), JS adds interactivity
- **Performance**: Virtual scrolling or pagination for large result sets (1000+ items)
- **Accessibility**: Semantic HTML, ARIA labels, keyboard navigation, focus indicators
- **Responsive**: Works on 1024px+ screens (laptop/desktop), graceful degradation on smaller

## Testing

- Manual testing via browser (document the test steps)
- Verify all API endpoints are called correctly
- Test with the benchmark result data (110 line items)
- Test with empty results (0 line items, no validation)
- Test error states (invalid API key, server error, network failure)
- Do NOT create automated JS tests — manual testing is fine for the frontend

## Constraints

- No JS frameworks (React, Vue, Angular, Svelte)
- No CSS frameworks (Tailwind, Bootstrap)
- No build tools (webpack, vite, esbuild)
- Keep it in 3 files: index.html, app.js, styles.css (split app.js into modules only if > 800 lines)
- All API calls go through the existing `apiFetch()` helper
- Must work with current API endpoints — don't add backend endpoints unless absolutely necessary
```

---

## Agent E: Taxonomy Intelligence & Learning Loop

### Prompt

```
You are building the entity learning loop — the competitive moat — for a financial model extraction platform. The project is at ~/DebtFund.

## Current State

The learning loop is partially built:

**What exists:**
- `EntityPattern` model in `src/db/models.py`: stores (entity_id, original_label, canonical_name, confidence, occurrence_count, created_by)
- Stage 5 (`src/extraction/stages/enhanced_mapping.py`): persists high-confidence mappings (>=0.8) as entity patterns via `crud.bulk_upsert_entity_patterns()`
- Stage 3 (`src/extraction/stages/mapping.py`): has `_lookup_patterns()` that shortcircuits Claude for labels with entity pattern confidence >= 0.95
- Corrections API (`src/api/corrections.py`): POST corrections, GET/DELETE patterns
- Taxonomy with 250+ canonical items across 5 categories

**What's missing:**
- No confidence decay (patterns from 2 years ago have same weight as yesterday's)
- No conflict resolution (two patterns for same label with different canonicals)
- No feedback loop from validation (if a pattern-mapped item fails validation, should pattern confidence decrease?)
- No industry-specific taxonomy adaptation
- No pattern quality metrics (which patterns actually improve accuracy?)
- Taxonomy aliases are static — no learning from real-world label variants

## Files to Read First

- `src/db/models.py` — EntityPattern model
- `src/db/crud.py` — search for "pattern" to find all pattern CRUD ops
- `src/extraction/stages/mapping.py` — `_lookup_patterns()` and `_build_entity_hints()`
- `src/extraction/stages/enhanced_mapping.py` — `_persist_entity_patterns()`
- `src/api/corrections.py` — correction/pattern API endpoints
- `data/taxonomy.json` — taxonomy structure with aliases
- `src/extraction/taxonomy_loader.py` — how taxonomy is loaded
- `tests/unit/test_mapping_shortcircuit.py` — pattern shortcircuit tests
- `tests/unit/test_corrections.py` — correction API tests

## Implementation Requirements

### 1. Pattern Confidence Decay

Add time-based confidence decay to entity patterns:
- Patterns should lose confidence over time if not reinforced
- Formula: `effective_confidence = base_confidence * decay_factor(days_since_last_seen)`
- Decay function: `decay_factor = max(0.5, 1.0 - (days / 365) * 0.3)` — 30% decay per year, floor at 0.5
- Add `last_seen_at` column to EntityPattern (Alembic migration)
- Update `last_seen_at` whenever a pattern matches during extraction
- Modify `_lookup_patterns()` to use effective_confidence instead of stored confidence

### 2. Pattern Conflict Resolution

When two patterns exist for the same (entity_id, original_label) with different canonical names:
- Keep both patterns in DB
- Add `is_active: bool` field — only one pattern per (entity_id, label) can be active
- Resolution strategy:
  1. User corrections always win (created_by="user_correction")
  2. Higher occurrence_count wins among auto-generated patterns
  3. More recent patterns win as tiebreaker
- Add `resolve_pattern_conflicts()` to crud.py
- Call after `bulk_upsert_entity_patterns()` in Stage 5

### 3. Validation Feedback Loop

After Stage 4 (validation), check if any pattern-mapped items failed validation:
- If a pattern-mapped canonical fails a cross-item validation rule, reduce the pattern's confidence by 0.1
- If a pattern-mapped item passes all validation, boost confidence by 0.02 (reinforcement)
- Add `_update_pattern_confidence_from_validation()` method to orchestrator
- Call after Stage 4 completes, before Stage 5

### 4. Pattern Quality Dashboard

Add API endpoint `GET /api/v1/entities/{entity_id}/pattern-stats`:
```json
{
  "entity_id": "uuid",
  "total_patterns": 45,
  "active_patterns": 42,
  "avg_confidence": 0.89,
  "by_method": {"claude": 38, "user_correction": 4, "entity_pattern": 3},
  "accuracy_rate": 0.94,
  "tokens_saved_estimate": 12500,
  "cost_saved_estimate": 0.12,
  "top_patterns": [],
  "conflicted_patterns": []
}
```

### 5. Dynamic Taxonomy Alias Learning

When Claude maps a label to a canonical name with high confidence (>=0.9) and the label is NOT already in the taxonomy's aliases:
- Record this as a "learned alias" in a new `learned_aliases` table
- After N occurrences (default 3) across different entities, promote to taxonomy.json
- Add `GET /api/v1/taxonomy/learned-aliases` endpoint to review pending aliases
- Add `POST /api/v1/taxonomy/learned-aliases/{id}/promote` to add to taxonomy

### 6. Industry-Specific Pattern Groups

Add ability to tag entities with industry (SaaS, manufacturing, banking, etc.):
- Patterns for an entity are automatically tagged with the entity's industry
- When a NEW entity is created with the same industry, pre-load patterns from other entities in that industry (with reduced confidence of 0.7x)
- Add `industry` column to Entity model (Alembic migration)
- Add `get_industry_patterns()` to crud.py

## Database Migrations Needed

1. Add `last_seen_at` (TIMESTAMP, default now) and `is_active` (BOOLEAN, default true) to entity_patterns
2. Create `learned_aliases` table: id, canonical_name, alias_text, occurrence_count, source_entities (JSON array), promoted (bool), created_at
3. Add `industry` (VARCHAR, nullable) to entities

## Testing

- Test confidence decay calculation
- Test conflict resolution (user correction wins over auto)
- Test validation feedback (failed validation reduces confidence)
- Test learned alias recording and promotion
- Test industry pattern sharing
- Run full suite — 731+ tests, 85%+ coverage

## Constraints

- Pattern operations must be fast (called during extraction)
- Use `get_db_sync()` context manager for all DB operations in stages
- Alembic migrations must be reversible (include downgrade)
- Don't change the extraction stage execution order
- Entity patterns are per-entity, not global (privacy boundary)
```

---

## Agent F: Test Infrastructure & Real-Data Validation

### Prompt

```
You are building production-grade test infrastructure for a financial model extraction platform. The project is at ~/DebtFund.

## Current State

- 731 tests, 85% coverage, 36s runtime
- All Claude API calls are mocked (no real API tests)
- Test fixtures: `tests/conftest.py` (517 lines) with module-level mocks for boto3, celery, redis
- One benchmark script: `scripts/benchmark_extraction.py` that runs real Claude calls
- One test model: `tests/fixtures/realistic_model.xlsx` (8 sheets, 159 rows)
- One expected result: `tests/fixtures/realistic_model_expected.json`

## What's Missing

1. **No VCR/cassette tests**: Real Claude responses aren't recorded, so we can't test against actual API behavior without spending money
2. **Only one test model**: Need diverse financial models (different industries, sizes, edge cases)
3. **No regression tracking**: No way to see if mapping accuracy improved or degraded between commits
4. **No stress tests**: Unknown behavior with large files (1000+ rows, 50+ sheets)
5. **No concurrent extraction tests**: Race conditions in dedup, pattern persistence, progress updates untested
6. **Coverage gaps**: lineage tracker, DLQ, S3 upload paths under-tested

## Files to Read First

- `tests/conftest.py` — fixture infrastructure
- `scripts/benchmark_extraction.py` — current benchmark script
- `scripts/create_realistic_model.py` — how test fixtures are generated
- `tests/fixtures/realistic_model_expected.json` — expected results format
- `data/benchmark_results/` — existing benchmark results
- `tests/unit/test_e2e_pipeline.py` — existing e2e tests
- `pyproject.toml` — test configuration (pytest section)

## Implementation Requirements

### 1. VCR Cassette Recording

Add a response recording system for Claude API calls:
- When `RECORD_CASSETTES=1` env var is set, intercept Claude API responses and save to `tests/cassettes/`
- Cassette format: JSON files with request hash → response mapping
- When cassettes exist, replay them instead of calling real API
- Add `@use_cassette("test_name")` decorator for tests
- Implementation: Patch `get_claude_client()` to return a recording/replaying wrapper

File structure:
```
tests/cassettes/
  realistic_model_parsing.json
  realistic_model_triage.json
  realistic_model_mapping.json
  realistic_model_validation.json
  realistic_model_enhanced_mapping.json
```

### 2. Diverse Test Fixtures

Create 3 additional test models using scripts similar to `create_realistic_model.py`:

**Model 2: SaaS Company** (`tests/fixtures/saas_model.xlsx`)
- 6 sheets: P&L, Balance Sheet, Cash Flow, MRR Analysis, Customer Metrics, Assumptions
- SaaS-specific labels: MRR, ARR, CAC, LTV, Churn Rate, Net Revenue Retention
- 3 periods: FY2024A, FY2025E, FY2026E
- Expected: 40 mappings, some unmapped SaaS metrics

**Model 3: Edge Cases** (`tests/fixtures/edge_case_model.xlsx`)
- 4 sheets with intentionally tricky content:
  - Sheet with merged cells spanning 5 columns for headers
  - Sheet with labels in column B instead of A (offset layout)
  - Sheet mixing quarterly (Q1-Q4) and annual data
  - Sheet with identical labels in different sections ("Total" appears 6 times)
- Expected: Test robustness, some items should map correctly despite unusual layout

**Model 4: Large Model** (`tests/fixtures/large_model.xlsx`)
- 15 sheets, ~500 rows total
- Full LBO model with sources & uses, returns analysis, sensitivity tables
- Purpose: Test chunking/token limits (should NOT be run in normal test suite — benchmark only)

### 3. Accuracy Regression Tracking

Create `scripts/accuracy_tracker.py`:
- Runs benchmark for all test fixtures
- Compares results to `data/benchmark_baselines/` (committed baseline files)
- Reports: accuracy delta per model, new unmapped items, confidence changes
- Exit code 1 if accuracy drops below baseline threshold
- Can be added to CI pipeline (with `ANTHROPIC_API_KEY` secret)

Add `data/benchmark_baselines/`:
```
realistic_model_baseline.json  # Current: triage 100%, mapping 96.4%
saas_model_baseline.json
edge_case_model_baseline.json
```

### 4. Concurrent Extraction Tests

Add `tests/unit/test_concurrency.py`:
- Test dedup race condition: Submit same file twice simultaneously, verify only one job created
- Test pattern persistence race: Two extractions for same entity finishing simultaneously
- Test progress update race: Two stages completing and updating job simultaneously
- Use `threading` or `asyncio` for concurrency simulation
- Mock Claude calls (don't use real API)

### 5. Coverage Gap Tests

**Lineage** (`tests/unit/test_lineage_coverage.py`):
- Test lineage validation with missing stages
- Test partial lineage save on stage failure
- Test lineage event ordering (timestamps monotonically increasing)

**DLQ** (`tests/unit/test_dlq_coverage.py`):
- Test DLQ routing: verify non-transient errors go to DLQ
- Test DLQ retry: requeue a failed job and verify it re-runs
- Test DLQ listing endpoint with filters

**S3** (`tests/unit/test_s3_coverage.py`):
- Test S3 upload with various file sizes
- Test S3 download for task execution
- Test S3 key generation format

### 6. Test Performance

Add `pytest-benchmark` integration:
- Benchmark `extract_json()` with various input sizes
- Benchmark `AccountingValidator.validate()` with 50 validation rules
- Benchmark taxonomy loading and formatting
- Add to CI as performance regression check

## Testing

- All new tests must pass
- Total test count should reach 780+
- Coverage should reach 87%+
- Test runtime should stay under 60s (excluding benchmarks)

## Constraints

- Cassettes must NOT contain API keys or secrets
- Test fixtures must be small enough to commit to git (< 1MB each)
- Concurrent tests must be deterministic (use locks, not random delays)
- Don't modify existing test files — only add new ones
- VCR system must be opt-in (existing tests keep using mocks)
```

---

## Agent G: Export, Cost & Observability

### Prompt

```
You are building production export capabilities and observability for a financial model extraction platform. The project is at ~/DebtFund.

## Current State

**Export**: JSON and CSV only. No Excel export. CSV is flat (no formatting, no formulas, no multi-sheet).

**Cost tracking**: Orchestrator calculates cost inline: input_tokens * $3/M + output_tokens * $15/M. Cost is stored in the result JSON blob but not in a dedicated field.

**Observability**: Prometheus metrics exist (extraction_duration, stage_duration, cost, tokens) but:
- No structured logging for queries
- No per-entity cost tracking
- No cost alerts or budgets
- No extraction analytics (avg accuracy, avg cost, popular canonical names)

## Files to Read First

- `src/api/main.py` — export endpoint (search for "/export"), lines 537-750
- `src/extraction/orchestrator.py` — cost calculation (search for "cost")
- `src/api/health.py` — health endpoints
- `src/core/logging.py` — logging setup
- `src/core/metrics.py` — Prometheus metrics
- `data/benchmark_results/20260304_200108.json` — sample result with cost data

## Implementation Requirements

### 1. Excel Export

Add `format=xlsx` option to the export endpoint:
- Create a multi-sheet Excel workbook:
  - Sheet 1 "Line Items": Same as CSV but with formatting (headers bold, confidence color-coded, values as currency)
  - Sheet 2 "Triage": Sheet classification results
  - Sheet 3 "Validation": Validation results with pass/fail highlighting
  - Sheet 4 "Summary": Extraction metadata (file, duration, cost, tokens, accuracy)
- Use openpyxl (already a dependency)
- Return as StreamingResponse with content-type application/vnd.openxmlformats-officedocument.spreadsheetml.sheet

### 2. Cost Tracking System

Add dedicated cost tracking:
- Add `cost_usd` column (DECIMAL) to `extraction_jobs` table (Alembic migration)
- Add `total_input_tokens` and `total_output_tokens` columns to `extraction_jobs`
- Update these fields after extraction completes (in tasks.py)
- Add `GET /api/v1/costs/summary` endpoint:
  ```json
  {
    "total_cost_usd": 12.45,
    "total_jobs": 28,
    "avg_cost_per_job": 0.44,
    "cost_by_entity": [{"entity_id": "...", "total_cost": 3.20, "job_count": 7}],
    "cost_trend": [{"date": "2026-03-01", "cost": 1.20}],
    "token_breakdown": {"input": 150000, "output": 80000}
  }
  ```
- Add `GET /api/v1/costs/budget` endpoint for per-entity budget alerts

### 3. Extraction Analytics

Add `GET /api/v1/analytics/extractions` endpoint:
```json
{
  "total_extractions": 28,
  "avg_mapping_accuracy": 0.94,
  "avg_validation_confidence": 0.97,
  "avg_duration_seconds": 180,
  "avg_cost_usd": 0.44,
  "top_unmapped_labels": [
    {"label": "EBITDA Margin", "count": 5},
    {"label": "Leverage Ratio", "count": 3}
  ],
  "canonical_name_distribution": {
    "revenue": 28, "ebitda": 25, "net_income": 24
  },
  "accuracy_trend": [{"date": "...", "accuracy": 0.92}]
}
```

This requires querying extraction_jobs.result JSON for stats — use PostgreSQL JSON operators.

### 4. Structured Logging Enhancement

Upgrade logging for production queryability:
- Add request_id to all log lines (middleware that generates UUID per request)
- Add job_id to all extraction log lines
- Add structured fields: stage, duration_ms, tokens, cost_usd, entity_id
- Configure JSON log format for production (already uses python-json-logger)
- Add log-based alerting hooks (log at CRITICAL for: cost > $5/job, duration > 600s, all stages failed)

### 5. Health Check Enhancements

Extend `src/api/health.py`:
- Add `/health/metrics` returning Prometheus metrics in text format
- Add `/health/dependencies` checking: PostgreSQL connectivity, Redis/Celery ping, S3 access, Claude API key validity
- Add `/health/cost-alert` returning any entities over budget

## Database Migrations

1. Add `cost_usd` (DECIMAL(10,6), nullable), `total_input_tokens` (INTEGER, nullable), `total_output_tokens` (INTEGER, nullable) to extraction_jobs

## Testing

- Test Excel export: verify workbook structure, sheet names, formatting
- Test cost tracking: verify cost_usd saved correctly after extraction
- Test analytics endpoint: verify JSON structure with mock data
- Test health endpoints: verify dependency checks
- Run full suite — 731+ tests, 85%+ coverage

## Constraints

- Excel export must handle 10K+ line items without memory issues (use write-only mode)
- Cost tracking must be accurate to 6 decimal places
- Analytics queries must be fast (< 500ms for 1000 jobs)
- Don't change the extraction pipeline stages
- Alembic migration must be reversible
```

---

## Recommended Execution Order

```
Phase 1 (Foundation):
  Agent A (Parsing)      — improves input quality for all downstream stages
  Agent C (Orchestrator)  — makes pipeline production-reliable

Phase 2 (Intelligence):
  Agent E (Learning Loop) — builds the competitive moat
  Agent B (Lineage)       — enables provenance tracking

Phase 3 (Experience):
  Agent D (Frontend)      — professional results UI
  Agent G (Export/Observability) — production operations

Phase 4 (Quality):
  Agent F (Testing)       — locks in quality with regression tracking
```

Agents within the same phase can run in parallel (separate chats). Cross-phase dependencies are minimal — each agent reads the current state of files, so later agents naturally pick up earlier changes.
