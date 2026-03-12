"""Unit tests for validation-aware remapping in Stage 5 (enhanced mapping)."""
from src.extraction.stages.enhanced_mapping import EnhancedMappingStage


class TestValidationAwareRemapping:
    """Test that validation failures feed into remapping candidate selection."""

    def setup_method(self):
        self.stage = EnhancedMappingStage()

    def test_validation_failed_items_become_candidates(self):
        """Items with error-severity validation flags should become candidates."""
        mappings = [
            {"original_label": "Total Rev", "canonical_name": "revenue", "confidence": 0.9},
            {"original_label": "Gross", "canonical_name": "gross_profit", "confidence": 0.85},
        ]
        validation_result = {
            "validation": {
                "flags": [
                    {
                        "severity": "error",
                        "item": "gross_profit",
                        "rule": "gross_profit == revenue - cogs",
                    },
                ]
            }
        }
        candidates = self.stage._find_remapping_candidates(mappings, validation_result)
        assert len(candidates) == 1
        assert candidates[0]["original_label"] == "Gross"
        assert candidates[0]["validation_context"]["validation_failed"] is True
        assert candidates[0]["validation_context"]["failed_rule"] == "gross_profit == revenue - cogs"

    def test_warning_flags_dont_trigger_remapping(self):
        """Warning-severity flags should NOT trigger remapping."""
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.9},
        ]
        validation_result = {
            "validation": {
                "flags": [
                    {"severity": "warning", "item": "revenue", "rule": "some_warning"},
                ]
            }
        }
        candidates = self.stage._find_remapping_candidates(mappings, validation_result)
        assert len(candidates) == 0

    def test_low_confidence_plus_validation_failure(self):
        """Item with both low confidence and validation failure should appear once."""
        mappings = [
            {"original_label": "Low", "canonical_name": "ebitda", "confidence": 0.5},
        ]
        validation_result = {
            "validation": {
                "flags": [
                    {"severity": "error", "item": "ebitda", "rule": "some_rule"},
                ]
            }
        }
        candidates = self.stage._find_remapping_candidates(mappings, validation_result)
        assert len(candidates) == 1

    def test_no_validation_result(self):
        """Without validation result, only low-confidence/unmapped items selected."""
        mappings = [
            {"original_label": "Rev", "canonical_name": "revenue", "confidence": 0.9},
            {"original_label": "Unk", "canonical_name": "unmapped", "confidence": 0.0},
        ]
        candidates = self.stage._find_remapping_candidates(mappings, None)
        assert len(candidates) == 1
        assert candidates[0]["original_label"] == "Unk"

    def test_empty_validation_result(self):
        """Empty validation result should not crash."""
        mappings = [
            {"original_label": "Rev", "canonical_name": "revenue", "confidence": 0.9},
        ]
        candidates = self.stage._find_remapping_candidates(mappings, {})
        assert len(candidates) == 0

    def test_unmapped_items_still_selected(self):
        """Unmapped items should still be candidates regardless of validation."""
        mappings = [
            {"original_label": "Unknown", "canonical_name": "unmapped", "confidence": 0.0},
            {"original_label": "Good", "canonical_name": "revenue", "confidence": 0.95},
        ]
        validation_result = {"validation": {"flags": []}}
        candidates = self.stage._find_remapping_candidates(mappings, validation_result)
        assert len(candidates) == 1
        assert candidates[0]["canonical_name"] == "unmapped"

    def test_no_duplicate_labels(self):
        """Multiple mappings with same label should only appear once."""
        mappings = [
            {"original_label": "Rev", "canonical_name": "revenue", "confidence": 0.5},
            {"original_label": "Rev", "canonical_name": "revenue", "confidence": 0.6},
        ]
        candidates = self.stage._find_remapping_candidates(mappings, None)
        assert len(candidates) == 1

    def test_multiple_validation_failures(self):
        """Multiple items failing validation should all become candidates."""
        mappings = [
            {"original_label": "A", "canonical_name": "revenue", "confidence": 0.9},
            {"original_label": "B", "canonical_name": "gross_profit", "confidence": 0.85},
            {"original_label": "C", "canonical_name": "ebitda", "confidence": 0.88},
        ]
        validation_result = {
            "validation": {
                "flags": [
                    {"severity": "error", "item": "gross_profit", "rule": "rule1"},
                    {"severity": "error", "item": "ebitda", "rule": "rule2"},
                ]
            }
        }
        candidates = self.stage._find_remapping_candidates(mappings, validation_result)
        assert len(candidates) == 2
        labels = {c["original_label"] for c in candidates}
        assert labels == {"B", "C"}


# ============================================================================
# HIERARCHY CONTEXT EDGE CASES
# ============================================================================


class TestHierarchyContextWindow:
    """Test expanded hierarchy context window and section header detection."""

    def setup_method(self):
        self.stage = EnhancedMappingStage()

    def test_hierarchy_context_captures_section_header(self):
        """Section headers (hierarchy_level=0, not subtotal) should be captured."""
        parsed = {
            "sheets": [{
                "sheet_name": "IS",
                "rows": [
                    {"label": "Income Statement", "hierarchy_level": 0, "is_subtotal": False},
                    {"label": "Revenue Breakdown", "hierarchy_level": 1},
                    {"label": "Product Sales", "hierarchy_level": 2},
                    {"label": "UnknownItem", "hierarchy_level": 2},
                    {"label": "Service Revenue", "hierarchy_level": 2},
                    {"label": "Total Revenue", "hierarchy_level": 1, "is_subtotal": True},
                ],
            }],
        }
        candidates = [{"original_label": "UnknownItem", "confidence": 0.4}]

        context_items = self.stage._build_hierarchy_context(parsed, candidates)
        assert len(context_items) == 1
        item = context_items[0]
        assert item["section_header"] == "Income Statement"
        # ±3 window should capture more neighbors than ±2
        assert len(item["nearby_labels"]) >= 4

    def test_hierarchy_context_subtotal_not_section_header(self):
        """Subtotal rows with hierarchy_level=0 should NOT be treated as headers."""
        parsed = {
            "sheets": [{
                "sheet_name": "IS",
                "rows": [
                    {"label": "Grand Total", "hierarchy_level": 0, "is_subtotal": True},
                    {"label": "Filler1", "hierarchy_level": 1},
                    {"label": "Filler2", "hierarchy_level": 1},
                    {"label": "UnknownItem", "hierarchy_level": 2},
                ],
            }],
        }
        candidates = [{"original_label": "UnknownItem", "confidence": 0.4}]

        context_items = self.stage._build_hierarchy_context(parsed, candidates)
        assert len(context_items) == 1
        assert context_items[0]["section_header"] is None
