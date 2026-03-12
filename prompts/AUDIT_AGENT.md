# Comprehensive Extraction Pipeline Audit & Stress-Test Agent

You are a senior QA engineer and financial modeling expert performing a deep audit of the DebtFund extraction pipeline. The project is at `~/DebtFund`. You have 10 real Excel files representing climate-hardware due-diligence financial models with deliberately embedded errors and structural challenges. Your job is to write exhaustive, deterministic pytest tests that stress-test every layer of the pipeline against these real files — parsing, period detection, section detection, triage, mapping lookups, validation rules, and quality scoring. You are NOT testing Claude's reasoning — you are testing every piece of deterministic Python logic that runs before, after, and around the LLM calls.

## Critical Mindset

Think like an adversarial auditor. The pipeline was built mostly with synthetic test fixtures (in-memory openpyxl workbooks). The 10 real files expose patterns the pipeline has NEVER seen:
- German labels in a transposed layout
- 36 monthly columns in a single sheet
- 3 scenarios side-by-side with gap columns
- Hidden assumption rows
- Fiscal year periods (FY26/27)
- Mixed quarterly + annual columns
- HoldCo/SPV/Consolidation multi-entity structures
- Fully hardcoded models (zero formulas)
- SaaS metrics masking a project finance model
- Commodity curve sub-tables

Your tests must verify the pipeline handles these gracefully — not crash, not silently corrupt data, not misclassify.

## Files to Read First (READ ALL before writing any code)

### Pipeline Source Code (read thoroughly)
- `src/extraction/stages/parsing.py` — _excel_to_structured_repr(), _structured_to_markdown(), cell extraction
- `src/extraction/stages/triage.py` — _build_sheet_summary(), rule-based triage
- `src/extraction/stages/mapping.py` — _build_grouped_line_items(), _normalize_label(), _SHEET_TO_CATEGORY, alias lookups
- `src/extraction/stages/validation.py` — _build_extracted_values(), _filter_lifecycle_flags()
- `src/extraction/stages/enhanced_mapping.py` — _find_remapping_candidates()
- `src/extraction/orchestrator.py` — _build_result(), _compute_quality()
- `src/extraction/section_detector.py` — SectionDetector.detect_sections()
- `src/extraction/period_parser.py` — PeriodParser, NormalizedPeriod, detect_periods_from_sheet()
- `src/extraction/taxonomy_loader.py` — get_alias_to_canonicals(), format_taxonomy_for_prompt()
- `src/extraction/base.py` — PipelineContext, ExtractionStage
- `src/extraction/utils.py` — helper functions
- `src/validation/accounting_validator.py` — AccountingValidator, validation rules
- `src/validation/completeness_scorer.py` — CompletenessScorer, model type detection, templates
- `src/validation/quality_scorer.py` — QualityScorer, letter grades
- `src/validation/time_series_validator.py` — TimeSeriesValidator
- `src/validation/lifecycle_detector.py` — LifecycleDetector, phase detection
- `data/taxonomy.json` — canonical items, aliases, validation_rules

### Test Infrastructure (read for patterns)
- `tests/conftest.py` — module-level mocks (boto3, celery, redis), test_client fixtures
- `tests/unit/test_excel_parsing.py` — _make_minimal_xlsx() helper, existing parsing tests
- `tests/unit/test_period_parser.py` — period detection tests
- `tests/unit/test_section_detector.py` — section detection tests
- `tests/unit/test_orchestrator.py` — orchestrator tests with mocked stages
- `tests/unit/test_validation_stage.py` — validation stage tests

### Real Test Files (read ERROR_MANIFEST for answer key)
- `tests/real data/ERROR_MANIFEST_v2.md` — 50 embedded errors, 11 structural challenges, scoring rubric
- `tests/real data/01_electrolyser_FOAK_singlesheet.xlsx` through `10_wind_nacelle_manufacturing_quarterly.xlsx`

### Key Constants
- Real data directory: `tests/real data/` (note the space in directory name)
- Taxonomy: `data/taxonomy.json` (version 3.0.0, ~350 items, 6 categories)
- All files span 2025-2035 (11-year projection horizon)

## Architecture Understanding

The pipeline has 5 stages: Parsing → Triage → Mapping → Validation → Enhanced Mapping.

