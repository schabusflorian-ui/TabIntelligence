"""Cross-entity anomaly detection using IQR and Z-score methods.

Lightweight outlier detection for financial data. No ML dependencies —
uses Python's statistics stdlib. Designed for comparing the same
canonical metric across multiple entities.
"""

import statistics
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class AnomalyResult:
    """Result of anomaly detection for a single entity value."""

    entity_id: str
    entity_name: Optional[str]
    value: float
    is_outlier: bool
    z_score: Optional[float]
    iqr_distance: Optional[float]
    direction: Optional[str]  # "high" or "low"
    peer_mean: float
    peer_median: float
    peer_count: int


def detect_iqr_anomalies(
    values: List[Tuple[str, Optional[str], float]],
    threshold: float = 1.5,
) -> List[AnomalyResult]:
    """Detect outliers using Interquartile Range method.

    Args:
        values: List of (entity_id, entity_name, value) tuples
        threshold: IQR multiplier for outlier boundary (default 1.5)

    Returns:
        List of AnomalyResult, one per input value
    """
    if len(values) < 3:
        return []

    amounts = sorted(v[2] for v in values)
    n = len(amounts)
    q1 = amounts[n // 4]
    q3 = amounts[(3 * n) // 4]
    iqr = q3 - q1

    lower = q1 - threshold * iqr
    upper = q3 + threshold * iqr
    mean_val = statistics.mean(amounts)
    median_val = statistics.median(amounts)

    results = []
    for entity_id, entity_name, value in values:
        is_outlier = value < lower or value > upper
        direction = None
        iqr_dist = None
        if iqr > 0:
            if value < lower:
                direction = "low"
                iqr_dist = round((lower - value) / iqr, 4)
            elif value > upper:
                direction = "high"
                iqr_dist = round((value - upper) / iqr, 4)

        results.append(
            AnomalyResult(
                entity_id=entity_id,
                entity_name=entity_name,
                value=value,
                is_outlier=is_outlier,
                z_score=None,
                iqr_distance=iqr_dist,
                direction=direction,
                peer_mean=round(mean_val, 4),
                peer_median=round(median_val, 4),
                peer_count=n,
            )
        )

    return results


def detect_zscore_anomalies(
    values: List[Tuple[str, Optional[str], float]],
    threshold: float = 2.0,
) -> List[AnomalyResult]:
    """Detect outliers using Z-score method.

    Args:
        values: List of (entity_id, entity_name, value) tuples
        threshold: Z-score threshold for outlier detection (default 2.0)

    Returns:
        List of AnomalyResult, one per input value
    """
    if len(values) < 3:
        return []

    amounts = [v[2] for v in values]
    mean_val = statistics.mean(amounts)
    stdev_val = statistics.stdev(amounts) if len(amounts) > 1 else 0
    median_val = statistics.median(amounts)

    results = []
    for entity_id, entity_name, value in values:
        z = (value - mean_val) / stdev_val if stdev_val > 0 else 0.0
        is_outlier = abs(z) > threshold
        direction = None
        if z > threshold:
            direction = "high"
        elif z < -threshold:
            direction = "low"

        results.append(
            AnomalyResult(
                entity_id=entity_id,
                entity_name=entity_name,
                value=value,
                is_outlier=is_outlier,
                z_score=round(z, 4),
                iqr_distance=None,
                direction=direction,
                peer_mean=round(mean_val, 4),
                peer_median=round(median_val, 4),
                peer_count=len(amounts),
            )
        )

    return results
