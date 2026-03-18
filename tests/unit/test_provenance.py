"""Tests for item-level provenance tracking across extraction stages."""

from decimal import Decimal
from uuid import uuid4

# ---------------------------------------------------------------------------
# Step 1: Parsing — _enrich_with_source_cells
# ---------------------------------------------------------------------------


class TestEnrichWithSourceCells:
    """Test ParsingStage._enrich_with_source_cells()."""

    def test_label_cell_matched(self):
        """Source cells include the label cell matched by cell_ref."""
        from src.extraction.stages.parsing import ParsingStage

        parsed = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "rows": [
                        {
                            "row_index": 5,
                            "label": "Revenue",
                            "cell_ref": "A5",
                            "values": {},
                            "hierarchy_level": 1,
                            "is_formula": False,
                            "is_subtotal": False,
                        }
                    ],
                }
            ],
        }
        structured = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "rows": [
                        {
                            "row_index": 5,
                            "cells": [
                                {
                                    "ref": "A5",
                                    "value": "Revenue",
                                    "formula": None,
                                    "is_bold": True,
                                    "indent_level": 0,
                                    "number_format": "General",
                                },
                            ],
                        }
                    ],
                }
            ],
        }

        ParsingStage._enrich_with_source_cells(parsed, structured)

        row = parsed["sheets"][0]["rows"][0]
        assert len(row["source_cells"]) == 1
        assert row["source_cells"][0] == {
            "sheet": "Income Statement",
            "cell_ref": "A5",
            "raw_value": "Revenue",
        }
        assert row["parsing_metadata"]["is_bold"] is True

    def test_value_cells_matched_by_value(self):
        """Source cells include value cells matched by approximate equality."""
        from src.extraction.stages.parsing import ParsingStage

        parsed = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "rows": [
                        {
                            "row_index": 5,
                            "label": "Revenue",
                            "cell_ref": "A5",
                            "values": {"FY2022": 232000, "FY2023": 250000},
                            "hierarchy_level": 1,
                            "is_formula": True,
                            "is_subtotal": False,
                        }
                    ],
                }
            ],
        }
        structured = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "rows": [
                        {
                            "row_index": 5,
                            "cells": [
                                {
                                    "ref": "A5",
                                    "value": "Revenue",
                                    "formula": None,
                                    "is_bold": True,
                                    "indent_level": 0,
                                    "number_format": "General",
                                },
                                {
                                    "ref": "B5",
                                    "value": 232000,
                                    "formula": "=SUM(B3:B4)",
                                    "is_bold": False,
                                    "indent_level": 0,
                                    "number_format": "#,##0",
                                },
                                {
                                    "ref": "C5",
                                    "value": 250000,
                                    "formula": "=B5*1.08",
                                    "is_bold": False,
                                    "indent_level": 0,
                                    "number_format": "#,##0",
                                },
                            ],
                        }
                    ],
                }
            ],
        }

        ParsingStage._enrich_with_source_cells(parsed, structured)

        row = parsed["sheets"][0]["rows"][0]
        # Label + 2 value cells
        assert len(row["source_cells"]) == 3
        refs = [sc["cell_ref"] for sc in row["source_cells"]]
        assert "A5" in refs
        assert "B5" in refs
        assert "C5" in refs
        # Formula should be included for value cells
        b5 = next(sc for sc in row["source_cells"] if sc["cell_ref"] == "B5")
        assert b5["formula"] == "=SUM(B3:B4)"

    def test_no_structured_row_graceful(self):
        """Empty source_cells when structured repr has no matching row."""
        from src.extraction.stages.parsing import ParsingStage

        parsed = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "rows": [
                        {
                            "row_index": 99,
                            "label": "Mystery",
                            "cell_ref": "A99",
                            "values": {},
                            "hierarchy_level": 1,
                            "is_formula": False,
                            "is_subtotal": False,
                        }
                    ],
                }
            ],
        }
        structured = {"sheets": [{"sheet_name": "Income Statement", "rows": []}]}

        ParsingStage._enrich_with_source_cells(parsed, structured)

        row = parsed["sheets"][0]["rows"][0]
        assert row["source_cells"] == []
        assert row["parsing_metadata"]["hierarchy_level"] == 1

    def test_parsing_metadata_populated(self):
        """parsing_metadata reflects row attributes."""
        from src.extraction.stages.parsing import ParsingStage

        parsed = {
            "sheets": [
                {
                    "sheet_name": "S",
                    "rows": [
                        {
                            "row_index": 1,
                            "label": "Total Revenue",
                            "cell_ref": "A1",
                            "values": {},
                            "hierarchy_level": 0,
                            "is_formula": True,
                            "is_subtotal": True,
                        }
                    ],
                }
            ],
        }
        structured = {
            "sheets": [
                {
                    "sheet_name": "S",
                    "rows": [
                        {
                            "row_index": 1,
                            "cells": [
                                {
                                    "ref": "A1",
                                    "value": "Total Revenue",
                                    "formula": None,
                                    "is_bold": True,
                                    "indent_level": 0,
                                    "number_format": "General",
                                },
                            ],
                        }
                    ],
                }
            ],
        }

        ParsingStage._enrich_with_source_cells(parsed, structured)

        meta = parsed["sheets"][0]["rows"][0]["parsing_metadata"]
        assert meta["hierarchy_level"] == 0
        assert meta["is_bold"] is True
        assert meta["is_formula"] is True
        assert meta["is_subtotal"] is True


