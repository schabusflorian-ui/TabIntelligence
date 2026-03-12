"""Unit tests for section_detector.py — section detection for multi-statement sheets."""

from src.extraction.section_detector import (
    SectionDetector,
    _guess_category,
    _has_distinct_fill,
    _is_content_header_row,
    _is_full_width_bold,
    _is_full_width_merge,
)


def _make_sheet(rows, label_column="A", sheet_name="S1"):
    """Build a minimal structured sheet dict from row specs.

    Each row spec is a dict with at least row_index and cells.
    """
    return {
        "sheet_name": sheet_name,
        "label_column": label_column,
        "rows": rows,
    }


def _make_row(row_index, label=None, bold=False, formula=None, is_subtotal=False):
    """Build a minimal row dict."""
    cells = []
    if label is not None:
        cells.append(
            {
                "ref": f"A{row_index}",
                "value": label,
                "is_bold": bold,
            }
        )
    if formula:
        cells.append(
            {
                "ref": f"B{row_index}",
                "value": 100,
                "formula": formula,
            }
        )
    else:
        cells.append(
            {
                "ref": f"B{row_index}",
                "value": 100,
            }
        )

    row = {"row_index": row_index, "cells": cells}
    if is_subtotal:
        row["is_subtotal"] = True
    return row


class TestSectionDetectorBasic:
    """Basic section detection tests."""

    def test_empty_sheet(self):
        """No rows -> empty list."""
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet([]))
        assert result == []

    def test_few_rows_single_section(self):
        """Fewer than 5 rows -> single section."""
        rows = [_make_row(1, "Revenue"), _make_row(2, "COGS"), _make_row(3, "Profit")]
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result) == 1
        assert result[0].label == "Revenue"
        assert result[0].start_row == 1
        assert result[0].end_row == 3

    def test_single_section_no_boundaries(self):
        """Contiguous rows, no boundaries -> single section."""
        rows = [_make_row(i, f"Row {i}") for i in range(1, 11)]
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result) == 1
        assert result[0].row_count == 10


class TestThreeSections:
    """Multi-section detection tests."""

    def test_three_section_sheet(self):
        """IS/BS/CF on one sheet with gaps -> 3 sections."""
        rows = (
            # Income Statement section (rows 1-8)
            [_make_row(1, "Income Statement", bold=True)]
            + [_make_row(i, f"IS row {i}") for i in range(2, 9)]
            # Gap: rows 9-11 are blank (row_index jumps from 8 to 12)
            # Balance Sheet section (rows 12-20)
            + [_make_row(12, "Balance Sheet", bold=True)]
            + [_make_row(i, f"BS row {i}") for i in range(13, 21)]
            # Gap: rows 21-23 are blank
            # Cash Flow section (rows 24-32)
            + [_make_row(24, "Cash Flow Statement", bold=True)]
            + [_make_row(i, f"CF row {i}") for i in range(25, 33)]
        )
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))

        assert len(result) == 3
        assert result[0].label == "Income Statement"
        assert result[0].category_hint == "income_statement"
        assert result[0].start_row == 1
        assert result[0].end_row == 8

        assert result[1].label == "Balance Sheet"
        assert result[1].category_hint == "balance_sheet"
        assert result[1].start_row == 12
        assert result[1].end_row == 20

        assert result[2].label == "Cash Flow Statement"
        assert result[2].category_hint == "cash_flow"
        assert result[2].start_row == 24
        assert result[2].end_row == 32


class TestBoundaryDetection:
    """Boundary detection edge cases."""

    def test_gap_boundary_without_bold(self):
        """3+ gap without bold still creates boundary."""
        rows = (
            [_make_row(i, f"Row {i}") for i in range(1, 6)]
            # gap: rows 6-8 blank
            + [_make_row(i, f"Row {i}") for i in range(9, 14)]
        )
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result) == 2
        assert result[0].end_row == 5
        assert result[1].start_row == 9

    def test_bold_after_blank_creates_boundary(self):
        """Bold cell after a blank row (gap=2) creates boundary."""
        rows = (
            [_make_row(i, f"Row {i}") for i in range(1, 6)]
            # row 6 is blank (gap of 2 from row 5 to row 7)
            + [_make_row(7, "New Section", bold=True)]
            + [_make_row(i, f"Row {i}") for i in range(8, 12)]
        )
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result) == 2
        assert result[1].label == "New Section"
        assert result[1].start_row == 7

    def test_bold_without_blank_not_boundary(self):
        """Bold cell at consecutive row (gap=1) is NOT a boundary."""
        rows = (
            [_make_row(1, "Section 1")]
            + [_make_row(i, f"Row {i}") for i in range(2, 6)]
            + [_make_row(6, "Bold Row", bold=True)]  # consecutive, no gap
            + [_make_row(i, f"Row {i}") for i in range(7, 11)]
        )
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result) == 1


