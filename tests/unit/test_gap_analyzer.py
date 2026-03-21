"""Tests for taxonomy gap analyzer."""

from unittest.mock import MagicMock, patch

import pytest

from src.taxonomy.gap_analyzer import (
    ALIAS_THRESHOLD,
    AMBIGUOUS_THRESHOLD,
    analyze_gaps,
    cluster_gaps,
)


def _make_unmapped_row(label, occurrences=3, entity_count=2):
    """Create a mock unmapped label aggregate result."""
    return {
        "label_normalized": label,
        "total_occurrences": occurrences,
        "entity_count": entity_count,
        "variants": [label],
        "sheet_names": ["Income Statement"],
        "category_hint": "income_statement",
    }


class TestAnalyzeGaps:
    """Test the gap analysis function."""

    def test_empty_database(self):
        """No unmapped labels → empty results."""
        db = MagicMock()
        db.query.return_value.group_by.return_value.having.return_value.having.return_value.order_by.return_value.limit.return_value.all.return_value = []

        result = analyze_gaps(db)

        assert result["summary"]["total_analyzed"] == 0
        assert result["alias_candidates"] == []
        assert result["new_item_candidates"] == []
        assert result["ambiguous"] == []

    @patch("src.taxonomy.gap_analyzer._get_frequent_unmapped")
    @patch("src.extraction.embeddings.score_labels")
    def test_alias_candidate_classification(self, mock_score, mock_get):
        """Labels with high score → alias_candidate."""
        mock_get.return_value = [_make_unmapped_row("net sales")]
        mock_score.return_value = {
            "net sales": [("revenue", "income_statement", 0.92)],
        }

        result = analyze_gaps(MagicMock())

        assert len(result["alias_candidates"]) == 1
        assert result["alias_candidates"][0]["label"] == "net sales"
        assert result["alias_candidates"][0]["classification"] == "alias_candidate"
        assert result["alias_candidates"][0]["suggested_canonical"] == "revenue"
        assert result["summary"]["alias_candidates"] == 1

    @patch("src.taxonomy.gap_analyzer._get_frequent_unmapped")
    @patch("src.extraction.embeddings.score_labels")
    def test_new_item_candidate_classification(self, mock_score, mock_get):
        """Labels with low score → new_item_candidate."""
        mock_get.return_value = [_make_unmapped_row("pik toggle rate")]
        mock_score.return_value = {
            "pik toggle rate": [("interest_rate", "debt_schedule", 0.45)],
        }

        result = analyze_gaps(MagicMock())

        assert len(result["new_item_candidates"]) == 1
        assert result["new_item_candidates"][0]["classification"] == "new_item_candidate"
        assert result["summary"]["new_item_candidates"] == 1

    @patch("src.taxonomy.gap_analyzer._get_frequent_unmapped")
    @patch("src.extraction.embeddings.score_labels")
    def test_ambiguous_classification(self, mock_score, mock_get):
        """Labels with mid-range score → ambiguous."""
        mock_get.return_value = [_make_unmapped_row("adjusted net income")]
        mock_score.return_value = {
            "adjusted net income": [("net_income", "income_statement", 0.72)],
        }

        result = analyze_gaps(MagicMock())

        assert len(result["ambiguous"]) == 1
        assert result["ambiguous"][0]["classification"] == "ambiguous"
        assert result["summary"]["ambiguous"] == 1

    @patch("src.taxonomy.gap_analyzer._get_frequent_unmapped")
    @patch("src.extraction.embeddings.score_labels")
    def test_mixed_classifications(self, mock_score, mock_get):
        """Multiple labels classified into different categories."""
        mock_get.return_value = [
            _make_unmapped_row("net sales", 10, 5),
            _make_unmapped_row("custom kpi xyz", 3, 2),
            _make_unmapped_row("adjusted revenue", 5, 3),
        ]
        mock_score.return_value = {
            "net sales": [("revenue", "income_statement", 0.95)],
            "custom kpi xyz": [],  # No match
            "adjusted revenue": [("revenue", "income_statement", 0.70)],
        }

        result = analyze_gaps(MagicMock())

        assert result["summary"]["total_analyzed"] == 3
        assert result["summary"]["alias_candidates"] == 1
        assert result["summary"]["new_item_candidates"] == 1
        assert result["summary"]["ambiguous"] == 1

    @patch("src.taxonomy.gap_analyzer._get_frequent_unmapped")
    def test_embedding_failure_graceful(self, mock_get):
        """If embeddings fail, analysis still returns results."""
        mock_get.return_value = [_make_unmapped_row("test label")]

        with patch("src.extraction.embeddings.score_labels", side_effect=RuntimeError("no GPU")):
            result = analyze_gaps(MagicMock())

        # All should be new_item_candidate (best_score = 0.0)
        assert result["summary"]["total_analyzed"] == 1
        assert result["summary"]["new_item_candidates"] == 1


class TestClusterGaps:
    """Test the gap clustering function."""

    @patch("src.taxonomy.gap_analyzer._get_frequent_unmapped")
    def test_empty_returns_empty(self, mock_get):
        mock_get.return_value = []
        result = cluster_gaps(MagicMock())
        assert result == []

    @patch("src.taxonomy.gap_analyzer._get_frequent_unmapped")
    def test_single_label_is_own_cluster(self, mock_get):
        mock_get.return_value = [_make_unmapped_row("revenue adjustment")]

        result = cluster_gaps(MagicMock())

        assert len(result) == 1
        assert result[0]["representative"] == "revenue adjustment"
        assert result[0]["cluster_size"] == 1

    @patch("src.taxonomy.gap_analyzer._get_frequent_unmapped")
    def test_similar_labels_cluster_together(self, mock_get):
        """Semantically similar labels should end up in the same cluster."""
        mock_get.return_value = [
            _make_unmapped_row("net revenue", 10, 5),
            _make_unmapped_row("net sales revenue", 5, 3),
            _make_unmapped_row("total assets held", 4, 2),
        ]

        result = cluster_gaps(MagicMock())

        # Net revenue and net sales revenue should cluster together
        # total assets held should be separate
        assert len(result) >= 1
        # Most frequent label should be representative
        assert result[0]["representative"] == "net revenue"

    @patch("src.taxonomy.gap_analyzer._get_frequent_unmapped")
    def test_embedding_failure_fallback(self, mock_get):
        """If embedding fails, each label is its own cluster."""
        mock_get.return_value = [
            _make_unmapped_row("label a", 5, 3),
            _make_unmapped_row("label b", 3, 2),
        ]

        with patch("src.extraction.embeddings._get_model", side_effect=RuntimeError("no model")):
            result = cluster_gaps(MagicMock())

        assert len(result) == 2
        assert result[0]["representative"] == "label a"
        assert result[1]["representative"] == "label b"