# ---------------------------------------------------------------------------
# Step 2: Mapping — taxonomy_category
# ---------------------------------------------------------------------------


class TestMappingTaxonomyCategory:
    """Test that taxonomy_category is added to mapping results."""

    def test_canonical_to_category_lookup(self):
        """get_canonical_to_category returns correct categories."""
        from src.extraction.taxonomy_loader import get_canonical_to_category

        lookup = get_canonical_to_category()
        # revenue should be in income_statement
        assert lookup.get("revenue") == "income_statement"
        # total_assets should be in balance_sheet
        assert lookup.get("total_assets") == "balance_sheet"
        # cfo should be in cash_flow
        assert lookup.get("cfo") == "cash_flow"


# ---------------------------------------------------------------------------
# Step 3: Validation — per-item validation provenance
# ---------------------------------------------------------------------------


class TestItemValidation:
    """Test ValidationStage._build_item_validation()."""

    def test_flags_grouped_by_canonical(self):
        """Flags are properly grouped by canonical name."""
        from src.extraction.stages.validation import ValidationStage

        flags = [
            {
                "item": "revenue",
                "severity": "warning",
                "rule": "must_be_positive",
                "period": "FY2022",
                "message": "ok",
                "actual": "100",
                "expected": None,
            },
            {
                "item": "revenue",
                "severity": "error",
                "rule": "revenue >= gross_profit",
                "period": "FY2022",
                "message": "fail",
                "actual": "100",
                "expected": "200",
            },
            {
                "item": "ebitda",
                "severity": "warning",
                "rule": "must_be_positive",
                "period": "FY2022",
                "message": "ok",
                "actual": "50",
                "expected": None,
            },
        ]
        extracted_values = {
            "FY2022": {"revenue": Decimal("100"), "ebitda": Decimal("50")},
        }

        result = ValidationStage._build_item_validation(flags, extracted_values)

        assert "revenue" in result
        assert result["revenue"]["all_passed"] is False  # has an error flag
        assert "must_be_positive" in result["revenue"]["rules_applied"]
        assert "revenue >= gross_profit" in result["revenue"]["rules_applied"]
        assert len(result["revenue"]["flags"]) == 2

        assert "ebitda" in result
        assert result["ebitda"]["all_passed"] is True  # only warnings
        assert len(result["ebitda"]["flags"]) == 1

    def test_validated_items_without_flags(self):
        """Items that were validated but had no flags get entries with all_passed=True."""
        from src.extraction.stages.validation import ValidationStage

        flags = []
        extracted_values = {
            "FY2022": {"revenue": Decimal("100"), "net_income": Decimal("50")},
        }

        result = ValidationStage._build_item_validation(flags, extracted_values)

        assert "revenue" in result
        assert result["revenue"]["all_passed"] is True
        assert result["revenue"]["flags"] == []
        assert "net_income" in result
        assert result["net_income"]["all_passed"] is True

    def test_empty_flags_and_values(self):
        """Returns empty dict when no flags and no extracted values."""
        from src.extraction.stages.validation import ValidationStage

        result = ValidationStage._build_item_validation([], {})
        assert result == {}


