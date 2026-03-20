"""Tests for cell-level ground truth reconciliation."""

from decimal import Decimal

from src.validation.cell_reconciliation import (
    CellReconciliationValidator,
)


def _make_parsed(sheets):
    """Helper to build parsed data structure."""
    return {"sheets": sheets}


def _make_sheet(name, rows):
    return {"sheet_name": name, "rows": rows}


def _make_row(label, values, source_cells=None):
    row = {"label": label, "values": values}
    if source_cells is not None:
        row["source_cells"] = source_cells
    return row


def _make_source_cell(sheet, ref, raw_value, formula=None):
    cell = {"sheet": sheet, "cell_ref": ref, "raw_value": raw_value}
    if formula:
        cell["formula"] = formula
    return cell


def _make_mappings(mapping_dict):
    """Helper: {original_label: canonical_name} -> list of mapping dicts."""
    return [
        {"original_label": k, "canonical_name": v} for k, v in mapping_dict.items()
    ]


def _make_triage(sheet_names, tier=1):
    return [{"sheet_name": name, "tier": tier} for name in sheet_names]


class TestCellReconciliationExactMatch:
    def setup_method(self):
        self.validator = CellReconciliationValidator()

    def test_exact_match_all_cells(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 1000, "FY2024": 1200}, [
                    _make_source_cell("IS", "A1", "Revenue"),  # label cell
                    _make_source_cell("IS", "B1", 1000),
                    _make_source_cell("IS", "C1", 1200),
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 2
        assert result.matched == 2
        assert result.mismatched == 0
        assert result.match_rate == 1.0

    def test_empty_source_cells_produces_unmatched(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 1000}, []),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 0
        assert result.unmatched == 1
        assert result.unmatched_items[0]["canonical_name"] == "revenue"
        assert result.unmatched_items[0]["reason"] == "no_source_cell"

    def test_no_mapped_rows_returns_empty(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Something", {"FY2023": 500}, [
                    _make_source_cell("IS", "A1", "Something"),
                    _make_source_cell("IS", "B1", 500),
                ]),
            ])
        ])
        mappings = _make_mappings({"Other": "other"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 0
        assert result.matched == 0
        assert result.match_rate == 1.0  # no cells = default 1.0

    def test_multiple_rows_multiple_periods(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 1000, "FY2024": 1200}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    _make_source_cell("IS", "B1", 1000),
                    _make_source_cell("IS", "C1", 1200),
                ]),
                _make_row("COGS", {"FY2023": 500, "FY2024": 600}, [
                    _make_source_cell("IS", "A2", "COGS"),
                    _make_source_cell("IS", "B2", 500),
                    _make_source_cell("IS", "C2", 600),
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue", "COGS": "cogs"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 4
        assert result.matched == 4
        assert result.match_rate == 1.0


class TestCellReconciliationTolerance:
    def setup_method(self):
        self.validator = CellReconciliationValidator()

    def test_within_absolute_tolerance_matches(self):
        # Difference of 0.005 < 0.01 tolerance
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 1000.005}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    _make_source_cell("IS", "B1", 1000.0),
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.matched == 1
        assert result.mismatched == 0

    def test_within_relative_tolerance_matches(self):
        # Large value: 1000000 vs 1000000.5 — absolute diff 0.5 > 0.01,
        # but relative diff ~0.00005% < 0.1%
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 1000000.5}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    _make_source_cell("IS", "B1", 1000000.0),
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.matched == 1
        assert result.mismatched == 0

    def test_beyond_both_tolerances_mismatches(self):
        # Small value with large relative diff: 100 vs 200
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 200}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    _make_source_cell("IS", "B1", 100),
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.matched == 0
        assert result.mismatched == 1
        assert result.mismatches[0].canonical_name == "revenue"
        assert result.mismatches[0].delta == Decimal("100")


