"""
Comprehensive tests for src/derivation/confidence.py.

Covers:
  - _confidence_to_uncertainty: all confidence buckets
  - propagate_confidence: min, product, weighted, unknown mode, empty, discount
  - compute_uncertainty_band: ratio, sum, difference, other, edge cases
  - is_covenant_sensitive: breach, sensitive, safe, no threshold, no bounds
"""

from decimal import Decimal

import pytest

from src.derivation.confidence import (
    _confidence_to_uncertainty,
    compute_uncertainty_band,
    is_covenant_sensitive,
    propagate_confidence,
)


# ─────────────────────────────────────────────────────────────────────────────
# _confidence_to_uncertainty
# ─────────────────────────────────────────────────────────────────────────────


class TestConfidenceToUncertainty:
    """Test the confidence → fractional uncertainty mapping."""

    def test_perfect_confidence(self):
        """confidence >= 0.99 → 1% uncertainty."""
        assert _confidence_to_uncertainty(1.0) == 0.01
        assert _confidence_to_uncertainty(0.99) == 0.01

    def test_high_confidence(self):
        """0.90 <= confidence < 0.99 → 3% uncertainty."""
        assert _confidence_to_uncertainty(0.95) == 0.03
        assert _confidence_to_uncertainty(0.90) == 0.03

    def test_medium_confidence(self):
        """0.80 <= confidence < 0.90 → 7% uncertainty."""
        assert _confidence_to_uncertainty(0.85) == 0.07
        assert _confidence_to_uncertainty(0.80) == 0.07

    def test_low_confidence(self):
        """0.70 <= confidence < 0.80 → 12% uncertainty."""
        assert _confidence_to_uncertainty(0.75) == 0.12
        assert _confidence_to_uncertainty(0.70) == 0.12

    def test_very_low_confidence(self):
        """confidence < 0.70 → 20% uncertainty."""
        assert _confidence_to_uncertainty(0.65) == 0.20
        assert _confidence_to_uncertainty(0.0) == 0.20
        assert _confidence_to_uncertainty(0.50) == 0.20


# ─────────────────────────────────────────────────────────────────────────────
# propagate_confidence
# ─────────────────────────────────────────────────────────────────────────────


class TestPropagateConfidence:
    """Test confidence propagation across formula types."""

    # ── min mode ──────────────────────────────────────────────────────────────

    def test_min_mode_single(self):
        result = propagate_confidence([0.80], mode="min")
        assert result == pytest.approx(0.80)

    def test_min_mode_returns_minimum(self):
        result = propagate_confidence([0.90, 0.75, 0.85], mode="min")
        assert result == pytest.approx(0.75)

    def test_min_mode_with_discount(self):
        result = propagate_confidence([0.90, 0.80], mode="min", derivation_discount=0.95)
        assert result == pytest.approx(0.80 * 0.95)

    # ── product mode ──────────────────────────────────────────────────────────

    def test_product_mode_single(self):
        result = propagate_confidence([0.90], mode="product")
        assert result == pytest.approx(0.90)

    def test_product_mode_multiplies(self):
        result = propagate_confidence([0.90, 0.80], mode="product")
        assert result == pytest.approx(0.90 * 0.80)

    def test_product_mode_three_inputs(self):
        result = propagate_confidence([0.95, 0.90, 0.85], mode="product")
        assert result == pytest.approx(0.95 * 0.90 * 0.85)

    def test_product_mode_with_discount(self):
        result = propagate_confidence([0.90, 0.80], mode="product", derivation_discount=0.95)
        assert result == pytest.approx(0.90 * 0.80 * 0.95)

    # ── weighted mode ─────────────────────────────────────────────────────────

    def test_weighted_mode_average(self):
        result = propagate_confidence([0.90, 0.80], mode="weighted")
        assert result == pytest.approx(0.85)

    def test_weighted_mode_three(self):
        result = propagate_confidence([0.90, 0.80, 0.70], mode="weighted")
        assert result == pytest.approx((0.90 + 0.80 + 0.70) / 3)

    # ── fallback and edge cases ────────────────────────────────────────────────

    def test_unknown_mode_falls_back_to_min(self):
        """Unknown mode should fall back to min."""
        result = propagate_confidence([0.90, 0.75], mode="unknown_mode")
        assert result == pytest.approx(0.75)

    def test_empty_returns_zero(self):
        result = propagate_confidence([], mode="min")
        assert result == 0.0

    def test_result_capped_at_one(self):
        """Can't exceed 1.0 even with high inputs."""
        result = propagate_confidence([1.0, 1.0], mode="product")
        assert result <= 1.0

    def test_result_floored_at_zero(self):
        """Very aggressive discount shouldn't go below 0."""
        result = propagate_confidence([0.5], mode="min", derivation_discount=0.0)
        assert result == 0.0

    def test_discount_one_leaves_unchanged(self):
        result = propagate_confidence([0.85], mode="min", derivation_discount=1.0)
        assert result == pytest.approx(0.85)


