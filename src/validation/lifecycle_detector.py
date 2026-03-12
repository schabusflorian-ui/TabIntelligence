"""
Project Finance Lifecycle Detector

Detects lifecycle phases in multi-period financial data using multiple signals
(revenue, capex, debt drawdown, development costs, DSCR). Distinguishes project
finance models from corporate models and assigns 7 lifecycle phases.

Usage:
    from src.validation.lifecycle_detector import LifecycleDetector

    detector = LifecycleDetector()
    result = detector.detect(multi_period_data)
    print(result.phases)         # {"1.0": "construction", "2.0": "operations", ...}
    print(result.is_project_finance)  # True/False
"""

from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Dict, List, Set

from src.validation.utils import sort_periods

ZERO = Decimal("0")


@dataclass
class LifecycleResult:
    """Result of lifecycle phase detection."""

    phases: Dict[str, str]  # period -> phase name
    is_project_finance: bool
    confidence: float  # 0.0 to 1.0
    signals_used: List[str]  # e.g. ["revenue", "capex", "debt_drawdown"]


class LifecycleDetector:
    """Detects project finance lifecycle phases from multi-period data.

    7 phases (in temporal order):
        pre_construction  — planning phase: no revenue, no capex, but dev_costs or drawdown
        construction      — active capex, no revenue
        ramp_up           — first 1-3 periods with revenue below 50% of median operational
        operations        — steady-state positive revenue
        maintenance_shutdown — isolated zero-revenue dip within operational window
        tail              — last 1-2 declining periods (PF models only)
        post_operations   — after last period with revenue > 0

    Non-PF (corporate) models receive a simplified 3-phase mapping:
        construction / operations / post_operations
    """

    PF_INDICATORS: Set[str] = {
        "cfads",
        "cfae",
        "dscr",
        "llcr",
        "plcr",
        "debt_service",
        "equity_irr",
        "dsra_balance",
        "sculpted_debt_service",
        "equity_contribution",
        "development_costs",
        "total_investment",
    }

    # Signals we look for in the data
    _SIGNAL_NAMES = ["revenue", "capex", "debt_drawdown", "development_costs", "dscr"]

    def detect(
        self,
        multi_period_data: Dict[str, Dict[str, Decimal]],
    ) -> LifecycleResult:
        """Detect lifecycle phases from multi-period extracted data.

        Args:
            multi_period_data: {period_key: {canonical_name: Decimal, ...}, ...}

        Returns:
            LifecycleResult with phases, PF detection, confidence, and signals used.
        """
        if not multi_period_data:
            return LifecycleResult(
                phases={},
                is_project_finance=False,
                confidence=0.0,
                signals_used=[],
            )

        sorted_periods = sort_periods(list(multi_period_data.keys()))

        # Detect whether this is a project finance model
        is_pf, pf_indicator_count = self._detect_project_finance(multi_period_data)

        # Determine which signals have data
        signals_used = self._find_signals(multi_period_data)

        # Find operational window from revenue
        rev_values = {p: multi_period_data[p].get("revenue", ZERO) for p in sorted_periods}
        op_periods = [p for p in sorted_periods if rev_values.get(p, ZERO) > 0]

        if not op_periods:
            # No revenue data — can't determine phases
            return LifecycleResult(
                phases={},
                is_project_finance=is_pf,
                confidence=0.0,
                signals_used=signals_used,
            )

        if is_pf:
            phases = self._detect_pf_phases(
                sorted_periods,
                multi_period_data,
                op_periods,
                rev_values,
            )
        else:
            phases = self._detect_corporate_phases(
                sorted_periods,
                op_periods,
            )

        confidence = self._compute_confidence(signals_used, is_pf, pf_indicator_count)

        return LifecycleResult(
            phases=phases,
            is_project_finance=is_pf,
            confidence=confidence,
            signals_used=signals_used,
        )

    # ------------------------------------------------------------------
    # Project finance detection
    # ------------------------------------------------------------------

    def _detect_project_finance(
        self,
        multi_period_data: Dict[str, Dict[str, Decimal]],
    ) -> tuple[bool, int]:
        """Check if PF indicators are present across any period.

        Returns (is_project_finance, indicator_count).
        """
        found: Set[str] = set()
        for values in multi_period_data.values():
            for name in values:
                if name in self.PF_INDICATORS:
                    found.add(name)
        return len(found) >= 2, len(found)

    # ------------------------------------------------------------------
    # Signal discovery
    # ------------------------------------------------------------------

    def _find_signals(
        self,
        multi_period_data: Dict[str, Dict[str, Decimal]],
    ) -> List[str]:
        """Return list of signal names that have data in at least one period."""
        signals = []
        for sig in self._SIGNAL_NAMES:
            for values in multi_period_data.values():
                if sig in values:
                    signals.append(sig)
                    break
        return signals

    # ------------------------------------------------------------------
    # Corporate (non-PF) phase detection — backward-compatible 3-phase
    # ------------------------------------------------------------------

    def _detect_corporate_phases(
        self,
        sorted_periods: List[str],
        op_periods: List[str],
    ) -> Dict[str, str]:
        """Simple 3-phase detection matching the original heuristic."""
        first_op = op_periods[0]
        last_op = op_periods[-1]
        first_idx = sorted_periods.index(first_op)
        last_idx = sorted_periods.index(last_op)

        phases: Dict[str, str] = {}
        for i, period in enumerate(sorted_periods):
            if i < first_idx:
                phases[period] = "construction"
            elif i > last_idx:
                phases[period] = "post_operations"
            else:
                phases[period] = "operations"
        return phases

    # ------------------------------------------------------------------
    # Project finance 7-phase detection
    # ------------------------------------------------------------------

    def _detect_pf_phases(
        self,
        sorted_periods: List[str],
        multi_period_data: Dict[str, Dict[str, Decimal]],
        op_periods: List[str],
        rev_values: Dict[str, Decimal],
    ) -> Dict[str, str]:
        """Full 7-phase detection for project finance models."""
        first_op = op_periods[0]
        last_op = op_periods[-1]
        first_op_idx = sorted_periods.index(first_op)
        last_op_idx = sorted_periods.index(last_op)

        # Median operational revenue for ramp_up / tail detection
        op_revenues = [float(rev_values[p]) for p in op_periods if rev_values[p] > 0]
        median_rev = median(op_revenues) if op_revenues else 0.0
        ramp_threshold = median_rev * 0.5
        peak_rev = max(op_revenues) if op_revenues else 0.0
        tail_threshold = peak_rev * 0.5

        phases: Dict[str, str] = {}

        # --- Pre-operational periods (before first revenue) ---
        for i in range(first_op_idx):
            period = sorted_periods[i]
            data = multi_period_data.get(period, {})
            capex = abs(float(data.get("capex", ZERO)))
            dev_costs = abs(float(data.get("development_costs", ZERO)))
            drawdown = float(data.get("debt_drawdown", ZERO))

            if capex == 0 and dev_costs == 0 and drawdown > 0:
                phases[period] = "pre_construction"
            elif capex > 0 or dev_costs > 0:
                phases[period] = "construction"
            elif drawdown > 0:
                phases[period] = "pre_construction"
            else:
                # Default: if before first revenue and no signals, call it construction
                phases[period] = "construction"

        # --- Operational window (first_op to last_op inclusive) ---
        # First pass: identify ramp-up, maintenance_shutdown, tail candidates
        operational_indices = list(range(first_op_idx, last_op_idx + 1))

        for i in operational_indices:
            period = sorted_periods[i]
            rev = float(rev_values.get(period, 0))
            phases[period] = "operations"  # default

        # Detect ramp-up: first 1-3 periods with revenue < ramp_threshold
        if ramp_threshold > 0:
            ramp_count = 0
            for i in operational_indices:
                if ramp_count >= 3:
                    break
                period = sorted_periods[i]
                rev = float(rev_values.get(period, 0))
                if 0 < rev < ramp_threshold:
                    phases[period] = "ramp_up"
                    ramp_count += 1
                elif rev >= ramp_threshold:
                    break  # stop once we hit steady-state

        # Detect maintenance_shutdown: isolated zero-revenue within operational window
        for i in operational_indices:
            period = sorted_periods[i]
            rev = float(rev_values.get(period, 0))
            if rev <= 0 and i > first_op_idx and i < last_op_idx:
                # Check if flanked by positive revenue
                prev_rev = float(rev_values.get(sorted_periods[i - 1], 0))
                next_rev = (
                    float(rev_values.get(sorted_periods[i + 1], 0))
                    if i + 1 < len(sorted_periods)
                    else 0
                )
                if prev_rev > 0 or next_rev > 0:
                    phases[period] = "maintenance_shutdown"

        # Detect tail: last 1-2 periods with revenue declining < tail_threshold
        if tail_threshold > 0:
            tail_count = 0
            for i in reversed(operational_indices):
                if tail_count >= 2:
                    break
                period = sorted_periods[i]
                if phases[period] != "operations":
                    continue  # skip ramp_up / maintenance_shutdown
                rev = float(rev_values.get(period, 0))
                if 0 < rev < tail_threshold:
                    # Check declining vs previous period
                    if i > 0:
                        prev_rev = float(rev_values.get(sorted_periods[i - 1], 0))
                        if rev < prev_rev:
                            phases[period] = "tail"
                            tail_count += 1
                        else:
                            break  # not declining, stop
                    else:
                        break
                else:
                    break  # above threshold, stop

        # --- Post-operational periods ---
        for i in range(last_op_idx + 1, len(sorted_periods)):
            period = sorted_periods[i]
            phases[period] = "post_operations"

        return phases

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_confidence(
        signals_used: List[str],
        is_pf: bool,
        pf_indicator_count: int,
    ) -> float:
        """Confidence based on how many signals were available."""
        total_possible = 5  # revenue, capex, debt_drawdown, development_costs, dscr
        signal_score = len(signals_used) / total_possible
        if is_pf:
            # PF models get a boost from indicator count
            pf_boost = min(pf_indicator_count / 5, 1.0) * 0.2
            return min(signal_score * 0.8 + pf_boost, 1.0)
        return signal_score
