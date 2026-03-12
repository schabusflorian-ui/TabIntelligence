"""Composite quality scorer for extraction results.

Combines multiple quality signals (mapping confidence, validation success,
completeness, time-series consistency) into a single trustworthiness score
with letter grade and label.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DimensionScore:
    """Score for a single quality dimension."""
    name: str
    score: float         # 0.0 to 1.0
    weight: float        # relative weight in composite
    details: Optional[str] = None


@dataclass
class QualityResult:
    """Composite quality scoring result."""
    numeric_score: float          # 0.0 to 1.0
    letter_grade: str             # A, B, C, D, F
    label: str                    # "trustworthy", "needs_review", "unreliable"
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


# Default quality dimension weights
DEFAULT_WEIGHTS: Dict[str, float] = {
    "mapping_confidence": 0.30,
    "validation_success": 0.25,
    "completeness": 0.25,
    "time_series_consistency": 0.20,
}

# Model-type-specific weight sets
MODEL_TYPE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "corporate": {
        "mapping_confidence": 0.30,
        "validation_success": 0.25,
        "completeness": 0.25,
        "time_series_consistency": 0.20,
    },
    "project_finance": {
        "mapping_confidence": 0.25,
        "validation_success": 0.30,
        "completeness": 0.20,
        "time_series_consistency": 0.25,
    },
    "construction_only": {
        "mapping_confidence": 0.35,
        "validation_success": 0.20,
        "completeness": 0.30,
        "time_series_consistency": 0.15,
    },
    "mixed": {
        "mapping_confidence": 0.25,
        "validation_success": 0.25,
        "completeness": 0.25,
        "time_series_consistency": 0.25,
    },
    "saas": {
        "mapping_confidence": 0.25,
        "validation_success": 0.25,
        "completeness": 0.30,
        "time_series_consistency": 0.20,
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
    ) -> QualityResult:
        """Compute composite quality score.

        All inputs must be floats in [0.0, 1.0].

        Returns:
            QualityResult with numeric score, letter grade, and label.
        """
        scores = {
            "mapping_confidence": max(0.0, min(1.0, mapping_confidence)),
            "validation_success": max(0.0, min(1.0, validation_success_rate)),
            "completeness": max(0.0, min(1.0, completeness_score)),
            "time_series_consistency": max(0.0, min(1.0, time_series_consistency)),
        }

        numeric = self._weighted_average(scores)
        grade = self._assign_grade(numeric)
        label = self._assign_label(numeric)

        dimensions = [
            DimensionScore(
                name=name,
                score=value,
                weight=self.weights.get(name, 0.0),
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

    def _weighted_average(self, scores: Dict[str, float]) -> float:
        """Compute weighted average from dimension scores."""
        total_weight = sum(self.weights.get(k, 0.0) for k in scores)
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(
            scores[k] * self.weights.get(k, 0.0) for k in scores
        )
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
