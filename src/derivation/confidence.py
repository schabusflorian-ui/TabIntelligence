"""
Confidence propagation for derived financial metrics.

Extracted values are uncertain observations — not point estimates.
When computing ratios and sums from them, uncertainty compounds.
This module provides principled confidence propagation and uncertainty bands.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple


# Heuristic: mapping confidence → approximate value uncertainty fraction.
# e.g., confidence=0.85 implies roughly ±8% value uncertainty.
# Calibrated to mapping method characteristics:
#   alias match (1.0)  → ±1%   (deterministic)
#   fuzzy (0.85-0.95)  → ±5%   (close enough)
#   claude (0.70-0.90) → ±10%  (interpretive)
def _confidence_to_uncertainty(confidence: float) -> float:
    """Convert mapping confidence to fractional value uncertainty."""
    if confidence >= 0.99:
        return 0.01
    elif confidence >= 0.90:
        return 0.03
    elif confidence >= 0.80:
        return 0.07
    elif confidence >= 0.70:
        return 0.12
    else:
        return 0.20


def propagate_confidence(
    input_confidences: List[float],
    mode: str,
    derivation_discount: float = 1.0,
) -> float:
    """Compute derived metric confidence from input confidences.

    Args:
        input_confidences: Confidence scores of each input canonical.
        mode: One of "min", "product", "weighted".
        derivation_discount: Additional discount for computational error risk.

    Returns:
        Propagated confidence in [0.0, 1.0].
    """
    if not input_confidences:
        return 0.0

    if mode == "min":
        # Conservative: weakest link determines overall quality
        conf = min(input_confidences)
    elif mode == "product":
        # Independent sources: uncertainty multiplies
        conf = 1.0
        for c in input_confidences:
            conf *= c
    elif mode == "weighted":
        # Simple average (weights not available here; use equal weights)
        conf = sum(input_confidences) / len(input_confidences)
    else:
        conf = min(input_confidences)

    return max(0.0, min(1.0, conf * derivation_discount))


def compute_uncertainty_band(
    value: Decimal,
    input_confidences: List[float],
    formula_type: str = "ratio",
) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """Compute lower and upper uncertainty bounds for a derived value.

    Uses error propagation: for a ratio A/B, fractional error ≈ √(σ_A² + σ_B²).
    For a difference A-B (near zero), the absolute error dominates.

    Args:
        value: The derived metric value.
        input_confidences: Confidence of each input.
        formula_type: "ratio" | "sum" | "difference" | "product_formula".

    Returns:
        (value_range_low, value_range_high) as Decimals, or (None, None) if
        inputs are too uncertain to bound meaningfully.
    """
    if not input_confidences or value is None:
        return None, None

    # Aggregate uncertainty across inputs
    uncertainties = [_confidence_to_uncertainty(c) for c in input_confidences]

    if formula_type == "ratio":
        # For A/B: σ_ratio/ratio ≈ √(σ_A² + σ_B²)
        combined = (sum(u * u for u in uncertainties)) ** 0.5
    elif formula_type in ("sum", "difference"):
        # Absolute errors add in quadrature; then express as fraction of total
        abs_val = abs(float(value))
        if abs_val < 1e-10:
            return None, None
        combined = (sum(u * u for u in uncertainties)) ** 0.5
    else:
        combined = max(uncertainties)

    band = Decimal(str(round(combined, 6)))
    low = value * (Decimal("1") - band)
    high = value * (Decimal("1") + band)

    # For ratios/metrics, keep bounds positive (ratio can't be negative)
    if value > 0:
        low = max(low, Decimal("0"))

    return low, high


def is_covenant_sensitive(
    value: Decimal,
    value_low: Optional[Decimal],
    value_high: Optional[Decimal],
    threshold: Optional[Decimal],
) -> Tuple[bool, Optional[Decimal]]:
    """Determine if a metric is within its uncertainty band of a covenant threshold.

    Args:
        value: Point estimate of the metric.
        value_low: Lower uncertainty bound.
        value_high: Upper uncertainty bound.
        threshold: Covenant threshold value (e.g., 1.25 for DSCR lock-up).

    Returns:
        (is_sensitive, headroom) where headroom = value - threshold.
        is_sensitive is True if the uncertainty band spans the threshold.
    """
    if threshold is None:
        return False, None

    headroom = value - threshold

    if value_low is None or value_high is None:
        # Can't determine sensitivity without bounds
        return False, headroom

    # Sensitive if the lower bound is below (or upper bound above) the threshold
    is_sens = (value_low < threshold < value_high) or (
        value > threshold and value_low < threshold
    )
    return is_sens, headroom