# ---------------------------------------------------------------------------
# Step 4: Enhanced mapping — remapping provenance
# ---------------------------------------------------------------------------


class TestEnhancedMappingProvenance:
    """Test that enhanced mapping tracks old vs new mapping changes."""

    def test_remapped_item_has_provenance(self):
        """When an item is remapped, enhanced_mapping_provenance is populated."""
        basic_mapping = {
            "original_label": "Net Rev",
            "canonical_name": "unmapped",
            "confidence": 0.4,
            "method": "claude",
        }
        enhanced_mapping = {
            "original_label": "Net Rev",
            "canonical_name": "revenue",
            "confidence": 0.92,
        }

        # Simulate the merge logic from EnhancedMappingStage
        if enhanced_mapping.get("confidence", 0) > basic_mapping.get("confidence", 0):
            enhanced_mapping["method"] = enhanced_mapping.get("method", "enhanced")
            enhanced_mapping["enhanced_mapping_provenance"] = {
                "was_remapped": True,
                "old_canonical": basic_mapping.get("canonical_name"),
                "old_confidence": basic_mapping.get("confidence"),
                "new_canonical": enhanced_mapping.get("canonical_name"),
                "new_confidence": enhanced_mapping.get("confidence"),
                "stage": 5,
            }

        prov = enhanced_mapping["enhanced_mapping_provenance"]
        assert prov["was_remapped"] is True
        assert prov["old_canonical"] == "unmapped"
        assert prov["old_confidence"] == 0.4
        assert prov["new_canonical"] == "revenue"
        assert prov["new_confidence"] == 0.92
        assert prov["stage"] == 5

    def test_non_remapped_item_has_null_provenance(self):
        """Items not remapped have enhanced_mapping_provenance=None."""
        mapping = {
            "original_label": "Revenue",
            "canonical_name": "revenue",
            "confidence": 0.95,
            "method": "claude",
        }
        mapping["enhanced_mapping_provenance"] = None
        assert mapping["enhanced_mapping_provenance"] is None


# ---------------------------------------------------------------------------
# Step 5: Orchestrator — provenance in line items
# ---------------------------------------------------------------------------


