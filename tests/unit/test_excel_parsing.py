"""
Unit tests for _excel_to_structured_repr() and _structured_to_markdown().

Tests run against the real sample_model.xlsx fixture to verify that
structured extraction preserves formulas, formatting, hierarchy, merged
cells, cell references, and sheet metadata.
"""
import io

import openpyxl
import pytest

from src.core.exceptions import InvalidFileError
from src.extraction.stages.parsing import ParsingStage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_xlsx(
    data: dict | None = None,
    bold_cells: set | None = None,
    formulas: dict | None = None,
    merged_ranges: list | None = None,
    hidden_sheets: set | None = None,
) -> bytes:
    """
    Create a tiny in-memory .xlsx from a dict of {sheet_name: [[cell, ...], ...]}.

    ``bold_cells``  – set of (sheet_name, row, col) tuples where font should be bold.
    ``formulas``    – dict of (sheet_name, row, col) -> formula string.
    ``merged_ranges`` – list of (sheet_name, range_string) to merge.
    ``hidden_sheets`` – set of sheet names to mark hidden.
    """
    if data is None:
        data = {"Sheet1": [["A", "B"], [1, 2]]}
    bold_cells = bold_cells or set()
    formulas = formulas or {}
    merged_ranges = merged_ranges or []
    hidden_sheets = hidden_sheets or set()

    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    for sheet_name, rows in data.items():
        ws = wb.create_sheet(title=sheet_name)
        if sheet_name in hidden_sheets:
            ws.sheet_state = "hidden"
        for r_idx, row in enumerate(rows, start=1):
            for c_idx, val in enumerate(row, start=1):
                key = (sheet_name, r_idx, c_idx)
                if key in formulas:
                    ws.cell(row=r_idx, column=c_idx, value=formulas[key])
                else:
                    ws.cell(row=r_idx, column=c_idx, value=val)
                if key in bold_cells:
                    ws.cell(row=r_idx, column=c_idx).font = openpyxl.styles.Font(bold=True)
        for merge_sheet, merge_range in merged_ranges:
            if merge_sheet == sheet_name:
                ws.merge_cells(merge_range)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ===========================================================================
# Tests against sample_model.xlsx fixture
# ===========================================================================


