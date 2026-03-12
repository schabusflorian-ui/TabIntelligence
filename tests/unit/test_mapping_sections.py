"""Unit tests for section context in mapping (WS-3 Part D)."""
import pytest

from src.extraction.stages.mapping import (
    MappingStage,
    _disambiguate_by_sheet_category,
)


class TestBuildSectionLookup:
    """Tests for _build_section_lookup()."""

    def test_empty_triage(self):
        """No section entries -> empty dict."""
        lookup = MappingStage._build_section_lookup([])
        assert lookup == {}

    def test_no_section_entries(self):
        """Triage with sheet-level entries only -> empty dict."""
        triage_list = [
            {"sheet_name": "IS", "tier": 1, "section": None, "section_start_row": None},
            {"sheet_name": "BS", "tier": 1, "section": None, "section_start_row": None},
        ]
        lookup = MappingStage._build_section_lookup(triage_list)
        assert lookup == {}

    def test_section_entries_grouped(self):
        """Section entries grouped by sheet_name."""
        triage_list = [
            {
                "sheet_name": "Combined",
                "tier": 1,
                "section": "Income Statement",
                "section_start_row": 1,
                "section_end_row": 25,
                "category_hint": "income_statement",
            },
            {
                "sheet_name": "Combined",
                "tier": 1,
                "section": "Balance Sheet",
                "section_start_row": 28,
                "section_end_row": 50,
                "category_hint": "balance_sheet",
            },
        ]
        lookup = MappingStage._build_section_lookup(triage_list)
        assert "Combined" in lookup
        assert len(lookup["Combined"]) == 2
        # Sorted by start_row
        assert lookup["Combined"][0]["section_start_row"] == 1
        assert lookup["Combined"][1]["section_start_row"] == 28


class TestGroupedItemsSectionCategory:
    """Tests for _build_grouped_line_items with section context."""

    def test_no_section_lookup(self):
        """Without section_lookup, items have no section_category."""
        parsed = {
            "sheets": [{
                "sheet_name": "IS",
                "rows": [
                    {"label": "Revenue", "row_index": 1},
                    {"label": "COGS", "row_index": 2},
                ],
            }],
        }
        items = MappingStage._build_grouped_line_items(parsed)
        assert all("section_category" not in item for item in items)

    def test_with_section_lookup(self):
        """Rows in a section get section_category."""
        parsed = {
            "sheets": [{
                "sheet_name": "Combined",
                "rows": [
                    {"label": "Revenue", "row_index": 5},
                    {"label": "Total Assets", "row_index": 30},
                ],
            }],
        }
        section_lookup = {
            "Combined": [
                {
                    "section_start_row": 1,
                    "section_end_row": 25,
                    "category_hint": "income_statement",
                },
                {
                    "section_start_row": 28,
                    "section_end_row": 50,
                    "category_hint": "balance_sheet",
                },
            ],
        }
        items = MappingStage._build_grouped_line_items(parsed, section_lookup)
        assert len(items) == 2
        assert items[0]["section_category"] == "income_statement"
        assert items[1]["section_category"] == "balance_sheet"

    def test_row_outside_sections(self):
        """Row not in any section range -> no section_category."""
        parsed = {
            "sheets": [{
                "sheet_name": "Combined",
                "rows": [
                    {"label": "Revenue", "row_index": 100},  # outside all sections
                ],
            }],
        }
        section_lookup = {
            "Combined": [
                {
                    "section_start_row": 1,
                    "section_end_row": 25,
                    "category_hint": "income_statement",
                },
            ],
        }
        items = MappingStage._build_grouped_line_items(parsed, section_lookup)
        assert len(items) == 1
        assert "section_category" not in items[0]


    def test_row_at_section_boundary_inclusive(self):
        """Rows at exact start/end of section are included (inclusive)."""
        parsed = {
            "sheets": [{
                "sheet_name": "Combined",
                "rows": [
                    {"label": "Revenue", "row_index": 1},    # exact start
                    {"label": "Net Income", "row_index": 25}, # exact end
                    {"label": "Cash", "row_index": 28},       # exact start
                    {"label": "Total", "row_index": 50},      # exact end
                ],
            }],
        }
        section_lookup = {
            "Combined": [
                {"section_start_row": 1, "section_end_row": 25, "category_hint": "income_statement"},
                {"section_start_row": 28, "section_end_row": 50, "category_hint": "balance_sheet"},
            ],
        }
        items = MappingStage._build_grouped_line_items(parsed, section_lookup)
        assert items[0]["section_category"] == "income_statement"
        assert items[1]["section_category"] == "income_statement"
        assert items[2]["section_category"] == "balance_sheet"
        assert items[3]["section_category"] == "balance_sheet"


class TestDisambiguationWithSections:
    """Tests for _disambiguate_by_sheet_category using section_category."""

    def test_section_category_overrides_sheet_name(self):
        """section_category takes priority over sheet name match."""
        # A row on sheet "Combined" (no match in _SHEET_TO_CATEGORY)
        # but with section_category = "income_statement"
        mappings = [
            {
                "original_label": "Depreciation & Amortization",
                "canonical_name": "depreciation_cf",  # wrong: cash_flow
            },
        ]
        grouped_items = [
            {
                "label": "Depreciation & Amortization",
                "sheet": "Combined",
                "section_category": "income_statement",
            },
        ]
        # Alias lookup: exact match for the label in income_statement category
        alias_lookup = {
            "depreciation & amortization": [
                ("depreciation_and_amortization", "income_statement"),
                ("depreciation_cf", "cash_flow"),
            ],
        }
        count = _disambiguate_by_sheet_category(
            mappings, grouped_items, alias_lookup,
        )
        assert count == 1
        assert mappings[0]["canonical_name"] == "depreciation_and_amortization"

    def test_falls_back_to_sheet_name(self):
        """Without section_category, falls back to _SHEET_TO_CATEGORY."""
        mappings = [
            {
                "original_label": "Depreciation & Amortization",
                "canonical_name": "depreciation_cf",
            },
        ]
        grouped_items = [
            {
                "label": "Depreciation & Amortization",
                "sheet": "Income Statement",  # matches _SHEET_TO_CATEGORY
            },
        ]
        alias_lookup = {
            "depreciation & amortization": [
                ("depreciation_and_amortization", "income_statement"),
                ("depreciation_cf", "cash_flow"),
            ],
        }
        count = _disambiguate_by_sheet_category(
            mappings, grouped_items, alias_lookup,
        )
        assert count == 1
        assert mappings[0]["canonical_name"] == "depreciation_and_amortization"

    def test_no_override_when_correct(self):
        """No override when canonical is already in the correct category."""
        mappings = [
            {
                "original_label": "Revenue",
                "canonical_name": "revenue",
            },
        ]
        grouped_items = [
            {
                "label": "Revenue",
                "sheet": "Income Statement",
                "section_category": "income_statement",
            },
        ]
        alias_lookup = {
            "revenue": [
                ("revenue", "income_statement"),
            ],
        }
        count = _disambiguate_by_sheet_category(
            mappings, grouped_items, alias_lookup,
        )
        assert count == 0
        assert mappings[0]["canonical_name"] == "revenue"
