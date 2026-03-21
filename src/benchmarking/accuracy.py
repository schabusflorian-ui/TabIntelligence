"""
Extraction accuracy measurement engine.

Provides precision/recall/F1 for mapping accuracy, value accuracy metrics
(exact match, tolerance match, MAE/MAPE), and per-stage error attribution
using lineage data.

Usage:
    from src.benchmarking.accuracy import (
        evaluate_mapping_accuracy,
        evaluate_value_accuracy,
        evaluate_triage_accuracy,
        attribute_errors_to_stages,
        run_full_evaluation,
    )

    result = run_full_evaluation(extraction_result, gold_standard)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data classes for structured results
# ---------------------------------------------------------------------------

@dataclass
class MappingAccuracyResult:
    """Precision/recall/F1 for label-to-canonical mapping."""
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    unmapped_count: int = 0
    total_expected: int = 0
    total_actual: int = 0

    # Per-item details
    correct: list = field(default_factory=list)
    mismatches: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    unexpected: list = field(default_factory=list)

    # Per-category breakdown
    per_category: dict = field(default_factory=dict)
    # Per-sheet breakdown
    per_sheet: dict = field(default_factory=dict)

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def accuracy(self) -> float:
        """Simple accuracy: correct / total expected."""
        return self.true_positives / self.total_expected if self.total_expected > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "accuracy": round(self.accuracy, 4),
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "unmapped_count": self.unmapped_count,
            "total_expected": self.total_expected,
            "total_actual": self.total_actual,
            "mismatches": self.mismatches,
            "missing": self.missing,
            "per_category": self.per_category,
            "per_sheet": self.per_sheet,
        }


@dataclass
class ValueAccuracyResult:
    """Numeric value accuracy metrics."""
    exact_matches: int = 0
    tolerance_matches: int = 0
    total_compared: int = 0
    total_expected: int = 0
    errors: list = field(default_factory=list)

    # Error distributions
    absolute_errors: list = field(default_factory=list)
    percentage_errors: list = field(default_factory=list)

    @property
    def exact_match_rate(self) -> float:
        return self.exact_matches / self.total_compared if self.total_compared > 0 else 0.0

    @property
    def tolerance_match_rate(self) -> float:
        return self.tolerance_matches / self.total_compared if self.total_compared > 0 else 0.0

    @property
    def mae(self) -> float:
        """Mean Absolute Error."""
        if not self.absolute_errors:
            return 0.0
        return sum(self.absolute_errors) / len(self.absolute_errors)

    @property
    def mape(self) -> float:
        """Mean Absolute Percentage Error."""
        if not self.percentage_errors:
            return 0.0
        return sum(self.percentage_errors) / len(self.percentage_errors)

    def to_dict(self) -> dict:
        return {
            "exact_match_rate": round(self.exact_match_rate, 4),
            "tolerance_match_rate": round(self.tolerance_match_rate, 4),
            "mae": round(self.mae, 4),
            "mape": round(self.mape, 4),
            "exact_matches": self.exact_matches,
            "tolerance_matches": self.tolerance_matches,
            "total_compared": self.total_compared,
            "total_expected": self.total_expected,
            "errors": self.errors[:20],  # Limit to first 20 for readability
        }


@dataclass
class StageAttributionResult:
    """Per-stage error attribution using lineage data."""
    parsing_errors: int = 0
    triage_errors: int = 0
    mapping_errors: int = 0
    enhanced_mapping_errors: int = 0
    validation_errors: int = 0
    total_errors: int = 0

    details: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "parsing_errors": self.parsing_errors,
            "triage_errors": self.triage_errors,
            "mapping_errors": self.mapping_errors,
            "enhanced_mapping_errors": self.enhanced_mapping_errors,
            "validation_errors": self.validation_errors,
            "total_errors": self.total_errors,
            "attribution": {
                "parsing_pct": round(self.parsing_errors / max(self.total_errors, 1) * 100, 1),
                "triage_pct": round(self.triage_errors / max(self.total_errors, 1) * 100, 1),
                "mapping_pct": round(self.mapping_errors / max(self.total_errors, 1) * 100, 1),
                "enhanced_mapping_pct": round(self.enhanced_mapping_errors / max(self.total_errors, 1) * 100, 1),
                "validation_pct": round(self.validation_errors / max(self.total_errors, 1) * 100, 1),
            },
            "details": self.details[:30],
        }


@dataclass
class TriageAccuracyResult:
    """Triage tier accuracy."""
    correct: int = 0
    total: int = 0
    details: list = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "accuracy": round(self.accuracy, 4),
            "correct": self.correct,
            "total": self.total,
            "details": self.details,
        }


@dataclass
class FullEvaluationResult:
    """Complete evaluation result combining all metrics."""
    mapping: MappingAccuracyResult = field(default_factory=MappingAccuracyResult)
    values: ValueAccuracyResult = field(default_factory=ValueAccuracyResult)
    triage: TriageAccuracyResult = field(default_factory=TriageAccuracyResult)
    stage_attribution: StageAttributionResult = field(default_factory=StageAttributionResult)

    def to_dict(self) -> dict:
        return {
            "mapping": self.mapping.to_dict(),
            "values": self.values.to_dict(),
            "triage": self.triage.to_dict(),
            "stage_attribution": self.stage_attribution.to_dict(),
            "summary": {
                "mapping_f1": round(self.mapping.f1, 4),
                "mapping_precision": round(self.mapping.precision, 4),
                "mapping_recall": round(self.mapping.recall, 4),
                "value_tolerance_match": round(self.values.tolerance_match_rate, 4),
                "triage_accuracy": round(self.triage.accuracy, 4),
            },
        }


# ---------------------------------------------------------------------------
# Evaluation functions
# ---------------------------------------------------------------------------

def evaluate_triage_accuracy(
    extraction_result: dict,
    gold: dict,
) -> TriageAccuracyResult:
    """Compare triage results against gold standard tiers."""
    actual_triage = {t["sheet_name"]: t for t in extraction_result.get("triage", [])}
    expected_triage = gold.get("expected_triage", [])

    result = TriageAccuracyResult(total=len(expected_triage))

    for exp in expected_triage:
        sheet = exp["sheet_name"]
        exp_tier = exp["tier"]
        actual = actual_triage.get(sheet, {})
        act_tier = actual.get("tier")

        is_correct = act_tier == exp_tier
        if is_correct:
            result.correct += 1

        result.details.append({
            "sheet_name": sheet,
            "expected_tier": exp_tier,
            "actual_tier": act_tier,
            "correct": is_correct,
        })

    return result


def evaluate_mapping_accuracy(
    extraction_result: dict,
    gold: dict,
) -> MappingAccuracyResult:
    """Evaluate mapping accuracy with precision/recall/F1.

    Uses gold standard expected_mappings and acceptable_alternatives.
    Computes per-category and per-sheet breakdowns.
    """
    # Build actual mapping lookup: label -> {canonical_name, sheet, ...}
    actual_items = {}
    for item in extraction_result.get("line_items", []):
        label = item.get("original_label", "")
        if label and label not in actual_items:
            actual_items[label] = {
                "canonical_name": item.get("canonical_name", "unmapped"),
                "sheet": item.get("sheet", ""),
                "confidence": item.get("confidence", 0),
                "provenance": item.get("provenance", {}),
            }

    expected_mappings = gold.get("expected_mappings", [])
    acceptable_alts = gold.get("acceptable_alternatives", {})

    result = MappingAccuracyResult(
        total_expected=len(expected_mappings),
        total_actual=len([v for v in actual_items.values() if v["canonical_name"] != "unmapped"]),
    )

    # Track which actual labels are accounted for
    matched_labels = set()

    for exp in expected_mappings:
        label = exp["original_label"]
        exp_canonical = exp["canonical_name"]
        sheet = exp.get("sheet", "Unknown")
        actual = actual_items.get(label)

        # Init per-sheet tracking
        if sheet not in result.per_sheet:
            result.per_sheet[sheet] = {
                "true_positives": 0, "false_positives": 0, "false_negatives": 0,
                "total": 0, "precision": 0, "recall": 0, "f1": 0,
            }
        result.per_sheet[sheet]["total"] += 1

        if actual is None or actual["canonical_name"] == "unmapped":
            # Expected mapping not found or unmapped → false negative
            result.false_negatives += 1
            result.unmapped_count += 1
            result.missing.append({
                "label": label,
                "expected": exp_canonical,
                "sheet": sheet,
            })
            result.per_sheet[sheet]["false_negatives"] += 1
            continue

        matched_labels.add(label)
        act_canonical = actual["canonical_name"]

        # Check if actual matches expected or acceptable alternative
        alts = acceptable_alts.get(exp_canonical, [exp_canonical])
        if act_canonical in alts:
            result.true_positives += 1
            result.correct.append({
                "label": label,
                "canonical_name": act_canonical,
                "sheet": sheet,
            })
            result.per_sheet[sheet]["true_positives"] += 1
        else:
            result.false_positives += 1
            result.false_negatives += 1
            result.mismatches.append({
                "label": label,
                "expected": exp_canonical,
                "actual": act_canonical,
                "acceptable": alts,
                "sheet": sheet,
            })
            result.per_sheet[sheet]["false_positives"] += 1
            result.per_sheet[sheet]["false_negatives"] += 1

    # Compute per-sheet metrics
    for sheet, stats in result.per_sheet.items():
        tp = stats["true_positives"]
        fp = stats["false_positives"]
        fn = stats["false_negatives"]
        stats["precision"] = round(tp / (tp + fp) if (tp + fp) > 0 else 0.0, 4)
        stats["recall"] = round(tp / (tp + fn) if (tp + fn) > 0 else 0.0, 4)
        p, r = stats["precision"], stats["recall"]
        stats["f1"] = round(2 * p * r / (p + r) if (p + r) > 0 else 0.0, 4)

    # Per-category breakdown (group by taxonomy category from gold standard)
    _compute_per_category(result, expected_mappings, actual_items, acceptable_alts)

    return result


def _compute_per_category(
    result: MappingAccuracyResult,
    expected_mappings: list,
    actual_items: dict,
    acceptable_alts: dict,
) -> None:
    """Compute accuracy per taxonomy category."""
    # Group expected mappings by sheet (proxy for category)
    categories = {}
    for exp in expected_mappings:
        sheet = exp.get("sheet", "Unknown")
        # Map sheet names to standard categories
        cat = _sheet_to_category(sheet)
        categories.setdefault(cat, {"tp": 0, "fp": 0, "fn": 0, "total": 0})
        categories[cat]["total"] += 1

        label = exp["original_label"]
        exp_canonical = exp["canonical_name"]
        actual = actual_items.get(label)

        if actual is None or actual["canonical_name"] == "unmapped":
            categories[cat]["fn"] += 1
            continue

        alts = acceptable_alts.get(exp_canonical, [exp_canonical])
        if actual["canonical_name"] in alts:
            categories[cat]["tp"] += 1
        else:
            categories[cat]["fp"] += 1
            categories[cat]["fn"] += 1

    for cat, stats in categories.items():
        tp, fp, fn = stats["tp"], stats["fp"], stats["fn"]
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        result.per_category[cat] = {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "total": stats["total"],
            "true_positives": tp,
        }


def _sheet_to_category(sheet_name: str) -> str:
    """Map sheet names to standard taxonomy categories."""
    name = sheet_name.lower()
    if "income" in name or "p&l" in name or "profit" in name:
        return "income_statement"
    if "balance" in name:
        return "balance_sheet"
    if "cash" in name:
        return "cash_flow"
    if "debt" in name:
        return "debt_schedule"
    if "working capital" in name:
        return "working_capital"
    if "assumption" in name:
        return "assumptions"
    return "other"


def evaluate_value_accuracy(
    extraction_result: dict,
    gold: dict,
) -> ValueAccuracyResult:
    """Evaluate numeric value accuracy against gold standard expected_values.

    Checks exact matches and tolerance-based matches. Computes MAE and MAPE.
    """
    expected_values = gold.get("expected_values", {})
    if not expected_values:
        return ValueAccuracyResult()

    # Build actual values lookup: canonical_name -> {period: value}
    actual_values: dict[str, dict[str, float | None]] = {}
    for item in extraction_result.get("line_items", []):
        canonical = item.get("canonical_name", "unmapped")
        if canonical == "unmapped":
            continue
        vals = item.get("values", {})
        if vals:
            actual_values[canonical] = vals

    result = ValueAccuracyResult()

    for canonical, periods in expected_values.items():
        for period, spec in periods.items():
            result.total_expected += 1
            expected_val = spec["value"] if isinstance(spec, dict) else spec
            tol_pct = spec.get("tolerance_pct", 1.0) if isinstance(spec, dict) else 1.0
            tol_abs = spec.get("tolerance_abs", 0.5) if isinstance(spec, dict) else 0.5

            actual_val = actual_values.get(canonical, {}).get(period)

            if actual_val is None:
                result.errors.append({
                    "canonical_name": canonical,
                    "period": period,
                    "expected": expected_val,
                    "actual": None,
                    "error_type": "missing",
                })
                continue

            result.total_compared += 1

            # Calculate errors
            abs_error = abs(actual_val - expected_val)
            pct_error = abs_error / abs(expected_val) * 100 if expected_val != 0 else (0 if actual_val == 0 else 100)

            result.absolute_errors.append(abs_error)
            result.percentage_errors.append(pct_error)

            # Exact match (within floating point tolerance)
            if math.isclose(actual_val, expected_val, rel_tol=1e-9, abs_tol=1e-9):
                result.exact_matches += 1
                result.tolerance_matches += 1
                continue

            # Tolerance match
            within_pct = pct_error <= tol_pct
            within_abs = abs_error <= tol_abs
            if within_pct or within_abs:
                result.tolerance_matches += 1
            else:
                result.errors.append({
                    "canonical_name": canonical,
                    "period": period,
                    "expected": expected_val,
                    "actual": actual_val,
                    "abs_error": round(abs_error, 4),
                    "pct_error": round(pct_error, 4),
                    "error_type": "value_mismatch",
                })

    return result


def attribute_errors_to_stages(
    extraction_result: dict,
    gold: dict,
) -> StageAttributionResult:
    """Attribute mapping errors to pipeline stages using lineage/provenance data.

    For each mismatch or missing mapping, examines the provenance chain to
    determine which stage introduced the error:
    - parsing: label not extracted from Excel at all
    - triage: sheet skipped that should have been processed
    - mapping: wrong canonical name assigned in Stage 3
    - enhanced_mapping: wrong canonical name from Stage 4 remapping
    - validation: label changed during validation stage
    """
    expected_mappings = gold.get("expected_mappings", [])
    acceptable_alts = gold.get("acceptable_alternatives", {})
    expected_triage = {t["sheet_name"]: t for t in gold.get("expected_triage", [])}

    # Build actual lookups
    actual_items = {}
    for item in extraction_result.get("line_items", []):
        label = item.get("original_label", "")
        if label:
            actual_items[label] = item

    actual_triage = {t["sheet_name"]: t for t in extraction_result.get("triage", [])}

    # All extracted labels
    all_extracted_labels = set()
    for item in extraction_result.get("line_items", []):
        label = item.get("original_label", "")
        if label:
            all_extracted_labels.add(label)

    result = StageAttributionResult()

    for exp in expected_mappings:
        label = exp["original_label"]
        exp_canonical = exp["canonical_name"]
        exp_sheet = exp.get("sheet", "")

        actual = actual_items.get(label)

        # Check if label is mapped correctly
        if actual:
            act_canonical = actual.get("canonical_name", "unmapped")
            alts = acceptable_alts.get(exp_canonical, [exp_canonical])
            if act_canonical in alts:
                continue  # Correct, no error to attribute

        result.total_errors += 1

        # Determine error stage
        if actual is None:
            # Label not in results at all
            # Was the sheet triaged correctly?
            triage_entry = actual_triage.get(exp_sheet, {})
            exp_triage_entry = expected_triage.get(exp_sheet, {})

            if triage_entry.get("tier", 0) >= 4 and exp_triage_entry.get("tier", 0) < 4:
                # Sheet was skipped but shouldn't have been
                result.triage_errors += 1
                result.details.append({
                    "label": label,
                    "expected": exp_canonical,
                    "stage": "triage",
                    "reason": f"Sheet '{exp_sheet}' was skipped (tier {triage_entry.get('tier')}) but expected tier {exp_triage_entry.get('tier')}",
                })
            elif label not in all_extracted_labels:
                # Label never parsed from Excel
                result.parsing_errors += 1
                result.details.append({
                    "label": label,
                    "expected": exp_canonical,
                    "stage": "parsing",
                    "reason": f"Label not extracted from sheet '{exp_sheet}'",
                })
            else:
                # Label extracted but mapped to something different under a different key
                result.mapping_errors += 1
                result.details.append({
                    "label": label,
                    "expected": exp_canonical,
                    "stage": "mapping",
                    "reason": "Label extracted but not found in final line items",
                })
        else:
            # Label found but mapped incorrectly
            act_canonical = actual.get("canonical_name", "unmapped")
            provenance = actual.get("provenance", {})
            mapping_prov = provenance.get("mapping", {})
            mapping_stage = mapping_prov.get("stage", "")

            if act_canonical == "unmapped":
                # Failed to map at all
                result.mapping_errors += 1
                result.details.append({
                    "label": label,
                    "expected": exp_canonical,
                    "actual": "unmapped",
                    "stage": "mapping",
                    "reason": "Label remained unmapped after all stages",
                })
            elif "enhanced" in mapping_stage or "stage_4" in mapping_stage:
                result.enhanced_mapping_errors += 1
                result.details.append({
                    "label": label,
                    "expected": exp_canonical,
                    "actual": act_canonical,
                    "stage": "enhanced_mapping",
                    "reason": f"Enhanced mapping (stage 4) assigned '{act_canonical}' instead of expected",
                })
            else:
                result.mapping_errors += 1
                result.details.append({
                    "label": label,
                    "expected": exp_canonical,
                    "actual": act_canonical,
                    "stage": "mapping",
                    "mapping_method": mapping_prov.get("method", "unknown"),
                    "reason": f"Mapping stage assigned '{act_canonical}' instead of expected",
                })

    return result


def run_full_evaluation(
    extraction_result: dict,
    gold: dict,
) -> FullEvaluationResult:
    """Run all evaluation metrics against a gold standard.

    Returns a complete FullEvaluationResult with mapping, value, triage,
    and stage attribution breakdowns.
    """
    return FullEvaluationResult(
        mapping=evaluate_mapping_accuracy(extraction_result, gold),
        values=evaluate_value_accuracy(extraction_result, gold),
        triage=evaluate_triage_accuracy(extraction_result, gold),
        stage_attribution=attribute_errors_to_stages(extraction_result, gold),
    )