# ─────────────────────────────────────────────────────────────────────────────
# compute_uncertainty_band
# ─────────────────────────────────────────────────────────────────────────────


class TestComputeUncertaintyBand:
    """Test value_range_low / value_range_high computation."""

    # ── ratio formula ─────────────────────────────────────────────────────────

    def test_ratio_returns_bounds_around_value(self):
        value = Decimal("1.35")
        low, high = compute_uncertainty_band(value, [0.90, 0.90], formula_type="ratio")
        assert low is not None
        assert high is not None
        assert low < value < high

    def test_ratio_single_input(self):
        value = Decimal("2.00")
        low, high = compute_uncertainty_band(value, [1.0], formula_type="ratio")
        # Perfect confidence → ±1% uncertainty
        assert low is not None
        assert high is not None
        assert abs(float(high - low) / float(value)) < 0.05  # Band < 5%

    def test_ratio_low_confidence_wide_band(self):
        """Low confidence inputs → wider band."""
        value = Decimal("1.00")
        low_narrow, high_narrow = compute_uncertainty_band(value, [1.0, 1.0], formula_type="ratio")
        low_wide, high_wide = compute_uncertainty_band(value, [0.50, 0.50], formula_type="ratio")
        # Wider band for lower confidence
        band_narrow = float(high_narrow - low_narrow)
        band_wide = float(high_wide - low_wide)
        assert band_wide > band_narrow

    def test_ratio_positive_value_low_floored_at_zero(self):
        """For positive metrics, lower bound must not go below zero."""
        # With 100% uncertainty, low would be negative — should be floored at 0
        value = Decimal("0.05")  # Small ratio, high uncertainty pushes low < 0
        low, high = compute_uncertainty_band(value, [0.50], formula_type="ratio")
        if low is not None:
            assert float(low) >= 0.0

    # ── sum / difference formula ───────────────────────────────────────────────

    def test_sum_returns_bounds(self):
        value = Decimal("1000000")
        low, high = compute_uncertainty_band(value, [0.90, 0.90], formula_type="sum")
        assert low is not None
        assert high is not None
        assert low < value < high

    def test_difference_returns_bounds(self):
        value = Decimal("500000")
        low, high = compute_uncertainty_band(value, [0.90, 0.90], formula_type="difference")
        assert low is not None
        assert high is not None

    def test_difference_near_zero_returns_none(self):
        """Near-zero value for sum/difference → can't bound meaningfully."""
        value = Decimal("0")
        low, high = compute_uncertainty_band(value, [0.90, 0.90], formula_type="difference")
        assert low is None
        assert high is None

    def test_small_absolute_value_near_zero_returns_none(self):
        """Value strictly below 1e-10 returns (None, None) for sum/difference."""
        value = Decimal("0.00000000001")  # 1e-11, strictly less than 1e-10
        low, high = compute_uncertainty_band(value, [0.90], formula_type="difference")
        assert low is None
        assert high is None

    # ── other / product formula ────────────────────────────────────────────────

    def test_other_formula_type_uses_max_uncertainty(self):
        value = Decimal("100")
        low, high = compute_uncertainty_band(value, [0.95, 0.70], formula_type="product_formula")
        assert low is not None
        assert high is not None

    # ── edge cases ────────────────────────────────────────────────────────────

    def test_empty_confidences_returns_none(self):
        low, high = compute_uncertainty_band(Decimal("1.0"), [], formula_type="ratio")
        assert low is None
        assert high is None

    def test_none_value_returns_none(self):
        low, high = compute_uncertainty_band(None, [0.90], formula_type="ratio")
        assert low is None
        assert high is None

    def test_band_symmetric_for_ratio(self):
        """Ratio band should be roughly symmetric around the value."""
        value = Decimal("2.00")
        low, high = compute_uncertainty_band(value, [0.95, 0.95], formula_type="ratio")
        diff_low = float(value - low)
        diff_high = float(high - value)
        assert abs(diff_low - diff_high) < 0.01  # Symmetric within 1 cent