class TestCategoryHints:
    """Category hint detection tests."""

    def test_income_statement(self):
        assert _guess_category("Profit & Loss") == "income_statement"
        assert _guess_category("Profit & Loss Statement") == "income_statement"

    def test_balance_sheet(self):
        assert _guess_category("Balance Sheet") == "balance_sheet"
        assert _guess_category("Statement of Financial Position") == "balance_sheet"

    def test_cash_flow(self):
        assert _guess_category("Cash Flow Statement") == "cash_flow"
        assert _guess_category("Statement of Cash Flows") == "cash_flow"

    def test_debt_schedule(self):
        assert _guess_category("Debt Schedule") == "debt_schedule"
        assert _guess_category("Loan Facility") == "debt_schedule"

    def test_unknown(self):
        assert _guess_category("Sensitivity Analysis") is None
        assert _guess_category("Assumptions") is None

    def test_net_income_not_matched(self):
        """'Net Income' is a line item, not a section header — should not match."""
        assert _guess_category("Net Income") is None

    def test_total_assets_not_matched(self):
        """'Total Assets' is a line item, not a section header — should not match."""
        assert _guess_category("Total Assets") is None

    def test_empty_string(self):
        assert _guess_category("") is None

    def test_abbreviations(self):
        """Common financial abbreviations are recognized."""
        assert _guess_category("P/L") == "income_statement"
        assert _guess_category("I/S") == "income_statement"
        assert _guess_category("B/S") == "balance_sheet"
        assert _guess_category("C/F") == "cash_flow"

    def test_gross_loss_not_matched(self):
        """'Gross Loss' is a line item, not a section header."""
        assert _guess_category("Gross Loss") is None

    def test_bad_debt_expense_not_matched(self):
        """'Bad Debt Expense' should not match debt_schedule."""
        assert _guess_category("Bad Debt Expense") is None

    def test_total_debt_not_matched(self):
        """Bare 'debt' removed — only compound phrases match."""
        assert _guess_category("Total Debt") is None
        assert _guess_category("Debt Schedule") == "debt_schedule"
        assert _guess_category("Debt Service Coverage") == "debt_schedule"


class TestPrecomputedBoundaries:
    """Tests for consuming section_boundaries from parsing stage."""

    def test_no_gap_bold_with_precomputed_boundary(self):
        """Bold header at gap=1 detected via pre-computed section_boundaries."""
        rows = (
            [_make_row(i, f"Row {i}") for i in range(1, 6)]
            # No gap — row 6 is immediately after row 5
            + [_make_row(6, "Balance Sheet", bold=True)]
            + [_make_row(i, f"Row {i}") for i in range(7, 11)]
        )
        sheet = _make_sheet(rows)
        # Simulate what parsing.py _detect_section_boundaries would compute
        sheet["section_boundaries"] = [
            {"row_index": 1, "label": "Row 1"},
            {"row_index": 6, "label": "Balance Sheet"},
        ]
        detector = SectionDetector()
        result = detector.detect_sections(sheet)
        assert len(result) == 2
        assert result[1].label == "Balance Sheet"
        assert result[1].start_row == 6

    def test_precomputed_merged_with_gap_boundaries(self):
        """Pre-computed and gap-detected boundaries merge without duplicates."""
        rows = (
            [_make_row(i, f"Row {i}") for i in range(1, 6)]
            # Gap: 3 blank rows (6, 7, 8 missing)
            + [_make_row(9, "Section 2", bold=True)]
            + [_make_row(i, f"Row {i}") for i in range(10, 14)]
        )
        sheet = _make_sheet(rows)
        # Pre-computed also finds row 9 — should not duplicate
        sheet["section_boundaries"] = [
            {"row_index": 9, "label": "Section 2"},
        ]
        detector = SectionDetector()
        result = detector.detect_sections(sheet)
        assert len(result) == 2  # Not 3

    def test_empty_precomputed_boundaries(self):
        """Empty section_boundaries list has no effect."""
        rows = [_make_row(i, f"Row {i}") for i in range(1, 11)]
        sheet = _make_sheet(rows)
        sheet["section_boundaries"] = []
        detector = SectionDetector()
        result = detector.detect_sections(sheet)
        assert len(result) == 1


