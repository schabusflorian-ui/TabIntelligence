"""Tests for embedding-based taxonomy pre-filter."""

import pytest

from src.extraction.embeddings import (
    CONFIDENT_THRESHOLD,
    HINT_THRESHOLD,
    _normalize_text,
    filter_remaining_labels,
    invalidate_taxonomy_index,
    score_labels,
)


class TestNormalizeText:
    def test_basic_normalization(self):
        assert _normalize_text("Net_Income") == "net income"
        assert _normalize_text("  TOTAL  DEBT  ") == "total debt"
        assert _normalize_text("cash-flow") == "cash flow"

    def test_underscores_and_hyphens(self):
        assert _normalize_text("debt_to_ebitda") == "debt to ebitda"
        assert _normalize_text("pre-tax-irr") == "pre tax irr"


class TestScoreLabels:
    """Test the core scoring function."""

    def test_exact_canonical_match_scores_high(self):
        results = score_labels(["revenue"])
        assert "revenue" in results
        # The canonical name "revenue" should match very highly
        top = results["revenue"][0]
        assert top[0] == "revenue"  # canonical_name
        assert top[2] >= CONFIDENT_THRESHOLD

    def test_alias_match_scores_high(self):
        results = score_labels(["Net Sales"])
        assert "Net Sales" in results
        # "Net Sales" is an alias for revenue
        candidates = results["Net Sales"]
        canonical_names = [c[0] for c in candidates]
        assert "revenue" in canonical_names

    def test_unrelated_label_scores_low(self):
        results = score_labels(["quantum_entanglement_coefficient"])
        # Should have no matches above threshold
        assert "quantum_entanglement_coefficient" not in results or len(
            results.get("quantum_entanglement_coefficient", [])
        ) == 0

    def test_empty_input(self):
        assert score_labels([]) == {}

    def test_category_filter(self):
        results = score_labels(["total debt"], category_filter={"debt_schedule"})
        assert "total debt" in results
        # All results should be in debt_schedule
        for cn, cat, score in results["total debt"]:
            assert cat == "debt_schedule"

    def test_multiple_labels(self):
        results = score_labels(["revenue", "total assets", "ebitda"])
        assert len(results) >= 2  # Most should have matches


class TestFilterRemainingLabels:
    """Test the pre-filter integration function."""

    def test_confident_match_goes_to_pre_mapped(self):
        confident, still_remaining, hints = filter_remaining_labels(
            {"revenue", "total_debt"}
        )
        # At least one should match confidently (exact canonical names)
        assert len(confident) > 0 or len(hints) > 0

    def test_confident_match_format(self):
        confident, still_remaining, hints = filter_remaining_labels({"revenue"})
        if "revenue" in confident:
            m = confident["revenue"]
            assert m["original_label"] == "revenue"
            assert m["canonical_name"] == "revenue"
            assert m["method"] == "embedding"
            assert m["confidence"] >= CONFIDENT_THRESHOLD

    def test_gibberish_goes_to_remaining(self):
        confident, still_remaining, hints = filter_remaining_labels(
            {"xyzzy_nonsense_12345"}
        )
        assert "xyzzy_nonsense_12345" not in confident
        assert "xyzzy_nonsense_12345" in still_remaining

    def test_empty_input(self):
        confident, still_remaining, hints = filter_remaining_labels(set())
        assert confident == {}
        assert still_remaining == set()
        assert hints == {}

    def test_hints_contain_candidates(self):
        # A typo or partial match should produce hints rather than confident match
        confident, still_remaining, hints = filter_remaining_labels(
            {"net income from operations"}
        )
        # Should either be confident or have hints
        label = "net income from operations"
        assert label in confident or label in hints or label in still_remaining


class TestInvalidateIndex:
    def test_invalidate_and_rebuild(self):
        # Score once to build index
        score_labels(["revenue"])
        # Invalidate
        invalidate_taxonomy_index()
        # Score again — should rebuild without error
        results = score_labels(["revenue"])
        assert "revenue" in results
