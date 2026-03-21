"""Tests for the benchmarking accuracy engine."""

import pytest

from src.benchmarking.accuracy import (
    MappingAccuracyResult,
    ValueAccuracyResult,
    StageAttributionResult,
    TriageAccuracyResult,
    FullEvaluationResult,
    evaluate_mapping_accuracy,
    evaluate_value_accuracy,
    evaluate_triage_accuracy,
    attribute_errors_to_stages,
    run_full_evaluation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_gold():
    """Simple gold standard with 5 mappings across 2 sheets."""
    return {
        "expected_triage": [
            {"sheet_name": "Income Statement", "tier": 1, "decision": "PROCESS_HIGH"},
            {"sheet_name": "Balance Sheet", "tier": 1, "decision": "PROCESS_HIGH"},
            {"sheet_name": "Notes", "tier": 4, "decision": "SKIP"},
        ],
        "expected_mappings": [
            {"original_label": "Revenue", "canonical_name": "revenue", "sheet": "Income Statement"},
            {"original_label": "COGS", "canonical_name": "cogs", "sheet": "Income Statement"},
            {"original_label": "Net Income", "canonical_name": "net_income", "sheet": "Income Statement"},
            {"original_label": "Total Assets", "canonical_name": "total_assets", "sheet": "Balance Sheet"},
            {"original_label": "Total Equity", "canonical_name": "total_equity", "sheet": "Balance Sheet"},
        ],
        "acceptable_alternatives": {
            "revenue": ["revenue", "net_revenue"],
            "cogs": ["cogs", "cost_of_sales"],
            "net_income": ["net_income", "net_profit"],
            "total_assets": ["total_assets"],
            "total_equity": ["total_equity", "shareholders_equity"],
        },
        "expected_values": {
            "revenue": {
                "FY2024": {"value": 1000, "tolerance_pct": 1.0, "tolerance_abs": 10},
                "FY2025": {"value": 1200, "tolerance_pct": 1.0, "tolerance_abs": 12},
            },
            "net_income": {
                "FY2024": {"value": 200, "tolerance_pct": 1.0, "tolerance_abs": 2},
                "FY2025": {"value": 250, "tolerance_pct": 1.0, "tolerance_abs": 2.5},
            },
        },
    }


@pytest.fixture
def perfect_result():
    """Extraction result that perfectly matches the gold standard."""
    return {
        "triage": [
            {"sheet_name": "Income Statement", "tier": 1},
            {"sheet_name": "Balance Sheet", "tier": 1},
            {"sheet_name": "Notes", "tier": 4},
        ],
        "line_items": [
            {"original_label": "Revenue", "canonical_name": "revenue", "sheet": "Income Statement",
             "confidence": 0.95, "values": {"FY2024": 1000, "FY2025": 1200}},
            {"original_label": "COGS", "canonical_name": "cogs", "sheet": "Income Statement",
             "confidence": 0.90, "values": {"FY2024": -600, "FY2025": -700}},
            {"original_label": "Net Income", "canonical_name": "net_income", "sheet": "Income Statement",
             "confidence": 0.92, "values": {"FY2024": 200, "FY2025": 250}},
            {"original_label": "Total Assets", "canonical_name": "total_assets", "sheet": "Balance Sheet",
             "confidence": 0.88, "values": {}},
            {"original_label": "Total Equity", "canonical_name": "total_equity", "sheet": "Balance Sheet",
             "confidence": 0.85, "values": {}},
        ],
    }


@pytest.fixture
def imperfect_result():
    """Extraction result with some mismatches and missing items."""
    return {
        "triage": [
            {"sheet_name": "Income Statement", "tier": 1},
            {"sheet_name": "Balance Sheet", "tier": 2},  # Wrong tier
            {"sheet_name": "Notes", "tier": 4},
        ],
        "line_items": [
            {"original_label": "Revenue", "canonical_name": "revenue", "sheet": "Income Statement",
             "confidence": 0.95, "values": {"FY2024": 1000, "FY2025": 1200},
             "provenance": {"mapping": {"stage": "stage_3", "method": "embedding"}}},
            {"original_label": "COGS", "canonical_name": "operating_expenses", "sheet": "Income Statement",
             "confidence": 0.70, "values": {"FY2024": -600, "FY2025": -700},
             "provenance": {"mapping": {"stage": "stage_3", "method": "claude"}}},
            # Net Income is missing (not extracted)
            {"original_label": "Total Assets", "canonical_name": "total_assets", "sheet": "Balance Sheet",
             "confidence": 0.88, "values": {}},
            {"original_label": "Total Equity", "canonical_name": "unmapped", "sheet": "Balance Sheet",
             "confidence": 0.0, "values": {}},
        ],
    }


# ---------------------------------------------------------------------------
# Mapping Accuracy Tests
# ---------------------------------------------------------------------------

class TestMappingAccuracy:

    def test_perfect_mapping(self, simple_gold, perfect_result):
        result = evaluate_mapping_accuracy(perfect_result, simple_gold)

        assert result.true_positives == 5
        assert result.false_positives == 0
        assert result.false_negatives == 0
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1 == 1.0

    def test_imperfect_mapping(self, simple_gold, imperfect_result):
        result = evaluate_mapping_accuracy(imperfect_result, simple_gold)

        # Revenue: correct (TP)
        # COGS: mapped to operating_expenses, not in acceptable alts → FP + FN
        # Net Income: missing → FN
        # Total Assets: correct (TP)
        # Total Equity: unmapped → FN
        assert result.true_positives == 2
        assert result.false_negatives == 3  # COGS mismatch + Net Income missing + Total Equity unmapped
        assert result.unmapped_count == 2  # Net Income + Total Equity
        assert len(result.mismatches) == 1  # COGS
        assert len(result.missing) == 2  # Net Income + Total Equity

    def test_acceptable_alternatives(self, simple_gold):
        """Test that acceptable alternatives are recognized as correct."""
        extraction = {
            "line_items": [
                {"original_label": "Revenue", "canonical_name": "net_revenue", "sheet": "IS"},
                {"original_label": "COGS", "canonical_name": "cost_of_sales", "sheet": "IS"},
                {"original_label": "Net Income", "canonical_name": "net_profit", "sheet": "IS"},
                {"original_label": "Total Assets", "canonical_name": "total_assets", "sheet": "BS"},
                {"original_label": "Total Equity", "canonical_name": "shareholders_equity", "sheet": "BS"},
            ],
        }

        result = evaluate_mapping_accuracy(extraction, simple_gold)
        assert result.true_positives == 5
        assert result.f1 == 1.0

    def test_empty_extraction(self, simple_gold):
        result = evaluate_mapping_accuracy({"line_items": []}, simple_gold)

        assert result.true_positives == 0
        assert result.false_negatives == 5
        assert result.recall == 0.0
        assert result.precision == 0.0
        assert result.f1 == 0.0

    def test_empty_gold(self):
        result = evaluate_mapping_accuracy(
            {"line_items": [{"original_label": "Revenue", "canonical_name": "revenue"}]},
            {"expected_mappings": [], "acceptable_alternatives": {}},
        )
        assert result.total_expected == 0
        assert result.f1 == 0.0

    def test_per_sheet_breakdown(self, simple_gold, imperfect_result):
        result = evaluate_mapping_accuracy(imperfect_result, simple_gold)

        assert "Income Statement" in result.per_sheet
        assert "Balance Sheet" in result.per_sheet

        is_stats = result.per_sheet["Income Statement"]
        assert is_stats["true_positives"] == 1  # Revenue
        assert is_stats["total"] == 3

        bs_stats = result.per_sheet["Balance Sheet"]
        assert bs_stats["true_positives"] == 1  # Total Assets
        assert bs_stats["total"] == 2

    def test_per_category_breakdown(self, simple_gold, perfect_result):
        result = evaluate_mapping_accuracy(perfect_result, simple_gold)

        assert "income_statement" in result.per_category
        assert "balance_sheet" in result.per_category
        assert result.per_category["income_statement"]["true_positives"] == 3
        assert result.per_category["balance_sheet"]["true_positives"] == 2

    def test_to_dict(self, simple_gold, perfect_result):
        result = evaluate_mapping_accuracy(perfect_result, simple_gold)
        d = result.to_dict()

        assert "precision" in d
        assert "recall" in d
        assert "f1" in d
        assert "per_sheet" in d
        assert "per_category" in d
        assert d["precision"] == 1.0
        assert d["f1"] == 1.0


# ---------------------------------------------------------------------------
# Value Accuracy Tests
# ---------------------------------------------------------------------------

class TestValueAccuracy:

    def test_perfect_values(self, simple_gold, perfect_result):
        result = evaluate_value_accuracy(perfect_result, simple_gold)

        assert result.exact_matches == 4  # 2 periods * 2 canonical names
        assert result.tolerance_matches == 4
        assert result.total_compared == 4
        assert result.exact_match_rate == 1.0
        assert result.mae == 0.0

    def test_within_tolerance(self, simple_gold):
        """Values within tolerance should be tolerance_matches but not exact."""
        extraction = {
            "line_items": [
                {"canonical_name": "revenue", "values": {"FY2024": 1005, "FY2025": 1208}},
                {"canonical_name": "net_income", "values": {"FY2024": 201, "FY2025": 251}},
            ],
        }

        result = evaluate_value_accuracy(extraction, simple_gold)

        # 1005 vs 1000: 0.5% error, within 1% tol → tolerance match
        # 1208 vs 1200: 0.67% error, within 1% tol → tolerance match
        # 201 vs 200: 0.5% error, within 1% tol → tolerance match
        # 251 vs 250: 0.4% error, within 1% tol → tolerance match
        assert result.tolerance_matches == 4
        assert result.exact_matches == 0  # None are exact
        assert result.total_compared == 4

    def test_outside_tolerance(self, simple_gold):
        """Values outside tolerance should be errors."""
        extraction = {
            "line_items": [
                {"canonical_name": "revenue", "values": {"FY2024": 1100, "FY2025": 1200}},
                {"canonical_name": "net_income", "values": {"FY2024": 200, "FY2025": 250}},
            ],
        }

        result = evaluate_value_accuracy(extraction, simple_gold)

        # 1100 vs 1000: 10% error, > 1% and > abs 10 → error
        # FY2025 revenue exact, FY2024 net_income exact, FY2025 net_income exact
        assert result.exact_matches == 3
        assert len(result.errors) == 1  # FY2024 revenue

    def test_missing_values(self, simple_gold):
        """Missing canonical names should be noted."""
        extraction = {
            "line_items": [
                {"canonical_name": "revenue", "values": {"FY2024": 1000}},
                # net_income not extracted at all
            ],
        }

        result = evaluate_value_accuracy(extraction, simple_gold)

        # Only FY2024 revenue compared; FY2025 revenue missing; both net_income missing
        assert result.total_compared == 1
        assert result.total_expected == 4

    def test_no_expected_values(self):
        """Gold standard without expected_values should return empty result."""
        result = evaluate_value_accuracy(
            {"line_items": [{"canonical_name": "revenue", "values": {"FY2024": 1000}}]},
            {"expected_values": {}},
        )
        assert result.total_expected == 0
        assert result.exact_match_rate == 0.0

    def test_to_dict(self, simple_gold, perfect_result):
        result = evaluate_value_accuracy(perfect_result, simple_gold)
        d = result.to_dict()

        assert "exact_match_rate" in d
        assert "tolerance_match_rate" in d
        assert "mae" in d
        assert "mape" in d


# ---------------------------------------------------------------------------
# Triage Accuracy Tests
# ---------------------------------------------------------------------------

class TestTriageAccuracy:

    def test_perfect_triage(self, simple_gold, perfect_result):
        result = evaluate_triage_accuracy(perfect_result, simple_gold)

        assert result.correct == 3
        assert result.total == 3
        assert result.accuracy == 1.0

    def test_imperfect_triage(self, simple_gold, imperfect_result):
        result = evaluate_triage_accuracy(imperfect_result, simple_gold)

        assert result.correct == 2  # IS correct, BS wrong tier, Notes correct
        assert result.total == 3
        assert abs(result.accuracy - 2 / 3) < 0.001

    def test_empty_triage(self, simple_gold):
        result = evaluate_triage_accuracy({"triage": []}, simple_gold)

        assert result.correct == 0
        assert result.total == 3
        assert result.accuracy == 0.0

    def test_to_dict(self, simple_gold, perfect_result):
        result = evaluate_triage_accuracy(perfect_result, simple_gold)
        d = result.to_dict()
        assert d["accuracy"] == 1.0
        assert len(d["details"]) == 3


# ---------------------------------------------------------------------------
# Stage Attribution Tests
# ---------------------------------------------------------------------------

class TestStageAttribution:

    def test_no_errors(self, simple_gold, perfect_result):
        result = attribute_errors_to_stages(perfect_result, simple_gold)
        assert result.total_errors == 0

    def test_mapping_error(self, simple_gold, imperfect_result):
        result = attribute_errors_to_stages(imperfect_result, simple_gold)

        # COGS mapped wrong → mapping error
        # Net Income missing → parsing error (not in line_items)
        # Total Equity unmapped → mapping error
        assert result.total_errors == 3
        assert result.mapping_errors >= 2  # COGS + Total Equity

    def test_triage_error(self, simple_gold):
        """Sheet skipped that shouldn't have been → triage error."""
        extraction = {
            "triage": [
                {"sheet_name": "Income Statement", "tier": 4},  # Skipped IS!
                {"sheet_name": "Balance Sheet", "tier": 1},
                {"sheet_name": "Notes", "tier": 4},
            ],
            "line_items": [
                {"original_label": "Total Assets", "canonical_name": "total_assets"},
                {"original_label": "Total Equity", "canonical_name": "total_equity"},
            ],
        }

        result = attribute_errors_to_stages(extraction, simple_gold)

        # Revenue, COGS, Net Income: sheet IS was skipped → triage errors
        triage_details = [d for d in result.details if d["stage"] == "triage"]
        assert len(triage_details) == 3
        assert result.triage_errors == 3

    def test_parsing_error(self, simple_gold):
        """Label not extracted from Excel at all → parsing error."""
        extraction = {
            "triage": [
                {"sheet_name": "Income Statement", "tier": 1},
                {"sheet_name": "Balance Sheet", "tier": 1},
                {"sheet_name": "Notes", "tier": 4},
            ],
            "line_items": [
                {"original_label": "Revenue", "canonical_name": "revenue"},
                {"original_label": "COGS", "canonical_name": "cogs"},
                # Net Income never parsed
                {"original_label": "Total Assets", "canonical_name": "total_assets"},
                {"original_label": "Total Equity", "canonical_name": "total_equity"},
            ],
        }

        result = attribute_errors_to_stages(extraction, simple_gold)

        assert result.parsing_errors == 1
        parsing_details = [d for d in result.details if d["stage"] == "parsing"]
        assert parsing_details[0]["label"] == "Net Income"

    def test_enhanced_mapping_error(self, simple_gold):
        """Wrong mapping from Stage 4 enhanced mapping."""
        extraction = {
            "triage": [
                {"sheet_name": "Income Statement", "tier": 1},
                {"sheet_name": "Balance Sheet", "tier": 1},
                {"sheet_name": "Notes", "tier": 4},
            ],
            "line_items": [
                {"original_label": "Revenue", "canonical_name": "revenue"},
                {"original_label": "COGS", "canonical_name": "wrong_name",
                 "provenance": {"mapping": {"stage": "enhanced_mapping", "method": "claude"}}},
                {"original_label": "Net Income", "canonical_name": "net_income"},
                {"original_label": "Total Assets", "canonical_name": "total_assets"},
                {"original_label": "Total Equity", "canonical_name": "total_equity"},
            ],
        }

        result = attribute_errors_to_stages(extraction, simple_gold)

        assert result.enhanced_mapping_errors == 1
        assert result.total_errors == 1

    def test_to_dict(self, simple_gold, imperfect_result):
        result = attribute_errors_to_stages(imperfect_result, simple_gold)
        d = result.to_dict()

        assert "parsing_errors" in d
        assert "mapping_errors" in d
        assert "attribution" in d
        assert "mapping_pct" in d["attribution"]


# ---------------------------------------------------------------------------
# Full Evaluation Tests
# ---------------------------------------------------------------------------

class TestFullEvaluation:

    def test_perfect_evaluation(self, simple_gold, perfect_result):
        result = run_full_evaluation(perfect_result, simple_gold)

        assert isinstance(result, FullEvaluationResult)
        assert result.mapping.f1 == 1.0
        assert result.triage.accuracy == 1.0
        assert result.values.exact_match_rate == 1.0
        assert result.stage_attribution.total_errors == 0

    def test_imperfect_evaluation(self, simple_gold, imperfect_result):
        result = run_full_evaluation(imperfect_result, simple_gold)

        assert result.mapping.f1 < 1.0
        assert result.triage.accuracy < 1.0
        assert result.stage_attribution.total_errors > 0

    def test_to_dict_structure(self, simple_gold, perfect_result):
        result = run_full_evaluation(perfect_result, simple_gold)
        d = result.to_dict()

        assert "mapping" in d
        assert "values" in d
        assert "triage" in d
        assert "stage_attribution" in d
        assert "summary" in d
        assert d["summary"]["mapping_f1"] == 1.0

    def test_empty_extraction(self, simple_gold):
        result = run_full_evaluation({"triage": [], "line_items": []}, simple_gold)

        assert result.mapping.f1 == 0.0
        assert result.triage.accuracy == 0.0
        assert result.values.total_compared == 0


# ---------------------------------------------------------------------------
# Dataclass Property Tests
# ---------------------------------------------------------------------------

class TestDataclassProperties:

    def test_mapping_result_defaults(self):
        r = MappingAccuracyResult()
        assert r.precision == 0.0
        assert r.recall == 0.0
        assert r.f1 == 0.0
        assert r.accuracy == 0.0

    def test_value_result_defaults(self):
        r = ValueAccuracyResult()
        assert r.exact_match_rate == 0.0
        assert r.tolerance_match_rate == 0.0
        assert r.mae == 0.0
        assert r.mape == 0.0

    def test_triage_result_defaults(self):
        r = TriageAccuracyResult()
        assert r.accuracy == 0.0

    def test_stage_attribution_defaults(self):
        r = StageAttributionResult()
        d = r.to_dict()
        assert d["total_errors"] == 0
        assert d["attribution"]["mapping_pct"] == 0.0