class TestSectionSummaryFields:
    """Verify section summary field computation."""

    def test_sample_labels(self):
        """First 5 labels collected."""
        rows = [_make_row(i, f"Label {i}") for i in range(1, 8)]
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result[0].sample_labels) == 5
        assert result[0].sample_labels[0] == "Label 1"

    def test_formula_count(self):
        """Formula count aggregated across rows."""
        rows = [
            _make_row(1, "Row 1", formula="=SUM(B2:B5)"),
            _make_row(2, "Row 2", formula="=A1+A2"),
            _make_row(3, "Row 3"),
            _make_row(4, "Row 4", formula="=B1*2"),
            _make_row(5, "Row 5"),
        ]
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert result[0].formula_count == 3

    def test_subtotal_detection(self):
        """has_subtotals flag set when subtotal rows present."""
        rows = [
            _make_row(1, "Revenue"),
            _make_row(2, "COGS"),
            _make_row(3, "Total Revenue", is_subtotal=True),
            _make_row(4, "OpEx"),
            _make_row(5, "Net Income"),
        ]
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert result[0].has_subtotals is True

    def test_bold_labels_collected(self):
        """Bold labels are tracked."""
        rows = [
            _make_row(1, "Revenue", bold=True),
            _make_row(2, "Operating Revenue"),
            _make_row(3, "Other Revenue"),
            _make_row(4, "Expenses", bold=True),
            _make_row(5, "OpEx"),
        ]
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert "Revenue" in result[0].bold_labels
        assert "Expenses" in result[0].bold_labels

    def test_label_column_used(self):
        """Section detector respects label_column metadata."""
        rows = [
            {
                "row_index": 1,
                "cells": [
                    {"ref": "A1", "value": 1},
                    {"ref": "B1", "value": "Revenue", "is_bold": True},
                ],
            },
            {
                "row_index": 2,
                "cells": [
                    {"ref": "A2", "value": 2},
                    {"ref": "B2", "value": "COGS"},
                ],
            },
            {
                "row_index": 3,
                "cells": [
                    {"ref": "A3", "value": 3},
                    {"ref": "B3", "value": "Profit"},
                ],
            },
        ]
        sheet = _make_sheet(rows, label_column="B")
        detector = SectionDetector()
        result = detector.detect_sections(sheet)
        assert len(result) == 1
        assert result[0].sample_labels[0] == "Revenue"


# ============================================================================
# FORMAT-BASED BOUNDARY TESTS
# ============================================================================


def _make_row_with_format(
    row_index,
    label=None,
    bold=False,
    fill_color=None,
    is_merged=False,
    merge_origin=None,
    num_cells=3,
):
    """Build a row dict with formatting metadata."""
    cells = []
    for col_idx in range(num_cells):
        col_letter = chr(ord("A") + col_idx)
        cell = {
            "ref": f"{col_letter}{row_index}",
            "value": label if col_idx == 0 and label else (100 if col_idx > 0 else None),
            "is_bold": bold,
        }
        if fill_color:
            cell["fill_color"] = fill_color
        if is_merged:
            cell["is_merged"] = True
            cell["merge_origin"] = merge_origin or f"A{row_index}"
        cells.append(cell)

    return {"row_index": row_index, "cells": cells}


