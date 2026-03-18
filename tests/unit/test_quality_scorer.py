"""Unit tests for composite quality scorer."""

from src.validation.quality_scorer import (
    DEFAULT_WEIGHTS,
    MODEL_TYPE_WEIGHTS,
    QualityScorer,
)


class TestGradeAssignment:
    """Test letter grade mapping from numeric score."""

    def setup_method(self):
        self.scorer = QualityScorer()

    def test_grade_a(self):
        result = self.scorer.score(0.95, 0.95, 0.95, 0.95)
        assert result.letter_grade == "A"

    def test_grade_b(self):
        result = self.scorer.score(0.80, 0.80, 0.80, 0.80)
        assert result.letter_grade == "B"

    def test_grade_c(self):
        result = self.scorer.score(0.65, 0.65, 0.65, 0.65)
        assert result.letter_grade == "C"

    def test_grade_d(self):
        result = self.scorer.score(0.45, 0.45, 0.45, 0.45)
        assert result.letter_grade == "D"

    def test_grade_f(self):
        result = self.scorer.score(0.1, 0.1, 0.1, 0.1)
        assert result.letter_grade == "F"

    def test_boundary_a(self):
        """Score exactly at 0.90 should be A."""
        # Pass all 5 dimensions to avoid floating-point drift from weight redistribution
        result = self.scorer.score(0.90, 0.90, 0.90, 0.90, cell_match_rate=0.90)
        assert result.letter_grade == "A"

    def test_boundary_b(self):
        """Score exactly at 0.75 should be B."""
        result = self.scorer.score(0.75, 0.75, 0.75, 0.75)
        assert result.letter_grade == "B"


class TestLabelAssignment:
    """Test quality label assignment."""

    def setup_method(self):
        self.scorer = QualityScorer()

    def test_trustworthy_label(self):
        result = self.scorer.score(0.9, 0.9, 0.9, 0.9)
        assert result.label == "trustworthy"
        assert result.is_trustworthy is True

    def test_needs_review_label(self):
        result = self.scorer.score(0.6, 0.6, 0.6, 0.6)
        assert result.label == "needs_review"
        assert result.is_trustworthy is False

    def test_unreliable_label(self):
        result = self.scorer.score(0.2, 0.2, 0.2, 0.2)
        assert result.label == "unreliable"
        assert result.is_trustworthy is False

    def test_boundary_trustworthy(self):
        """Score exactly at 0.80 should be trustworthy."""
        result = self.scorer.score(0.80, 0.80, 0.80, 0.80)
        assert result.label == "trustworthy"


class TestWeightedAverage:
    """Test weighted average computation."""

    def setup_method(self):
        self.scorer = QualityScorer()

    def test_equal_scores_returns_score(self):
        result = self.scorer.score(0.8, 0.8, 0.8, 0.8)
        assert abs(result.numeric_score - 0.8) < 0.001

    def test_weighted_average_correct(self):
        """Verify weighted average with known weights (backward compat: no cell_match_rate).

        Without cell_match_rate, the cell_reconciliation weight (0.20) is
        redistributed proportionally among the other 4 dimensions.
        Effective weights: mapping=0.3125, validation=0.25, completeness=0.25, ts=0.1875
        """
        result = self.scorer.score(1.0, 0.0, 0.0, 0.0)
        # Only mapping contributes: 1.0 * 0.3125 = 0.3125
        expected = 0.3125
        assert abs(result.numeric_score - expected) < 0.001

    def test_zero_scores(self):
        result = self.scorer.score(0.0, 0.0, 0.0, 0.0)
        assert result.numeric_score == 0.0
        assert result.letter_grade == "F"
        assert result.label == "unreliable"

    def test_perfect_scores(self):
        result = self.scorer.score(1.0, 1.0, 1.0, 1.0)
        assert abs(result.numeric_score - 1.0) < 0.001
        assert result.letter_grade == "A"
        assert result.label == "trustworthy"

    def test_mixed_scores_weighted(self):
        """High mapping + low others should reflect redistributed weights."""
        result = self.scorer.score(1.0, 0.5, 0.5, 0.5)
        # Effective: mapping=0.3125, validation=0.25, completeness=0.25, ts=0.1875
        # 1.0*0.3125 + 0.5*0.25 + 0.5*0.25 + 0.5*0.1875 = 0.3125 + 0.125 + 0.125 + 0.09375 = 0.65625
        expected = 0.65625
        assert abs(result.numeric_score - expected) < 0.01


