"""Unit tests for time-series validator."""

from decimal import Decimal

from src.validation.time_series_validator import (
    TimeSeriesConfig,
    TimeSeriesValidator,
)
from src.validation.utils import sort_periods

# ============================================================================
# HELPERS
# ============================================================================


def _make_taxonomy(items=None):
    """Create minimal taxonomy entries."""
    default = [
        {
            "canonical_name": "revenue",
            "category": "income_statement",
            "typical_sign": "positive",
            "industry_tags": ["all"],
        },
        {
            "canonical_name": "net_income",
            "category": "income_statement",
            "typical_sign": "positive",
            "industry_tags": ["all"],
        },
        {
            "canonical_name": "capex",
            "category": "cash_flow",
            "typical_sign": "negative",
            "industry_tags": ["all"],
        },
        {
            "canonical_name": "cfads",
            "category": "project_finance",
            "typical_sign": "positive",
            "industry_tags": ["project_finance"],
        },
        {
            "canonical_name": "accumulated_depreciation",
            "category": "balance_sheet",
            "typical_sign": "negative",
            "industry_tags": ["all"],
        },
    ]
    return items or default


# ============================================================================
# PERIOD SORTING
# ============================================================================


class TestPeriodSorting:
    """Test period key sorting logic."""

    def test_numeric_period_sorting(self):
        periods = ["3.0", "1.0", "2.0", "10.0"]
        result = sort_periods(periods)
        assert result == ["1.0", "2.0", "3.0", "10.0"]

    def test_fiscal_year_sorting(self):
        periods = ["FY2024", "FY2022", "FY2023"]
        result = sort_periods(periods)
        assert result == ["FY2022", "FY2023", "FY2024"]

    def test_mixed_format_numeric_first(self):
        """Numeric periods should sort before non-numeric."""
        periods = ["FY2022", "1.0", "2.0"]
        result = sort_periods(periods)
        assert result[0] == "1.0"
        assert result[1] == "2.0"

    def test_empty_periods(self):
        assert sort_periods([]) == []

    def test_single_period(self):
        assert sort_periods(["1.0"]) == ["1.0"]

    def test_quarterly_vs_fiscal_correct_order(self):
        """2024-Q3 should sort AFTER FY2023 (not before, as naive sort would)."""
        periods = ["2024-Q3", "FY2023"]
        result = sort_periods(periods)
        assert result == ["FY2023", "2024-Q3"]


# ============================================================================
# LIFECYCLE AWARENESS
# ============================================================================


class TestLifecycleAwareness:
    """Test lifecycle phase detection and transition suppression."""

    def test_lifecycle_detection(self):
        data = {
            "1.0": {"revenue": Decimal("0"), "capex": Decimal("-15000000")},
            "2.0": {"revenue": Decimal("0")},
            "3.0": {"revenue": Decimal("0")},
            "4.0": {"revenue": Decimal("21000000")},
            "5.0": {"revenue": Decimal("22000000")},
            "23.0": {"revenue": Decimal("31000000")},
            "24.0": {"revenue": Decimal("0")},
            "25.0": {"revenue": Decimal("0")},
        }
        phases = TimeSeriesValidator._detect_lifecycle_phases(data)
        assert phases["1.0"] == "construction"
        assert phases["2.0"] == "construction"
        assert phases["3.0"] == "construction"
        assert phases["4.0"] == "operations"
        assert phases["5.0"] == "operations"
        assert phases["23.0"] == "operations"
        assert phases["24.0"] == "post_operations"
        assert phases["25.0"] == "post_operations"

    def test_no_revenue_returns_empty_phases(self):
        data = {"1.0": {"capex": Decimal("-5000000")}}
        phases = TimeSeriesValidator._detect_lifecycle_phases(data)
        assert phases == {}

    def test_transition_period_detected(self):
        validator = TimeSeriesValidator(_make_taxonomy())
        phases = {"3.0": "construction", "4.0": "operations"}
        assert validator._is_transition_period("4.0", "3.0", phases) is True
        assert (
            validator._is_transition_period(
                "5.0", "4.0", {"4.0": "operations", "5.0": "operations"}
            )
            is False
        )

    def test_yoy_suppressed_at_transition(self):
        """Large changes at construction→operations boundary should not flag."""
        validator = TimeSeriesValidator(_make_taxonomy())
        data = {
            "3.0": {"revenue": Decimal("0"), "net_income": Decimal("-5000000")},
            "4.0": {"revenue": Decimal("21000000"), "net_income": Decimal("3000000")},
            "5.0": {"revenue": Decimal("22000000"), "net_income": Decimal("3200000")},
        }
        result = validator.validate(data)
        # Should not flag the 3→4 transition; net_income flip from -5M to +3M is lifecycle
        yoy_flags = [f for f in result.flags if f.check_type == "yoy_change" and f.period == "4.0"]
        assert len(yoy_flags) == 0

    def test_sign_flip_suppressed_at_transition(self):
        """Sign flips at construction→operations boundary should not flag."""
        validator = TimeSeriesValidator(_make_taxonomy())
        data = {
            "3.0": {"revenue": Decimal("0"), "net_income": Decimal("-5000000")},
            "4.0": {"revenue": Decimal("21000000"), "net_income": Decimal("3000000")},
            "5.0": {"revenue": Decimal("22000000"), "net_income": Decimal("3200000")},
        }
        result = validator.validate(data)
        flip_flags = [f for f in result.flags if f.check_type == "sign_flip" and f.period == "4.0"]
        assert len(flip_flags) == 0