class TestFormatBasedBoundaries:
    """Tests for format-based boundary detection (full-width bold, fill, merge)."""

    def test_full_width_bold_boundary(self):
        """All-bold row creates boundary without gap."""
        rows = (
            [_make_row(i, f"Row {i}") for i in range(1, 6)]
            # Row 6: all cells bold (no gap from row 5)
            + [_make_row_with_format(6, "Balance Sheet", bold=True)]
            + [_make_row(i, f"Row {i}") for i in range(7, 12)]
        )
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result) == 2
        assert result[1].label == "Balance Sheet"
        assert result[1].start_row == 6

    def test_fill_color_boundary(self):
        """Row with distinct fill colour creates boundary."""
        rows = (
            [_make_row_with_format(i, f"Row {i}", fill_color="ffffff") for i in range(1, 6)]
            # Row 6: different fill colour (header)
            + [_make_row_with_format(6, "Cash Flow", fill_color="4472c4")]
            # Rows 7-11: same fill as header (no second colour change)
            + [_make_row_with_format(i, f"Row {i}", fill_color="4472c4") for i in range(7, 12)]
        )
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result) == 2
        assert result[1].label == "Cash Flow"

    def test_full_width_merge_boundary(self):
        """Merged row creates boundary."""
        rows = (
            [_make_row(i, f"Row {i}") for i in range(1, 6)]
            + [
                _make_row_with_format(
                    6, "Debt Schedule", is_merged=True, merge_origin="A6", num_cells=3
                )
            ]
            + [_make_row(i, f"Row {i}") for i in range(7, 12)]
        )
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result) == 2
        assert result[1].label == "Debt Schedule"

    def test_no_false_positive_same_fill(self):
        """Uniform fill colour does NOT create boundaries."""
        rows = [_make_row_with_format(i, f"Row {i}", fill_color="4472c4") for i in range(1, 11)]
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result) == 1

    def test_no_false_positive_no_label(self):
        """Full-width bold row without a label text does NOT create boundary."""
        rows = (
            [_make_row(i, f"Row {i}") for i in range(1, 6)]
            # Row 6: all bold but no label value (label is None → value cells only)
            + [_make_row_with_format(6, label=None, bold=True)]
            + [_make_row(i, f"Row {i}") for i in range(7, 12)]
        )
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result) == 1  # No boundary because no label

    def test_new_signals_additive(self):
        """New format signals coexist with existing gap+bold detection."""
        rows = (
            # Section 1: rows 1-5
            [_make_row(i, f"Row {i}") for i in range(1, 6)]
            # Gap boundary: rows 6-8 blank
            + [_make_row(9, "Section 2", bold=True)]
            + [_make_row(i, f"Row {i}") for i in range(10, 14)]
            # Fill colour boundary (no gap): row 14
            + [_make_row_with_format(14, "Section 3", fill_color="ff0000")]
            + [_make_row(i, f"Row {i}") for i in range(15, 20)]
        )
        # Previous rows need fill_color=None so the fill change is detected
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result) == 3
        assert result[0].start_row == 1
        assert result[1].start_row == 9
        assert result[2].start_row == 14


class TestHelperFunctions:
    """Test the new helper functions directly."""

    def test_is_full_width_bold_true(self):
        row = {"cells": [{"is_bold": True}, {"is_bold": True}, {"is_bold": True}]}
        assert _is_full_width_bold(row) is True

    def test_is_full_width_bold_false_mixed(self):
        row = {"cells": [{"is_bold": True}, {"is_bold": False}, {"is_bold": True}]}
        assert _is_full_width_bold(row) is False

    def test_is_full_width_bold_single_cell(self):
        """Single cell row → False (need >= 2 cells)."""
        row = {"cells": [{"is_bold": True}]}
        assert _is_full_width_bold(row) is False

    def test_has_distinct_fill_different(self):
        row = {"cells": [{"fill_color": "ff0000"}, {"fill_color": "ff0000"}]}
        prev = {"cells": [{"fill_color": "ffffff"}, {"fill_color": "ffffff"}]}
        assert _has_distinct_fill(row, prev) is True

    def test_has_distinct_fill_same(self):
        row = {"cells": [{"fill_color": "ffffff"}, {"fill_color": "ffffff"}]}
        prev = {"cells": [{"fill_color": "ffffff"}, {"fill_color": "ffffff"}]}
        assert _has_distinct_fill(row, prev) is False

    def test_has_distinct_fill_no_fill(self):
        row = {"cells": [{"value": 100}, {"value": 200}]}
        prev = {"cells": [{"value": 100}, {"value": 200}]}
        assert _has_distinct_fill(row, prev) is False

    def test_is_full_width_merge_true(self):
        row = {
            "cells": [
                {"is_merged": True, "merge_origin": "A1"},
                {"is_merged": True, "merge_origin": "A1"},
                {"is_merged": True, "merge_origin": "A1"},
            ]
        }
        assert _is_full_width_merge(row) is True

    def test_is_full_width_merge_false_different_origins(self):
        row = {
            "cells": [
                {"is_merged": True, "merge_origin": "A1"},
                {"is_merged": True, "merge_origin": "C1"},
            ]
        }
        assert _is_full_width_merge(row) is False

    def test_is_full_width_merge_false_not_merged(self):
        row = {"cells": [{"value": "A"}, {"value": "B"}, {"value": "C"}]}
        assert _is_full_width_merge(row) is False