class TestStructuredReprWithFixture:
    """Test _excel_to_structured_repr on the real sample_model.xlsx."""

    def test_top_level_keys(self, sample_xlsx):
        result = ParsingStage._excel_to_structured_repr(sample_xlsx)
        assert "sheets" in result
        assert "named_ranges" in result
        assert "sheet_count" in result
        assert "total_rows" in result

    def test_sheet_count(self, sample_xlsx):
        result = ParsingStage._excel_to_structured_repr(sample_xlsx)
        assert result["sheet_count"] == 4
        names = [s["sheet_name"] for s in result["sheets"]]
        assert "Income Statement" in names
        assert "Balance Sheet" in names
        assert "Cash Flow" in names
        assert "Scratch - Working" in names

    def test_total_rows_positive(self, sample_xlsx):
        result = ParsingStage._excel_to_structured_repr(sample_xlsx)
        assert result["total_rows"] > 0

    def test_sheet_has_required_keys(self, sample_xlsx):
        result = ParsingStage._excel_to_structured_repr(sample_xlsx)
        for sheet in result["sheets"]:
            assert "sheet_name" in sheet
            assert "is_hidden" in sheet
            assert "merged_regions" in sheet
            assert "rows" in sheet
            assert isinstance(sheet["is_hidden"], bool)
            assert isinstance(sheet["merged_regions"], list)

    def test_cell_has_required_keys(self, sample_xlsx):
        result = ParsingStage._excel_to_structured_repr(sample_xlsx)
        income = next(s for s in result["sheets"] if s["sheet_name"] == "Income Statement")
        assert len(income["rows"]) > 0
        first_row = income["rows"][0]
        assert "row_index" in first_row
        assert "cells" in first_row
        first_cell = first_row["cells"][0]
        for key in ("ref", "value", "formula", "is_bold", "indent_level", "number_format"):
            assert key in first_cell, f"Missing key '{key}' in cell dict"

    def test_cell_refs_are_valid(self, sample_xlsx):
        """Every cell ref must look like A1, B12, AA3 etc."""
        import re
        ref_pat = re.compile(r"^[A-Z]+\d+$")
        result = ParsingStage._excel_to_structured_repr(sample_xlsx)
        for sheet in result["sheets"]:
            for row in sheet["rows"]:
                for cell in row["cells"]:
                    assert ref_pat.match(cell["ref"]), f"Invalid ref: {cell['ref']}"

    def test_revenue_row_present(self, sample_xlsx):
        result = ParsingStage._excel_to_structured_repr(sample_xlsx)
        income = next(s for s in result["sheets"] if s["sheet_name"] == "Income Statement")
        # Row 2 should contain "Revenue" in cell A2
        row2 = next((r for r in income["rows"] if r["row_index"] == 2), None)
        assert row2 is not None
        a2 = next((c for c in row2["cells"] if c["ref"] == "A2"), None)
        assert a2 is not None
        assert a2["value"] == "Revenue"

    def test_bold_header_detection(self, sample_xlsx):
        """Header row (FY2022, FY2023, FY2024E) should have bold=True."""
        result = ParsingStage._excel_to_structured_repr(sample_xlsx)
        income = next(s for s in result["sheets"] if s["sheet_name"] == "Income Statement")
        row1 = next((r for r in income["rows"] if r["row_index"] == 1), None)
        assert row1 is not None
        bold_cells = [c for c in row1["cells"] if c["is_bold"]]
        assert len(bold_cells) >= 3, "FY2022/FY2023/FY2024E should be bold"

    def test_subtotal_detection(self, sample_xlsx):
        """'Total Operating Expenses' and 'Total Assets' should be marked as subtotal."""
        result = ParsingStage._excel_to_structured_repr(sample_xlsx)
        income = next(s for s in result["sheets"] if s["sheet_name"] == "Income Statement")
        # Row 12: Total Operating Expenses
        row12 = next((r for r in income["rows"] if r["row_index"] == 12), None)
        assert row12 is not None
        a12 = next((c for c in row12["cells"] if c["ref"] == "A12"), None)
        assert a12 is not None
        assert a12.get("is_subtotal") is True

    def test_gross_profit_subtotal(self, sample_xlsx):
        """'Gross Profit' contains the word 'Gross' which matches the subtotal pattern."""
        result = ParsingStage._excel_to_structured_repr(sample_xlsx)
        income = next(s for s in result["sheets"] if s["sheet_name"] == "Income Statement")
        row6 = next((r for r in income["rows"] if r["row_index"] == 6), None)
        assert row6 is not None
        a6 = next((c for c in row6["cells"] if c["ref"] == "A6"), None)
        assert a6 is not None
        assert a6.get("is_subtotal") is True

    def test_empty_rows_skipped(self, sample_xlsx):
        """Row 7 in Income Statement is empty and should not appear."""
        result = ParsingStage._excel_to_structured_repr(sample_xlsx)
        income = next(s for s in result["sheets"] if s["sheet_name"] == "Income Statement")
        row_indices = {r["row_index"] for r in income["rows"]}
        assert 7 not in row_indices

    def test_named_ranges_is_dict(self, sample_xlsx):
        result = ParsingStage._excel_to_structured_repr(sample_xlsx)
        assert isinstance(result["named_ranges"], dict)


# ===========================================================================
# Tests with synthetic workbooks (edge cases)
# ===========================================================================