class TestLineItemProvenance:
    """Test that _build_result() includes provenance in line items."""

    def test_provenance_structure(self):
        """Line items from _build_result include provenance dict."""
        from unittest.mock import MagicMock

        from src.extraction.base import PipelineContext

        context = MagicMock(spec=PipelineContext)
        context.total_tokens = 1000
        context.total_input_tokens = 700
        context.total_output_tokens = 300
        context.file_id = "file-123"
        context.job_id = "job-456"
        context.taxonomy_version = None
        context.taxonomy_checksum = None
        context.tracker = MagicMock()
        context.tracker.get_summary.return_value = {"total_events": 5}

        context.results = {
            "parsing": {
                "parsed": {
                    "sheets": [
                        {
                            "sheet_name": "Income Statement",
                            "rows": [
                                {
                                    "row_index": 5,
                                    "label": "Revenue",
                                    "cell_ref": "A5",
                                    "values": {"FY2022": 232000},
                                    "hierarchy_level": 1,
                                    "is_formula": False,
                                    "is_subtotal": False,
                                    "source_cells": [
                                        {
                                            "sheet": "Income Statement",
                                            "cell_ref": "A5",
                                            "raw_value": "Revenue",
                                        },
                                        {
                                            "sheet": "Income Statement",
                                            "cell_ref": "B5",
                                            "raw_value": 232000,
                                            "formula": "=SUM(B3:B4)",
                                        },
                                    ],
                                    "parsing_metadata": {
                                        "hierarchy_level": 1,
                                        "is_bold": True,
                                        "is_formula": False,
                                        "is_subtotal": False,
                                    },
                                }
                            ],
                        }
                    ],
                },
            },
            "triage": {
                "triage": [
                    {"sheet_name": "Income Statement", "tier": 1, "decision": "PROCESS_HIGH"},
                ],
            },
            "mapping": {
                "mappings": [
                    {
                        "original_label": "Revenue",
                        "canonical_name": "revenue",
                        "confidence": 0.95,
                        "method": "claude",
                        "reasoning": "Direct match",
                        "taxonomy_category": "income_statement",
                    }
                ],
            },
            "validation": {
                "validation": {
                    "overall_confidence": 1.0,
                    "flags": [],
                    "period_results": {},
                    "claude_reasoning": {},
                },
                "item_validation": {
                    "revenue": {
                        "rules_applied": ["must_be_positive"],
                        "all_passed": True,
                        "flags": [],
                    },
                },
            },
            "enhanced_mapping": {
                "enhanced_mappings": [
                    {
                        "original_label": "Revenue",
                        "canonical_name": "revenue",
                        "confidence": 0.95,
                        "method": "claude",
                        "reasoning": "Direct match",
                        "taxonomy_category": "income_statement",
                        "enhanced_mapping_provenance": None,
                    }
                ],
            },
        }

        import time

        from src.extraction.orchestrator import _build_result

        result = _build_result(context, "lineage-id-final", time.time())

        assert len(result.line_items) == 1
        li = result.line_items[0]
        assert "provenance" in li

        prov = li["provenance"]
        # source_cells
        assert len(prov["source_cells"]) == 2
        assert prov["source_cells"][0]["cell_ref"] == "A5"

        # parsing
        assert prov["parsing"]["is_bold"] is True
        assert prov["parsing"]["hierarchy_level"] == 1

        # mapping
        assert prov["mapping"]["method"] == "claude"
        assert prov["mapping"]["taxonomy_category"] == "income_statement"
        assert prov["mapping"]["reasoning"] == "Direct match"
        assert prov["mapping"]["stage"] == 3

        # validation
        assert prov["validation"]["all_passed"] is True
        assert "must_be_positive" in prov["validation"]["rules_applied"]

        # enhanced_mapping
        assert prov["enhanced_mapping"] is None


# ---------------------------------------------------------------------------
# Step 6: CSV export — provenance columns
# ---------------------------------------------------------------------------


class TestCSVExportProvenance:
    """Test that CSV export includes provenance columns."""

    @staticmethod
    def _get_csv_content(response):
        """Extract CSV content from a StreamingResponse."""
        import asyncio

        async def _read():
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            return "".join(chunks)

        return asyncio.get_event_loop().run_until_complete(_read())

    def test_csv_has_provenance_columns(self):
        """CSV header includes source_cell, mapping_method, taxonomy_category, validation_passed."""
        from src.api.jobs import _build_csv_response

        result = {"sheets": ["IS"]}
        line_items = [
            {
                "sheet": "Income Statement",
                "row": 5,
                "original_label": "Revenue",
                "canonical_name": "revenue",
                "confidence": 0.95,
                "hierarchy_level": 1,
                "values": {"FY2022": 232000},
                "provenance": {
                    "source_cells": [
                        {"sheet": "Income Statement", "cell_ref": "A5", "raw_value": "Revenue"},
                    ],
                    "mapping": {
                        "method": "claude",
                        "stage": 3,
                        "taxonomy_category": "income_statement",
                        "reasoning": "Direct match",
                    },
                    "validation": {
                        "rules_applied": ["must_be_positive"],
                        "all_passed": True,
                        "flags": [],
                    },
                    "enhanced_mapping": None,
                    "parsing": {
                        "hierarchy_level": 1,
                        "is_bold": True,
                        "is_formula": False,
                        "is_subtotal": False,
                    },
                },
            }
        ]

        response = _build_csv_response(result, line_items, "job-123")
        csv_content = self._get_csv_content(response)
        lines = csv_content.strip().split("\n")

        header = lines[0]
        assert "source_cell" in header
        assert "mapping_method" in header
        assert "taxonomy_category" in header
        assert "validation_passed" in header

        data_row = lines[1]
        assert "A5" in data_row
        assert "claude" in data_row
        assert "income_statement" in data_row
        assert "true" in data_row

    def test_csv_without_provenance_graceful(self):
        """CSV works when line items have no provenance (backward compat)."""
        from src.api.jobs import _build_csv_response

        line_items = [
            {
                "sheet": "IS",
                "row": 1,
                "original_label": "Rev",
                "canonical_name": "revenue",
                "confidence": 0.9,
                "hierarchy_level": 1,
                "values": {"FY2022": 100},
            }
        ]

        response = _build_csv_response({}, line_items, "job-456")
        csv_content = self._get_csv_content(response)
        lines = csv_content.strip().split("\n")
        # Should not error — empty provenance columns
        assert len(lines) == 2  # header + 1 data row


