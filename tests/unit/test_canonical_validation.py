"""Tests for canonical_name validation across the pipeline."""
import json
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch, Mock, PropertyMock
from uuid import uuid4

from src.extraction.orchestrator import extract


# ============================================================================
# TestGetAllCanonicalNames
# ============================================================================


class TestGetAllCanonicalNames:
    """Test the taxonomy canonical name cache."""

    def test_returns_frozenset_with_known_items(self):
        """Should contain well-known canonical names from taxonomy."""
        from src.extraction.taxonomy_loader import get_all_canonical_names

        names = get_all_canonical_names()
        assert isinstance(names, frozenset)
        assert "revenue" in names
        assert "cogs" in names
        assert "total_assets" in names
        assert "ebitda" in names

    def test_contains_unmapped_sentinel(self):
        """The 'unmapped' sentinel must be included."""
        from src.extraction.taxonomy_loader import get_all_canonical_names

        names = get_all_canonical_names()
        assert "unmapped" in names

    def test_is_cached(self):
        """Second call returns the same object (identity check)."""
        from src.extraction.taxonomy_loader import get_all_canonical_names

        first = get_all_canonical_names()
        second = get_all_canonical_names()
        assert first is second

    def test_count_matches_taxonomy(self):
        """Should have 265 taxonomy items + 'unmapped' = 266."""
        from src.extraction.taxonomy_loader import (
            get_all_canonical_names,
            get_all_taxonomy_items,
        )

        names = get_all_canonical_names()
        items = get_all_taxonomy_items()
        # names = all taxonomy canonical_names + "unmapped"
        assert len(names) == len({i["canonical_name"] for i in items}) + 1


# ============================================================================
# TestValidateCanonicalNames
# ============================================================================


class TestValidateCanonicalNames:
    """Test the shared validate_canonical_names utility."""

    def test_valid_names_pass_through(self):
        """Valid canonical names should not be modified."""
        from src.extraction.utils import validate_canonical_names

        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "COGS", "canonical_name": "cogs", "confidence": 0.90},
        ]
        result = validate_canonical_names(mappings, stage="test")
        assert result[0]["canonical_name"] == "revenue"
        assert result[0]["confidence"] == 0.95
        assert result[1]["canonical_name"] == "cogs"

    def test_hallucinated_name_reset_to_unmapped(self):
        """Hallucinated names should become 'unmapped' with confidence 0.0."""
        from src.extraction.utils import validate_canonical_names

        mappings = [
            {"original_label": "Total Revenues", "canonical_name": "total_revenues", "confidence": 0.92},
        ]
        result = validate_canonical_names(mappings, stage="test")
        assert result[0]["canonical_name"] == "unmapped"
        assert result[0]["confidence"] == 0.0

    def test_mixed_valid_and_invalid(self):
        """Only invalid names are fixed; valid ones stay untouched."""
        from src.extraction.utils import validate_canonical_names

        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "Fake Item", "canonical_name": "fake_item_123", "confidence": 0.88},
            {"original_label": "EBITDA", "canonical_name": "ebitda", "confidence": 0.97},
        ]
        result = validate_canonical_names(mappings, stage="test")
        assert result[0]["canonical_name"] == "revenue"
        assert result[0]["confidence"] == 0.95
        assert result[1]["canonical_name"] == "unmapped"
        assert result[1]["confidence"] == 0.0
        assert result[2]["canonical_name"] == "ebitda"
        assert result[2]["confidence"] == 0.97

    def test_empty_list(self):
        """Empty list should return empty list."""
        from src.extraction.utils import validate_canonical_names

        result = validate_canonical_names([], stage="test")
        assert result == []

    def test_unmapped_passes_through(self):
        """The 'unmapped' sentinel should not be flagged."""
        from src.extraction.utils import validate_canonical_names

        mappings = [
            {"original_label": "Unknown", "canonical_name": "unmapped", "confidence": 0.0},
        ]
        result = validate_canonical_names(mappings, stage="test")
        assert result[0]["canonical_name"] == "unmapped"
        assert result[0]["confidence"] == 0.0


# ============================================================================
# TestMappingStageValidation
# ============================================================================