class TestCustomConfig:
    """Test custom weights and thresholds."""

    def test_custom_weights(self):
        scorer = QualityScorer(
            weights={
                "mapping_confidence": 1.0,
                "validation_success": 0.0,
                "completeness": 0.0,
                "time_series_consistency": 0.0,
            }
        )
        result = scorer.score(0.95, 0.0, 0.0, 0.0)
        assert abs(result.numeric_score - 0.95) < 0.001

    def test_custom_grade_thresholds(self):
        scorer = QualityScorer(
            grade_thresholds=[
                ("A", 0.95),
                ("B", 0.50),
                ("F", 0.0),
            ]
        )
        result = scorer.score(0.92, 0.92, 0.92, 0.92)
        assert result.letter_grade == "B"  # below custom A threshold

    def test_custom_label_thresholds(self):
        scorer = QualityScorer(
            label_thresholds=[
                ("trustworthy", 0.95),
                ("unreliable", 0.0),
            ]
        )
        result = scorer.score(0.9, 0.9, 0.9, 0.9)
        assert result.label == "unreliable"  # below custom trustworthy threshold


class TestSerialization:
    """Test to_dict() output format."""

    def setup_method(self):
        self.scorer = QualityScorer()

    def test_to_dict_format(self):
        result = self.scorer.score(0.85, 0.90, 0.75, 0.80)
        d = result.to_dict()
        assert "numeric_score" in d
        assert "letter_grade" in d
        assert "label" in d
        assert "dimensions" in d
        assert isinstance(d["dimensions"], list)
        # Without cell_match_rate, 4 dimensions are returned
        assert len(d["dimensions"]) == 4

    def test_to_dict_format_with_cell_rate(self):
        result = self.scorer.score(0.85, 0.90, 0.75, 0.80, cell_match_rate=0.95)
        d = result.to_dict()
        assert len(d["dimensions"]) == 5

    def test_to_dict_dimension_fields(self):
        result = self.scorer.score(0.85, 0.90, 0.75, 0.80)
        d = result.to_dict()
        dim = d["dimensions"][0]
        assert "name" in dim
        assert "score" in dim
        assert "weight" in dim
        assert "details" in dim

    def test_to_dict_scores_rounded(self):
        result = self.scorer.score(0.8333333, 0.9111111, 0.7555555, 0.8222222)
        d = result.to_dict()
        # numeric_score should be rounded to 3 decimal places
        assert d["numeric_score"] == round(d["numeric_score"], 3)


class TestEdgeCases:
    """Test edge cases and input clamping."""

    def setup_method(self):
        self.scorer = QualityScorer()

    def test_input_clamped_above_one(self):
        """Values > 1.0 should be clamped to 1.0."""
        result = self.scorer.score(1.5, 1.5, 1.5, 1.5)
        assert abs(result.numeric_score - 1.0) < 0.001

    def test_input_clamped_below_zero(self):
        """Negative values should be clamped to 0.0."""
        result = self.scorer.score(-0.5, -0.5, -0.5, -0.5)
        assert result.numeric_score == 0.0

    def test_single_dimension_low(self):
        """One very low dimension shouldn't crater the whole score."""
        result = self.scorer.score(0.95, 0.95, 0.0, 0.95)
        # Effective weights (redistributed): mapping=0.3125, validation=0.25,
        # completeness=0.25, ts=0.1875
        # 0.95*0.3125 + 0.95*0.25 + 0.0*0.25 + 0.95*0.1875
        # = 0.296875 + 0.2375 + 0 + 0.178125 = 0.7125
        assert abs(result.numeric_score - 0.7125) < 0.001

    def test_dimensions_list_matches_inputs(self):
        result = self.scorer.score(0.5, 0.6, 0.7, 0.8)
        assert len(result.dimensions) == 4
        names = [d.name for d in result.dimensions]
        assert "mapping_confidence" in names
        assert "validation_success" in names
        assert "completeness" in names
        assert "time_series_consistency" in names

    def test_dimensions_list_with_cell_rate(self):
        result = self.scorer.score(0.5, 0.6, 0.7, 0.8, cell_match_rate=0.9)
        assert len(result.dimensions) == 5
        names = [d.name for d in result.dimensions]
        assert "cell_reconciliation" in names


# ============================================================================
# MODEL TYPE WEIGHTS
# ============================================================================