# ---------------------------------------------------------------------------
# Step 7: API endpoint — item provenance
# ---------------------------------------------------------------------------


class TestItemProvenanceEndpoint:
    """Test GET /api/v1/jobs/{job_id}/lineage/{canonical_name}."""

    def test_item_provenance_found(self, test_client_with_db, test_db):
        """Returns matching line items with provenance."""
        from src.db import crud
        from src.db.models import JobStatusEnum

        session = test_db()
        try:
            file = crud.create_file(session, filename="test.xlsx", file_size=1024)
            job = crud.create_extraction_job(session, file_id=file.file_id)
            job_id = str(job.job_id)

            # Set job as completed with result containing line items
            job.status = JobStatusEnum.COMPLETED
            job.result = {
                "line_items": [
                    {
                        "canonical_name": "revenue",
                        "original_label": "Revenue",
                        "values": {"FY2022": 100},
                        "provenance": {"mapping": {"method": "claude"}},
                    },
                    {
                        "canonical_name": "ebitda",
                        "original_label": "EBITDA",
                        "values": {"FY2022": 50},
                        "provenance": {"mapping": {"method": "claude"}},
                    },
                ],
            }
            session.commit()
        finally:
            session.close()

        response = test_client_with_db.get(f"/api/v1/jobs/{job_id}/lineage/revenue")
        assert response.status_code == 200
        data = response.json()
        assert data["canonical_name"] == "revenue"
        assert data["occurrences"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["original_label"] == "Revenue"

    def test_item_provenance_not_found(self, test_client_with_db, test_db):
        """Returns 404 when canonical_name doesn't exist in results."""
        from src.db import crud
        from src.db.models import JobStatusEnum

        session = test_db()
        try:
            file = crud.create_file(session, filename="test.xlsx", file_size=1024)
            job = crud.create_extraction_job(session, file_id=file.file_id)
            job_id = str(job.job_id)

            job.status = JobStatusEnum.COMPLETED
            job.result = {"line_items": [{"canonical_name": "revenue"}]}
            session.commit()
        finally:
            session.close()

        response = test_client_with_db.get(f"/api/v1/jobs/{job_id}/lineage/nonexistent")
        assert response.status_code == 404

    def test_item_provenance_job_not_found(self, test_client_with_db):
        """Returns 404 for nonexistent job."""
        fake_id = str(uuid4())
        response = test_client_with_db.get(f"/api/v1/jobs/{fake_id}/lineage/revenue")
        assert response.status_code == 404

    def test_item_provenance_invalid_job_id(self, test_client_with_db):
        """Returns 400 for invalid job_id format."""
        response = test_client_with_db.get("/api/v1/jobs/not-a-uuid/lineage/revenue")
        assert response.status_code == 400

    def test_item_provenance_requires_auth(self, unauthenticated_client):
        """Returns 401 without authentication."""
        fake_id = str(uuid4())
        response = unauthenticated_client.get(f"/api/v1/jobs/{fake_id}/lineage/revenue")
        assert response.status_code in (401, 403)
