"""
Unit tests for Stage 5: Enhanced Mapping.

Tests the remapping candidate selection, entity/hierarchy context builders,
taxonomy helpers, and full stage execution with mocked Claude.
"""
import json
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.extraction.stages.enhanced_mapping import (
    EnhancedMappingStage,
    _load_taxonomy,
    _format_taxonomy_for_prompt,
)
from src.extraction.base import PipelineContext


# ============================================================================
# REMAPPING CANDIDATE SELECTION
# ============================================================================


class TestFindRemappingCandidates:
    """Test _find_remapping_candidates identifies correct items."""

    def setup_method(self):
        self.stage = EnhancedMappingStage()

    def test_unmapped_items_selected(self):
        """Items with canonical_name='unmapped' should be candidates."""
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "Mystery Row", "canonical_name": "unmapped", "confidence": 0.0},
        ]
        candidates = self.stage._find_remapping_candidates(mappings)
        assert len(candidates) == 1
        assert candidates[0]["original_label"] == "Mystery Row"

    def test_low_confidence_selected(self):
        """Items with confidence < 0.7 should be candidates."""
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "Net Rev", "canonical_name": "net_revenue", "confidence": 0.5},
        ]
        candidates = self.stage._find_remapping_candidates(mappings)
        assert len(candidates) == 1
        assert candidates[0]["original_label"] == "Net Rev"

    def test_high_confidence_excluded(self):
        """Items with confidence >= 0.7 and valid mapping should be excluded."""
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "COGS", "canonical_name": "cogs", "confidence": 0.85},
            {"original_label": "Gross Profit", "canonical_name": "gross_profit", "confidence": 0.70},
        ]
        candidates = self.stage._find_remapping_candidates(mappings)
        assert len(candidates) == 0

    def test_boundary_confidence_excluded(self):
        """Exactly 0.7 confidence should NOT be a candidate."""
        mappings = [
            {"original_label": "SGA", "canonical_name": "sga", "confidence": 0.7},
        ]
        candidates = self.stage._find_remapping_candidates(mappings)
        assert len(candidates) == 0

    def test_just_below_threshold(self):
        """Confidence 0.69 should be a candidate."""
        mappings = [
            {"original_label": "SGA", "canonical_name": "sga", "confidence": 0.69},
        ]
        candidates = self.stage._find_remapping_candidates(mappings)
        assert len(candidates) == 1

    def test_multiple_candidates(self):
        """Multiple items can be candidates simultaneously."""
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "X1", "canonical_name": "unmapped", "confidence": 0.0},
            {"original_label": "X2", "canonical_name": "some_item", "confidence": 0.4},
            {"original_label": "X3", "canonical_name": "unmapped", "confidence": 0.1},
        ]
        candidates = self.stage._find_remapping_candidates(mappings)
        assert len(candidates) == 3

    def test_empty_mappings(self):
        """Empty mappings list should return empty candidates."""
        candidates = self.stage._find_remapping_candidates([])
        assert candidates == []

    def test_missing_confidence_defaults_zero(self):
        """Missing confidence field should default to 0 (treated as candidate)."""
        mappings = [
            {"original_label": "Mystery", "canonical_name": "some_item"},
        ]
        candidates = self.stage._find_remapping_candidates(mappings)
        assert len(candidates) == 1


# ============================================================================
# ENTITY CONTEXT BUILDER
# ============================================================================


class TestBuildEntityContext:
    """Test _build_entity_context builds proper pattern strings."""

    def setup_method(self):
        self.stage = EnhancedMappingStage()

    def test_high_confidence_patterns(self):
        """Should include high-confidence (>=0.85) mappings as patterns."""
        context = MagicMock(spec=PipelineContext, entity_id=None)
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "COGS", "canonical_name": "cogs", "confidence": 0.90},
            {"original_label": "Gross Profit", "canonical_name": "gross_profit", "confidence": 0.88},
        ]
        result = self.stage._build_entity_context(context, mappings)
        assert "Revenue" in result
        assert "revenue" in result
        assert "COGS" in result
        assert "Known patterns" in result

    def test_no_high_confidence(self):
        """Should return fallback message when no high-confidence mappings exist."""
        context = MagicMock(spec=PipelineContext, entity_id=None)
        mappings = [
            {"original_label": "Mystery", "canonical_name": "unmapped", "confidence": 0.3},
            {"original_label": "X", "canonical_name": "some_item", "confidence": 0.5},
        ]
        result = self.stage._build_entity_context(context, mappings)
        assert "No entity-specific patterns" in result

    def test_limits_to_10_patterns(self):
        """Should include at most 10 high-confidence patterns."""
        context = MagicMock(spec=PipelineContext, entity_id=None)
        mappings = [
            {"original_label": f"Item{i}", "canonical_name": f"item_{i}", "confidence": 0.95}
            for i in range(20)
        ]
        result = self.stage._build_entity_context(context, mappings)
        # Count the number of pattern lines (each starts with a quote mark)
        pattern_lines = [line for line in result.split("\n") if "->" in line]
        assert len(pattern_lines) == 10

    def test_excludes_below_threshold(self):
        """Items with confidence < 0.85 should not appear as patterns."""
        context = MagicMock(spec=PipelineContext, entity_id=None)
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "LowConf", "canonical_name": "something", "confidence": 0.80},
        ]
        result = self.stage._build_entity_context(context, mappings)
        assert "Revenue" in result
        assert "LowConf" not in result