# ============================================================================
# YOY CHANGE CHECKS
# ============================================================================


class TestYoYChecks:
    """Test year-over-year change detection."""

    def setup_method(self):
        self.validator = TimeSeriesValidator(_make_taxonomy())

    def test_normal_growth_passes(self):
        data = {
            "1.0": {"revenue": Decimal("100000")},
            "2.0": {"revenue": Decimal("120000")},  # 20% growth
            "3.0": {"revenue": Decimal("140000")},  # 17% growth
        }
        result = self.validator.validate(data)
        yoy_flags = [f for f in result.flags if f.check_type == "yoy_change"]
        assert len(yoy_flags) == 0

    def test_excessive_growth_flags(self):
        data = {
            "1.0": {"revenue": Decimal("100000")},
            "2.0": {"revenue": Decimal("500000")},  # 400% growth > 300% revenue threshold
        }
        result = self.validator.validate(data)
        yoy_flags = [f for f in result.flags if f.check_type == "yoy_change"]
        assert len(yoy_flags) > 0
        assert yoy_flags[0].severity == "warning"

    def test_excessive_decline_flags(self):
        data = {
            "1.0": {"revenue": Decimal("1000000")},
            "2.0": {"revenue": Decimal("100000")},  # -90% decline > -80% threshold
        }
        result = self.validator.validate(data)
        yoy_flags = [f for f in result.flags if f.check_type == "yoy_change"]
        assert len(yoy_flags) > 0

    def test_skips_single_period(self):
        data = {"1.0": {"revenue": Decimal("100000")}}
        result = self.validator.validate(data)
        assert result.total_checks == 0

    def test_skips_zero_base(self):
        """Can't compute % change from zero; should skip, not crash."""
        data = {
            "1.0": {"revenue": Decimal("0")},
            "2.0": {"revenue": Decimal("100000")},
        }
        result = self.validator.validate(data)
        yoy_flags = [
            f
            for f in result.flags
            if f.check_type == "yoy_change" and f.canonical_name == "revenue"
        ]
        assert len(yoy_flags) == 0

    def test_revenue_uses_item_override(self):
        """Revenue threshold is 300% (ITEM_OVERRIDES), not default 200%."""
        data = {
            "1.0": {"revenue": Decimal("100000")},
            "2.0": {"revenue": Decimal("350000")},  # 250% growth — under 300%
        }
        result = self.validator.validate(data)
        yoy_flags = [
            f
            for f in result.flags
            if f.check_type == "yoy_change" and f.canonical_name == "revenue"
        ]
        assert len(yoy_flags) == 0  # Under item-specific threshold


# ============================================================================
# SIGN FLIP CHECKS
# ============================================================================