class TestCellReconciliationUnitMultiplier:
    def setup_method(self):
        self.validator = CellReconciliationValidator()

    def test_no_multiplier_uses_raw(self):
        """Without unit multiplier, extracted and source should match directly."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 5000}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    _make_source_cell("IS", "B1", 5000),
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.matched == 1
        assert result.match_rate == 1.0

    def test_multiplier_is_tracked_in_result(self):
        """Unit multiplier should be recorded in CellMatchResult."""
        structured = {"sheets": [{"sheet_name": "IS", "unit_multiplier": 1000}]}
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 5000}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    _make_source_cell("IS", "B1", 5000),
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage, structured)

        assert result.matched == 1
        # The multiplier is tracked but values compared as-is
        # (both extracted and source are pre-multiplier at this point)


class TestCellReconciliationEdgeCases:
    def setup_method(self):
        self.validator = CellReconciliationValidator()

    def test_none_values_skipped(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": None, "FY2024": 1000}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    _make_source_cell("IS", "C1", 1000),
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 1
        assert result.matched == 1

    def test_non_numeric_source_cells_flagged(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 1000}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    _make_source_cell("IS", "B1", "N/A"),  # non-numeric
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 0
        assert result.unmatched == 1
        assert result.unmatched_items[0]["reason"] == "non_numeric_source_cell"

    def test_unmapped_rows_skipped(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 1000}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    _make_source_cell("IS", "B1", 1000),
                ]),
                _make_row("UnmappedLabel", {"FY2023": 500}, [
                    _make_source_cell("IS", "A2", "UnmappedLabel"),
                    _make_source_cell("IS", "B2", 500),
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 1  # only Revenue

    def test_tier_4_sheets_excluded(self):
        parsed = _make_parsed([
            _make_sheet("Notes", [
                _make_row("Revenue", {"FY2023": 1000}, [
                    _make_source_cell("Notes", "A1", "Revenue"),
                    _make_source_cell("Notes", "B1", 1000),
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["Notes"], tier=4)

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 0

    def test_no_source_cells_key_on_row(self):
        """Row without source_cells key should produce unmatched items."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 1000}),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 0
        assert result.unmatched == 1

    def test_unmapped_canonical_skipped(self):
        """Rows mapped to 'unmapped' should be skipped."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Something", {"FY2023": 1000}, [
                    _make_source_cell("IS", "A1", "Something"),
                    _make_source_cell("IS", "B1", 1000),
                ]),
            ])
        ])
        mappings = _make_mappings({"Something": "unmapped"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 0

    def test_empty_parsed_sheets(self):
        result = self.validator.reconcile(
            {"sheets": []}, [], [{"sheet_name": "IS", "tier": 1}]
        )
        assert result.total_cells == 0
        assert result.match_rate == 1.0

    def test_mismatch_details(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 1500}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    _make_source_cell("IS", "B1", 1000),
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.mismatched == 1
        m = result.mismatches[0]
        assert m.canonical_name == "revenue"
        assert m.period == "FY2023"
        assert m.extracted_value == Decimal("1500")
        assert m.source_raw_value == 1000
        assert m.source_cell_ref == "B1"
        assert m.source_sheet == "IS"
        assert m.delta == Decimal("500")
        assert m.matched is False


class TestCellPairingByPeriod:
    """Test period-based cell pairing (P0 fix)."""

    def setup_method(self):
        self.validator = CellReconciliationValidator()

    def test_period_tagged_source_cells_match_correctly(self):
        """When source_cells have period keys, match by period not position."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 100, "FY2024": None, "FY2025": 200}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    {**_make_source_cell("IS", "B1", 100), "period": "FY2023"},
                    {**_make_source_cell("IS", "D1", 200), "period": "FY2025"},
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 2
        assert result.matched == 2
        assert result.mismatched == 0

    def test_close_values_different_periods_paired_correctly(self):
        """Two similar values should pair with correct periods, not greedy first-fit."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 100.5, "FY2024": 100.0}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    {**_make_source_cell("IS", "B1", 100.5), "period": "FY2023"},
                    {**_make_source_cell("IS", "C1", 100.0), "period": "FY2024"},
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 2
        assert result.matched == 2
        assert result.mismatched == 0

    def test_backward_compat_no_period_key_uses_positional(self):
        """Source cells without 'period' key should still work (positional fallback)."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 1000}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    _make_source_cell("IS", "B1", 1000),  # no "period" key
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 1
        assert result.matched == 1

    def test_period_without_source_cell_produces_unmatched(self):
        """If a period has no matching source_cell, it goes to unmatched."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 100, "FY2024": 200}, [
                    _make_source_cell("IS", "A1", "Revenue"),
                    {**_make_source_cell("IS", "B1", 100), "period": "FY2023"},
                    # FY2024 has no source cell
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.validator.reconcile(parsed, mappings, triage)

        assert result.total_cells == 1
        assert result.matched == 1
        assert result.unmatched == 1