# ─────────────────────────────────────────────────────────────────────────────
# is_covenant_sensitive
# ─────────────────────────────────────────────────────────────────────────────


class TestIsCovenantSensitive:
    """Test covenant sensitivity detection."""

    # ── no threshold ──────────────────────────────────────────────────────────

    def test_no_threshold_returns_false_none(self):
        sensitive, headroom = is_covenant_sensitive(
            Decimal("1.35"),
            Decimal("1.20"),
            Decimal("1.50"),
            threshold=None,
        )
        assert sensitive is False
        assert headroom is None

    # ── comfortable headroom (not sensitive) ──────────────────────────────────

    def test_comfortable_headroom_not_sensitive(self):
        """Value well above threshold, lower bound also above → not sensitive."""
        sensitive, headroom = is_covenant_sensitive(
            Decimal("1.80"),
            Decimal("1.65"),
            Decimal("1.95"),
            threshold=Decimal("1.25"),
        )
        assert sensitive is False
        assert headroom is not None
        assert float(headroom) == pytest.approx(0.55)

    # ── covenant sensitive (band spans threshold) ─────────────────────────────

    def test_sensitive_when_lower_bound_below_threshold(self):
        """Value > threshold but lower bound < threshold → sensitive."""
        sensitive, headroom = is_covenant_sensitive(
            Decimal("1.29"),
            Decimal("1.20"),   # Below 1.25
            Decimal("1.38"),
            threshold=Decimal("1.25"),
        )
        assert sensitive is True
        assert float(headroom) == pytest.approx(0.04)

    def test_sensitive_when_band_spans_threshold_both_sides(self):
        """Upper > threshold > lower → sensitive."""
        sensitive, headroom = is_covenant_sensitive(
            Decimal("1.30"),
            Decimal("1.10"),   # Below 1.25
            Decimal("1.50"),   # Above 1.25
            threshold=Decimal("1.25"),
        )
        assert sensitive is True

    # ── covenant breach (value below threshold) ────────────────────────────────

    def test_breach_value_below_threshold(self):
        """Value itself below threshold → headroom negative."""
        sensitive, headroom = is_covenant_sensitive(
            Decimal("1.10"),
            Decimal("0.95"),
            Decimal("1.25"),
            threshold=Decimal("1.25"),
        )
        assert headroom is not None
        assert float(headroom) < 0  # Negative headroom = breach

    # ── no bounds provided ────────────────────────────────────────────────────

    def test_no_bounds_returns_false_with_headroom(self):
        """Without bounds, can't determine sensitivity but headroom is still computed."""
        sensitive, headroom = is_covenant_sensitive(
            Decimal("1.29"),
            value_low=None,
            value_high=None,
            threshold=Decimal("1.25"),
        )
        assert sensitive is False
        assert float(headroom) == pytest.approx(0.04)

    def test_no_low_bound_only(self):
        sensitive, headroom = is_covenant_sensitive(
            Decimal("1.35"),
            value_low=None,
            value_high=Decimal("1.50"),
            threshold=Decimal("1.25"),
        )
        assert sensitive is False
        assert headroom is not None

    # ── exact boundary ────────────────────────────────────────────────────────

    def test_exactly_at_threshold(self):
        """Value exactly at threshold — headroom is 0."""
        sensitive, headroom = is_covenant_sensitive(
            Decimal("1.25"),
            Decimal("1.10"),
            Decimal("1.40"),
            threshold=Decimal("1.25"),
        )
        assert headroom is not None
        assert float(headroom) == pytest.approx(0.0)

    # ── leverage metric (higher is worse) ─────────────────────────────────────

    def test_leverage_metric_value_above_threshold(self):
        """For leverage (debt/EBITDA), value > threshold is a breach."""
        sensitive, headroom = is_covenant_sensitive(
            Decimal("7.5"),     # Debt/EBITDA = 7.5x
            Decimal("6.8"),
            Decimal("8.2"),
            threshold=Decimal("7.0"),  # Covenant max
        )
        # Headroom = value - threshold (negative means breach for upper-bound covenants)
        assert headroom is not None
        assert float(headroom) == pytest.approx(0.5)  # 7.5 - 7.0 = 0.5 (positive = above threshold)