class TestSignFlipChecks:
    """Test unexpected sign change detection."""

    def setup_method(self):
        self.validator = TimeSeriesValidator(_make_taxonomy())

    def test_sign_flip_detected(self):
        """Flip within operational window (surrounded by positive revenue)."""
        data = {
            "1.0": {"revenue": Decimal("100000")},
            "2.0": {"revenue": Decimal("120000")},
            "3.0": {"revenue": Decimal("-50000")},  # Unexpected flip
            "4.0": {"revenue": Decimal("130000")},  # Back to positive → 3.0 is within ops window
        }
        result = self.validator.validate(data)
        flip_flags = [
            f for f in result.flags if f.check_type == "sign_flip" and f.canonical_name == "revenue"
        ]
        assert len(flip_flags) > 0
        assert flip_flags[0].severity == "error"

    def test_consistent_negative_no_flip(self):
        data = {
            "1.0": {"net_income": Decimal("-100000")},
            "2.0": {"net_income": Decimal("-80000")},
            "3.0": {"net_income": Decimal("-60000")},
        }
        result = self.validator.validate(data)
        flip_flags = [
            f
            for f in result.flags
            if f.check_type == "sign_flip" and f.canonical_name == "net_income"
        ]
        assert len(flip_flags) == 0

    def test_zero_to_positive_not_a_flip(self):
        """Zero is not a meaningful sign — should not flag."""
        data = {
            "1.0": {"revenue": Decimal("0")},
            "2.0": {"revenue": Decimal("100000")},
        }
        result = self.validator.validate(data)
        flip_flags = [
            f for f in result.flags if f.check_type == "sign_flip" and f.canonical_name == "revenue"
        ]
        assert len(flip_flags) == 0


# ============================================================================
# OUTLIER CHECKS
# ============================================================================


class TestOutlierChecks:
    """Test statistical outlier detection."""

    def setup_method(self):
        self.validator = TimeSeriesValidator(_make_taxonomy())

    def test_outlier_detected(self):
        """Need enough normal values so the outlier exceeds 3σ.
        With n points, max z-score approaches √(n-1), so need n≥20.
        """
        base = {
            f"{float(i)}": {
                "net_income": Decimal(str(100000 + i * 500)),
                "revenue": Decimal("500000"),
            }
            for i in range(1, 20)
        }
        base["20.0"] = {"net_income": Decimal("5000000"), "revenue": Decimal("520000")}
        result = self.validator.validate(base)
        outlier_flags = [
            f
            for f in result.flags
            if f.check_type == "outlier" and f.canonical_name == "net_income"
        ]
        assert len(outlier_flags) > 0

    def test_no_outlier_with_few_periods(self):
        """Need min_periods_for_outlier (4) to compute sigma."""
        data = {
            "1.0": {"revenue": Decimal("100000")},
            "2.0": {"revenue": Decimal("500000")},
            "3.0": {"revenue": Decimal("100000")},
        }
        result = self.validator.validate(data)
        outlier_flags = [f for f in result.flags if f.check_type == "outlier"]
        assert len(outlier_flags) == 0

    def test_all_identical_no_outlier(self):
        """If all values identical, stdev=0, no outliers possible."""
        data = {str(float(i)): {"revenue": Decimal("100000")} for i in range(1, 6)}
        result = self.validator.validate(data)
        outlier_flags = [f for f in result.flags if f.check_type == "outlier"]
        assert len(outlier_flags) == 0

    def test_outlier_threshold_configurable(self):
        config = TimeSeriesConfig(outlier_sigma=1.5)  # Tighter threshold
        validator = TimeSeriesValidator(_make_taxonomy(), config=config)
        data = {
            "1.0": {"revenue": Decimal("100000")},
            "2.0": {"revenue": Decimal("105000")},
            "3.0": {"revenue": Decimal("102000")},
            "4.0": {"revenue": Decimal("103000")},
            "5.0": {"revenue": Decimal("150000")},  # Moderate deviation
        }
        result = validator.validate(data)
        outlier_flags = [f for f in result.flags if f.check_type == "outlier"]
        assert len(outlier_flags) > 0  # Caught with tighter threshold


# ============================================================================
# GAP CHECKS
# ============================================================================


