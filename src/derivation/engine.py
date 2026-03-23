"""
Stage 6 Derivation Engine

Computes derived financial metrics from extracted facts using the
declarative DerivationRule registry.  Runs after validation (Stage 4/5)
in a multi-pass DAG so that derived values can themselves be inputs to
further derivations (e.g. net_debt → net_debt_to_ebitda).

Responsibilities:
  1. Gap-filling  — compute metrics absent from the source Excel
  2. Consistency  — compare extracted vs. computed when both are available
  3. Uncertainty  — attach confidence bounds and covenant sensitivity flags
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from src.derivation.confidence import (
    compute_uncertainty_band,
    is_covenant_sensitive,
    propagate_confidence,
)
from src.derivation.rules import DerivationRule, get_rules_for_model_type

logger = logging.getLogger(__name__)

# Minimum input confidence required to attempt gap-filling
MIN_GAP_FILL_CONFIDENCE = 0.60
# Minimum input confidence required for consistency check
MIN_CONSISTENCY_CHECK_CONFIDENCE = 0.75
# Minimum extracted confidence threshold below which we supplement with computed
LOW_EXTRACTION_CONFIDENCE = 0.70


@dataclass
class CovenantContext:
    threshold: Optional[Decimal] = None
    headroom: Optional[Decimal] = None
    headroom_range_low: Optional[Decimal] = None
    headroom_range_high: Optional[Decimal] = None
    is_sensitive: bool = False
    flag_message: Optional[str] = None


@dataclass
class ConsistencyResult:
    extracted_value: Optional[Decimal]
    computed_value: Decimal
    divergence_pct: Optional[float]   # None if no extracted value
    passed: bool
    threshold_pct: float


@dataclass
class DerivedFact:
    """A single derived financial metric for one canonical name and period."""
    canonical_name: str
    period: str
    computed_value: Decimal
    confidence: float
    value_range_low: Optional[Decimal]
    value_range_high: Optional[Decimal]
    computation_rule_id: str
    formula: str
    source_canonicals: List[str]
    confidence_mode: str
    derivation_pass: int
    # Set when a metric is also extracted (for consistency check)
    consistency: Optional[ConsistencyResult] = None
    covenant: Optional[CovenantContext] = None
    # Whether this fills a gap (True) or supplements / consistency-checks (False)
    is_gap_fill: bool = True


class DerivationEngine:
    """
    Derives financial metrics from extracted facts.

    Usage:
        engine = DerivationEngine()
        derived = engine.run(
            extracted={"revenue": {"2023": Decimal("1000000"), ...}, ...},
            confidences={"revenue": {"2023": 0.95}, ...},
            model_type="corporate",
        )
    """

    def run(
        self,
        extracted: Dict[str, Dict[str, Decimal]],
        confidences: Dict[str, Dict[str, float]],
        model_type: Optional[str] = None,
    ) -> List[DerivedFact]:
        """
        Run the derivation engine over all periods.

        Args:
            extracted: {canonical_name: {period: value}}
            confidences: {canonical_name: {period: confidence_score}}
            model_type: Detected model type (corporate / project_finance / etc.)

        Returns:
            List of DerivedFact objects (one per canonical × period).
        """
        rules = get_rules_for_model_type(model_type)
        # Collect periods from all extracted data
        all_periods: set = set()
        for period_map in extracted.values():
            all_periods.update(period_map.keys())

        results: List[DerivedFact] = []

        # Multi-pass: work through rules in priority order (already sorted).
        # After each derivation we add the new value to `working_extracted` so
        # later rules can use it as input.
        working = {cn: dict(per_map) for cn, per_map in extracted.items()}
        working_conf = {cn: dict(per_map) for cn, per_map in confidences.items()}

        # Group rules by priority for pass tracking
        max_priority = max((r.priority for r in rules), default=1)

        for pass_num in range(1, max_priority + 1):
            pass_rules = [r for r in rules if r.priority == pass_num]
            for rule in pass_rules:
                for period in sorted(all_periods):
                    fact = self._apply_rule(
                        rule=rule,
                        period=period,
                        working=working,
                        working_conf=working_conf,
                        derivation_pass=pass_num,
                    )
                    if fact is None:
                        continue

                    results.append(fact)

                    # Make this value available for subsequent passes
                    # Only add to working if it fills a gap (don't replace a
                    # high-confidence extraction with a lower-confidence derived value)
                    existing = working.get(rule.target, {}).get(period)
                    existing_conf = working_conf.get(rule.target, {}).get(period, 0.0)
                    if existing is None or existing_conf < LOW_EXTRACTION_CONFIDENCE:
                        working.setdefault(rule.target, {})[period] = fact.computed_value
                        working_conf.setdefault(rule.target, {})[period] = fact.confidence

        return results

    def _apply_rule(
        self,
        rule: DerivationRule,
        period: str,
        working: Dict[str, Dict[str, Decimal]],
        working_conf: Dict[str, Dict[str, float]],
        derivation_pass: int,
    ) -> Optional[DerivedFact]:
        """Apply one derivation rule for one period.  Returns None to skip."""
        # Collect input values and confidences
        input_values: Dict[str, Decimal] = {}
        input_confs: List[float] = []
        for inp in rule.inputs:
            val = working.get(inp, {}).get(period)
            if val is None:
                return None  # Can't compute — missing input
            conf = working_conf.get(inp, {}).get(period, 0.5)
            input_values[inp] = val
            input_confs.append(conf)

        min_conf = min(input_confs) if input_confs else 0.0
        # Decide what to do with this rule for this period
        existing_val = working.get(rule.target, {}).get(period)
        existing_conf = working_conf.get(rule.target, {}).get(period, 0.0)

        if existing_val is not None:
            # Target already extracted
            if existing_conf >= LOW_EXTRACTION_CONFIDENCE:
                if min_conf < MIN_CONSISTENCY_CHECK_CONFIDENCE:
                    return None  # Inputs not good enough for a meaningful consistency check
                mode = "consistency_check"
            else:
                # Low-confidence extraction — supplement with computed
                if min_conf < MIN_GAP_FILL_CONFIDENCE:
                    return None
                mode = "supplement"
        else:
            # Gap fill
            if min_conf < MIN_GAP_FILL_CONFIDENCE:
                return None
            mode = "gap_fill"

        # Compute value
        computed = self._evaluate_formula(rule, input_values)
        if computed is None:
            return None

        # Propagate confidence
        propagated_conf = propagate_confidence(
            input_confs,
            mode=rule.confidence_mode,
            derivation_discount=rule.derivation_discount,
        )

        # Determine formula type for uncertainty band
        formula_type = self._infer_formula_type(rule.formula)

        # Uncertainty band
        val_low, val_high = compute_uncertainty_band(
            computed, input_confs, formula_type=formula_type
        )

        # Consistency check
        consistency = None
        if mode in ("consistency_check", "supplement") and existing_val is not None:
            divisor = float(max(abs(existing_val), abs(computed), Decimal("0.001")))
            div_pct = abs(float(existing_val - computed)) / divisor
            threshold = rule.consistency_threshold
            consistency = ConsistencyResult(
                extracted_value=existing_val,
                computed_value=computed,
                divergence_pct=div_pct,
                passed=div_pct <= threshold,
                threshold_pct=threshold,
            )
            if not consistency.passed:
                logger.warning(
                    "Derivation consistency check failed: %s period=%s "
                    "extracted=%.4f computed=%.4f divergence=%.1f%%",
                    rule.target, period,
                    float(existing_val), float(computed), div_pct * 100,
                )

        # Covenant context (for DSCR, coverage metrics)
        covenant = self._build_covenant_context(
            rule=rule,
            computed=computed,
            val_low=val_low,
            val_high=val_high,
            working=working,
            period=period,
        )

        return DerivedFact(
            canonical_name=rule.target,
            period=period,
            computed_value=computed,
            confidence=propagated_conf,
            value_range_low=val_low,
            value_range_high=val_high,
            computation_rule_id=rule.id,
            formula=rule.formula,
            source_canonicals=rule.inputs,
            confidence_mode=rule.confidence_mode,
            derivation_pass=derivation_pass,
            consistency=consistency,
            covenant=covenant,
            is_gap_fill=(mode == "gap_fill"),
        )

    def _evaluate_formula(
        self,
        rule: DerivationRule,
        inputs: Dict[str, Decimal],
    ) -> Optional[Decimal]:
        """Evaluate the rule formula using the provided input values."""
        # We evaluate only known safe formula patterns.
        # Patterns supported: A - B, A + B, A / B, A * B, A / B * C
        formula = rule.formula.strip()

        # Try to build an evaluation environment
        try:
            return self._safe_eval(formula, inputs)
        except Exception as exc:
            logger.debug("Formula eval error for %s: %s", rule.id, exc)
            return None

    def _safe_eval(self, formula: str, inputs: Dict[str, Decimal]) -> Optional[Decimal]:
        """Safely evaluate a simple financial formula string.

        Supports: A - B, A + B, A / B, A * B, A / B * C.
        Does NOT use eval() — parses left to right for known operators.
        """
        # Tokenise: split on operators while keeping operator tokens
        import re
        tokens = re.split(r'\s*([\+\-\*/])\s*', formula)
        tokens = [t.strip() for t in tokens if t.strip()]

        if not tokens:
            return None

        def resolve(t: str) -> Optional[Decimal]:
            # Direct variable reference
            if t in inputs:
                return inputs[t]
            # Numeric literal
            try:
                return Decimal(t)
            except (ValueError, InvalidOperation):
                return None

        if len(tokens) == 1:
            return resolve(tokens[0])

        # Build left-to-right evaluation
        # tokens = [val, op, val, op, val, ...]
        result = resolve(tokens[0])
        if result is None:
            return None

        i = 1
        while i < len(tokens) - 1:
            op = tokens[i]
            rhs = resolve(tokens[i + 1])
            if rhs is None:
                return None
            try:
                if op == "+":
                    result = result + rhs
                elif op == "-":
                    result = result - rhs
                elif op == "*":
                    result = result * rhs
                elif op == "/":
                    if rhs == 0:
                        return None
                    result = result / rhs
                else:
                    return None
            except (DivisionByZero, InvalidOperation):
                return None
            i += 2

        return result

    @staticmethod
    def _infer_formula_type(formula: str) -> str:
        """Heuristically classify formula type for uncertainty band calculation."""
        if "/" in formula and "+" not in formula and "-" not in formula:
            return "ratio"
        if "-" in formula and "/" not in formula and "*" not in formula:
            return "difference"
        if "+" in formula and "/" not in formula and "*" not in formula:
            return "sum"
        return "ratio"  # default

    def _build_covenant_context(
        self,
        rule: DerivationRule,
        computed: Decimal,
        val_low: Optional[Decimal],
        val_high: Optional[Decimal],
        working: Dict[str, Dict[str, Decimal]],
        period: str,
    ) -> Optional[CovenantContext]:
        """Build covenant context for coverage/leverage metrics."""
        # Only applicable for coverage metrics where a lock-up/covenant is known
        threshold_canonical: Optional[str] = None
        if rule.target in ("dscr_project_finance", "dscr_corporate", "dscr"):
            threshold_canonical = "distribution_lock_up"
        elif rule.target == "debt_to_ebitda":
            threshold_canonical = "leverage_covenant_level"
        elif rule.target in ("interest_coverage", "fixed_charge_coverage"):
            threshold_canonical = "coverage_covenant_level"

        if threshold_canonical is None:
            return None

        threshold_val = working.get(threshold_canonical, {}).get(period)
        if threshold_val is None:
            return None

        sensitive, headroom = is_covenant_sensitive(
            computed, val_low, val_high, threshold_val
        )

        # Headroom range from uncertainty bands
        hr_low = val_low - threshold_val if val_low is not None else None
        hr_high = val_high - threshold_val if val_high is not None else None

        flag_msg: Optional[str] = None
        if headroom is not None and headroom < 0:
            flag_msg = (
                f"COVENANT BREACH: {rule.target} ({float(computed):.3f}x)"
                f" < threshold ({float(threshold_val):.3f}x)"
                f" by {abs(float(headroom)):.3f}x"
            )
        elif sensitive:
            flag_msg = (
                f"COVENANT SENSITIVE: {rule.target} ({float(computed):.3f}x)"
                f" — uncertainty band spans threshold ({float(threshold_val):.3f}x)"
            )

        return CovenantContext(
            threshold=threshold_val,
            headroom=headroom,
            headroom_range_low=hr_low,
            headroom_range_high=hr_high,
            is_sensitive=sensitive,
            flag_message=flag_msg,
        )


def run_derivation(
    extracted_facts: List[Dict],
    model_type: Optional[str] = None,
) -> List[DerivedFact]:
    """
    Convenience wrapper used by Stage 6 pipeline.

    Args:
        extracted_facts: List of dicts with keys:
            canonical_name, period, value, confidence
        model_type: Detected model type string

    Returns:
        List of DerivedFact objects
    """
    # Reshape flat list → nested {canonical: {period: value}} dicts
    extracted: Dict[str, Dict[str, Decimal]] = {}
    confidences: Dict[str, Dict[str, float]] = {}

    for fact in extracted_facts:
        cn = fact.get("canonical_name")
        period = fact.get("period")
        value = fact.get("value")
        conf = fact.get("confidence") or 0.5

        if cn is None or period is None or value is None:
            continue

        try:
            dec_val = Decimal(str(value)) if not isinstance(value, Decimal) else value
        except (ValueError, InvalidOperation):
            continue

        extracted.setdefault(cn, {})[period] = dec_val
        confidences.setdefault(cn, {})[period] = float(conf)

    engine = DerivationEngine()
    return engine.run(extracted, confidences, model_type=model_type)