class TestModelTypeWeights:
    """Test model-type-specific weight selection."""

    def test_corporate_matches_default(self):
        scorer = QualityScorer(model_type="corporate")
        assert scorer.weights == DEFAULT_WEIGHTS

    def test_project_finance_weights(self):
        scorer = QualityScorer(model_type="project_finance")
        assert scorer.weights["validation_success"] == 0.25
        assert scorer.weights["time_series_consistency"] == 0.20
        assert scorer.weights["mapping_confidence"] == 0.20
        assert scorer.weights["cell_reconciliation"] == 0.20

    def test_construction_only_weights(self):
        scorer = QualityScorer(model_type="construction_only")
        assert scorer.weights["mapping_confidence"] == 0.30
        assert scorer.weights["completeness"] == 0.25
        assert scorer.weights["time_series_consistency"] == 0.10
        assert scorer.weights["cell_reconciliation"] == 0.20

    def test_saas_weights(self):
        scorer = QualityScorer(model_type="saas")
        assert scorer.weights["completeness"] == 0.25
        assert scorer.weights["mapping_confidence"] == 0.20
        assert scorer.weights["cell_reconciliation"] == 0.20

    def test_mixed_weights_equal(self):
        scorer = QualityScorer(model_type="mixed")
        assert all(v == 0.20 for v in scorer.weights.values())

    def test_unknown_model_type_uses_default(self):
        scorer = QualityScorer(model_type="unknown_type")
        assert scorer.weights == DEFAULT_WEIGHTS

    def test_none_model_type_uses_default(self):
        scorer = QualityScorer(model_type=None)
        assert scorer.weights == DEFAULT_WEIGHTS

    def test_explicit_weights_override_model_type(self):
        custom = {
            "mapping_confidence": 1.0,
            "validation_success": 0.0,
            "completeness": 0.0,
            "time_series_consistency": 0.0,
        }
        scorer = QualityScorer(weights=custom, model_type="project_finance")
        assert scorer.weights == custom

    def test_model_type_in_to_dict(self):
        scorer = QualityScorer(model_type="project_finance")
        result = scorer.score(0.8, 0.8, 0.8, 0.8)
        d = result.to_dict()
        assert d["model_type"] == "project_finance"

    def test_no_model_type_not_in_to_dict(self):
        scorer = QualityScorer()
        result = scorer.score(0.8, 0.8, 0.8, 0.8)
        d = result.to_dict()
        assert "model_type" not in d

    def test_all_weights_sum_to_one(self):
        for model_type, weights in MODEL_TYPE_WEIGHTS.items():
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.001, f"{model_type} weights sum to {total}"

    def test_pf_scoring_differs_from_default(self):
        """PF model should produce different score than corporate for asymmetric inputs."""
        corporate = QualityScorer(model_type="corporate")
        pf = QualityScorer(model_type="project_finance")
        # High mapping, low validation — PF weights validation more
        r_corp = corporate.score(0.95, 0.50, 0.70, 0.70)
        r_pf = pf.score(0.95, 0.50, 0.70, 0.70)
        assert r_corp.numeric_score != r_pf.numeric_score


# ============================================================================
# CELL RECONCILIATION DIMENSION
# ============================================================================