class TestGapChecks:
    """Test missing period gap detection."""

    def setup_method(self):
        self.validator = TimeSeriesValidator(_make_taxonomy())

    def test_gap_detected_numeric_periods(self):
        """Item present in periods 1,2,4 but missing 3 should flag."""
        data = {
            "1.0": {"revenue": Decimal("100000")},
            "2.0": {"revenue": Decimal("110000")},
            "3.0": {},  # No revenue here
            "4.0": {"revenue": Decimal("130000")},
        }
        result = self.validator.validate(data)
        gap_flags = [
            f for f in result.flags if f.check_type == "gap" and f.canonical_name == "revenue"
        ]
        assert len(gap_flags) == 1
        assert gap_flags[0].period == "3.0"
        assert gap_flags[0].severity == "info"

    def test_no_gap_when_all_present(self):
        data = {
            "1.0": {"revenue": Decimal("100000")},
            "2.0": {"revenue": Decimal("110000")},
            "3.0": {"revenue": Decimal("120000")},
        }
        result = self.validator.validate(data)
        gap_flags = [f for f in result.flags if f.check_type == "gap"]
        assert len(gap_flags) == 0

    def test_leading_absence_not_flagged(self):
        """Item starting at period 3 shouldn't flag 1,2 as gaps."""
        data = {
            "1.0": {},
            "2.0": {},
            "3.0": {"revenue": Decimal("100000")},
            "4.0": {"revenue": Decimal("110000")},
        }
        result = self.validator.validate(data)
        gap_flags = [
            f for f in result.flags if f.check_type == "gap" and f.canonical_name == "revenue"
        ]
        assert len(gap_flags) == 0


# ============================================================================
# MONOTONICITY CHECKS
# ============================================================================


class TestMonotonicity:
    """Test cumulative item monotonicity checks."""

    def test_cumulative_decreasing_flags(self):
        config = TimeSeriesConfig(cumulative_items={"accumulated_depreciation"})
        validator = TimeSeriesValidator(_make_taxonomy(), config=config)
        data = {
            "1.0": {"accumulated_depreciation": Decimal("100000")},
            "2.0": {"accumulated_depreciation": Decimal("200000")},
            "3.0": {"accumulated_depreciation": Decimal("150000")},  # Decreased!
        }
        result = validator.validate(data)
        mono_flags = [f for f in result.flags if f.check_type == "monotonicity"]
        assert len(mono_flags) == 1
        assert mono_flags[0].period == "3.0"

    def test_non_decreasing_passes(self):
        config = TimeSeriesConfig(cumulative_items={"accumulated_depreciation"})
        validator = TimeSeriesValidator(_make_taxonomy(), config=config)
        data = {
            "1.0": {"accumulated_depreciation": Decimal("100000")},
            "2.0": {"accumulated_depreciation": Decimal("200000")},
            "3.0": {"accumulated_depreciation": Decimal("300000")},
        }
        result = validator.validate(data)
        mono_flags = [f for f in result.flags if f.check_type == "monotonicity"]
        assert len(mono_flags) == 0

    def test_non_cumulative_not_checked(self):
        """Revenue is not cumulative — should not get monotonicity checks."""
        validator = TimeSeriesValidator(_make_taxonomy())
        data = {
            "1.0": {"revenue": Decimal("200000")},
            "2.0": {"revenue": Decimal("100000")},  # Decrease is normal for revenue
        }
        result = validator.validate(data)
        mono_flags = [
            f
            for f in result.flags
            if f.check_type == "monotonicity" and f.canonical_name == "revenue"
        ]
        assert len(mono_flags) == 0


# ============================================================================
# THRESHOLD OVERRIDES
# ============================================================================


