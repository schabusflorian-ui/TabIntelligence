"""Tests for deterministic period detection and normalization."""

from datetime import datetime

import pytest

from src.extraction.period_parser import (
    PeriodDetectionResult,
    PeriodParser,
    _expand_year,
    check_period_consistency,
    sort_period_keys,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cell(col: str, row: int, value):
    """Build a minimal cell dict."""
    return {
        "ref": f"{col}{row}",
        "value": value,
        "formula": None,
        "is_bold": False,
        "indent_level": 0,
        "number_format": "General",
    }


def _make_sheet(
    name: str = "Sheet1",
    header_values=None,
    header_columns=None,
    header_row: int = 1,
    extra_rows=None,
) -> dict:
    """Build a minimal structured sheet dict for testing.

    Args:
        header_values: List of values for the header row.
        header_columns: List of column letters (defaults to A, B, C...).
        extra_rows: Additional row dicts to append.
    """
    rows = []
    if header_values is not None:
        if header_columns is None:
            header_columns = [chr(65 + i) for i in range(len(header_values))]
        cells = [
            _make_cell(col, header_row, val) for col, val in zip(header_columns, header_values)
        ]
        rows.append({"row_index": header_row, "cells": cells})

    for row_data in extra_rows or []:
        rows.append(row_data)

    return {
        "sheet_name": name,
        "is_hidden": False,
        "merged_regions": [],
        "rows": rows,
    }


@pytest.fixture
def parser():
    return PeriodParser()


# ---------------------------------------------------------------------------
# _expand_year helper
# ---------------------------------------------------------------------------


class TestExpandYear:
    def test_two_digit_low(self):
        assert _expand_year("24") == 2024

    def test_two_digit_high(self):
        assert _expand_year("50") == 1950

    def test_two_digit_boundary(self):
        assert _expand_year("49") == 2049

    def test_four_digit(self):
        assert _expand_year("2024") == 2024

    def test_four_digit_1900s(self):
        assert _expand_year("1999") == 1999


# ---------------------------------------------------------------------------
# parse_single_value — Fiscal Year
# ---------------------------------------------------------------------------


class TestFiscalYear:
    def test_fy_4digit(self, parser):
        p = parser.parse_single_value("FY2024", "C")
        assert p is not None
        assert p.normalized == "FY2024"
        assert p.period_type == "fiscal_year"
        assert p.year == 2024
        assert p.is_actual is False
        assert p.is_forecast is False
        assert p.confidence == 1.0

    def test_fy_2digit(self, parser):
        p = parser.parse_single_value("FY24", "C")
        assert p.normalized == "FY2024"
        assert p.year == 2024
        assert p.confidence == 0.9  # 2-digit expansion

    def test_fy_with_space(self, parser):
        p = parser.parse_single_value("FY 2024", "C")
        assert p.normalized == "FY2024"

    def test_fy_with_apostrophe(self, parser):
        p = parser.parse_single_value("FY'24", "C")
        assert p.normalized == "FY2024"

    def test_fy_actual(self, parser):
        p = parser.parse_single_value("FY2024A", "C")
        assert p.normalized == "FY2024A"
        assert p.is_actual is True
        assert p.is_forecast is False

    def test_fy_estimate(self, parser):
        p = parser.parse_single_value("FY2024E", "C")
        assert p.normalized == "FY2024E"
        assert p.is_actual is False
        assert p.is_forecast is True

    def test_fy_forecast(self, parser):
        p = parser.parse_single_value("FY2025F", "C")
        assert p.normalized == "FY2025F"
        assert p.is_forecast is True

    def test_fy_projected(self, parser):
        p = parser.parse_single_value("FY2026P", "C")
        assert p.normalized == "FY2026P"
        assert p.is_forecast is True

    def test_fy_case_insensitive(self, parser):
        p = parser.parse_single_value("fy2024e", "C")
        assert p.normalized == "FY2024E"
        assert p.is_forecast is True


# ---------------------------------------------------------------------------
# parse_single_value — Calendar Year
# ---------------------------------------------------------------------------


class TestCalendarYear:
    def test_cy_4digit(self, parser):
        p = parser.parse_single_value("CY2024", "C")
        assert p.normalized == "CY2024"
        assert p.period_type == "calendar_year"
        assert p.year == 2024

    def test_cy_2digit(self, parser):
        p = parser.parse_single_value("CY24", "C")
        assert p.normalized == "CY2024"
        assert p.confidence == 0.9

    def test_cy_with_suffix(self, parser):
        p = parser.parse_single_value("CY2024E", "C")
        assert p.normalized == "CY2024E"
        assert p.is_forecast is True


# ---------------------------------------------------------------------------
# parse_single_value — Year with Suffix
# ---------------------------------------------------------------------------


class TestYearSuffix:
    def test_year_actual(self, parser):
        p = parser.parse_single_value("2022A", "C")
        assert p.normalized == "2022A"
        assert p.period_type == "calendar_year"
        assert p.is_actual is True
        assert p.year == 2022

    def test_year_estimate(self, parser):
        p = parser.parse_single_value("2024E", "C")
        assert p.normalized == "2024E"
        assert p.is_forecast is True

    def test_year_forecast(self, parser):
        p = parser.parse_single_value("2025F", "C")
        assert p.normalized == "2025F"
        assert p.is_forecast is True

    def test_year_projected(self, parser):
        p = parser.parse_single_value("2026P", "C")
        assert p.normalized == "2026P"
        assert p.is_forecast is True

    def test_two_digit_year_suffix_not_recognized(self, parser):
        """2-digit year + suffix is intentionally NOT matched to avoid ambiguity."""
        assert parser.parse_single_value("24A", "C") is None
        assert parser.parse_single_value("25E", "C") is None

    def test_fy_two_digit_with_suffix_works(self, parser):
        """FY prefix + 2-digit year + suffix works via _RE_FISCAL_YEAR."""
        p = parser.parse_single_value("FY24A", "C")
        assert p is not None
        assert p.normalized == "FY2024A"
        assert p.is_actual is True
        assert p.year == 2024


# ---------------------------------------------------------------------------
# parse_single_value — Standalone Year
# ---------------------------------------------------------------------------


class TestStandaloneYear:
    def test_4digit_year(self, parser):
        p = parser.parse_single_value("2024", "C")
        assert p.normalized == "2024"
        assert p.period_type == "calendar_year"
        assert p.year == 2024
        assert p.is_actual is False
        assert p.is_forecast is False

    def test_another_year(self, parser):
        p = parser.parse_single_value("1999", "C")
        assert p.normalized == "1999"
        assert p.year == 1999


# ---------------------------------------------------------------------------
# parse_single_value — Quarterly
# ---------------------------------------------------------------------------


class TestQuarterly:
    def test_q_first_with_space(self, parser):
        p = parser.parse_single_value("Q3 2024", "C")
        assert p.normalized == "2024-Q3"
        assert p.period_type == "quarterly"
        assert p.year == 2024
        assert p.sub_period == 3

    def test_q_first_apostrophe(self, parser):
        p = parser.parse_single_value("Q4'24", "C")
        assert p.normalized == "2024-Q4"
        assert p.year == 2024
        assert p.sub_period == 4

    def test_year_first(self, parser):
        p = parser.parse_single_value("2024 Q1", "C")
        assert p.normalized == "2024-Q1"
        assert p.sub_period == 1

    def test_year_first_no_space(self, parser):
        p = parser.parse_single_value("2024Q3", "C")
        assert p.normalized == "2024-Q3"
        assert p.sub_period == 3


# ---------------------------------------------------------------------------
# parse_single_value — Half-Year
# ---------------------------------------------------------------------------


class TestHalfYear:
    def test_h_first(self, parser):
        p = parser.parse_single_value("H1 2024", "C")
        assert p.normalized == "2024-H1"
        assert p.period_type == "half_year"
        assert p.year == 2024
        assert p.sub_period == 1

    def test_number_first(self, parser):
        p = parser.parse_single_value("2H24", "C")
        assert p.normalized == "2024-H2"
        assert p.sub_period == 2

    def test_h_with_apostrophe(self, parser):
        p = parser.parse_single_value("H1'24", "C")
        assert p.normalized == "2024-H1"
        assert p.year == 2024


# ---------------------------------------------------------------------------
# parse_single_value — Monthly
# ---------------------------------------------------------------------------


class TestMonthly:
    def test_abbrev_dash(self, parser):
        p = parser.parse_single_value("Jan-24", "C")
        assert p.normalized == "2024-01"
        assert p.period_type == "monthly"
        assert p.year == 2024
        assert p.sub_period == 1

    def test_full_name(self, parser):
        p = parser.parse_single_value("March 2024", "C")
        assert p.normalized == "2024-03"
        assert p.sub_period == 3

    def test_slash_separator(self, parser):
        p = parser.parse_single_value("Dec/2024", "C")
        assert p.normalized == "2024-12"
        assert p.sub_period == 12

    def test_abbrev_4digit(self, parser):
        p = parser.parse_single_value("Sep 2023", "C")
        assert p.normalized == "2023-09"
        assert p.confidence == 1.0


# ---------------------------------------------------------------------------
# parse_single_value — LTM / TTM / NTM
# ---------------------------------------------------------------------------


class TestLtmTtmNtm:
    def test_ltm(self, parser):
        p = parser.parse_single_value("LTM", "C")
        assert p.normalized == "LTM"
        assert p.period_type == "ltm_ttm_ntm"

    def test_ttm(self, parser):
        p = parser.parse_single_value("TTM", "C")
        assert p.normalized == "TTM"

    def test_ntm(self, parser):
        p = parser.parse_single_value("NTM", "C")
        assert p.normalized == "NTM"

    def test_ltm_with_date(self, parser):
        p = parser.parse_single_value("LTM 12/31/2024", "C")
        assert p.normalized == "LTM"
        assert p.period_type == "ltm_ttm_ntm"

    def test_case_insensitive(self, parser):
        p = parser.parse_single_value("ltm", "C")
        assert p.normalized == "LTM"


# ---------------------------------------------------------------------------
# parse_single_value — Datetime objects
# ---------------------------------------------------------------------------


class TestDatetime:
    def test_dec_31_annual(self, parser):
        p = parser.parse_single_value(datetime(2024, 12, 31), "C")
        assert p.normalized == "2024"
        assert p.period_type == "date"
        assert p.year == 2024
        assert p.sub_period is None

    def test_jan_1_annual(self, parser):
        p = parser.parse_single_value(datetime(2024, 1, 1), "C")
        assert p.normalized == "2024"
        assert p.sub_period is None

    def test_mid_year_monthly(self, parser):
        p = parser.parse_single_value(datetime(2024, 3, 15), "C")
        assert p.normalized == "2024-03"
        assert p.sub_period == 3


# ---------------------------------------------------------------------------
# parse_single_value — Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_none_returns_none(self, parser):
        assert parser.parse_single_value(None, "C") is None

    def test_empty_string_returns_none(self, parser):
        assert parser.parse_single_value("", "C") is None

    def test_whitespace_only_returns_none(self, parser):
        assert parser.parse_single_value("   ", "C") is None

    def test_text_label_returns_none(self, parser):
        assert parser.parse_single_value("Revenue", "C") is None

    def test_large_number_not_period(self, parser):
        # Numbers >3 digits shouldn't match as numeric periods
        # parse_single_value doesn't try _RE_NUMERIC (only via sequential detection)
        # but standalone year regex won't match 5-digit numbers
        assert parser.parse_single_value("100000", "C") is None

    def test_whitespace_tolerance(self, parser):
        p = parser.parse_single_value("  FY2024  ", "C")
        assert p.normalized == "FY2024"

    def test_two_digit_year_boundary_49(self, parser):
        p = parser.parse_single_value("FY49", "C")
        assert p.year == 2049

    def test_two_digit_year_boundary_50(self, parser):
        p = parser.parse_single_value("FY50", "C")
        assert p.year == 1950

    def test_integer_input(self, parser):
        # Standalone integers don't match via parse_single_value
        # (no _RE_NUMERIC path). 2024 matches _RE_STANDALONE_YEAR.
        p = parser.parse_single_value(2024, "C")
        assert p is not None
        assert p.normalized == "2024"
        assert p.year == 2024

    def test_float_input_year(self, parser):
        p = parser.parse_single_value(2024.0, "C")
        assert p is not None
        assert p.normalized == "2024"

    def test_column_letter_preserved(self, parser):
        p = parser.parse_single_value("FY2024", "AA")
        assert p.column_letter == "AA"


# ---------------------------------------------------------------------------
# Sort key ordering
# ---------------------------------------------------------------------------


class TestSortKey:
    def test_fiscal_years_chronological(self, parser):
        periods = [
            parser.parse_single_value("FY2024", "C"),
            parser.parse_single_value("FY2022", "A"),
            parser.parse_single_value("FY2023", "B"),
        ]
        sorted_p = PeriodParser.sort_periods(periods)
        assert [p.normalized for p in sorted_p] == ["FY2022", "FY2023", "FY2024"]

    def test_actual_before_forecast_same_year(self, parser):
        periods = [
            parser.parse_single_value("FY2024E", "B"),
            parser.parse_single_value("FY2024A", "A"),
        ]
        sorted_p = PeriodParser.sort_periods(periods)
        assert sorted_p[0].is_actual is True
        assert sorted_p[1].is_forecast is True

    def test_quarterly_chronological(self, parser):
        periods = [
            parser.parse_single_value("Q3 2024", "C"),
            parser.parse_single_value("Q1 2024", "A"),
            parser.parse_single_value("Q1 2025", "D"),
        ]
        sorted_p = PeriodParser.sort_periods(periods)
        assert [p.normalized for p in sorted_p] == ["2024-Q1", "2024-Q3", "2025-Q1"]

    def test_mixed_fiscal_years_with_suffixes(self, parser):
        periods = [
            parser.parse_single_value("FY2025E", "D"),
            parser.parse_single_value("FY2022A", "A"),
            parser.parse_single_value("FY2024E", "C"),
            parser.parse_single_value("FY2023A", "B"),
        ]
        sorted_p = PeriodParser.sort_periods(periods)
        assert [p.normalized for p in sorted_p] == [
            "FY2022A",
            "FY2023A",
            "FY2024E",
            "FY2025E",
        ]

    def test_annual_before_quarterly_same_year(self, parser):
        periods = [
            parser.parse_single_value("Q1 2024", "B"),
            parser.parse_single_value("FY2024", "A"),
            parser.parse_single_value("Q3 2024", "C"),
        ]
        sorted_p = PeriodParser.sort_periods(periods)
        assert sorted_p[0].normalized == "FY2024"
        assert sorted_p[1].normalized == "2024-Q1"
        assert sorted_p[2].normalized == "2024-Q3"

    def test_sort_key_has_six_elements(self, parser):
        p = parser.parse_single_value("FY2024", "C")
        assert len(p.sort_key) == 6


# ---------------------------------------------------------------------------
# NormalizedPeriod serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict(self, parser):
        p = parser.parse_single_value("FY2024E", "C")
        d = p.to_dict()
        assert d["raw_value"] == "FY2024E"
        assert d["normalized"] == "FY2024E"
        assert d["column_letter"] == "C"
        assert d["period_type"] == "fiscal_year"
        assert d["year"] == 2024
        assert d["is_forecast"] is True
        assert isinstance(d["sort_key"], list)  # tuple → list for JSON


# ---------------------------------------------------------------------------
# Sheet-level detection — time_across_columns
# ---------------------------------------------------------------------------


class TestDetectPeriodsFromSheet:
    def test_fiscal_year_header_row(self, parser):
        sheet = _make_sheet(
            header_values=["Item", "FY2022", "FY2023", "FY2024E"],
            header_columns=["A", "B", "C", "D"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 3
        assert result.dominant_type == "fiscal_year"
        assert result.layout == "time_across_columns"
        assert result.confidence > 0.5

    def test_mixed_actual_forecast(self, parser):
        sheet = _make_sheet(
            header_values=["Label", "FY2022A", "FY2023A", "FY2024E", "FY2025E"],
            header_columns=["A", "B", "C", "D", "E"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 4
        normals = [p.normalized for p in result.periods]
        assert normals == ["FY2022A", "FY2023A", "FY2024E", "FY2025E"]

    def test_standalone_years(self, parser):
        sheet = _make_sheet(
            header_values=["", "2022", "2023", "2024"],
            header_columns=["A", "B", "C", "D"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 3
        assert result.dominant_type == "calendar_year"

    def test_no_periods(self, parser):
        sheet = _make_sheet(
            header_values=["Revenue", "COGS", "Gross Profit"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 0
        assert result.confidence == 0.0

    def test_empty_sheet(self, parser):
        sheet = _make_sheet()
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 0
        assert result.confidence == 0.0

    def test_skips_label_columns(self, parser):
        """Label in col A should not affect period detection in cols B-F."""
        sheet = _make_sheet(
            header_values=["Income Statement", "FY2022", "FY2023", "FY2024E"],
            header_columns=["A", "B", "C", "D"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 3
        # All detected periods should be in B, C, D
        cols = {p.column_letter for p in result.periods}
        assert cols == {"B", "C", "D"}

    def test_periods_sorted_chronologically(self, parser):
        sheet = _make_sheet(
            header_values=["", "FY2024E", "FY2022", "FY2023"],
            header_columns=["A", "B", "C", "D"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        normals = [p.normalized for p in result.periods]
        assert normals == ["FY2022", "FY2023", "FY2024E"]

    def test_header_in_second_row(self, parser):
        """Period headers might be in row 2 if row 1 is a title."""
        title_row = {
            "row_index": 1,
            "cells": [_make_cell("A", 1, "Financial Summary")],
        }
        period_row = {
            "row_index": 2,
            "cells": [
                _make_cell("A", 2, ""),
                _make_cell("B", 2, "FY2022"),
                _make_cell("C", 2, "FY2023"),
                _make_cell("D", 2, "FY2024"),
            ],
        }
        sheet = _make_sheet(extra_rows=[title_row, period_row])
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 3
        assert result.header_row_indices == [2]

    def test_to_dict(self, parser):
        sheet = _make_sheet(
            header_values=["", "FY2022", "FY2023"],
            header_columns=["A", "B", "C"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        d = result.to_dict()
        assert "periods" in d
        assert "dominant_type" in d
        assert "confidence" in d
        assert "layout" in d
        assert len(d["periods"]) == 2

    def test_header_in_row_7(self, parser):
        """Period headers in row 7 after 6 rows of metadata are detected."""
        metadata_rows = [
            {"row_index": i, "cells": [_make_cell("A", i, f"Metadata line {i}")]}
            for i in range(1, 7)
        ]
        period_row = {
            "row_index": 7,
            "cells": [
                _make_cell("A", 7, ""),
                _make_cell("B", 7, "FY2022"),
                _make_cell("C", 7, "FY2023"),
                _make_cell("D", 7, "FY2024"),
            ],
        }
        sheet = _make_sheet(extra_rows=metadata_rows + [period_row])
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 3
        assert result.header_row_indices == [7]

    def test_header_in_row_10_not_detected(self, parser):
        """Period headers beyond MAX_HEADER_SCAN_ROWS are not detected as headers."""
        metadata_rows = [
            {"row_index": i, "cells": [_make_cell("A", i, f"Metadata line {i}")]}
            for i in range(1, 10)
        ]
        period_row = {
            "row_index": 10,
            "cells": [
                _make_cell("A", 10, ""),
                _make_cell("B", 10, "FY2022"),
                _make_cell("C", 10, "FY2023"),
                _make_cell("D", 10, "FY2024"),
            ],
        }
        sheet = _make_sheet(extra_rows=metadata_rows + [period_row])
        result = parser.detect_periods_from_sheet(sheet)
        # Row 10 is outside scan window (row 1 + 8 = row 9 max)
        assert len(result.periods) == 0 or result.layout == "time_down_rows"


# ---------------------------------------------------------------------------
# Numeric sequential detection
# ---------------------------------------------------------------------------


class TestNumericSequential:
    def test_integer_sequence(self, parser):
        sheet = _make_sheet(
            header_values=["Label", 1, 2, 3, 4, 5],
            header_columns=["A", "B", "C", "D", "E", "F"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 5
        assert result.dominant_type == "numeric"
        normals = [p.normalized for p in result.periods]
        assert normals == ["P1", "P2", "P3", "P4", "P5"]

    def test_float_sequence(self, parser):
        sheet = _make_sheet(
            header_values=["Label", 1.0, 2.0, 3.0, 4.0],
            header_columns=["A", "B", "C", "D", "E"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 4
        assert result.dominant_type == "numeric"

    def test_string_number_sequence(self, parser):
        sheet = _make_sheet(
            header_values=["", "1", "2", "3", "4"],
            header_columns=["A", "B", "C", "D", "E"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 4
        normals = [p.normalized for p in result.periods]
        assert normals == ["P1", "P2", "P3", "P4"]

    def test_two_values_not_enough(self, parser):
        """Need at least 3 consecutive values for numeric sequential."""
        sheet = _make_sheet(
            header_values=["Label", 1, 2],
            header_columns=["A", "B", "C"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 0

    def test_non_consecutive_not_sequential(self, parser):
        sheet = _make_sheet(
            header_values=["Label", 1, 3, 5, 7],
            header_columns=["A", "B", "C", "D", "E"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        # Should not detect as sequential (gaps)
        assert result.dominant_type != "numeric" or len(result.periods) == 0


# ---------------------------------------------------------------------------
# Multi-row header detection
# ---------------------------------------------------------------------------


class TestMultiRowHeader:
    def test_year_keyword_plus_values(self, parser):
        """'Year' in row 1, '2022'/'2023'/'2024' in row 2."""
        rows = [
            {
                "row_index": 1,
                "cells": [
                    _make_cell("A", 1, ""),
                    _make_cell("B", 1, "Year"),
                    _make_cell("C", 1, "Year"),
                    _make_cell("D", 1, "Year"),
                ],
            },
            {
                "row_index": 2,
                "cells": [
                    _make_cell("A", 2, "Item"),
                    _make_cell("B", 2, "2022"),
                    _make_cell("C", 2, "2023"),
                    _make_cell("D", 2, "2024"),
                ],
            },
        ]
        sheet = _make_sheet(extra_rows=rows)
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 3
        assert result.header_row_indices == [1, 2]

    def test_fy_keyword_plus_year_suffix(self, parser):
        """'FY' in row 1, '2022A'/'2023A'/'2024E' in row 2."""
        rows = [
            {
                "row_index": 1,
                "cells": [
                    _make_cell("A", 1, ""),
                    _make_cell("B", 1, "FY"),
                    _make_cell("C", 1, "FY"),
                    _make_cell("D", 1, "FY"),
                ],
            },
            {
                "row_index": 2,
                "cells": [
                    _make_cell("A", 2, ""),
                    _make_cell("B", 2, "2022A"),
                    _make_cell("C", 2, "2023A"),
                    _make_cell("D", 2, "2024E"),
                ],
            },
        ]
        sheet = _make_sheet(extra_rows=rows)
        result = parser.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 3
        # Should combine FY + 2022A → FY2022A
        assert result.periods[0].normalized == "FY2022A"
        assert result.periods[0].is_actual is True
        assert result.periods[2].normalized == "FY2024E"
        assert result.periods[2].is_forecast is True


# ---------------------------------------------------------------------------
# Layout detection — time_down_rows
# ---------------------------------------------------------------------------


class TestLayoutDetection:
    def test_time_down_rows(self, parser):
        """Periods in column A running down rows."""
        rows = [
            {
                "row_index": i,
                "cells": [
                    _make_cell("A", i, f"FY{2020 + i}"),
                    _make_cell("B", i, 100 * i),
                ],
            }
            for i in range(1, 6)
        ]
        sheet = _make_sheet(extra_rows=rows)
        result = parser.detect_periods_from_sheet(sheet)
        assert result.layout == "time_down_rows"
        assert len(result.periods) == 5

    def test_default_is_across_columns(self, parser):
        sheet = _make_sheet(
            header_values=["", "FY2022", "FY2023", "FY2024"],
            header_columns=["A", "B", "C", "D"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        assert result.layout == "time_across_columns"


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------


class TestConfidence:
    def test_all_match_high_confidence(self, parser):
        sheet = _make_sheet(
            header_values=["FY2022", "FY2023", "FY2024", "FY2025"],
            header_columns=["B", "C", "D", "E"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        assert result.confidence >= 0.9

    def test_partial_match_lower_confidence(self, parser):
        sheet = _make_sheet(
            header_values=["Revenue", "FY2022", "FY2023", "Notes", "Ref"],
            header_columns=["A", "B", "C", "D", "E"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        assert result.confidence < 0.9

    def test_numeric_lower_confidence(self, parser):
        sheet = _make_sheet(
            header_values=["", 1, 2, 3, 4],
            header_columns=["A", "B", "C", "D", "E"],
        )
        result = parser.detect_periods_from_sheet(sheet)
        if result.periods:
            assert result.confidence <= 0.7


# ---------------------------------------------------------------------------
# PeriodDetectionResult.to_dict
# ---------------------------------------------------------------------------


class TestPeriodDetectionResultDict:
    def test_empty_result(self):
        result = PeriodDetectionResult(
            periods=[],
            header_row_indices=[],
            dominant_type="unknown",
            confidence=0.0,
            layout="time_across_columns",
        )
        d = result.to_dict()
        assert d["periods"] == []
        assert d["dominant_type"] == "unknown"
        assert d["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Robustness / edge cases (post-review additions)
# ---------------------------------------------------------------------------


class TestRobustness:
    """Tests for defensive behaviour and untested edge cases."""

    def test_malformed_sheet_returns_empty(self, parser):
        """detect_periods_from_sheet must never raise, even on bad input."""
        # Rows without row_index key
        sheet = {"rows": [{"cells": [_make_cell("A", 1, "FY2024")]}]}
        del sheet["rows"][0]["cells"][0]["ref"]  # remove ref key
        result = parser.detect_periods_from_sheet(sheet)
        # Should not crash — returns empty or partial result
        assert isinstance(result, PeriodDetectionResult)

    def test_completely_empty_dict(self, parser):
        result = parser.detect_periods_from_sheet({})
        assert result.periods == []
        assert result.confidence == 0.0

    def test_rows_key_missing(self, parser):
        result = parser.detect_periods_from_sheet({"sheet_name": "X"})
        assert result.periods == []

    def test_non_standard_input_types_return_none(self, parser):
        """bool, list, dict, bytes should all return None."""
        assert parser.parse_single_value(True, "A") is None
        assert parser.parse_single_value([1, 2], "A") is None
        assert parser.parse_single_value({"a": 1}, "A") is None
        assert parser.parse_single_value(b"FY2024", "A") is None

    def test_float_non_integer_returns_none(self, parser):
        """A float like 2024.5 doesn't match any period pattern."""
        assert parser.parse_single_value(2024.5, "A") is None

    def test_invalid_quarter_rejected(self, parser):
        assert parser.parse_single_value("Q0 2024", "A") is None
        assert parser.parse_single_value("Q5 2024", "A") is None

    def test_invalid_half_rejected(self, parser):
        assert parser.parse_single_value("H0 2024", "A") is None
        assert parser.parse_single_value("H3 2024", "A") is None

    def test_invalid_suffix_rejected(self, parser):
        assert parser.parse_single_value("FY2024B", "A") is None
        assert parser.parse_single_value("FY2024X", "A") is None

    def test_month_space_separator(self, parser):
        """Month with space-only separator (no dash/slash)."""
        p = parser.parse_single_value("Jan 24", "A")
        assert p is not None
        assert p.normalized == "2024-01"

    def test_three_digit_year(self, parser):
        """3-digit year strings pass through _expand_year correctly."""
        assert _expand_year("001") == 2001
        assert _expand_year("099") == 1999  # 99 >= 50 → 1900+99
        assert _expand_year("100") == 100  # >= 100 returned as-is

    def test_datetime_with_time_component(self, parser):
        """Time-of-day should not affect period detection."""
        p = parser.parse_single_value(datetime(2024, 12, 31, 23, 59, 59), "A")
        assert p.normalized == "2024"
        assert p.sub_period is None


# ---------------------------------------------------------------------------
# check_period_consistency
# ---------------------------------------------------------------------------


class TestPeriodConsistency:
    """Tests for cross-sheet period consistency checking."""

    def test_single_sheet_returns_empty(self):
        """Fewer than 2 sheets → no warnings."""
        result = check_period_consistency({"Sheet1": {"dominant_type": "fiscal_year"}})
        assert result == []

    def test_empty_input_returns_empty(self):
        result = check_period_consistency({})
        assert result == []

    def test_matching_types_no_warning(self):
        data = {
            "IS": {"dominant_type": "fiscal_year", "periods": [{"year": 2022}, {"year": 2023}]},
            "BS": {"dominant_type": "fiscal_year", "periods": [{"year": 2022}, {"year": 2023}]},
        }
        result = check_period_consistency(data)
        assert len(result) == 0

    def test_mismatched_types_warning(self):
        data = {
            "IS": {"dominant_type": "fiscal_year", "periods": []},
            "BS": {"dominant_type": "quarterly", "periods": []},
        }
        result = check_period_consistency(data)
        type_warnings = [w for w in result if w["type"] == "mismatched_period_type"]
        assert len(type_warnings) == 1
        assert type_warnings[0]["severity"] == "warning"

    def test_period_coverage_gap(self):
        data = {
            "IS": {"dominant_type": "fiscal_year", "periods": [{"year": 2022}, {"year": 2023}]},
            "BS": {"dominant_type": "fiscal_year", "periods": [{"year": 2023}]},
        }
        result = check_period_consistency(data)
        gap_warnings = [w for w in result if w["type"] == "period_coverage_gap"]
        assert len(gap_warnings) == 1
        assert gap_warnings[0]["details"]["sheet"] == "BS"
        assert 2022 in gap_warnings[0]["details"]["missing_years"]

    def test_layout_inconsistency(self):
        data = {
            "IS": {"dominant_type": "fiscal_year", "layout": "time_across_columns", "periods": []},
            "BS": {"dominant_type": "fiscal_year", "layout": "time_down_rows", "periods": []},
        }
        result = check_period_consistency(data)
        layout_warnings = [w for w in result if w["type"] == "layout_inconsistency"]
        assert len(layout_warnings) == 1

    def test_unknown_type_excluded_from_mismatch(self):
        """Unknown types don't trigger mismatch warning alone."""
        data = {
            "IS": {"dominant_type": "fiscal_year", "periods": []},
            "BS": {"dominant_type": "unknown", "periods": []},
        }
        result = check_period_consistency(data)
        type_warnings = [w for w in result if w["type"] == "mismatched_period_type"]
        assert len(type_warnings) == 0


# ---------------------------------------------------------------------------
# sort_period_keys edge cases
# ---------------------------------------------------------------------------


class TestSortPeriodKeysEdgeCases:
    """Test sort_period_keys fallbacks for non-standard period strings."""

    def test_float_fallback_sorts_numerically(self):
        """Numeric strings that aren't periods sort by float value."""
        keys = ["3.0", "1.0", "2.0"]
        result = sort_period_keys(keys)
        assert result == ["1.0", "2.0", "3.0"]

    def test_lexicographic_fallback(self):
        """Non-parseable, non-numeric strings sort lexicographically after others."""
        keys = ["FY2023", "zzz_unknown", "FY2022"]
        result = sort_period_keys(keys)
        # FY2022 < FY2023 < zzz_unknown (lex)
        assert result[0] == "FY2022"
        assert result[1] == "FY2023"
        assert result[2] == "zzz_unknown"

    def test_mixed_recognized_and_fallback(self):
        """Recognized periods come before lexicographic fallbacks."""
        keys = ["unknown_period", "FY2022"]
        result = sort_period_keys(keys)
        assert result[0] == "FY2022"
        assert result[1] == "unknown_period"

    def test_empty_list(self):
        assert sort_period_keys([]) == []


# ============================================================================
# PROJECT FINANCE PERIOD PATTERNS
# ============================================================================


class TestRelativeYear:
    """Tests for 'Year 1', 'Yr 5', etc."""

    def test_year_1(self, parser):
        p = parser.parse_single_value("Year 1")
        assert p is not None
        assert p.period_type == "relative_year"
        assert p.normalized == "Year1"
        assert p.sub_period == 1

    def test_yr_5(self, parser):
        p = parser.parse_single_value("Yr 5")
        assert p is not None
        assert p.normalized == "Year5"

    def test_year_30(self, parser):
        p = parser.parse_single_value("Year 30")
        assert p is not None
        assert p.normalized == "Year30"
        assert p.sub_period == 30

    def test_yr_dot_2(self, parser):
        p = parser.parse_single_value("Yr. 2")
        assert p is not None
        assert p.normalized == "Year2"

    def test_year_1_actual(self, parser):
        p = parser.parse_single_value("Year 1A")
        assert p is not None
        assert p.normalized == "Year1A"
        assert p.is_actual is True

    def test_year_2_forecast(self, parser):
        p = parser.parse_single_value("Year 2E")
        assert p is not None
        assert p.normalized == "Year2E"
        assert p.is_forecast is True

    def test_case_insensitive(self, parser):
        p = parser.parse_single_value("YEAR 3")
        assert p is not None
        assert p.normalized == "Year3"

    def test_rejects_year_alone(self, parser):
        """Bare 'Year' without a number should not match."""
        p = parser.parse_single_value("Year")
        assert p is None or p.period_type != "relative_year"

    def test_rejects_year_abc(self, parser):
        p = parser.parse_single_value("Year abc")
        assert p is None


class TestCODRelative:
    """Tests for COD, COD+1, COD-3, Pre-COD, Post-COD."""

    def test_cod_standalone(self, parser):
        p = parser.parse_single_value("COD")
        assert p is not None
        assert p.period_type == "cod_relative"
        assert p.normalized == "COD"
        assert p.sub_period == 0

    def test_cod_plus_1(self, parser):
        p = parser.parse_single_value("COD+1")
        assert p is not None
        assert p.normalized == "COD+1"
        assert p.sub_period == 1

    def test_cod_minus_3(self, parser):
        p = parser.parse_single_value("COD-3")
        assert p is not None
        assert p.normalized == "COD-3"
        assert p.sub_period == -3

    def test_cod_plus_25(self, parser):
        p = parser.parse_single_value("COD+25")
        assert p is not None
        assert p.normalized == "COD+25"
        assert p.sub_period == 25

    def test_pre_cod(self, parser):
        p = parser.parse_single_value("Pre-COD")
        assert p is not None
        assert p.normalized == "PreCOD"
        assert p.sub_period == -999

    def test_post_cod(self, parser):
        p = parser.parse_single_value("Post-COD")
        assert p is not None
        assert p.normalized == "PostCOD"
        assert p.sub_period == 999

    def test_precod_no_hyphen(self, parser):
        p = parser.parse_single_value("PreCOD")
        assert p is not None
        assert p.normalized == "PreCOD"

    def test_case_insensitive(self, parser):
        p = parser.parse_single_value("cod+2")
        assert p is not None
        assert p.normalized == "COD+2"


class TestPhaseYear:
    """Tests for 'Construction Year 1', 'Ops Yr 3', etc."""

    def test_construction_year_1(self, parser):
        p = parser.parse_single_value("Construction Year 1")
        assert p is not None
        assert p.period_type == "phase_year"
        assert p.normalized == "Const-Year1"
        assert p.year == 0  # phase_order for construction
        assert p.sub_period == 1

    def test_const_dot_year_2(self, parser):
        p = parser.parse_single_value("Const. Year 2")
        assert p is not None
        assert p.normalized == "Const-Year2"

    def test_ops_yr_3(self, parser):
        p = parser.parse_single_value("Ops Yr 3")
        assert p is not None
        assert p.normalized == "Ops-Year3"
        assert p.year == 1  # phase_order for operations

    def test_operations_year_10(self, parser):
        p = parser.parse_single_value("Operations Year 10")
        assert p is not None
        assert p.normalized == "Ops-Year10"
        assert p.sub_period == 10

    def test_case_insensitive(self, parser):
        p = parser.parse_single_value("CONSTRUCTION YEAR 5")
        assert p is not None
        assert p.normalized == "Const-Year5"


class TestStub:
    """Tests for stub periods."""

    def test_stub_alone(self, parser):
        p = parser.parse_single_value("Stub")
        assert p is not None
        assert p.period_type == "stub"
        assert p.normalized == "Stub"
        assert p.sub_period == 0

    def test_6_month_stub(self, parser):
        p = parser.parse_single_value("6-month stub")
        assert p is not None
        assert p.normalized == "Stub-6M"
        assert p.sub_period == 6

    def test_3_mo_stub(self, parser):
        p = parser.parse_single_value("3 mo stub")
        assert p is not None
        assert p.normalized == "Stub-3M"
        assert p.sub_period == 3

    def test_stub_period(self, parser):
        p = parser.parse_single_value("Stub Period")
        assert p is not None
        assert p.normalized == "Stub"

    def test_short_period(self, parser):
        p = parser.parse_single_value("Short Period")
        assert p is not None
        assert p.period_type == "stub"
        assert p.normalized == "Stub"

    def test_rejects_stub_data(self, parser):
        """Should not match partial word."""
        p = parser.parse_single_value("Stub data")
        assert p is None


class TestFiscalYearEnd:
    """Tests for 'FYE Mar 2024', etc."""

    def test_fye_mar_2024(self, parser):
        p = parser.parse_single_value("FYE Mar 2024")
        assert p is not None
        assert p.period_type == "fiscal_year_end"
        assert p.normalized == "FYE-2024-03"
        assert p.year == 2024
        assert p.sub_period == 3

    def test_fye_jun_short_year(self, parser):
        p = parser.parse_single_value("FYE Jun '24")
        assert p is not None
        assert p.normalized == "FYE-2024-06"
        assert p.confidence == 0.9

    def test_fye_december_with_suffix(self, parser):
        p = parser.parse_single_value("FYE December 2025E")
        assert p is not None
        assert p.normalized == "FYE-2025-12E"
        assert p.is_forecast is True

    def test_fye_does_not_match_fy(self, parser):
        """FY2024 should still match _try_fiscal_year, not FYE."""
        p = parser.parse_single_value("FY2024")
        assert p is not None
        assert p.period_type == "fiscal_year"  # NOT fiscal_year_end


class TestSemiAnnual:
    """Tests for S1/S2 prefix (mapped to half_year)."""

    def test_s1_2024(self, parser):
        p = parser.parse_single_value("S1 2024")
        assert p is not None
        assert p.period_type == "half_year"
        assert p.normalized == "2024-H1"

    def test_s2_short_year(self, parser):
        p = parser.parse_single_value("S2'24")
        assert p is not None
        assert p.normalized == "2024-H2"

    def test_1s_2024(self, parser):
        p = parser.parse_single_value("1S 2024")
        assert p is not None
        assert p.normalized == "2024-H1"

    def test_h1_still_works(self, parser):
        """Existing H1/H2 format should still match."""
        p = parser.parse_single_value("H1 2024")
        assert p is not None
        assert p.period_type == "half_year"


class TestISOMonthly:
    """Tests for '2024-01', '2024/12' ISO monthly format."""

    def test_iso_dash(self, parser):
        p = parser.parse_single_value("2024-01")
        assert p is not None
        assert p.period_type == "monthly"
        assert p.normalized == "2024-01"
        assert p.year == 2024
        assert p.sub_period == 1

    def test_iso_slash(self, parser):
        p = parser.parse_single_value("2024/12")
        assert p is not None
        assert p.normalized == "2024-12"
        assert p.sub_period == 12

    def test_rejects_standalone_year(self, parser):
        """'2024' should match standalone year, not ISO monthly."""
        p = parser.parse_single_value("2024")
        assert p is not None
        assert p.period_type == "calendar_year"

    def test_rejects_invalid_month_13(self, parser):
        p = parser.parse_single_value("2024-13")
        assert p is None

    def test_rejects_invalid_month_00(self, parser):
        p = parser.parse_single_value("2024-00")
        assert p is None


# ============================================================================
# PROJECT FINANCE SORT ORDER
# ============================================================================


class TestPFSortOrder:
    """Verify chronological sort order for PF period types."""

    def test_relative_year_numeric_sort(self):
        """Year 1 < Year 2 < Year 10 < Year 30 (not lexicographic)."""
        keys = ["Year 10", "Year 2", "Year 30", "Year 1"]
        result = sort_period_keys(keys)
        assert result == ["Year 1", "Year 2", "Year 10", "Year 30"]

    def test_cod_sort(self):
        """PreCOD < COD-2 < COD < COD+1 < COD+10 < PostCOD."""
        keys = ["COD+10", "COD", "PostCOD", "COD-2", "PreCOD", "COD+1"]
        result = sort_period_keys(keys)
        assert result == ["PreCOD", "COD-2", "COD", "COD+1", "COD+10", "PostCOD"]

    def test_phase_year_sort(self):
        """Const-Year1 < Const-Year2 < Ops-Year1 < Ops-Year2."""
        keys = [
            "Operations Year 2",
            "Construction Year 2",
            "Operations Year 1",
            "Construction Year 1",
        ]
        result = sort_period_keys(keys)
        assert result == [
            "Construction Year 1",
            "Construction Year 2",
            "Operations Year 1",
            "Operations Year 2",
        ]

    def test_stub_sorts_after_cod(self):
        """Stub periods sort after COD-relative periods."""
        keys = ["Stub", "COD+1", "COD"]
        result = sort_period_keys(keys)
        assert result == ["COD", "COD+1", "Stub"]

    def test_relative_year_actual_before_forecast(self):
        """Year 1A < Year 1E."""
        keys = ["Year 1E", "Year 1A"]
        result = sort_period_keys(keys)
        assert result == ["Year 1A", "Year 1E"]


# ============================================================================
# PROJECT FINANCE SHEET DETECTION
# ============================================================================


class TestPFSheetDetection:
    """Verify detect_periods_from_sheet works with PF formats."""

    def test_relative_year_header(self):
        """Row with Year 1..Year 5 should be detected."""
        sheet = _make_sheet(
            header_values=["Year 1", "Year 2", "Year 3", "Year 4", "Year 5"],
        )
        p = PeriodParser()
        result = p.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 5
        assert result.dominant_type == "relative_year"

    def test_multi_row_construction_header(self):
        """Top: 'Construction' | 'Construction', Bottom: '1' | '2' → phase_year."""
        rows = [
            {
                "row_index": 1,
                "cells": [
                    _make_cell("A", 1, "Line Item"),
                    _make_cell("B", 1, "Construction"),
                    _make_cell("C", 1, "Construction"),
                    _make_cell("D", 1, "Construction"),
                ],
            },
            {
                "row_index": 2,
                "cells": [
                    _make_cell("A", 2, "Revenue"),
                    _make_cell("B", 2, "1"),
                    _make_cell("C", 2, "2"),
                    _make_cell("D", 2, "3"),
                ],
            },
        ]
        sheet = {"sheet_name": "Model", "rows": rows}
        p = PeriodParser()
        result = p.detect_periods_from_sheet(sheet)
        assert len(result.periods) >= 2
        # Should detect phase_year via "Construction Year 1" combined
        assert any(p.period_type == "phase_year" for p in result.periods)

    def test_cod_relative_header(self):
        """Row with COD-1, COD, COD+1, COD+2 should be detected."""
        sheet = _make_sheet(
            header_values=["COD-1", "COD", "COD+1", "COD+2"],
        )
        p = PeriodParser()
        result = p.detect_periods_from_sheet(sheet)
        assert len(result.periods) == 4
        assert result.dominant_type == "cod_relative"

    def test_mixed_pf_and_fy(self):
        """Mixed Year 1..Year 3 + FY2028..FY2030 in same row."""
        sheet = _make_sheet(
            header_values=["Year 1", "Year 2", "Year 3", "FY2028", "FY2029", "FY2030"],
            header_columns=["B", "C", "D", "E", "F", "G"],
        )
        p = PeriodParser()
        result = p.detect_periods_from_sheet(sheet)
        # All 6 should be detected (mix of relative_year and fiscal_year)
        assert len(result.periods) == 6


# ============================================================================
# PF PERIOD CONSISTENCY
# ============================================================================


class TestPFPeriodConsistency:
    """PF types should not trigger false 'mismatched_period_type' warnings."""

    def test_pf_types_compatible(self):
        """relative_year + phase_year on different sheets should NOT warn."""
        all_periods = {
            "Sheet1": {
                "dominant_type": "relative_year",
                "periods": [],
                "layout": "time_across_columns",
            },
            "Sheet2": {
                "dominant_type": "phase_year",
                "periods": [],
                "layout": "time_across_columns",
            },
        }
        warnings = check_period_consistency(all_periods)
        type_warnings = [w for w in warnings if w["type"] == "mismatched_period_type"]
        assert len(type_warnings) == 0

    def test_pf_vs_fiscal_warns(self):
        """relative_year vs fiscal_year SHOULD warn (different families)."""
        all_periods = {
            "Sheet1": {
                "dominant_type": "relative_year",
                "periods": [],
                "layout": "time_across_columns",
            },
            "Sheet2": {
                "dominant_type": "fiscal_year",
                "periods": [],
                "layout": "time_across_columns",
            },
        }
        warnings = check_period_consistency(all_periods)
        type_warnings = [w for w in warnings if w["type"] == "mismatched_period_type"]
        assert len(type_warnings) == 1