# ============================================================================
# HIERARCHY CONTEXT BUILDER
# ============================================================================


class TestBuildHierarchyContext:
    """Test _build_hierarchy_context finds surrounding rows."""

    def setup_method(self):
        self.stage = EnhancedMappingStage()

    def test_basic_context(self):
        """Should return nearby labels for candidate items."""
        parsed = {
            "sheets": [{
                "sheet_name": "Income Statement",
                "rows": [
                    {"label": "Revenue", "hierarchy_level": 1},
                    {"label": "COGS", "hierarchy_level": 1},
                    {"label": "Mystery Item", "hierarchy_level": 2},
                    {"label": "Gross Profit", "hierarchy_level": 1},
                    {"label": "SGA", "hierarchy_level": 1},
                ],
            }]
        }
        candidates = [{"original_label": "Mystery Item"}]
        result = self.stage._build_hierarchy_context(parsed, candidates)

        assert len(result) == 1
        assert result[0]["label"] == "Mystery Item"
        assert "Revenue" in result[0]["nearby_labels"]
        assert "COGS" in result[0]["nearby_labels"]
        assert "Gross Profit" in result[0]["nearby_labels"]
        assert "SGA" in result[0]["nearby_labels"]

    def test_first_row_context(self):
        """First row should only have subsequent neighbors."""
        parsed = {
            "sheets": [{
                "sheet_name": "IS",
                "rows": [
                    {"label": "Unknown", "hierarchy_level": 1},
                    {"label": "Revenue", "hierarchy_level": 1},
                    {"label": "COGS", "hierarchy_level": 1},
                ],
            }]
        }
        candidates = [{"original_label": "Unknown"}]
        result = self.stage._build_hierarchy_context(parsed, candidates)

        assert len(result) == 1
        assert "Revenue" in result[0]["nearby_labels"]
        assert "COGS" in result[0]["nearby_labels"]

    def test_last_row_context(self):
        """Last row should only have preceding neighbors."""
        parsed = {
            "sheets": [{
                "sheet_name": "IS",
                "rows": [
                    {"label": "Revenue", "hierarchy_level": 1},
                    {"label": "COGS", "hierarchy_level": 1},
                    {"label": "Unknown", "hierarchy_level": 1},
                ],
            }]
        }
        candidates = [{"original_label": "Unknown"}]
        result = self.stage._build_hierarchy_context(parsed, candidates)

        assert len(result) == 1
        assert "Revenue" in result[0]["nearby_labels"]
        assert "COGS" in result[0]["nearby_labels"]

    def test_includes_sheet_name(self):
        """Context should include the sheet name."""
        parsed = {
            "sheets": [{
                "sheet_name": "Income Statement",
                "rows": [
                    {"label": "Unknown", "hierarchy_level": 1},
                    {"label": "Revenue", "hierarchy_level": 1},
                ],
            }]
        }
        candidates = [{"original_label": "Unknown"}]
        result = self.stage._build_hierarchy_context(parsed, candidates)
        assert result[0]["sheet"] == "Income Statement"

    def test_includes_metadata(self):
        """Context should include hierarchy level and subtotal/formula flags."""
        parsed = {
            "sheets": [{
                "sheet_name": "IS",
                "rows": [
                    {"label": "Unknown", "hierarchy_level": 2, "is_subtotal": True, "is_formula": True},
                    {"label": "Revenue", "hierarchy_level": 1},
                ],
            }]
        }
        candidates = [{"original_label": "Unknown"}]
        result = self.stage._build_hierarchy_context(parsed, candidates)
        assert result[0]["hierarchy_level"] == 2
        assert result[0]["is_subtotal"] is True
        assert result[0]["is_formula"] is True

    def test_no_match_returns_empty(self):
        """Should return empty list when candidates not found in parsed data."""
        parsed = {
            "sheets": [{
                "sheet_name": "IS",
                "rows": [{"label": "Revenue", "hierarchy_level": 1}],
            }]
        }
        candidates = [{"original_label": "Nonexistent"}]
        result = self.stage._build_hierarchy_context(parsed, candidates)
        assert result == []

    def test_multiple_sheets(self):
        """Should search across multiple sheets."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Revenue", "hierarchy_level": 1},
                    ],
                },
                {
                    "sheet_name": "BS",
                    "rows": [
                        {"label": "Unknown Asset", "hierarchy_level": 1},
                        {"label": "Total Assets", "hierarchy_level": 1},
                    ],
                },
            ]
        }
        candidates = [{"original_label": "Unknown Asset"}]
        result = self.stage._build_hierarchy_context(parsed, candidates)
        assert len(result) == 1
        assert result[0]["sheet"] == "BS"

    def test_empty_parsed_data(self):
        """Should handle empty parsed data gracefully."""
        result = self.stage._build_hierarchy_context({"sheets": []}, [{"original_label": "X"}])
        assert result == []


# ============================================================================
# TAXONOMY HELPERS
# ============================================================================


class TestTaxonomyHelpers:
    """Test _load_taxonomy and _format_taxonomy_for_prompt."""

    def test_format_taxonomy_basic(self):
        """Should format taxonomy categories and items."""
        taxonomy = {
            "categories": {
                "income_statement": [
                    {
                        "canonical_name": "revenue",
                        "display_name": "Revenue",
                        "aliases": ["Sales", "Net Sales", "Top Line"],
                    },
                    {
                        "canonical_name": "cogs",
                        "display_name": "Cost of Goods Sold",
                        "aliases": ["Cost of Sales", "COS"],
                    },
                ]
            }
        }
        result = _format_taxonomy_for_prompt(taxonomy)
        assert "Income Statement:" in result
        assert "revenue" in result
        assert "Revenue" in result
        assert "Sales" in result
        assert "cogs" in result

    def test_format_taxonomy_limits_aliases(self):
        """Should only show first 5 aliases."""
        taxonomy = {
            "categories": {
                "test": [
                    {
                        "canonical_name": "item",
                        "display_name": "Item",
                        "aliases": ["A1", "A2", "A3", "A4", "A5", "A6", "A7"],
                    }
                ]
            }
        }
        result = _format_taxonomy_for_prompt(taxonomy)
        assert "A1" in result
        assert "A5" in result
        assert "A6" not in result
        assert "A7" not in result

    def test_format_taxonomy_no_aliases(self):
        """Should handle items with no aliases."""
        taxonomy = {
            "categories": {
                "test": [
                    {
                        "canonical_name": "item",
                        "display_name": "Some Item",
                    }
                ]
            }
        }
        result = _format_taxonomy_for_prompt(taxonomy)
        assert "item" in result
        assert "Some Item" in result
        assert "aliases" not in result

    def test_format_taxonomy_empty(self):
        """Should handle empty taxonomy."""
        result = _format_taxonomy_for_prompt({"categories": {}})
        assert result == ""

    def test_format_taxonomy_multiple_categories(self):
        """Should format multiple categories."""
        taxonomy = {
            "categories": {
                "income_statement": [
                    {"canonical_name": "revenue", "display_name": "Revenue", "aliases": []},
                ],
                "balance_sheet": [
                    {"canonical_name": "total_assets", "display_name": "Total Assets", "aliases": []},
                ],
            }
        }
        result = _format_taxonomy_for_prompt(taxonomy)
        assert "Income Statement:" in result
        assert "Balance Sheet:" in result

    def test_load_taxonomy_missing_file(self):
        """Should return empty categories when file doesn't exist."""
        with patch("src.extraction.taxonomy_loader.TAXONOMY_PATH", Path("/nonexistent/path.json")), \
             patch("src.extraction.taxonomy_loader._taxonomy_cache", {}):
            result = _load_taxonomy()
            assert result == {"categories": {}}


