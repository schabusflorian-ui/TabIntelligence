"""Tests for check_period_consistency() — cross-sheet period validation."""

from src.extraction.period_parser import check_period_consistency


class TestBasicBehavior:
    """Edge cases and basic behavior."""

    def test_empty_dict_returns_empty(self):
        assert check_period_consistency({}) == []

    def test_single_sheet_returns_empty(self):
        result = check_period_consistency(
            {
                "Sheet1": {
                    "dominant_type": "fiscal_year",
                    "periods": [],
                    "layout": "time_across_columns",
                },
            }
        )
        assert result == []

    def test_consistent_sheets_no_warnings(self):
        result = check_period_consistency(
            {
                "Sheet1": {
                    "dominant_type": "fiscal_year",
                    "periods": [{"year": 2023}, {"year": 2024}],
                    "layout": "time_across_columns",
                },
                "Sheet2": {
                    "dominant_type": "fiscal_year",
                    "periods": [{"year": 2023}, {"year": 2024}],
                    "layout": "time_across_columns",
                },
            }
        )
        assert result == []


class TestMismatchedType:
    """Check 1: Mismatched dominant_type across sheets."""

    def test_different_types_produces_warning(self):
        result = check_period_consistency(
            {
                "Income": {
                    "dominant_type": "fiscal_year",
                    "periods": [{"year": 2023}],
                    "layout": "time_across_columns",
                },
                "CashFlow": {
                    "dominant_type": "quarterly",
                    "periods": [{"year": 2023}],
                    "layout": "time_across_columns",
                },
            }
        )
        assert len(result) == 1
        assert result[0]["type"] == "mismatched_period_type"
        assert result[0]["severity"] == "warning"

    def test_unknown_type_ignored(self):
        """Sheets with 'unknown' type are excluded from mismatch check."""
        result = check_period_consistency(
            {
                "Sheet1": {
                    "dominant_type": "fiscal_year",
                    "periods": [{"year": 2023}],
                    "layout": "time_across_columns",
                },
                "Sheet2": {
                    "dominant_type": "unknown",
                    "periods": [],
                    "layout": "time_across_columns",
                },
            }
        )
        # Only one unique non-unknown type → no warning
        assert not any(w["type"] == "mismatched_period_type" for w in result)


class TestCoverageGaps:
    """Check 2: Period coverage gaps between sheets."""

    def test_missing_years_flagged(self):
        result = check_period_consistency(
            {
                "Sheet1": {
                    "dominant_type": "fiscal_year",
                    "periods": [{"year": 2022}, {"year": 2023}, {"year": 2024}],
                    "layout": "time_across_columns",
                },
                "Sheet2": {
                    "dominant_type": "fiscal_year",
                    "periods": [{"year": 2023}],
                    "layout": "time_across_columns",
                },
            }
        )
        gap_warnings = [w for w in result if w["type"] == "period_coverage_gap"]
        assert len(gap_warnings) == 1
        assert gap_warnings[0]["details"]["sheet"] == "Sheet2"
        assert set(gap_warnings[0]["details"]["missing_years"]) == {2022, 2024}


class TestLayoutInconsistency:
    """Check 3: Layout inconsistency across sheets."""

    def test_different_layouts_flagged(self):
        result = check_period_consistency(
            {
                "Sheet1": {
                    "dominant_type": "fiscal_year",
                    "periods": [{"year": 2023}],
                    "layout": "time_across_columns",
                },
                "Sheet2": {
                    "dominant_type": "fiscal_year",
                    "periods": [{"year": 2023}],
                    "layout": "time_down_rows",
                },
            }
        )
        layout_warnings = [w for w in result if w["type"] == "layout_inconsistency"]
        assert len(layout_warnings) == 1
        assert layout_warnings[0]["severity"] == "info"


class TestMissingFields:
    """Graceful handling of missing/unexpected fields."""

    def test_missing_dominant_type_no_crash(self):
        result = check_period_consistency(
            {
                "Sheet1": {"periods": [{"year": 2023}], "layout": "time_across_columns"},
                "Sheet2": {"periods": [{"year": 2023}], "layout": "time_across_columns"},
            }
        )
        # Should not crash; dominant_type defaults to "unknown"
        assert isinstance(result, list)

    def test_missing_periods_no_crash(self):
        result = check_period_consistency(
            {
                "Sheet1": {"dominant_type": "fiscal_year", "layout": "time_across_columns"},
                "Sheet2": {"dominant_type": "fiscal_year", "layout": "time_across_columns"},
            }
        )
        assert isinstance(result, list)

    def test_missing_layout_no_crash(self):
        result = check_period_consistency(
            {
                "Sheet1": {"dominant_type": "fiscal_year", "periods": [{"year": 2023}]},
                "Sheet2": {"dominant_type": "fiscal_year", "periods": [{"year": 2023}]},
            }
        )
        assert isinstance(result, list)