**What is deterministic (testable without Claude):**
1. `_excel_to_structured_repr()` — openpyxl extraction (cells, formulas, colors, merges, metadata)
2. `_structured_to_markdown()` — markdown formatting
3. `_detect_label_column()`, `_detect_header_row()`, `_detect_table_regions()` — layout heuristics
4. `_detect_transposed_layout()`, `_detect_units()`, `_is_financial_row()` — structural detection
5. `PeriodParser.parse()`, `detect_periods_from_sheet()` — period normalization
6. `SectionDetector.detect_sections()` — multi-statement section splitting
7. `_build_sheet_summary()` — triage input preparation
8. `_rule_based_triage()` — deterministic sheet classification (skipping Claude)
9. `_SHEET_TO_CATEGORY` — sheet name → category mapping
10. `_normalize_label()` — label cleaning before mapping
11. `get_alias_to_canonicals()` — taxonomy alias lookups
12. `_build_grouped_line_items()` — hierarchy assembly
13. `_disambiguate_by_sheet_category()` — deterministic mapping overrides
14. `_build_extracted_values()` — value assembly with unit normalization
15. `AccountingValidator.validate()` — 60+ deterministic rules
16. `LifecycleDetector.detect()` — lifecycle phase detection
17. `CompletenessScorer` — model type detection + coverage
18. `QualityScorer` — composite scoring with model-type weights
19. `TimeSeriesValidator` — time-series consistency
20. `_filter_lifecycle_flags()` — lifecycle-aware flag suppression

**What requires Claude (mock in tests):**
- Parsing prompt response (structured extraction from markdown)
- Triage prompt response (tier classification)
- Mapping prompt response (label → canonical mapping)
- Validation anomaly reasoning
- Enhanced mapping prompt response

## Implementation Plan

Create a single comprehensive test file: `tests/unit/test_real_excel_audit.py`

Use this structure:
```python
"""
Comprehensive audit tests using 10 real climate-hardware financial models.

These tests exercise the DETERMINISTIC parts of the extraction pipeline
against real Excel files with known structural challenges and embedded errors.
No Claude API calls are made — all LLM interactions are mocked.
"""
import io
import json
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

REAL_DATA_DIR = Path(__file__).parent.parent / "real data"

def _skip_if_no_real_data():
    """Skip tests if real data directory doesn't exist."""
    if not REAL_DATA_DIR.exists():
        pytest.skip("Real data directory not found")

def _load_file(filename: str) -> bytes:
    """Load a real Excel file as bytes."""
    _skip_if_no_real_data()
    path = REAL_DATA_DIR / filename
    if not path.exists():
        pytest.skip(f"{filename} not found")
    return path.read_bytes()

def _load_workbook(filename: str):
    """Load as openpyxl workbook for inspection."""
    return openpyxl.load_workbook(io.BytesIO(_load_file(filename)), data_only=False)
```

## Test Categories (implement ALL of these)

### Category 1: Raw Structural Extraction (parsing.py)

For each of the 10 files, call `_excel_to_structured_repr()` and verify:

**File 01 (Electrolyser FOAK — single sheet):**
- Returns exactly 1 sheet named "Model"
- Extracts 89 rows × 13 columns
- Detects 17 merged cell regions (section headers A1:M1, A6:M6, A36:M36, etc.)
- Identifies formulas (e.g., `=B7*1000*B8*8760/B9/1000` in the model)
- Detects blue font (#0000FF) cells as inputs
- Label column detected as column A
- Units column detected as column B (EUR, kWh, MW, MWh, kg)
- Period row at row 3 or 4 with years 2025-2035 across columns C-M
- Extracts font_color for white headers (on dark background) vs blue inputs vs black formulas

**File 02 (Biochar NOAK — transposed, German):**
- Returns 4 sheets: Modell, Annahmen, Meilensteinplan, Working Capital
- `Modell` sheet: detects TRANSPOSED layout (years down rows, items across columns)
- Extracts German labels: "Umsatz", "EBITDA", "Betriebskosten", etc.
- Detects formula `=B4*B5` in Annahmen sheet
- Detects formula `=SUM(D5:D9)` in Meilensteinplan
- `Working Capital` sheet has standard layout (years across columns) — NOT transposed
- Red font (#CC0000) extracted for warning cells

**File 03 (Heat Pump HaaS — monthly):**
- Returns 2 sheets: "Monthly CF", "Annual Summary"
- `Monthly CF`: 33 rows × 38 columns (36 monthly columns)
- `Annual Summary`: contains cross-sheet formulas referencing `'Monthly CF'!C17:N17`
- Blue (#0000FF) inputs and red (#CC0000) warnings detected

**File 04 (DAC Pre-revenue — 9 tabs):**
- Returns exactly 9 sheets: Cover, MacroAsm, TechSpec, CapEx_Depr, OpEx, Revenue_Grants, Debt_DSRA, CFADS_Waterfall, Sensitivity
- Cross-sheet formulas detected (e.g., `=MacroAsm!B14*MacroAsm!B8/MacroAsm!B8` in TechSpec)
- Debt_DSRA sheet has N/A placeholder values (not real financial data)
- Sensitivity sheet contains 2D table structure

**File 05 (Pyrolysis W2E — inline scenarios):**
- Returns 2 sheets: P&L_Model, Debt_DSCR
- `P&L_Model`: 45 rows × 39 columns
- Debt_DSCR sheet is EMPTY (1×1, placeholder)
- Detects 3 scenario column blocks from merged headers in row 2: BASE CASE, HIGH CASE, LOW/STRESS
- Separator columns (N, Z) detected as non-data

**File 06 (LDES Hidden — SaaS metrics):**
- Returns 2 sheets: LDES_Model, Debt Schedule
- `LDES_Model` row 1 contains the literal text `=== HIDDEN ASSUMPTIONS — unhide rows 1-15 to edit ===`
- Rows 1-15 contain hidden assumption values (storage capacity 200 MWh, etc.)
- Strong color coding: red (#FF0000) and blue (#0000FF) only
- Detects pseudo-formula text cells (strings that look like formulas but aren't: `=ARR/12 -- meaningless for storage dispatch`)
- 11 merged cells for section headers

**File 07 (Green Ammonia — 3 scenarios + curves):**
- Returns 3 sheets: Green_NH3_Model, Commodity Curves, Debt Tranches
- `Green_NH3_Model`: 3 scenario column blocks (same pattern as File 05)
- `Commodity Curves`: TRANSPOSED layout (years going down rows 2025-2035)
- `Debt Tranches`: structured table with formulas (`=B3*0.40`, `=B3*0.25`)
- Multi-currency: EUR and USD values

**File 08 (Geothermal EGS — HoldCo/SPV):**
- Returns 3 sheets: SPV_ProjectCo, HoldCo, Consolidation
- All 3 have standard layout with years 2025-2035
- SPV has "EUR k" units
- HoldCo has dual header pattern (years in row 3 AND row 5)
- Consolidation tab mentions intercompany eliminations in a warning

**File 09 (CCUS Cement — hardcoded, fiscal year):**
- Returns 1 sheet: FY_Model
- ZERO formulas detected (all hardcoded) — this is a critical structural signal
- Period headers are fiscal years: FY26/27, FY27/28, ... FY35/36
- Column C labeled "Construction"
- Multiple currencies in labels: EUR, $, GBP (£)

**File 10 (Wind Nacelle — quarterly + annual):**
- Returns 4 sheets: P&L_Quarterly, Working Capital, Order Backlog, Covenant Tracker
- `P&L_Quarterly`: mixed periodicity — Q1-Q4 2025, Q1-Q4 2026 (quarterly), then 2028-2035 (annual)
- Column K is visual separator: `<- QUARTERLY | ANNUAL ->`
- `Working Capital` has formulas: `=C4+C5+C6`
- `Order Backlog`: TRANSPOSED — customer orders listed vertically
- `Covenant Tracker`: DSCR and leverage thresholds

### Category 2: Period Detection (period_parser.py)

For each file, extract the period headers and run through PeriodParser:

**File 01:** Years 2025-2035 in columns C-M → period_type="calendar_year" or "standalone_year", 11 periods, layout="time_across_columns"
**File 02 (Modell sheet):** Years 2025-2035 going DOWN rows → layout="time_down_rows"
**File 02 (Working Capital):** Same years but across columns → layout="time_across_columns"
**File 03:** 36 monthly columns → period_type should contain "monthly", detect month patterns
**File 04:** Standard annual 2025-2035 across tabs
**File 05:** Years 2025-2035 repeated 3× across columns (one per scenario) — parser should normalize to unique set
**File 09:** Fiscal year labels FY26/27 through FY35/36 → period_type="fiscal_year", parse start/end years correctly
**File 10:** Mixed Q1 2025...Q4 2026, then 2028-2035 → detect mixed periodicity (quarterly + annual)

Edge cases to test:
- PeriodParser.parse("FY26/27") → should recognize fiscal year format
- PeriodParser.parse("Construction") → should return None or confidence=0.0 (not a period)
- PeriodParser.parse_series(["Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025", "Q1 2026", ...]) → quarterly
- PeriodParser.parse("2025") vs PeriodParser.parse("FY2025") → different period_type
- datetime objects from openpyxl → proper handling

### Category 3: Section Detection (section_detector.py)

**File 01:** Single sheet with 17 merged section headers → detect multiple sections (assumptions, revenue, costs, capex, depreciation, tax, debt service, etc.)
**File 04:** 9 separate tabs → each tab is its own section (no multi-section within a single tab)
**File 05:** P&L_Model has 3 scenario blocks → sections should be identified (or at minimum, not crash)
**File 06:** Rows 1-15 hidden assumptions, rows 16-30 SaaS KPIs, rows 31+ actual PF model → should detect at least 2-3 sections
**File 08:** Each tab is single-purpose → 1 section per tab
**File 10:** P&L_Quarterly has a visual separator at column K → verify section detection handles this

For each detection, verify:
- category_hint matches expected financial statement type
- sample_labels are reasonable (actual financial labels, not metadata)
- Sections don't overlap (end_row of section N < start_row of section N+1)
- Empty sheets return empty section list

### Category 4: Layout Detection Heuristics (parsing.py)

**Label column detection (_detect_label_column):**
- File 01: column A (standard)
- File 02 Modell: column B (first financial label column in transposed layout)
- File 06: column A (despite hidden rows)
- All files: label column should contain mostly string values

**Header row detection (_detect_header_row):**
- File 01: row 3 or 4 (after title + subtitle)
- File 02 Modell: different because transposed
- File 08 HoldCo: dual header rows (3 and 5) — pick the correct one
- File 10 P&L_Quarterly: row with Q1 2025, Q2 2025, etc.

**Transposition detection (_detect_transposed_layout):**
- File 02 Modell: TRUE
- File 07 Commodity Curves: TRUE
- File 10 Order Backlog: TRUE
- All other sheets: FALSE
- Must NOT false-positive on standard layouts

**Unit detection (_detect_units):**
- File 01: EUR (from number_format or unit column)
- File 02: EUR + USD mixed
- File 03: EUR + MWh
- File 08 SPV: "EUR k" (thousands)
- File 09: EUR + $ + GBP (£) mixed — should flag multi-currency

**Table region detection (_detect_table_regions):**
- File 06: should detect gap between SaaS KPI block and PF model block
- File 01: single continuous table (no gaps)
- File 10: P&L_Quarterly has column separator but rows are continuous

### Category 5: Triage (triage.py)

Test `_rule_based_triage()` (deterministic, no Claude) for sheet names:

| Sheet Name | Expected Tier | Expected Category |
|---|---|---|
| "Model" (File 01) | None (ambiguous — needs Claude) | None |
| "Modell" (File 02) | None (German, ambiguous) | None |
| "Annahmen" (File 02) | None (German) | None |
| "P&L_Model" (File 05) | 1 (contains "P&L") | income_statement |
| "Monthly CF" (File 03) | 1 (contains "CF") | cash_flow |
| "Annual Summary" (File 03) | None or 2 (ambiguous) | None |
| "Cover" (File 04) | 4 (cover page) | None |
| "MacroAsm" (File 04) | 3 (assumptions) | None |
| "CapEx_Depr" (File 04) | 2 (supporting schedule) | None |
| "Revenue_Grants" (File 04) | 2 | income_statement |
| "Debt_DSRA" (File 04) | 2 (debt schedule) | debt_schedule |
| "CFADS_Waterfall" (File 04) | 1 or 2 (cash flow waterfall) | cash_flow |
| "Sensitivity" (File 04) | 3 or 4 | None |
| "Debt_DSCR" (File 05, empty) | 4 (empty sheet) | None |
| "LDES_Model" (File 06) | None (ambiguous) | None |
| "Debt Schedule" (File 06) | 2 | debt_schedule |
| "Commodity Curves" (File 07) | 3 (supporting data) | None |
| "Debt Tranches" (File 07) | 2 | debt_schedule |
| "SPV_ProjectCo" (File 08) | None (ambiguous) | None |
| "HoldCo" (File 08) | None (ambiguous) | None |
| "Consolidation" (File 08) | None (ambiguous) | None |
| "FY_Model" (File 09) | None (ambiguous) | None |
| "P&L_Quarterly" (File 10) | 1 | income_statement |
| "Working Capital" (File 10) | 2 | None |
| "Order Backlog" (File 10) | 3 | None |
| "Covenant Tracker" (File 10) | 2 or 3 | debt_schedule |

Also test `_build_sheet_summary()` for each sheet — verify it produces valid summary dicts with:
- row_count > 0 (except empty Debt_DSCR)
- col_count > 0
- sample_labels populated
- has_formulas boolean correct
- has_numeric_values boolean correct

### Category 6: Taxonomy Alias Coverage

Load taxonomy and verify alias coverage for labels found in real files:

**German labels (File 02):**
- "Umsatz" → should map to "revenue" (check aliases)
- "EBITDA" → should map to "ebitda"
- "Betriebskosten" → should map to something in income_statement (opex or operating_expenses)
- "Biomasse-Input" → likely unmapped (very specialized)
- "Biokohle-Ausbeute" → likely unmapped

**Project finance labels (Files 01, 03, 04, 06, 07):**
- "CFADS" → check taxonomy contains this
- "DSCR" → should map to "dscr"
- "DSRA" → check taxonomy
- "LLCR" → check taxonomy
- "Debt Service" → should map to "debt_service"
- "Senior Debt" → check aliases
- "Mezzanine" → check aliases
- "Equity IRR" → should map to "equity_irr"

**SaaS-style labels (File 06):**
- "ARR" → should map to "arr"
- "MRR" → should map to "mrr"
- "CAC" → should map to "customer_acquisition_cost"
- "LTV" → should map to "lifetime_value"
- "Churn Rate" → should map to something in metrics

**Manufacturing labels (File 10):**
- "Order Backlog" → check if mapped
- "Nacelle" → not a financial term, should be unmapped
- "CFRP" → not a financial term

**Common labels across files:**
- "Revenue", "EBITDA", "CapEx", "OpEx", "Depreciation", "Tax", "Net Income" → all must resolve
- "Total CapEx" → should map to "total_capex" or "capex"
- "Gross Profit" → must resolve
- "Working Capital" → must resolve

Test `_normalize_label()` on messy variants found in real files:
- "  Revenue  " → "Revenue" (whitespace stripped)
- "1. Revenue" → "Revenue" (numbering stripped)
- "Revenue ($M)" → "Revenue" (unit parenthetical stripped)
- "Revenue:" → "Revenue" (trailing colon stripped)
- "- EBITDA" → "EBITDA" (leading dash stripped)
- "Total CapEx (EUR)" → "Total CapEx" or "CapEx"

### Category 7: Validation Rules

Build synthetic `extracted_values` dicts mimicking data from each file and run through AccountingValidator:

**File 01 (Electrolyser):**
```python
# DSCR = EBITDA / Debt Service (ERROR: should use CFADS)
# Test that validation can flag: DSCR numerator should be CFADS not EBITDA
values_2028 = {
    "revenue": Decimal("5000000"),
    "ebitda": Decimal("2500000"),
    "debt_service": Decimal("1200000"),
    "dscr": Decimal("2.08"),  # 2500000/1200000 — wrong, should be CFADS-based
}
```
- Verify derivation rule: gross_profit = revenue - cogs
- Verify DSCR range check (if rule exists)

**File 04 (DAC — pre-revenue):**
```python
# Revenue in Year 1 despite 18-month construction period
values_2025 = {
    "revenue": Decimal("0"),  # Pre-revenue year
    "capex": Decimal("25000000"),
}
values_2026 = {
    "revenue": Decimal("1500000"),  # Revenue starts — but construction not done
    "capex": Decimal("5000000"),  # Still spending capex
}
```
- Test lifecycle detection: 2025 = construction (capex > 0, revenue = 0)
- Test that revenue in construction phase gets flagged

**File 06 (LDES — missing depreciation):**
```python
# EBIT = EBITDA (no depreciation)
values = {
    "ebitda": Decimal("3200000"),
    "ebit": Decimal("3200000"),  # Should differ by depreciation
    "depreciation_and_amortization": Decimal("0"),  # Missing!
    "capex": Decimal("28500000"),  # Significant capex → depreciation expected
}
```
- Test derivation: ebit = ebitda - depreciation_and_amortization
- If depreciation is 0 but capex is large, should flag

**File 08 (Geothermal — interco):**
```python
# Consolidation without interco elimination
spv_revenue = Decimal("8000000")
holdco_revenue = Decimal("2000000")  # Includes interco royalties
consolidated_revenue = Decimal("10000000")  # Should be less after elimination
```
- Cross-entity validation: consolidated ≠ sum of parts (elimination required)

**File 09 (CCUS — fully hardcoded):**
- Test that formula_count = 0 is detectable as structural concern
- Test that mixed currencies (EUR + GBP) are flagged

**General validation tests:**
- Must_be_positive: revenue, total_assets, total_liabilities
- Sign convention: expenses typically negative, assets typically positive
- Derivation: gross_profit = revenue - cogs (within tolerance)
- Derivation: ebitda = operating_income + depreciation_and_amortization
- Cross-statement: retained_earnings change ≈ net_income
- Balance sheet identity: total_assets = total_liabilities + total_equity

### Category 8: Lifecycle Detection

Using data patterns from the real files:

**File 01 (Electrolyser):** Has construction + operations phases. Revenue starts from a specific year.
**File 03 (Heat Pump):** Monthly data — lifecycle detection on monthly periods.
**File 04 (DAC):** Pre-revenue model → should detect construction phase clearly (capex + zero revenue).
**File 09 (CCUS):** Column C is "Construction" → detect construction phase.

Test:
- `LifecycleDetector.detect()` with multi-period data from each file pattern
- Correct phase assignment: construction periods have capex + no revenue
- is_project_finance = True for files 01-09, False for file 10 (manufacturing)
- Flag suppression: construction-phase items shouldn't trigger must_be_positive for revenue

### Category 9: Completeness & Quality Scoring

**Model type detection:**
- Files 01-09: should detect as "project_finance" (contain PF indicators)
- File 10: should detect as "corporate" or "standard_3_statement"
- File 06: should NOT detect as "saas" despite having SaaS metrics (they're applied incorrectly to PF)

**Completeness templates:**
- Project finance model → expect: revenue, capex, debt_service, dscr, ebitda at minimum
- Corporate model (File 10) → expect: revenue, cogs, gross_profit, opex, ebitda, net_income

**Quality scoring:**
- Test that model_type_weights are applied correctly (PF vs corporate vs construction_only)
- Test grade boundaries: A ≥ 0.9, B ≥ 0.75, C ≥ 0.6, D ≥ 0.45, F < 0.45
- Test quality_gate: grade F → NEEDS_REVIEW

### Category 10: Markdown Conversion Fidelity

For each file, run `_structured_to_markdown()` on the structured repr and verify:

- Markdown is non-empty
- Contains period headers (years/quarters/months)
- Contains financial labels
- Table is parseable (consistent column count per row)
- No crashes on special characters, German labels, or empty cells
- Merged cell values are propagated (not showing as empty)
- Format annotations present (currency, percentage columns)
- Type column present (I/F/L/V for input/formula/label/value)
- Unit annotation line present if units detected

### Category 11: Edge Case Resilience

**Empty/placeholder sheets:**
- File 05 Debt_DSCR (empty) → parsing returns sheet with 0 or 1 rows, no crash
- File 04 Debt_DSRA (N/A placeholder) → parsing extracts N/A values, triage should classify as tier 4

**Pseudo-formulas (File 06):**
- String values that look like formulas: `=ARR/12 -- meaningless for storage dispatch`
- Should be extracted as STRING values, NOT as formulas

**Wide sheets (Files 05, 07):**
- 39+ columns → no truncation, all data extracted
- Separator columns (gap between scenarios) handled gracefully

**Hidden rows (File 06):**
- Rows 1-15 hidden but contain values → values MUST be extracted
- Sheet state detection: verify hidden row values are accessible

**Mixed frequencies (File 10):**
- Same sheet has quarterly AND annual columns
- Period parser should identify mixed periodicity
- No crash or data corruption at the boundary

**Multi-currency (Files 02, 07, 09):**
- EUR + USD in same model
- EUR + GBP + $ in File 09
- Unit detection should flag mixed currencies

**Fiscal years (File 09):**
- FY26/27 format → PeriodParser must handle slash notation
- Not calendar year 2026 or 2027

### Category 12: Regression Guards

Tests that verify existing functionality doesn't break:

- All 10 files can be loaded as bytes without error
- `_excel_to_structured_repr()` completes without exception for all 10
- `_structured_to_markdown()` produces valid markdown for all 10
- PeriodParser doesn't crash on any header value from any file
- SectionDetector doesn't crash on any sheet from any file
- `_build_sheet_summary()` produces valid dict for all sheets across all files
- `_rule_based_triage()` returns None or valid tier (1-4) for all sheet names
- AccountingValidator doesn't crash on empty values dict
- CompletenessScorer returns valid model type for any input
- QualityScorer returns valid grade (A-F) for any score 0.0-1.0

## Test File Structure

```
tests/unit/test_real_excel_audit.py
├── class TestRawStructuralExtraction
│   ├── test_file01_single_sheet_structure
│   ├── test_file01_formula_detection
│   ├── test_file01_font_color_extraction
│   ├── test_file01_merged_cells
│   ├── test_file02_four_sheets
│   ├── test_file02_transposed_modell
│   ├── test_file02_german_labels
│   ├── test_file02_formula_extraction
│   ├── test_file03_monthly_columns
│   ├── test_file03_cross_sheet_formulas
│   ├── test_file04_nine_tabs
│   ├── test_file04_cross_tab_formulas
│   ├── test_file04_debt_placeholder
│   ├── test_file05_three_scenarios_wide
│   ├── test_file05_empty_debt_sheet
│   ├── test_file06_hidden_rows_accessible
│   ├── test_file06_pseudo_formulas_as_strings
│   ├── test_file06_color_coding
│   ├── test_file07_three_scenarios_plus_curves
│   ├── test_file07_commodity_curves_transposed
│   ├── test_file07_debt_tranches_formulas
│   ├── test_file08_holdco_spv_three_sheets
│   ├── test_file08_dual_header_holdco
│   ├── test_file09_zero_formulas
│   ├── test_file09_fiscal_year_headers
│   ├── test_file09_mixed_currencies
│   ├── test_file10_mixed_periodicity
│   ├── test_file10_column_separator
│   ├── test_file10_order_backlog_transposed
│   └── test_file10_covenant_tracker
├── class TestPeriodDetection
│   ├── test_standard_annual_periods (Files 01, 04, 08)
│   ├── test_transposed_periods (File 02 Modell)
│   ├── test_monthly_periods (File 03)
│   ├── test_scenario_repeated_periods (Files 05, 07)
│   ├── test_fiscal_year_periods (File 09)
│   ├── test_mixed_quarterly_annual (File 10)
│   ├── test_construction_label_not_period (File 09)
│   └── test_all_files_no_crash
├── class TestSectionDetection
│   ├── test_single_sheet_sections (File 01)
│   ├── test_transposed_sections (File 02)
│   ├── test_saas_vs_pf_sections (File 06)
│   ├── test_holdco_spv_sections (File 08)
│   └── test_all_sheets_no_crash
├── class TestLayoutDetection
│   ├── test_label_column_detection
│   ├── test_header_row_detection
│   ├── test_transposition_detection
│   ├── test_unit_detection
│   └── test_table_region_detection
├── class TestRuleBasedTriage
│   ├── test_known_sheet_names
│   ├── test_german_sheet_names
│   ├── test_empty_sheet_classification
│   ├── test_sheet_summary_generation
│   └── test_all_sheets_no_crash
├── class TestTaxonomyAliasCoverage
│   ├── test_common_labels_resolve
│   ├── test_german_labels
│   ├── test_project_finance_labels
│   ├── test_saas_labels
│   ├── test_label_normalization
│   └── test_no_conflicting_aliases_across_categories
├── class TestValidationRules
│   ├── test_gross_profit_derivation
│   ├── test_ebitda_derivation
│   ├── test_balance_sheet_identity
│   ├── test_sign_conventions
│   ├── test_cross_statement_cash
│   ├── test_missing_depreciation_flag
│   └── test_lifecycle_flag_suppression
├── class TestLifecycleDetection
│   ├── test_construction_phase
│   ├── test_operations_phase
│   ├── test_pre_revenue
│   ├── test_corporate_no_lifecycle
│   └── test_is_project_finance
├── class TestCompletenessAndQuality
│   ├── test_model_type_detection
│   ├── test_pf_completeness_template
│   ├── test_corporate_completeness_template
│   ├── test_quality_grade_boundaries
│   └── test_quality_gate_needs_review
├── class TestMarkdownConversion
│   ├── test_all_files_produce_valid_markdown
│   ├── test_markdown_contains_periods
│   ├── test_markdown_table_consistency
│   ├── test_german_labels_in_markdown
│   └── test_merged_cells_propagated
├── class TestEdgeCaseResilience
│   ├── test_empty_sheet_handling
│   ├── test_placeholder_sheet_handling
│   ├── test_wide_sheet_no_truncation
│   ├── test_hidden_rows_extracted
│   ├── test_mixed_frequency_no_crash
│   └── test_multi_currency_flagged
└── class TestRegressionGuards
    ├── test_all_files_loadable
    ├── test_all_files_structured_repr
    ├── test_all_files_markdown
    ├── test_all_period_headers_parseable
    ├── test_all_sections_detectable
    └── test_empty_inputs_no_crash
```

## Implementation Constraints

1. **No Claude calls** — mock ALL LLM interactions. Tests are 100% deterministic.
2. **Use real file bytes** — load from `tests/real data/`, skip gracefully if directory missing.
3. **Test deterministic code paths only** — don't test what Claude returns, test what Python computes.
4. **Each test is independent** — no test ordering dependencies.
5. **Clear assertions** — every test must have at least one assert. Use descriptive assertion messages.
6. **Skip missing files gracefully** — use `pytest.skip()` if real data not available (CI may not have them).
7. **Performance** — individual tests should complete in <5 seconds. The entire suite in <60 seconds.
8. **Follow existing patterns** — look at `tests/unit/test_excel_parsing.py` for the _make_minimal_xlsx helper pattern. For real files, just load bytes directly.
9. **Mark with custom marker** — add `@pytest.mark.realdata` to all tests so they can be selectively run/skipped.
10. **Handle import errors gracefully** — if a function doesn't exist (e.g., _detect_label_column not yet implemented), skip with a clear message rather than failing the entire module.

## Expected Deliverables

1. `tests/unit/test_real_excel_audit.py` — comprehensive test file (200+ test cases)
2. `conftest.py` additions if needed (e.g., `realdata` marker registration)
3. Run the FULL test suite (`pytest tests/ -x -q`) and report results
4. List any pipeline bugs discovered (code that crashes or produces wrong output on real data)
5. List any missing features discovered (functions referenced but not implemented)

## Success Criteria

- 200+ new test cases covering all 12 categories
- All tests pass (or are properly skipped if dependencies missing)
- Zero crashes when processing any of the 10 real files through deterministic pipeline stages
- Existing 1800+ tests still pass
- Test file is well-organized with clear class/method names
- Every structural challenge from the ERROR_MANIFEST is covered by at least one test
- Every deterministic validation rule is tested with data patterns from real files

## Final Note

This is not a "write tests that pass" exercise. This is a "find where the pipeline breaks on real data" exercise. If a test reveals that `_detect_transposed_layout()` returns False for File 02's transposed Modell sheet, that's a VALUABLE finding — document it with `pytest.xfail("Transposition detection doesn't handle German transposed models yet")` and move on. The goal is to map the gap between what we built and what real data demands.