class TestStructuredReprSynthetic:
    """Test edge cases using in-memory workbooks."""

    def test_hidden_sheet_marked(self):
        xlsx = _make_minimal_xlsx(
            data={"Visible": [[1]], "Secret": [[2]]},
            hidden_sheets={"Secret"},
        )
        result = ParsingStage._excel_to_structured_repr(xlsx)
        visible = next(s for s in result["sheets"] if s["sheet_name"] == "Visible")
        secret = next(s for s in result["sheets"] if s["sheet_name"] == "Secret")
        assert visible["is_hidden"] is False
        assert secret["is_hidden"] is True

    def test_merged_cells_detected(self):
        xlsx = _make_minimal_xlsx(
            data={"S1": [["Header", None, None], [1, 2, 3]]},
            merged_ranges=[("S1", "A1:C1")],
        )
        result = ParsingStage._excel_to_structured_repr(xlsx)
        s1 = result["sheets"][0]
        assert "A1:C1" in s1["merged_regions"]

    def test_formula_captured(self):
        xlsx = _make_minimal_xlsx(
            data={"S1": [[10, 20, None]]},
            formulas={("S1", 1, 3): "=A1+B1"},
        )
        result = ParsingStage._excel_to_structured_repr(xlsx)
        s1 = result["sheets"][0]
        row1 = s1["rows"][0]
        c3 = next((c for c in row1["cells"] if c["ref"] == "C1"), None)
        assert c3 is not None
        assert c3["formula"] == "=A1+B1"

    def test_bold_formatting_preserved(self):
        xlsx = _make_minimal_xlsx(
            data={"S1": [["Header", "Normal"]]},
            bold_cells={("S1", 1, 1)},
        )
        result = ParsingStage._excel_to_structured_repr(xlsx)
        row = result["sheets"][0]["rows"][0]
        a1 = next(c for c in row["cells"] if c["ref"] == "A1")
        b1 = next(c for c in row["cells"] if c["ref"] == "B1")
        assert a1["is_bold"] is True
        assert b1["is_bold"] is False

    def test_corrupted_file_raises_invalid_file_error(self):
        with pytest.raises(InvalidFileError):
            ParsingStage._excel_to_structured_repr(b"not an xlsx file at all")

    def test_empty_workbook(self):
        """A workbook with one sheet but no data should produce 0 rows."""
        wb = openpyxl.Workbook()
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        result = ParsingStage._excel_to_structured_repr(buf.read())
        assert result["sheet_count"] == 1
        assert result["total_rows"] == 0


# ===========================================================================
# Markdown conversion tests
# ===========================================================================


class TestStructuredToMarkdown:
    """Test _structured_to_markdown output."""

    def test_returns_string(self, sample_xlsx):
        structured = ParsingStage._excel_to_structured_repr(sample_xlsx)
        md = ParsingStage._structured_to_markdown(structured)
        assert isinstance(md, str)
        assert len(md) > 0

    def test_sheet_headers_present(self, sample_xlsx):
        structured = ParsingStage._excel_to_structured_repr(sample_xlsx)
        md = ParsingStage._structured_to_markdown(structured)
        assert "## Sheet: Income Statement" in md
        assert "## Sheet: Balance Sheet" in md
        assert "## Sheet: Cash Flow" in md

    def test_hidden_sheet_annotated(self):
        structured = {
            "sheets": [
                {
                    "sheet_name": "Hidden",
                    "is_hidden": True,
                    "merged_regions": [],
                    "rows": [],
                }
            ],
            "named_ranges": {},
            "sheet_count": 1,
            "total_rows": 0,
        }
        md = ParsingStage._structured_to_markdown(structured)
        assert "(hidden)" in md

    def test_merged_regions_in_output(self):
        structured = {
            "sheets": [
                {
                    "sheet_name": "S1",
                    "is_hidden": False,
                    "merged_regions": ["A1:C1"],
                    "rows": [
                        {
                            "row_index": 1,
                            "cells": [
                                {"ref": "A1", "value": "x", "formula": None,
                                 "is_bold": False, "indent_level": 0,
                                 "number_format": "General"},
                            ],
                        }
                    ],
                }
            ],
            "named_ranges": {},
            "sheet_count": 1,
            "total_rows": 1,
        }
        md = ParsingStage._structured_to_markdown(structured)
        assert "Merged: A1:C1" in md

    def test_markdown_table_pipe_delimited(self, sample_xlsx):
        structured = ParsingStage._excel_to_structured_repr(sample_xlsx)
        md = ParsingStage._structured_to_markdown(structured)
        # Should have pipe-delimited table rows
        lines = md.strip().split("\n")
        table_lines = [l for l in lines if l.startswith("|")]
        assert len(table_lines) > 0

    def test_empty_structured_produces_output(self):
        md = ParsingStage._structured_to_markdown({
            "sheets": [], "named_ranges": {}, "sheet_count": 0, "total_rows": 0
        })
        assert isinstance(md, str)

    def test_named_ranges_section(self):
        structured = {
            "sheets": [],
            "named_ranges": {"EBITDA": "Sheet1!B15"},
            "sheet_count": 0,
            "total_rows": 0,
        }
        md = ParsingStage._structured_to_markdown(structured)
        assert "## Named Ranges" in md
        assert "EBITDA" in md
        assert "Sheet1!B15" in md