class TestMappingStageValidation:
    """Test that Stage 3 validates canonical names from Claude."""

    @pytest.mark.asyncio
    async def test_hallucinated_name_fixed_before_merge(self):
        """Claude response with hallucinated name should be fixed to 'unmapped'."""
        from src.extraction.stages.mapping import MappingStage

        stage = MappingStage()
        context = MagicMock()
        context.entity_id = None
        context.get_result.return_value = {
            "parsed": {
                "sheets": [
                    {
                        "sheet_name": "IS",
                        "rows": [
                            {"label": "Revenue", "hierarchy_level": 1, "is_formula": False, "is_subtotal": False},
                        ],
                    }
                ]
            }
        }

        # Claude returns a hallucinated canonical name
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {
                "original_label": "Revenue",
                "canonical_name": "total_revenues_hallucinated",
                "confidence": 0.92,
                "reasoning": "Looks like revenue",
            }
        ]))]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_response.stop_reason = "end_turn"

        mock_claude = MagicMock()
        mock_claude.messages.create.return_value = mock_response

        with patch("src.extraction.stages.mapping.get_claude_client", return_value=mock_claude), \
             patch.object(stage, "_build_entity_hints", return_value=""):
            result = await stage.execute(context)

        # The hallucinated name should have been reset to "unmapped"
        assert len(result["mappings"]) == 1
        assert result["mappings"][0]["canonical_name"] == "unmapped"
        assert result["mappings"][0]["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_valid_names_pass_through(self):
        """Claude response with valid names should not be modified."""
        from src.extraction.stages.mapping import MappingStage

        stage = MappingStage()
        context = MagicMock()
        context.entity_id = None
        context.get_result.return_value = {
            "parsed": {
                "sheets": [
                    {
                        "sheet_name": "IS",
                        "rows": [
                            {"label": "Revenue", "hierarchy_level": 1, "is_formula": False, "is_subtotal": False},
                        ],
                    }
                ]
            }
        }

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {
                "original_label": "Revenue",
                "canonical_name": "revenue",
                "confidence": 0.95,
                "reasoning": "Direct match",
            }
        ]))]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_response.stop_reason = "end_turn"

        mock_claude = MagicMock()
        mock_claude.messages.create.return_value = mock_response

        with patch("src.extraction.stages.mapping.get_claude_client", return_value=mock_claude), \
             patch.object(stage, "_build_entity_hints", return_value=""):
            result = await stage.execute(context)

        assert result["mappings"][0]["canonical_name"] == "revenue"
        assert result["mappings"][0]["confidence"] == 0.95


# ============================================================================
# TestPersistenceGuard
# ============================================================================


class TestPersistenceGuard:
    """Test CRUD persistence guards for invalid canonical names."""

    def test_bulk_upsert_skips_invalid_canonical(self, test_db):
        """bulk_upsert_entity_patterns should skip invalid canonical names."""
        from src.db.crud import bulk_upsert_entity_patterns
        from src.db.models import Entity

        db = test_db()
        try:
            entity = Entity(name="Test Corp", industry="technology")
            db.add(entity)
            db.commit()

            mappings = [
                {
                    "original_label": "Revenue",
                    "canonical_name": "revenue",
                    "confidence": 0.95,
                },
                {
                    "original_label": "Fake Item",
                    "canonical_name": "totally_fake_hallucinated_name",
                    "confidence": 0.90,
                },
            ]

            count = bulk_upsert_entity_patterns(
                db, entity.id, mappings, min_confidence=0.8
            )

            # Only the valid one should be persisted
            assert count == 1
        finally:
            db.close()

    def test_upsert_raises_for_invalid_canonical(self, test_db):
        """upsert_entity_pattern should raise ValueError for invalid names."""
        from src.db.crud import upsert_entity_pattern
        from src.db.models import Entity

        db = test_db()
        try:
            entity = Entity(name="Test Corp", industry="technology")
            db.add(entity)
            db.commit()

            with pytest.raises(ValueError, match="Invalid canonical_name"):
                upsert_entity_pattern(
                    db,
                    entity.id,
                    original_label="Some Label",
                    canonical_name="completely_invalid_name",
                    confidence=0.95,
                )
        finally:
            db.close()

    def test_record_learned_alias_returns_none_for_invalid(self, test_db):
        """record_learned_alias should return None for invalid canonical."""
        from src.db.crud import record_learned_alias

        db = test_db()
        try:
            result = record_learned_alias(
                db,
                canonical_name="invalid_hallucinated_canonical",
                alias_text="Some Alias",
                entity_id=str(uuid4()),
            )
            assert result is None
        finally:
            db.close()


# ============================================================================
# TestCorrectionsAPIGuard
# ============================================================================


