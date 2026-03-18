"""Tests for Excel formula verification."""

from decimal import Decimal

from src.validation.formula_verifier import FormulaVerifier


def _make_parsed(sheets):
    return {"sheets": sheets}


def _make_sheet(name, rows):
    return {"sheet_name": name, "rows": rows}


def _make_row(label, values, source_cells=None):
    row = {"label": label, "values": values}
    if source_cells is not None:
        row["source_cells"] = source_cells
    return row


def _sc(sheet, ref, raw_value, formula=None):
    """Shorthand for source cell."""
    cell = {"sheet": sheet, "cell_ref": ref, "raw_value": raw_value}
    if formula:
        cell["formula"] = formula
    return cell


def _make_mappings(mapping_dict):
    return [
        {"original_label": k, "canonical_name": v} for k, v in mapping_dict.items()
    ]


def _make_triage(sheet_names, tier=1):
    return [{"sheet_name": name, "tier": tier} for name in sheet_names]


class TestSumFormula:
    def setup_method(self):
        self.verifier = FormulaVerifier()

    def test_sum_formula_matches(self):
        """=SUM(B2:B4) where B2=100, B3=200, B4=300 should verify against 600."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Item1", {"FY2023": 100}, [
                    _sc("IS", "A2", "Item1"),
                    _sc("IS", "B2", 100),
                ]),
                _make_row("Item2", {"FY2023": 200}, [
                    _sc("IS", "A3", "Item2"),
                    _sc("IS", "B3", 200),
                ]),
                _make_row("Item3", {"FY2023": 300}, [
                    _sc("IS", "A4", "Item3"),
                    _sc("IS", "B4", 300),
                ]),
                _make_row("Total", {"FY2023": 600}, [
                    _sc("IS", "A5", "Total"),
                    _sc("IS", "B5", 600, formula="=SUM(B2:B4)"),
                ]),
            ])
        ])
        mappings = _make_mappings({
            "Item1": "item1", "Item2": "item2",
            "Item3": "item3", "Total": "total",
        })
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.total_formulas == 1
        assert result.verified == 1
        assert result.mismatched == 0
        assert result.results[0].reason == "verified"
        assert result.results[0].computed_value == Decimal("600")

    def test_sum_formula_mismatches(self):
        """=SUM(B2:B3) where B2=100, B3=200 but extracted says 400."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Item1", {"FY2023": 100}, [
                    _sc("IS", "A2", "Item1"),
                    _sc("IS", "B2", 100),
                ]),
                _make_row("Item2", {"FY2023": 200}, [
                    _sc("IS", "A3", "Item2"),
                    _sc("IS", "B3", 200),
                ]),
                _make_row("Total", {"FY2023": 400}, [
                    _sc("IS", "A4", "Total"),
                    _sc("IS", "B4", 400, formula="=SUM(B2:B3)"),
                ]),
            ])
        ])
        mappings = _make_mappings({
            "Item1": "item1", "Item2": "item2", "Total": "total",
        })
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.total_formulas == 1
        assert result.mismatched == 1
        assert result.results[0].reason == "mismatch"
        assert result.results[0].computed_value == Decimal("300")

    def test_sum_formula_missing_cells_unresolvable(self):
        """SUM over cells that don't exist in lookup → unresolvable."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Total", {"FY2023": 500}, [
                    _sc("IS", "A1", "Total"),
                    _sc("IS", "B1", 500, formula="=SUM(B2:B5)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"Total": "total"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.total_formulas == 1
        assert result.unresolvable == 1

    def test_row_sum_formula(self):
        """=SUM(B1:D1) horizontal range."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 600}, [
                    _sc("IS", "A1", "Revenue"),
                    _sc("IS", "E1", 600, formula="=SUM(B1:D1)"),
                ]),
                # Provide cells B1, C1, D1 via other rows' source_cells
                _make_row("Helper", {"p1": 100, "p2": 200, "p3": 300}, [
                    _sc("IS", "A2", "Helper"),
                    _sc("IS", "B1", 100),
                    _sc("IS", "C1", 200),
                    _sc("IS", "D1", 300),
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue", "Helper": "helper"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1


class TestArithmeticFormulas:
    def setup_method(self):
        self.verifier = FormulaVerifier()

    def test_addition_formula(self):
        """=B2+B3 where B2=100, B3=200 → 300."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("A", {"FY2023": 100}, [
                    _sc("IS", "A2", "A"), _sc("IS", "B2", 100),
                ]),
                _make_row("B", {"FY2023": 200}, [
                    _sc("IS", "A3", "B"), _sc("IS", "B3", 200),
                ]),
                _make_row("Total", {"FY2023": 300}, [
                    _sc("IS", "A4", "Total"),
                    _sc("IS", "B4", 300, formula="=B2+B3"),
                ]),
            ])
        ])
        mappings = _make_mappings({"A": "a", "B": "b", "Total": "total"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1
        assert result.results[0].computed_value == Decimal("300")

    def test_subtraction_formula(self):
        """=B2-B3 where B2=1000, B3=400 → 600."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Rev", {"FY2023": 1000}, [
                    _sc("IS", "A2", "Rev"), _sc("IS", "B2", 1000),
                ]),
                _make_row("Cost", {"FY2023": 400}, [
                    _sc("IS", "A3", "Cost"), _sc("IS", "B3", 400),
                ]),
                _make_row("Profit", {"FY2023": 600}, [
                    _sc("IS", "A4", "Profit"),
                    _sc("IS", "B4", 600, formula="=B2-B3"),
                ]),
            ])
        ])
        mappings = _make_mappings({"Rev": "revenue", "Cost": "cogs", "Profit": "gross_profit"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1

    def test_mixed_arithmetic(self):
        """=B2+B3-B4 where B2=500, B3=300, B4=100 → 700."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("A", {"FY2023": 500}, [
                    _sc("IS", "A2", "A"), _sc("IS", "B2", 500),
                ]),
                _make_row("B", {"FY2023": 300}, [
                    _sc("IS", "A3", "B"), _sc("IS", "B3", 300),
                ]),
                _make_row("C", {"FY2023": 100}, [
                    _sc("IS", "A4", "C"), _sc("IS", "B4", 100),
                ]),
                _make_row("Result", {"FY2023": 700}, [
                    _sc("IS", "A5", "Result"),
                    _sc("IS", "B5", 700, formula="=B2+B3-B4"),
                ]),
            ])
        ])
        mappings = _make_mappings({"A": "a", "B": "b", "C": "c", "Result": "result"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1
        assert result.results[0].computed_value == Decimal("700")


class TestComplexFormulas:
    def setup_method(self):
        self.verifier = FormulaVerifier()

    def test_vlookup_marked_unresolvable(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Item", {"FY2023": 100}, [
                    _sc("IS", "A1", "Item"),
                    _sc("IS", "B1", 100, formula="=VLOOKUP(A1,Data!A:B,2,0)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"Item": "item"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.unresolvable == 1
        assert result.results[0].reason == "unresolvable"

    def test_if_marked_unresolvable(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Item", {"FY2023": 100}, [
                    _sc("IS", "A1", "Item"),
                    _sc("IS", "B1", 100, formula="=IF(A1>0,B2,0)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"Item": "item"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.unresolvable == 1

    def test_iferror_marked_unresolvable(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Item", {"FY2023": 100}, [
                    _sc("IS", "A1", "Item"),
                    _sc("IS", "B1", 100, formula="=IFERROR(B2/B3,0)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"Item": "item"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.unresolvable == 1

    def test_round_marked_unresolvable(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Item", {"FY2023": 100}, [
                    _sc("IS", "A1", "Item"),
                    _sc("IS", "B1", 100, formula="=ROUND(B2,2)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"Item": "item"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.unresolvable == 1


class TestFormulaEdgeCases:
    def setup_method(self):
        self.verifier = FormulaVerifier()

    def test_no_formulas_returns_empty(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Revenue", {"FY2023": 1000}, [
                    _sc("IS", "A1", "Revenue"),
                    _sc("IS", "B1", 1000),  # no formula
                ]),
            ])
        ])
        mappings = _make_mappings({"Revenue": "revenue"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.total_formulas == 0
        assert result.verified == 0

    def test_empty_input(self):
        result = self.verifier.verify(
            {"sheets": []}, [], [{"sheet_name": "IS", "tier": 1}]
        )
        assert result.total_formulas == 0

    def test_unmapped_rows_skipped(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Unknown", {"FY2023": 100}, [
                    _sc("IS", "A1", "Unknown"),
                    _sc("IS", "B1", 100, formula="=SUM(B2:B5)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"Other": "other"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.total_formulas == 0

    def test_tier_4_excluded(self):
        parsed = _make_parsed([
            _make_sheet("Notes", [
                _make_row("Item", {"FY2023": 100}, [
                    _sc("Notes", "A1", "Item"),
                    _sc("Notes", "B1", 100, formula="=SUM(B2:B3)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"Item": "item"})
        triage = _make_triage(["Notes"], tier=4)

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.total_formulas == 0

    def test_none_values_skipped(self):
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Item", {"FY2023": None}, [
                    _sc("IS", "A1", "Item"),
                    _sc("IS", "B1", 100, formula="=SUM(B2:B3)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"Item": "item"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.total_formulas == 0

    def test_multiple_periods_with_formulas(self):
        """Multiple periods, each with a formula."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("A", {"FY2023": 100, "FY2024": 200}, [
                    _sc("IS", "A2", "A"),
                    _sc("IS", "B2", 100),
                    _sc("IS", "C2", 200),
                ]),
                _make_row("B", {"FY2023": 50, "FY2024": 80}, [
                    _sc("IS", "A3", "B"),
                    _sc("IS", "B3", 50),
                    _sc("IS", "C3", 80),
                ]),
                _make_row("Total", {"FY2023": 150, "FY2024": 280}, [
                    _sc("IS", "A4", "Total"),
                    _sc("IS", "B4", 150, formula="=B2+B3"),
                    _sc("IS", "C4", 280, formula="=C2+C3"),
                ]),
            ])
        ])
        mappings = _make_mappings({"A": "a", "B": "b", "Total": "total"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.total_formulas == 2
        assert result.verified == 2


class TestNegatedSumFormula:
    def setup_method(self):
        self.verifier = FormulaVerifier()

    def test_negated_sum_matches(self):
        """=-SUM(B2:B3) where B2=100, B3=200 should verify against -300."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("A", {"FY2023": 100}, [
                    _sc("IS", "A2", "A"), _sc("IS", "B2", 100),
                ]),
                _make_row("B", {"FY2023": 200}, [
                    _sc("IS", "A3", "B"), _sc("IS", "B3", 200),
                ]),
                _make_row("Total", {"FY2023": -300}, [
                    _sc("IS", "A4", "Total"),
                    _sc("IS", "B4", -300, formula="=-SUM(B2:B3)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"A": "a", "B": "b", "Total": "total"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1
        assert result.results[0].computed_value == Decimal("-300")

    def test_negated_sum_mismatch(self):
        """=-SUM(B2:B3) = -300 but extracted says -400."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("A", {"FY2023": 100}, [
                    _sc("IS", "A2", "A"), _sc("IS", "B2", 100),
                ]),
                _make_row("B", {"FY2023": 200}, [
                    _sc("IS", "A3", "B"), _sc("IS", "B3", 200),
                ]),
                _make_row("Total", {"FY2023": -400}, [
                    _sc("IS", "A4", "Total"),
                    _sc("IS", "B4", -400, formula="=-SUM(B2:B3)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"A": "a", "B": "b", "Total": "total"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.mismatched == 1
        assert result.results[0].computed_value == Decimal("-300")


class TestNonContiguousSum:
    def setup_method(self):
        self.verifier = FormulaVerifier()

    def test_sum_list_matches(self):
        """=SUM(B2,B4,B6) — non-contiguous cells."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("A", {"FY2023": 100}, [
                    _sc("IS", "A2", "A"), _sc("IS", "B2", 100),
                ]),
                _make_row("B", {"FY2023": 200}, [
                    _sc("IS", "A4", "B"), _sc("IS", "B4", 200),
                ]),
                _make_row("C", {"FY2023": 300}, [
                    _sc("IS", "A6", "C"), _sc("IS", "B6", 300),
                ]),
                _make_row("Total", {"FY2023": 600}, [
                    _sc("IS", "A7", "Total"),
                    _sc("IS", "B7", 600, formula="=SUM(B2,B4,B6)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"A": "a", "B": "b", "C": "c", "Total": "total"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1
        assert result.results[0].computed_value == Decimal("600")

    def test_sum_list_missing_cell_unresolvable(self):
        """Non-contiguous SUM where one cell is not in lookup."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("A", {"FY2023": 100}, [
                    _sc("IS", "A2", "A"), _sc("IS", "B2", 100),
                ]),
                _make_row("Total", {"FY2023": 400}, [
                    _sc("IS", "A3", "Total"),
                    _sc("IS", "B3", 400, formula="=SUM(B2,B4,B6)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"A": "a", "Total": "total"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.unresolvable == 1


class TestAggregateFormulas:
    def setup_method(self):
        self.verifier = FormulaVerifier()

    def _make_range_data(self, formula, extracted):
        """Helper: 3 cells B2=100, B3=300, B4=200 with a formula row."""
        return _make_parsed([
            _make_sheet("IS", [
                _make_row("A", {"FY2023": 100}, [
                    _sc("IS", "A2", "A"), _sc("IS", "B2", 100),
                ]),
                _make_row("B", {"FY2023": 300}, [
                    _sc("IS", "A3", "B"), _sc("IS", "B3", 300),
                ]),
                _make_row("C", {"FY2023": 200}, [
                    _sc("IS", "A4", "C"), _sc("IS", "B4", 200),
                ]),
                _make_row("Result", {"FY2023": extracted}, [
                    _sc("IS", "A5", "Result"),
                    _sc("IS", "B5", extracted, formula=formula),
                ]),
            ])
        ])

    def test_max_formula_matches(self):
        """=MAX(B2:B4) should verify against 300."""
        parsed = self._make_range_data("=MAX(B2:B4)", 300)
        mappings = _make_mappings({"A": "a", "B": "b", "C": "c", "Result": "result"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1
        assert result.results[0].computed_value == Decimal("300")

    def test_min_formula_matches(self):
        """=MIN(B2:B4) should verify against 100."""
        parsed = self._make_range_data("=MIN(B2:B4)", 100)
        mappings = _make_mappings({"A": "a", "B": "b", "C": "c", "Result": "result"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1
        assert result.results[0].computed_value == Decimal("100")

    def test_average_formula_matches(self):
        """=AVERAGE(B2:B4) should verify against 200."""
        parsed = self._make_range_data("=AVERAGE(B2:B4)", 200)
        mappings = _make_mappings({"A": "a", "B": "b", "C": "c", "Result": "result"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1
        assert result.results[0].computed_value == Decimal("200")

    def test_negated_max(self):
        """=-MAX(B2:B4) should negate the result."""
        parsed = self._make_range_data("=-MAX(B2:B4)", -300)
        mappings = _make_mappings({"A": "a", "B": "b", "C": "c", "Result": "result"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1
        assert result.results[0].computed_value == Decimal("-300")


class TestAbsFormula:
    def setup_method(self):
        self.verifier = FormulaVerifier()

    def test_abs_of_cell_ref(self):
        """=ABS(B2) where B2=-500 should verify against 500."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Val", {"FY2023": -500}, [
                    _sc("IS", "A2", "Val"), _sc("IS", "B2", -500),
                ]),
                _make_row("Result", {"FY2023": 500}, [
                    _sc("IS", "A3", "Result"),
                    _sc("IS", "B3", 500, formula="=ABS(B2)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"Val": "val", "Result": "result"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1
        assert result.results[0].computed_value == Decimal("500")

    def test_abs_of_arithmetic(self):
        """=ABS(B2-B3) where B2=100, B3=400 → abs(-300) = 300."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("A", {"FY2023": 100}, [
                    _sc("IS", "A2", "A"), _sc("IS", "B2", 100),
                ]),
                _make_row("B", {"FY2023": 400}, [
                    _sc("IS", "A3", "B"), _sc("IS", "B3", 400),
                ]),
                _make_row("Result", {"FY2023": 300}, [
                    _sc("IS", "A4", "Result"),
                    _sc("IS", "B4", 300, formula="=ABS(B2-B3)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"A": "a", "B": "b", "Result": "result"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1
        assert result.results[0].computed_value == Decimal("300")


class TestRoundFormula:
    def setup_method(self):
        self.verifier = FormulaVerifier()

    def test_round_of_cell_ref(self):
        """=ROUND(B2,2) where B2=3.14159 should verify against 3.14."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("Val", {"FY2023": 3.14159}, [
                    _sc("IS", "A2", "Val"), _sc("IS", "B2", 3.14159),
                ]),
                _make_row("Result", {"FY2023": 3.14}, [
                    _sc("IS", "A3", "Result"),
                    _sc("IS", "B3", 3.14, formula="=ROUND(B2,2)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"Val": "val", "Result": "result"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1
        assert result.results[0].computed_value == Decimal("3.14")

    def test_round_of_arithmetic(self):
        """=ROUND(B2+B3,0) where B2=1.7, B3=2.6 → round(4.3, 0) = 4."""
        parsed = _make_parsed([
            _make_sheet("IS", [
                _make_row("A", {"FY2023": 1.7}, [
                    _sc("IS", "A2", "A"), _sc("IS", "B2", 1.7),
                ]),
                _make_row("B", {"FY2023": 2.6}, [
                    _sc("IS", "A3", "B"), _sc("IS", "B3", 2.6),
                ]),
                _make_row("Result", {"FY2023": 4}, [
                    _sc("IS", "A4", "Result"),
                    _sc("IS", "B4", 4, formula="=ROUND(B2+B3,0)"),
                ]),
            ])
        ])
        mappings = _make_mappings({"A": "a", "B": "b", "Result": "result"})
        triage = _make_triage(["IS"])

        result = self.verifier.verify(parsed, mappings, triage)

        assert result.verified == 1