class TestCellReconciliationDimension:
    """Test the 5th quality dimension: cell_reconciliation."""

    def setup_method(self):
        self.scorer = QualityScorer()

    def test_five_dimensions_with_cell_rate(self):
        """With cell_match_rate, all 5 dimensions contribute."""
        result = self.scorer.score(0.9, 0.9, 0.9, 0.9, cell_match_rate=0.9)
        assert abs(result.numeric_score - 0.9) < 0.001
        assert len(result.dimensions) == 5

    def test_backward_compat_without_cell_rate(self):
        """Without cell_match_rate, scoring still works with 4 dimensions."""
        result = self.scorer.score(0.8, 0.8, 0.8, 0.8)
        assert abs(result.numeric_score - 0.8) < 0.001
        assert len(result.dimensions) == 4

    def test_weight_redistribution_when_omitted(self):
        """When cell_match_rate is None, its weight redistributes proportionally."""
        # With cell_match_rate = 1.0 (perfect): all dimensions at 0.8
        result_with = self.scorer.score(0.8, 0.8, 0.8, 0.8, cell_match_rate=0.8)
        # Without: same 4 dimensions at 0.8
        result_without = self.scorer.score(0.8, 0.8, 0.8, 0.8)
        # Both should give 0.8 since all inputs are equal
        assert abs(result_with.numeric_score - 0.8) < 0.001
        assert abs(result_without.numeric_score - 0.8) < 0.001

    def test_cell_rate_impacts_score(self):
        """Low cell_match_rate should reduce the composite score."""
        result_high = self.scorer.score(0.9, 0.9, 0.9, 0.9, cell_match_rate=0.95)
        result_low = self.scorer.score(0.9, 0.9, 0.9, 0.9, cell_match_rate=0.3)
        assert result_high.numeric_score > result_low.numeric_score

    def test_grade_floor_below_50_pct(self):
        """cell_match_rate < 0.5 caps grade at D, even if other dimensions are perfect."""
        result = self.scorer.score(1.0, 1.0, 1.0, 1.0, cell_match_rate=0.4)
        assert result.letter_grade == "D"

    def test_grade_floor_above_50_pct_no_cap(self):
        """cell_match_rate >= 0.5 does not trigger grade floor."""
        result = self.scorer.score(1.0, 1.0, 1.0, 1.0, cell_match_rate=0.5)
        # 1.0*0.25 + 1.0*0.20 + 1.0*0.20 + 1.0*0.15 + 0.5*0.20 = 0.9
        assert result.letter_grade == "A"

    def test_grade_floor_does_not_upgrade(self):
        """Grade floor only caps upward; low grades remain low."""
        result = self.scorer.score(0.0, 0.0, 0.0, 0.0, cell_match_rate=0.3)
        assert result.letter_grade == "F"  # already below D

    def test_cell_rate_clamped(self):
        """cell_match_rate > 1.0 is clamped to 1.0."""
        result = self.scorer.score(0.9, 0.9, 0.9, 0.9, cell_match_rate=1.5)
        # cell_reconciliation clamped to 1.0 (weight 0.20), rest at 0.9
        # expected: 0.9*0.25 + 0.9*0.20 + 0.9*0.20 + 0.9*0.15 + 1.0*0.20 = 0.72 + 0.20 = 0.92
        assert abs(result.numeric_score - 0.92) < 0.01


class TestFormulaMismatchModifier:
    """Test formula_mismatch_rate grade modifier."""

    def setup_method(self):
        self.scorer = QualityScorer()

    def test_high_formula_mismatch_caps_at_c(self):
        """formula_mismatch_rate > 0.3 caps grade at C even if others are perfect."""
        result = self.scorer.score(
            1.0, 1.0, 1.0, 1.0, cell_match_rate=1.0, formula_mismatch_rate=0.5,
        )
        assert result.letter_grade == "C"

    def test_formula_mismatch_at_boundary_no_cap(self):
        """formula_mismatch_rate == 0.3 should NOT trigger the cap."""
        result = self.scorer.score(
            1.0, 1.0, 1.0, 1.0, cell_match_rate=1.0, formula_mismatch_rate=0.3,
        )
        assert result.letter_grade == "A"

    def test_formula_mismatch_none_no_effect(self):
        """When formula_mismatch_rate is None, no grade modifier applied."""
        result = self.scorer.score(1.0, 1.0, 1.0, 1.0, cell_match_rate=1.0)
        assert result.letter_grade == "A"

    def test_formula_mismatch_does_not_upgrade(self):
        """Low grade stays low even with formula_mismatch_rate > 0.3."""
        result = self.scorer.score(0.0, 0.0, 0.0, 0.0, formula_mismatch_rate=0.5)
        assert result.letter_grade == "F"

    def test_formula_and_cell_caps_stack(self):
        """Both cell_match_rate < 0.5 AND formula_mismatch_rate > 0.3:
        cell cap (D) is stricter, so D wins."""
        result = self.scorer.score(
            1.0, 1.0, 1.0, 1.0, cell_match_rate=0.4, formula_mismatch_rate=0.5,
        )
        assert result.letter_grade == "D"

    def test_formula_mismatch_zero_no_cap(self):
        """formula_mismatch_rate = 0.0 should not cap anything."""
        result = self.scorer.score(
            0.95, 0.95, 0.95, 0.95, cell_match_rate=0.95, formula_mismatch_rate=0.0,
        )
        assert result.letter_grade == "A"

    def test_backward_compat_without_formula_rate(self):
        """Existing code that does not pass formula_mismatch_rate still works."""
        result = self.scorer.score(0.9, 0.9, 0.9, 0.9, cell_match_rate=0.9)
        assert result.letter_grade == "A"
