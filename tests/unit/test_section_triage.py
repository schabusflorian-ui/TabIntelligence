"""Unit tests for section-aware triage (WS-3 Part C)."""
import pytest

from src.extraction.stages.triage import TriageStage


class TestBuildSheetSummaryWithSections:
    """Tests for _build_sheet_summary section detection integration."""

    def test_no_sections_for_simple_sheet(self):
        """Standard sheet with contiguous rows -> no 'sections' key."""
        parsed = {
            "sheets": [{"sheet_name": "IS", "rows": [
                {"label": f"Row {i}"} for i in range(10)
            ]}],
        }
        structured = {
            "sheets": [{
                "sheet_name": "IS",
                "rows": [
                    {"row_index": i, "cells": [
                        {"ref": f"A{i}", "value": f"Row {i}", "is_bold": False},
                    ]}
                    for i in range(1, 11)
                ],
                "merged_regions": [],
            }],
        }
        summaries = TriageStage._build_sheet_summary(parsed, structured)
        assert len(summaries) == 1
        assert "sections" not in summaries[0]

    def test_sections_for_multi_statement_sheet(self):
        """Sheet with 3 sections separated by gaps -> 'sections' key present."""
        parsed = {
            "sheets": [{"sheet_name": "Combined", "rows": [
                {"label": f"Row {i}"} for i in range(25)
            ]}],
        }
        # Build structured with gaps: rows 1-8, gap, rows 12-20, gap, rows 24-32
        struct_rows = (
            [{"row_index": 1, "cells": [
                {"ref": "A1", "value": "Income Statement", "is_bold": True},
            ]}]
            + [{"row_index": i, "cells": [
                {"ref": f"A{i}", "value": f"IS row {i}", "is_bold": False},
            ]} for i in range(2, 9)]
            + [{"row_index": 12, "cells": [
                {"ref": "A12", "value": "Balance Sheet", "is_bold": True},
            ]}]
            + [{"row_index": i, "cells": [
                {"ref": f"A{i}", "value": f"BS row {i}", "is_bold": False},
            ]} for i in range(13, 21)]
            + [{"row_index": 24, "cells": [
                {"ref": "A24", "value": "Cash Flow", "is_bold": True},
            ]}]
            + [{"row_index": i, "cells": [
                {"ref": f"A{i}", "value": f"CF row {i}", "is_bold": False},
            ]} for i in range(25, 33)]
        )
        structured = {
            "sheets": [{
                "sheet_name": "Combined",
                "rows": struct_rows,
                "merged_regions": [],
            }],
        }
        summaries = TriageStage._build_sheet_summary(parsed, structured)
        assert len(summaries) == 1
        assert "sections" in summaries[0]
        sections = summaries[0]["sections"]
        assert len(sections) == 3
        assert sections[0]["label"] == "Income Statement"
        assert sections[1]["label"] == "Balance Sheet"
        assert sections[2]["label"] == "Cash Flow"

    def test_no_sections_without_structured_data(self):
        """Without structured data, no sections detected."""
        parsed = {
            "sheets": [{"sheet_name": "IS", "rows": [
                {"label": "Revenue"},
            ]}],
        }
        summaries = TriageStage._build_sheet_summary(parsed, {})
        assert len(summaries) == 1
        assert "sections" not in summaries[0]


class TestTriageEntryNormalization:
    """Tests for section entry normalization."""

    def test_entries_get_section_defaults(self):
        """Triage entries without section fields get None defaults."""
        # Simulate what happens after extract_json returns triage list
        triage_list = [
            {"sheet_name": "IS", "tier": 1, "decision": "PROCESS_HIGH"},
            {"sheet_name": "BS", "tier": 1, "decision": "PROCESS_HIGH"},
        ]
        # Apply the same normalization as execute()
        for entry in triage_list:
            entry.setdefault("section", None)
            entry.setdefault("section_start_row", None)
            entry.setdefault("section_end_row", None)

        assert triage_list[0]["section"] is None
        assert triage_list[0]["section_start_row"] is None
        assert triage_list[0]["section_end_row"] is None

    def test_entries_with_section_preserved(self):
        """Triage entries with section fields are preserved."""
        triage_list = [
            {
                "sheet_name": "Combined",
                "tier": 1,
                "section": "Income Statement",
                "section_start_row": 1,
                "section_end_row": 25,
            },
        ]
        for entry in triage_list:
            entry.setdefault("section", None)
            entry.setdefault("section_start_row", None)
            entry.setdefault("section_end_row", None)

        assert triage_list[0]["section"] == "Income Statement"
        assert triage_list[0]["section_start_row"] == 1
        assert triage_list[0]["section_end_row"] == 25


class TestSectionMetricsComputation:
    """Tests for section metrics that flow into lineage_metadata."""

    def test_section_counts_from_summaries(self):
        """Section metrics are correctly computed from sheet summaries."""
        summaries = [
            {"name": "Combined", "sections": [
                {"label": "IS", "start_row": 1, "end_row": 10},
                {"label": "BS", "start_row": 15, "end_row": 25},
                {"label": "CF", "start_row": 30, "end_row": 40},
            ]},
            {"name": "IS Only"},  # No sections key
            {"name": "Another Combined", "sections": [
                {"label": "IS", "start_row": 1, "end_row": 10},
                {"label": "BS", "start_row": 15, "end_row": 25},
            ]},
        ]

        # Same computation as triage.py execute()
        total_sections = sum(
            len(s.get("sections", []))
            for s in summaries
        )
        multi_section_sheets = sum(
            1 for s in summaries
            if "sections" in s
        )

        assert total_sections == 5
        assert multi_section_sheets == 2

    def test_no_sections_yields_zero_counts(self):
        """When no sheets have sections, metrics are zero."""
        summaries = [
            {"name": "IS Only"},
            {"name": "BS Only"},
        ]

        total_sections = sum(
            len(s.get("sections", []))
            for s in summaries
        )
        multi_section_sheets = sum(
            1 for s in summaries
            if "sections" in s
        )

        assert total_sections == 0
        assert multi_section_sheets == 0
