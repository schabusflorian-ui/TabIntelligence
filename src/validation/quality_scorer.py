"""Composite quality scorer for extraction results.

Combines multiple quality signals (mapping confidence, validation success,
completeness, time-series consistency, cell reconciliation) into a single
trustworthiness score with letter grade and label.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DimensionScore:
    """Score for a single quality dimension."""

    name: str
    score: float  # 0.0 to 1.0
    weight: float  # relative weight in composite
    details: Optional[str] = None


@dataclass
class QualityResult:
    """Composite quality scoring result."""

    numeric_score: float  # 0.0 to 1.0
    letter_grade: str  # A, B, C, D, F
    label: str  # "trustworthy", "needs_review", "unreliable"
    dimensions: List[DimensionScore] = field(default_factory=list)
    model_type: Optional[str] = None

    @property
    def is_trustworthy(self) -> bool:
        return self.label == "trustworthy"

    def to_dict(self) -> Dict:
        d = {
            "numeric_score": round(self.numeric_score, 3),
            "letter_grade": self.letter_grade,
            "label": self.label,
            "dimensions": [
                {
                    "name": dim.name,
                    "score": round(dim.score, 3),
                    "weight": dim.weight,
                    "details": dim.details,
                }
                for dim in self.dimensions
            ],
        }
        if self.model_type:
            d["model_type"] = self.model_type
        return d


# Default quality dimension weights (5 dimensions)
DEFAULT_WEIGHTS: Dict[str, float] = {
    "mapping_confidence": 0.25,
    "validation_success": 0.20,
    "completeness": 0.20,
    "time_series_consistency": 0.15,
    "cell_reconciliation": 0.20,
}

# Model-type-specific weight sets
MODEL_TYPE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "corporate": {
        "mapping_confidence": 0.25,
        "validation_success": 0.20,
        "completeness": 0.20,
        "time_series_consistency": 0.15,
        "cell_reconciliation": 0.20,
    },
    "project_finance": {
        "mapping_confidence": 0.20,
        "validation_success": 0.25,
        "completeness": 0.15,
        "time_series_consistency": 0.20,
        "cell_reconciliation": 0.20,
    },
    "construction_only": {
        "mapping_confidence": 0.30,
        "validation_success": 0.15,
        "completeness": 0.25,
        "time_series_consistency": 0.10,
        "cell_reconciliation": 0.20,
    },
    "mixed": {
        "mapping_confidence": 0.20,
        "validation_success": 0.20,
        "completeness": 0.20,
        "time_series_consistency": 0.20,
        "cell_reconciliation": 0.20,
    },
    "saas": {
        "mapping_confidence": 0.20,
        "validation_success": 0.20,
        "completeness": 0.25,
        "time_series_consistency": 0.15,
        "cell_reconciliation": 0.20,
    },
}

# Grade thresholds (descending order checked)
GRADE_THRESHOLDS: List[tuple] = [
    ("A", 0.90),
    ("B", 0.75),
    ("C", 0.60),
    ("D", 0.40),
    ("F", 0.0),
]

# Label thresholds (descending order checked)
LABEL_THRESHOLDS: List[tuple] = [
    ("trustworthy", 0.80),
    ("needs_review", 0.55),
    ("unreliable", 0.0),
]


class QualityScorer:
    """Combines multiple quality signals into a composite score."""

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        model_type: Optional[str] = None,
        grade_thresholds: Optional[List[tuple]] = None,
        label_thresholds: Optional[List[tuple]] = None,
    ):
        if weights is not None:
            self.weights = weights
        elif model_type and model_type in MODEL_TYPE_WEIGHTS:
            self.weights = MODEL_TYPE_WEIGHTS[model_type]
        else:
            self.weights = DEFAULT_WEIGHTS
        self.model_type = model_type
        self.grade_thresholds = grade_thresholds or GRADE_THRESHOLDS
        self.label_thresholds = label_thresholds or LABEL_THRESHOLDS

    def score(
        self,
        mapping_confidence: float,
        validation_success_rate: float,
        completeness_score: float,
        time_series_consistency: float,
        cell_match_rate: Optional[float] = None,
        formula_mismatch_rate: Optional[float] = None,
    ) -> QualityResult:
        """Compute composite quality score.

        All inputs must be floats in [0.0, 1.0].
        cell_match_rate is optional for backward compatibility — when not
        provided, its weight is redistributed proportionally among the
        other 4 dimensions.
        formula_mismatch_rate is optional — if > 0.3, caps grade at "C".

        Returns:
            QualityResult with numeric score, letter grade, and label.
        """
        scores = {
            "mapping_confidence": max(0.0, min(1.0, mapping_confidence)),
            "validation_success": max(0.0, min(1.0, validation_success_rate)),
            "completeness": max(0.0, min(1.0, completeness_score)),
            "time_series_consistency": max(0.0, min(1.0, time_series_consistency)),
        }

        # Handle cell_reconciliation dimension
        effective_weights = dict(self.weights)
        if cell_match_rate is not None:
            scores["cell_reconciliation"] = max(0.0, min(1.0, cell_match_rate))
        elif "cell_reconciliation" in effective_weights:
            # Redistribute cell_reconciliation weight proportionally
            recon_weight = effective_weights.pop("cell_reconciliation")
            remaining = sum(effective_weights.values())
            if remaining > 0:
                for k in effective_weights:
                    effective_weights[k] += recon_weight * (effective_weights[k] / remaining)

        numeric = self._weighted_average(scores, effective_weights)
        grade = self._assign_grade(numeric)
        label = self._assign_label(numeric)

        # Grade floor: if cell_match_rate < 0.5, cap grade at "D"
        grade_rank = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        if cell_match_rate is not None and cell_match_rate < 0.5:
            if grade_rank.get(grade, 0) > grade_rank["D"]:
                grade = "D"

        # Grade floor: if formula_mismatch_rate > 0.3, cap grade at "C"
        if formula_mismatch_rate is not None and formula_mismatch_rate > 0.3:
            if grade_rank.get(grade, 0) > grade_rank["C"]:
                grade = "C"

        dimensions = [
            DimensionScore(
                name=name,
                score=value,
                weight=effective_weights.get(name, 0.0),
            )
            for name, value in scores.items()
        ]

        return QualityResult(
            numeric_score=numeric,
            letter_grade=grade,
            label=label,
            dimensions=dimensions,
            model_type=self.model_type,
        )

    def _weighted_average(
        self,
        scores: Dict[str, float],
        weights: Optional[Dict[str, float]] = None,
    ) -> float:
        """Compute weighted average from dimension scores."""
        w = weights if weights is not None else self.weights
        total_weight = sum(w.get(k, 0.0) for k in scores)
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(scores[k] * w.get(k, 0.0) for k in scores)
        return weighted_sum / total_weight

    def _assign_grade(self, score: float) -> str:
        """Map numeric score to letter grade."""
        for grade, threshold in self.grade_thresholds:
            if score >= threshold:
                return grade
        return "F"

    def _assign_label(self, score: float) -> str:
        """Map numeric score to quality label."""
        for label, threshold in self.label_thresholds:
            if score >= threshold:
                return label
        return "unreliable"