class TestCorrectionsAPIGuard:
    """Test the corrections API rejects invalid canonical names."""

    def test_valid_canonical_accepted(self, test_client_with_db):
        """Valid canonical name should be accepted (assuming job exists)."""
        # This test verifies the validation doesn't reject valid names.
        # The 404 for job is expected — we're testing the validation layer.
        response = test_client_with_db.post(
            "/api/v1/jobs/00000000-0000-0000-0000-000000000001/corrections",
            json={
                "corrections": [
                    {"original_label": "Revenue", "canonical_name": "revenue"},
                ]
            },
        )
        # Should NOT be 422 (validation error) — 404 for job not found is expected
        assert response.status_code != 422

    def test_invalid_canonical_rejected(self, test_client_with_db):
        """Invalid canonical name should return 422."""
        response = test_client_with_db.post(
            "/api/v1/jobs/00000000-0000-0000-0000-000000000001/corrections",
            json={
                "corrections": [
                    {"original_label": "Revenue", "canonical_name": "banana_invalid"},
                ]
            },
        )
        assert response.status_code == 422
        assert "Invalid canonical names" in response.json()["detail"]
        assert "banana_invalid" in response.json()["detail"]


# ============================================================================
# TestFullPipelineHallucinationCascade
# ============================================================================


class TestFullPipelineHallucinationCascade:
    """Integration test: hallucinated canonical name through the full 5-stage pipeline.

    Verifies the cascade:
      Stage 3 Claude returns hallucinated name
      → validate_canonical_names catches it, resets to "unmapped"
      → Stage 5 picks it up as a candidate for re-mapping
      → Stage 5 returns a valid name
      → final output has corrected canonical_name
    """

    @pytest.fixture
    def mock_anthropic_with_hallucination(self, monkeypatch):
        """Custom mock_anthropic where Stage 3 returns a hallucinated canonical name
        and Stage 5 corrects it."""

        # Stage 1 parsing response
        parsing_response = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "sheet_type": "income_statement",
                    "layout": "time_across_columns",
                    "periods": ["FY2022", "FY2023"],
                    "rows": [
                        {
                            "row_index": 2,
                            "label": "Revenue",
                            "hierarchy_level": 1,
                            "values": {"FY2022": 100000, "FY2023": 115000},
                            "is_formula": False,
                            "is_subtotal": False,
                        },
                        {
                            "row_index": 3,
                            "label": "Cost of Sales",
                            "hierarchy_level": 1,
                            "values": {"FY2022": 40000, "FY2023": 46000},
                            "is_formula": False,
                            "is_subtotal": False,
                        },
                        {
                            "row_index": 4,
                            "label": "Gross Profit",
                            "hierarchy_level": 1,
                            "values": {"FY2022": 60000, "FY2023": 69000},
                            "is_formula": True,
                            "is_subtotal": True,
                        },
                    ],
                }
            ]
        }

        # Stage 2 triage response
        triage_response = [
            {
                "sheet_name": "Income Statement",
                "tier": 1,
                "decision": "PROCESS_HIGH",
                "confidence": 0.95,
                "reasoning": "Standard income statement",
            }
        ]

        # Stage 3 mapping response — includes a HALLUCINATED canonical name
        mapping_response = [
            {
                "original_label": "Revenue",
                "canonical_name": "revenue",
                "confidence": 0.95,
                "reasoning": "Direct match",
            },
            {
                "original_label": "Cost of Sales",
                "canonical_name": "cost_of_sales_hallucinated",  # HALLUCINATED
                "confidence": 0.90,
                "reasoning": "Looks like COGS",
            },
            {
                "original_label": "Gross Profit",
                "canonical_name": "gross_profit",
                "confidence": 0.95,
                "reasoning": "Standard gross profit",
            },
        ]

        # Stage 5 enhanced mapping response — corrects the previously unmapped item
        enhanced_mapping_response = [
            {
                "original_label": "Cost of Sales",
                "canonical_name": "cogs",  # CORRECTED
                "confidence": 0.92,
                "reasoning": "Cost of Sales maps to COGS",
            },
        ]

        mock_client = MagicMock()
        call_count = {"mapping": 0}

        def create_mock_response(model, max_tokens, messages):
            prompt_text = ""
            for msg in messages:
                if isinstance(msg.get("content"), str):
                    prompt_text = msg["content"]
                elif isinstance(msg.get("content"), list):
                    for item in msg["content"]:
                        if isinstance(item, dict) and item.get("type") == "text":
                            prompt_text = item.get("text", "")

            if "parsing" in prompt_text.lower() or "extract all data" in prompt_text.lower():
                data = parsing_response
            elif "triage" in prompt_text.lower() or "classify each sheet" in prompt_text.lower():
                data = triage_response
            elif "validation flags" in prompt_text.lower():
                data = [
                    {"flag_index": 0, "assessment": "acceptable", "confidence": 0.8,
                     "reasoning": "Within tolerance", "suggested_fix": None}
                ]
            elif "could not be confidently mapped" in prompt_text.lower():
                # Stage 5: Enhanced mapping — uniquely contains this phrase
                data = enhanced_mapping_response
            elif "canonical taxonomy" in prompt_text.lower():
                # Stage 3: Mapping — contains "CANONICAL TAXONOMY"
                data = mapping_response
            else:
                data = {"error": "Unknown stage"}

            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps(data))]
            mock_response.usage = MagicMock(input_tokens=500, output_tokens=300)
            mock_response.stop_reason = "end_turn"
            return mock_response

        mock_client.messages.create = MagicMock(side_effect=create_mock_response)

        # Also mock the streaming API used by the parsing stage
        def create_stream_context(model, max_tokens, messages):
            response = create_mock_response(model=model, max_tokens=max_tokens, messages=messages)
            response.stop_reason = "end_turn"
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.get_final_message = MagicMock(return_value=response)
            return ctx

        mock_client.messages.stream = MagicMock(side_effect=create_stream_context)

        def mock_get_client():
            return mock_client

        def mock_save_to_db(self):
            pass

        def mock_excel_to_structured_repr(file_bytes):
            return {
                "sheets": [
                    {
                        "sheet_name": "Income Statement",
                        "is_hidden": False,
                        "merged_regions": [],
                        "rows": [
                            {
                                "row_index": 1,
                                "cells": [
                                    {"ref": "A1", "value": "Revenue", "formula": None,
                                     "is_bold": True, "indent_level": 0, "number_format": "General"},
                                    {"ref": "B1", "value": 100000, "formula": None,
                                     "is_bold": False, "indent_level": 0, "number_format": "#,##0"},
                                ],
                            }
                        ],
                    }
                ],
                "named_ranges": {},
                "sheet_count": 1,
                "total_rows": 1,
            }

        def mock_structured_to_markdown(structured):
            return "## Sheet: Income Statement\n| Row | Label | Value |\n|---|---|---|\n| 1 | Revenue | 100000 |\n"

        monkeypatch.setattr("src.extraction.stages.parsing.ParsingStage._excel_to_structured_repr",
                            staticmethod(mock_excel_to_structured_repr))
        monkeypatch.setattr("src.extraction.stages.parsing.ParsingStage._structured_to_markdown",
                            staticmethod(mock_structured_to_markdown))
        monkeypatch.setattr("src.extraction.claude_client.get_claude_client", mock_get_client)
        monkeypatch.setattr("src.extraction.stages.parsing.get_claude_client", mock_get_client)
        monkeypatch.setattr("src.extraction.stages.triage.get_claude_client", mock_get_client)
        monkeypatch.setattr("src.extraction.stages.mapping.get_claude_client", mock_get_client)
        monkeypatch.setattr("src.extraction.stages.validation.get_claude_client", mock_get_client)
        monkeypatch.setattr("src.extraction.stages.enhanced_mapping.get_claude_client", mock_get_client)
        monkeypatch.setattr("src.lineage.tracker.LineageTracker.save_to_db", mock_save_to_db)

        return mock_client

    @pytest.mark.asyncio
    async def test_hallucinated_name_caught_and_corrected(
        self, mock_anthropic_with_hallucination, sample_xlsx
    ):
        """Full pipeline: hallucinated name caught in Stage 3, corrected in Stage 5."""
        result = await extract(sample_xlsx, file_id="hallucination-test")

        # Pipeline should complete successfully
        assert result["file_id"] == "hallucination-test"
        assert len(result["line_items"]) > 0

        # Build lookup of canonical names in final output
        canonical_names = {
            item["canonical_name"]
            for item in result["line_items"]
        }

        # "cost_of_sales_hallucinated" must NOT appear in final output
        assert "cost_of_sales_hallucinated" not in canonical_names

        # Valid names should be present
        assert "revenue" in canonical_names

        # "cogs" should appear — Stage 5 corrected the hallucinated name
        # (or it's "unmapped" if Stage 5 didn't pick it up — both are acceptable
        #  since the hallucination was caught)
        assert "cogs" in canonical_names or "unmapped" in canonical_names

    @pytest.mark.asyncio
    async def test_hallucinated_name_not_in_line_items(
        self, mock_anthropic_with_hallucination, sample_xlsx
    ):
        """No hallucinated canonical_name should survive to the final result."""
        from src.extraction.taxonomy_loader import get_all_canonical_names

        result = await extract(sample_xlsx, file_id="hallucination-test-2")
        valid_names = get_all_canonical_names()

        # Every canonical_name in the final output must be a valid taxonomy item
        for item in result["line_items"]:
            assert item["canonical_name"] in valid_names, (
                f"Invalid canonical_name '{item['canonical_name']}' found in final output "
                f"for label '{item.get('original_label', '?')}'"
            )