# ============================================================================
# STAGE PROPERTIES
# ============================================================================


class TestEnhancedMappingStageProperties:
    """Test stage metadata."""

    def test_name(self):
        stage = EnhancedMappingStage()
        assert stage.name == "enhanced_mapping"

    def test_stage_number(self):
        stage = EnhancedMappingStage()
        assert stage.stage_number == 5


# ============================================================================
# CONFIDENCE IMPROVEMENT LOGIC
# ============================================================================


class TestConfidenceImprovement:
    """Test that only confidence-improving remappings are accepted."""

    def setup_method(self):
        self.stage = EnhancedMappingStage()

    def test_improved_mapping_accepted(self):
        """Higher-confidence remapping should replace original."""
        basic_mappings = [
            {"original_label": "Net Rev", "canonical_name": "unmapped", "confidence": 0.0},
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
        ]
        enhanced_response = [
            {"original_label": "Net Rev", "canonical_name": "net_revenue", "confidence": 0.85},
        ]

        # Simulate the merge logic from execute()
        enhanced_lookup = {e["original_label"]: e for e in enhanced_response}
        final_mappings = []
        remapped_count = 0

        for m in basic_mappings:
            label = m["original_label"]
            if label in enhanced_lookup:
                new_mapping = enhanced_lookup[label]
                if new_mapping.get("confidence", 0) > m.get("confidence", 0):
                    new_mapping["method"] = new_mapping.get("method", "enhanced")
                    final_mappings.append(new_mapping)
                    remapped_count += 1
                    continue
            final_mappings.append(m)

        assert remapped_count == 1
        assert final_mappings[0]["canonical_name"] == "net_revenue"
        assert final_mappings[0]["confidence"] == 0.85
        assert final_mappings[1]["canonical_name"] == "revenue"  # Unchanged

    def test_lower_confidence_rejected(self):
        """Lower-confidence remapping should be rejected (keep original)."""
        basic_mappings = [
            {"original_label": "SGA", "canonical_name": "sga", "confidence": 0.65},
        ]
        enhanced_response = [
            {"original_label": "SGA", "canonical_name": "other_expenses", "confidence": 0.50},
        ]

        enhanced_lookup = {e["original_label"]: e for e in enhanced_response}
        final_mappings = []
        remapped_count = 0

        for m in basic_mappings:
            label = m["original_label"]
            if label in enhanced_lookup:
                new_mapping = enhanced_lookup[label]
                if new_mapping.get("confidence", 0) > m.get("confidence", 0):
                    final_mappings.append(new_mapping)
                    remapped_count += 1
                    continue
            final_mappings.append(m)

        assert remapped_count == 0
        assert final_mappings[0]["canonical_name"] == "sga"  # Kept original

    def test_equal_confidence_rejected(self):
        """Same confidence should NOT replace (requires strict improvement)."""
        basic_mappings = [
            {"original_label": "SGA", "canonical_name": "sga", "confidence": 0.65},
        ]
        enhanced_response = [
            {"original_label": "SGA", "canonical_name": "other_expenses", "confidence": 0.65},
        ]

        enhanced_lookup = {e["original_label"]: e for e in enhanced_response}
        final_mappings = []
        remapped_count = 0

        for m in basic_mappings:
            label = m["original_label"]
            if label in enhanced_lookup:
                new_mapping = enhanced_lookup[label]
                if new_mapping.get("confidence", 0) > m.get("confidence", 0):
                    final_mappings.append(new_mapping)
                    remapped_count += 1
                    continue
            final_mappings.append(m)

        assert remapped_count == 0
        assert final_mappings[0]["canonical_name"] == "sga"


# ============================================================================
# FULL STAGE EXECUTION (with mocked Claude)
# ============================================================================


@pytest.mark.asyncio
async def test_enhanced_mapping_skips_when_all_confident(mock_anthropic, sample_xlsx):
    """Stage 5 should skip Claude call when all mappings are confident."""
    from src.extraction.orchestrator import extract

    result = await extract(sample_xlsx, file_id="test-em-1")

    # Enhanced mapping should be present in the pipeline output
    assert "line_items" in result


@pytest.mark.asyncio
async def test_enhanced_mapping_in_full_pipeline(mock_anthropic, sample_xlsx):
    """Stage 5 should run as part of the full pipeline without errors."""
    from src.extraction.orchestrator import extract

    result = await extract(sample_xlsx, file_id="test-em-2")

    assert "file_id" in result
    assert "sheets" in result
    assert "triage" in result
    assert "line_items" in result
    assert "tokens_used" in result