class TestThresholdOverrides:
    """Test threshold cascade: item > category > default."""

    def test_default_threshold(self):
        validator = TimeSeriesValidator(_make_taxonomy())
        thresholds = validator._get_thresholds("net_income")
        assert thresholds["yoy_max_growth"] == 2.0  # Default

    def test_category_override(self):
        validator = TimeSeriesValidator(_make_taxonomy())
        thresholds = validator._get_thresholds("cfads")
        assert thresholds["yoy_max_growth"] == 5.0  # project_finance override

    def test_item_override(self):
        validator = TimeSeriesValidator(_make_taxonomy())
        thresholds = validator._get_thresholds("revenue")
        assert thresholds["yoy_max_growth"] == 3.0  # revenue-specific override

    def test_custom_config(self):
        config = TimeSeriesConfig(yoy_max_growth=1.0, yoy_max_decline=-0.5)
        validator = TimeSeriesValidator(_make_taxonomy(), config=config)
        # For items without overrides, custom config applies
        thresholds = validator._get_thresholds("net_income")
        assert thresholds["yoy_max_growth"] == 1.0
        assert thresholds["yoy_max_decline"] == -0.5


# ============================================================================
# CONSISTENCY SCORE
# ============================================================================


class TestConsistencyScore:
    """Test consistency score computation."""

    def test_perfect_consistency_score(self):
        """No flags should give 1.0."""
        validator = TimeSeriesValidator(_make_taxonomy())
        data = {
            "1.0": {"revenue": Decimal("100000")},
            "2.0": {"revenue": Decimal("120000")},
            "3.0": {"revenue": Decimal("140000")},
        }
        result = validator.validate(data)
        assert result.consistency_score == 1.0

    def test_degraded_consistency_score(self):
        """Flags should reduce score below 1.0."""
        validator = TimeSeriesValidator(_make_taxonomy())
        data = {
            "1.0": {"revenue": Decimal("100000"), "net_income": Decimal("50000")},
            "2.0": {"revenue": Decimal("120000"), "net_income": Decimal("-50000")},  # Sign flip
            "3.0": {"revenue": Decimal("130000"), "net_income": Decimal("60000")},
        }
        result = validator.validate(data)
        assert result.consistency_score < 1.0

    def test_empty_data_gives_perfect_score(self):
        validator = TimeSeriesValidator(_make_taxonomy())
        result = validator.validate({})
        assert result.consistency_score == 1.0
        assert result.total_checks == 0


# ============================================================================
# EDGE CASES
# ============================================================================


class TestEdgeCases:
    """Test edge cases."""

    def setup_method(self):
        self.validator = TimeSeriesValidator(_make_taxonomy())

    def test_empty_data(self):
        result = self.validator.validate({})
        assert result.total_checks == 0
        assert result.items_checked == 0
        assert result.periods_analyzed == 0
        assert result.consistency_score == 1.0

    def test_single_period(self):
        data = {"1.0": {"revenue": Decimal("100000")}}
        result = self.validator.validate(data)
        assert result.items_checked == 1
        assert result.periods_analyzed == 1
        assert result.total_checks == 0  # Need ≥2 periods for checks

    def test_all_zero_values(self):
        data = {str(float(i)): {"revenue": Decimal("0")} for i in range(1, 5)}
        result = self.validator.validate(data)
        # Zeros shouldn't crash or generate false positives
        assert result.periods_analyzed == 4

    def test_multiple_items(self):
        """Multiple items should all get checked."""
        data = {
            "1.0": {"revenue": Decimal("100000"), "net_income": Decimal("20000")},
            "2.0": {"revenue": Decimal("120000"), "net_income": Decimal("25000")},
        }
        result = self.validator.validate(data)
        assert result.items_checked == 2

    def test_summary_counts(self):
        data = {
            "1.0": {"revenue": Decimal("100000")},
            "2.0": {"revenue": Decimal("120000")},
            "3.0": {"revenue": Decimal("140000")},
        }
        result = self.validator.validate(data)
        assert result.items_checked >= 1
        assert result.periods_analyzed == 3
        assert result.total_checks > 0

    def test_lifecycle_aware_false(self):
        """With lifecycle_aware=False, transitions should still flag."""
        config = TimeSeriesConfig(lifecycle_aware=False)
        validator = TimeSeriesValidator(_make_taxonomy(), config=config)
        data = {
            "3.0": {"net_income": Decimal("-5000000")},
            "4.0": {"net_income": Decimal("3000000")},  # Huge flip
        }
        result = validator.validate(data)
        # Should flag since lifecycle awareness is off
        flip_flags = [f for f in result.flags if f.check_type == "sign_flip"]
        assert len(flip_flags) > 0
