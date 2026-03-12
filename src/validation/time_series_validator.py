"""Time-series validator for financial extraction results.

Validates financial data across periods (not just within a single period).
Catches extraction errors like:
- Abnormal period-over-period changes (>200% growth, >80% decline)
- Unexpected sign flips (revenue going negative mid-operations)
- Statistical outliers (one period wildly different from others)
- Missing periods (gaps in the extracted range)
- Monotonicity violations (cumulative items decreasing)

All checks are lifecycle-aware: phase transitions (construction→operations)
are expected to produce large changes and are not flagged.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple
import statistics

from src.validation.utils import sort_periods


@dataclass
class TimeSeriesFlag:
    """A single time-series anomaly flag."""
    check_type: str          # "yoy_change", "sign_flip", "outlier", "gap", "monotonicity"
    canonical_name: str
    period: str
    severity: str            # "error", "warning", "info"
    message: str
    details: Optional[Dict] = None


@dataclass
class TimeSeriesSummary:
    """Summary of all time-series validation results."""
    total_checks: int
    flags: List[TimeSeriesFlag]
    items_checked: int
    periods_analyzed: int
    consistency_score: float  # 0.0 to 1.0 (1.0 = no anomalies)

    @property
    def has_flags(self) -> bool:
        return len(self.flags) > 0

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.flags if f.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.flags if f.severity == "warning")


@dataclass
class TimeSeriesConfig:
    """Configuration for time-series thresholds."""
    yoy_max_growth: float = 2.0         # 200% growth threshold
    yoy_max_decline: float = -0.8       # 80% decline threshold
    outlier_sigma: float = 3.0          # standard deviations for outlier detection
    min_periods_for_outlier: int = 4    # need at least 4 periods for sigma calc
    min_periods_for_yoy: int = 2        # need at least 2 consecutive periods
    lifecycle_aware: bool = True        # suppress flags at construction/ops transitions
    cumulative_items: Set[str] = field(default_factory=lambda: {
        "accumulated_depreciation",
        "retained_earnings",
        "debt_closing_balance",
    })


# Per-category threshold overrides
CATEGORY_OVERRIDES: Dict[str, Dict[str, float]] = {
    "project_finance": {"yoy_max_growth": 5.0, "yoy_max_decline": -0.95},
    "metrics": {"yoy_max_growth": 3.0},
}

# Per-item threshold overrides (highest priority)
ITEM_OVERRIDES: Dict[str, Dict[str, float]] = {
    "revenue": {"yoy_max_growth": 3.0},
    "capex": {"yoy_max_growth": 5.0, "yoy_max_decline": -0.95},
    "equity_contribution": {"yoy_max_growth": 10.0, "yoy_max_decline": -1.0},
    "development_costs": {"yoy_max_growth": 10.0, "yoy_max_decline": -1.0},
}


class TimeSeriesValidator:
    """Validates financial data across time periods."""

    def __init__(
        self,
        taxonomy_items: List[Dict],
        config: Optional[TimeSeriesConfig] = None,
    ):
        self.taxonomy = {item["canonical_name"]: item for item in taxonomy_items}
        self.config = config or TimeSeriesConfig()

    def validate(
        self,
        multi_period_data: Dict[str, Dict[str, Decimal]],
    ) -> TimeSeriesSummary:
        """Validate time-series consistency across all periods.

        Args:
            multi_period_data: period_key -> {canonical_name -> Decimal}

        Returns:
            TimeSeriesSummary with flags for anomalies.
        """
        if not multi_period_data:
            return TimeSeriesSummary(
                total_checks=0, flags=[], items_checked=0,
                periods_analyzed=0, consistency_score=1.0,
            )

        sorted_periods = sort_periods(list(multi_period_data.keys()))
        phases = self._detect_lifecycle_phases(multi_period_data) if self.config.lifecycle_aware else {}

        # Collect all canonical names across all periods
        all_items: Set[str] = set()
        for period_vals in multi_period_data.values():
            all_items.update(period_vals.keys())

        all_flags: List[TimeSeriesFlag] = []
        total_checks = 0

        for canonical_name in sorted(all_items):
            # Build per-item time series: {period: value}
            values_by_period: Dict[str, Decimal] = {}
            for period in sorted_periods:
                val = multi_period_data.get(period, {}).get(canonical_name)
                if val is not None:
                    values_by_period[period] = val

            if len(values_by_period) < self.config.min_periods_for_yoy:
                continue

            item_periods = [p for p in sorted_periods if p in values_by_period]

            # YoY change checks
            yoy_flags, yoy_checks = self._check_yoy_changes(
                canonical_name, item_periods, values_by_period, phases,
            )
            all_flags.extend(yoy_flags)
            total_checks += yoy_checks

            # Sign flip checks
            flip_flags, flip_checks = self._check_sign_flips(
                canonical_name, item_periods, values_by_period, phases,
            )
            all_flags.extend(flip_flags)
            total_checks += flip_checks

            # Outlier checks
            outlier_flags, outlier_checks = self._check_outliers(
                canonical_name, item_periods, values_by_period,
            )
            all_flags.extend(outlier_flags)
            total_checks += outlier_checks

            # Gap checks
            gap_flags, gap_checks = self._check_gaps(
                sorted_periods, values_by_period, canonical_name,
            )
            all_flags.extend(gap_flags)
            total_checks += gap_checks

            # Monotonicity checks
            if canonical_name in self.config.cumulative_items:
                mono_flags, mono_checks = self._check_monotonicity(
                    canonical_name, item_periods, values_by_period,
                )
                all_flags.extend(mono_flags)
                total_checks += mono_checks

        consistency = self._compute_consistency_score(all_flags, total_checks)

        return TimeSeriesSummary(
            total_checks=total_checks,
            flags=all_flags,
            items_checked=len(all_items),
            periods_analyzed=len(sorted_periods),
            consistency_score=consistency,
        )

    @staticmethod
    def _detect_lifecycle_phases(
        multi_period_data: Dict[str, Dict[str, Decimal]],
    ) -> Dict[str, str]:
        """Auto-detect lifecycle phases using LifecycleDetector.

        Returns dict mapping period keys to phase names. For non-PF models
        this produces the same 3-phase mapping (construction/operations/
        post_operations) as the original heuristic. For PF models it produces
        up to 7 phases.
        """
        from src.validation.lifecycle_detector import LifecycleDetector

        detector = LifecycleDetector()
        result = detector.detect(multi_period_data)
        return result.phases

    def _is_transition_period(
        self, period: str, prev_period: str, phases: Dict[str, str],
    ) -> bool:
        """Check if period crosses a lifecycle phase boundary."""
        if not phases:
            return False
        return phases.get(period, "") != phases.get(prev_period, "")

    def _get_thresholds(self, canonical_name: str) -> Dict[str, float]:
        """Get effective thresholds: item overrides > category overrides > defaults."""
        thresholds = {
            "yoy_max_growth": self.config.yoy_max_growth,
            "yoy_max_decline": self.config.yoy_max_decline,
        }

        # Category override
        item_meta = self.taxonomy.get(canonical_name, {})
        category = item_meta.get("category", "")
        if category in CATEGORY_OVERRIDES:
            thresholds.update(CATEGORY_OVERRIDES[category])

        # Item override (highest priority)
        if canonical_name in ITEM_OVERRIDES:
            thresholds.update(ITEM_OVERRIDES[canonical_name])

        return thresholds

    # ------------------------------------------------------------------
    # Check implementations
    # ------------------------------------------------------------------

    def _check_yoy_changes(
        self,
        canonical_name: str,
        sorted_periods: List[str],
        values_by_period: Dict[str, Decimal],
        phases: Dict[str, str],
    ) -> Tuple[List[TimeSeriesFlag], int]:
        """Flag period-over-period changes exceeding thresholds."""
        flags: List[TimeSeriesFlag] = []
        checks = 0
        thresholds = self._get_thresholds(canonical_name)

        for i in range(1, len(sorted_periods)):
            prev_p = sorted_periods[i - 1]
            curr_p = sorted_periods[i]
            prev_val = float(values_by_period[prev_p])
            curr_val = float(values_by_period[curr_p])

            checks += 1

            # Skip if previous value is zero (can't compute % change)
            if abs(prev_val) < 1e-10:
                continue

            pct_change = (curr_val - prev_val) / abs(prev_val)

            # Suppress flags at lifecycle transitions
            if self._is_transition_period(curr_p, prev_p, phases):
                continue

            if pct_change > thresholds["yoy_max_growth"]:
                flags.append(TimeSeriesFlag(
                    check_type="yoy_change",
                    canonical_name=canonical_name,
                    period=curr_p,
                    severity="warning",
                    message=(
                        f"{canonical_name} grew {pct_change:.0%} from {prev_p} to {curr_p} "
                        f"(threshold: {thresholds['yoy_max_growth']:.0%})"
                    ),
                    details={"pct_change": round(pct_change, 4),
                             "threshold": thresholds["yoy_max_growth"]},
                ))
            elif pct_change < thresholds["yoy_max_decline"]:
                flags.append(TimeSeriesFlag(
                    check_type="yoy_change",
                    canonical_name=canonical_name,
                    period=curr_p,
                    severity="warning",
                    message=(
                        f"{canonical_name} declined {pct_change:.0%} from {prev_p} to {curr_p} "
                        f"(threshold: {thresholds['yoy_max_decline']:.0%})"
                    ),
                    details={"pct_change": round(pct_change, 4),
                             "threshold": thresholds["yoy_max_decline"]},
                ))

        return flags, checks

    def _check_sign_flips(
        self,
        canonical_name: str,
        sorted_periods: List[str],
        values_by_period: Dict[str, Decimal],
        phases: Dict[str, str],
    ) -> Tuple[List[TimeSeriesFlag], int]:
        """Flag unexpected sign changes within the same lifecycle phase."""
        flags: List[TimeSeriesFlag] = []
        checks = 0

        for i in range(1, len(sorted_periods)):
            prev_p = sorted_periods[i - 1]
            curr_p = sorted_periods[i]
            prev_val = float(values_by_period[prev_p])
            curr_val = float(values_by_period[curr_p])

            checks += 1

            # Skip zeros (not a meaningful sign)
            if abs(prev_val) < 1e-10 or abs(curr_val) < 1e-10:
                continue

            # Suppress at lifecycle transitions
            if self._is_transition_period(curr_p, prev_p, phases):
                continue

            prev_sign = prev_val > 0
            curr_sign = curr_val > 0

            if prev_sign != curr_sign:
                flags.append(TimeSeriesFlag(
                    check_type="sign_flip",
                    canonical_name=canonical_name,
                    period=curr_p,
                    severity="error",
                    message=(
                        f"{canonical_name} flipped sign from "
                        f"{'positive' if prev_sign else 'negative'} to "
                        f"{'positive' if curr_sign else 'negative'} "
                        f"between {prev_p} and {curr_p}"
                    ),
                    details={"prev_value": prev_val, "curr_value": curr_val},
                ))

        return flags, checks

    def _check_outliers(
        self,
        canonical_name: str,
        sorted_periods: List[str],
        values_by_period: Dict[str, Decimal],
    ) -> Tuple[List[TimeSeriesFlag], int]:
        """Flag values deviating > N sigma from mean across periods."""
        flags: List[TimeSeriesFlag] = []

        if len(sorted_periods) < self.config.min_periods_for_outlier:
            return flags, 0

        float_values = [float(values_by_period[p]) for p in sorted_periods]
        checks = len(float_values)

        mean = statistics.mean(float_values)
        stdev = statistics.stdev(float_values)

        if stdev < 1e-10:
            return flags, checks  # All values identical, no outliers

        for i, period in enumerate(sorted_periods):
            z_score = abs(float_values[i] - mean) / stdev
            if z_score > self.config.outlier_sigma:
                flags.append(TimeSeriesFlag(
                    check_type="outlier",
                    canonical_name=canonical_name,
                    period=period,
                    severity="warning",
                    message=(
                        f"{canonical_name} in period {period} is {z_score:.1f}σ "
                        f"from mean (threshold: {self.config.outlier_sigma}σ)"
                    ),
                    details={"z_score": round(z_score, 2), "mean": round(mean, 2),
                             "stdev": round(stdev, 2), "value": float_values[i]},
                ))

        return flags, checks

    def _check_gaps(
        self,
        all_sorted_periods: List[str],
        values_by_period: Dict[str, Decimal],
        canonical_name: str,
    ) -> Tuple[List[TimeSeriesFlag], int]:
        """Flag missing values in periods where the item should have data.

        Only flags gaps *between* the first and last period where the item
        has data (doesn't flag leading/trailing absence).
        """
        flags: List[TimeSeriesFlag] = []

        present = [p for p in all_sorted_periods if p in values_by_period]
        if len(present) < 2:
            return flags, 0

        first_idx = all_sorted_periods.index(present[0])
        last_idx = all_sorted_periods.index(present[-1])
        span = all_sorted_periods[first_idx:last_idx + 1]

        checks = len(span)
        for period in span:
            if period not in values_by_period:
                flags.append(TimeSeriesFlag(
                    check_type="gap",
                    canonical_name=canonical_name,
                    period=period,
                    severity="info",
                    message=f"{canonical_name} missing in period {period} (gap in series)",
                ))

        return flags, checks

    def _check_monotonicity(
        self,
        canonical_name: str,
        sorted_periods: List[str],
        values_by_period: Dict[str, Decimal],
    ) -> Tuple[List[TimeSeriesFlag], int]:
        """For cumulative items, values should be non-decreasing."""
        flags: List[TimeSeriesFlag] = []
        checks = 0

        for i in range(1, len(sorted_periods)):
            prev_p = sorted_periods[i - 1]
            curr_p = sorted_periods[i]
            checks += 1

            if values_by_period[curr_p] < values_by_period[prev_p]:
                flags.append(TimeSeriesFlag(
                    check_type="monotonicity",
                    canonical_name=canonical_name,
                    period=curr_p,
                    severity="warning",
                    message=(
                        f"{canonical_name} decreased from {values_by_period[prev_p]} "
                        f"to {values_by_period[curr_p]} between {prev_p} and {curr_p} "
                        f"(expected non-decreasing)"
                    ),
                ))

        return flags, checks

    # ------------------------------------------------------------------
    # Score computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_consistency_score(
        flags: List[TimeSeriesFlag], total_checks: int,
    ) -> float:
        """Compute consistency score from flags.

        Errors count 2x, warnings 1x, info 0.5x.
        Score = 1.0 - (weighted_flags / total_checks), clamped to [0, 1].
        """
        if total_checks == 0:
            return 1.0

        severity_weights = {"error": 2.0, "warning": 1.0, "info": 0.5}
        weighted_count = sum(
            severity_weights.get(f.severity, 1.0) for f in flags
        )
        score = 1.0 - (weighted_count / total_checks)
        return max(0.0, min(1.0, score))