class TestContentBasedFallback:
    """Test _is_content_header_row and content-based boundary detection."""

    def test_plain_text_header_detected(self):
        """Unformatted 'Income Statement' with no numeric values → True."""
        row = {
            "row_index": 5,
            "cells": [
                {"ref": "A5", "value": "Income Statement"},
            ],
        }
        assert _is_content_header_row(row, "A") is True

    def test_data_row_not_detected(self):
        """'Cash Flow' with numeric values → False (data row, not header)."""
        row = {
            "row_index": 5,
            "cells": [
                {"ref": "A5", "value": "Cash Flow"},
                {"ref": "B5", "value": 50000},
            ],
        }
        assert _is_content_header_row(row, "A") is False

    def test_line_item_not_detected(self):
        """'Revenue' is not a section keyword → False."""
        row = {
            "row_index": 5,
            "cells": [
                {"ref": "A5", "value": "Revenue"},
            ],
        }
        assert _is_content_header_row(row, "A") is False

    def test_empty_label_not_detected(self):
        """Row with no label → False."""
        row = {
            "row_index": 5,
            "cells": [
                {"ref": "A5", "value": None},
            ],
        }
        assert _is_content_header_row(row, "A") is False

    def test_content_fallback_creates_boundary(self):
        """Plain text 'Balance Sheet' (no formatting) should create a boundary."""
        rows = (
            # Section 1: rows 1-5 (no gap, no formatting at all)
            [_make_row(i, f"Row {i}") for i in range(1, 6)]
            # Row 6: plain text "Balance Sheet" — no bold, no gap, no color
            + [
                {
                    "row_index": 6,
                    "cells": [
                        {"ref": "A6", "value": "Balance Sheet"},
                    ],
                }
            ]
            + [_make_row(i, f"Row {i}") for i in range(7, 12)]
        )
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result) == 2, (
            f"Expected 2 sections, got {len(result)}: {[s.label for s in result]}"
        )
        assert result[1].label == "Balance Sheet"
        assert result[1].category_hint == "balance_sheet"

    def test_content_fallback_no_duplicate(self):
        """Row already detected by gap should not be duplicated."""
        rows = (
            [_make_row(i, f"Row {i}") for i in range(1, 6)]
            # Gap of 3 + keyword label → detected by gap AND content
            + [_make_row(9, "Cash Flow Statement")]
            + [_make_row(i, f"Row {i}") for i in range(10, 15)]
        )
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        # Should be 2 (not 3 from duplicate detection)
        assert len(result) == 2

    def test_content_fallback_with_numeric_no_match(self):
        """'Profit & Loss' row WITH numeric values → no boundary."""
        rows = (
            [_make_row(i, f"Row {i}") for i in range(1, 6)]
            # Row 6: keyword but has numeric value
            + [
                {
                    "row_index": 6,
                    "cells": [
                        {"ref": "A6", "value": "Profit & Loss"},
                        {"ref": "B6", "value": 100000},
                    ],
                }
            ]
            + [_make_row(i, f"Row {i}") for i in range(7, 12)]
        )
        detector = SectionDetector()
        result = detector.detect_sections(_make_sheet(rows))
        assert len(result) == 1  # No boundary
