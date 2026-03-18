"""Stage 4: Validation - Verify extracted data against accounting rules."""

import json
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import anthropic

from src.core.exceptions import ClaudeAPIError, ExtractionError, RateLimitError
from src.core.logging import extraction_logger as logger
from src.core.logging import log_performance
from src.extraction.base import ExtractionStage, PipelineContext
from src.extraction.claude_client import get_claude_client
from src.extraction.prompts import get_prompt
from src.extraction.taxonomy_loader import get_all_taxonomy_items, get_validation_rules
from src.extraction.utils import extract_json
from src.validation.accounting_validator import AccountingValidator
from src.validation.cell_reconciliation import CellReconciliationValidator, ReconciliationSummary
from src.validation.formula_verifier import FormulaVerificationSummary, FormulaVerifier
from src.validation.completeness_scorer import CompletenessScorer
from src.validation.lifecycle_detector import LifecycleDetector, LifecycleResult
from src.validation.quality_scorer import QualityScorer
from src.validation.time_series_validator import TimeSeriesValidator

# Load validation rules from taxonomy.json (29 rules vs. old 7 hardcoded)
DERIVATION_RULES = get_validation_rules()
# Full taxonomy for sign convention checks
ALL_TAXONOMY_ITEMS = get_all_taxonomy_items()


class ValidationStage(ExtractionStage):
    """Stage 4: Validate extracted data against accounting rules."""

    CONFLICT_ABSOLUTE_TOLERANCE = Decimal("0.01")
    CONFLICT_RELATIVE_TOLERANCE = 0.001  # 0.1%

    @property
    def name(self) -> str:
        return "validation"

    @property
    def stage_number(self) -> int:
        return 4

    @property
    def timeout_seconds(self):
        return 60.0

    def should_skip(self, context: PipelineContext) -> bool:
        """Skip validation if no tier 1-2 sheets exist."""
        try:
            triage_result = context.get_result("triage")
            triage_list = triage_result.get("triage", [])
            has_high_priority = any(t.get("tier", 4) in (1, 2) for t in triage_list)
            if not has_high_priority:
                logger.info("Stage 4: Skipping validation (no tier 1-2 sheets)")
                return True
            return False
        except KeyError:
            return False

    async def execute(self, context: PipelineContext) -> Dict[str, Any]:
        """Run deterministic validation checks, then Claude for anomaly reasoning."""
        logger.info("Stage 4: Validation started")
        start_time = time.time()

        # Get data from previous stages
        parse_stage_result = context.get_result("parsing")
        parse_result = parse_stage_result["parsed"]
        structured_data = parse_stage_result.get("structured")
        mapping_result = context.get_result("mapping")["mappings"]
        triage_result = context.get_result("triage")["triage"]

        # Build per-period data for validation (with unit normalization)
        extracted_values = self._build_extracted_values(
            parse_result, mapping_result, triage_result, structured_data
        )

        # --- Cell-Level Reconciliation ---
        try:
            cell_reconciler = CellReconciliationValidator()
            cell_recon_summary = cell_reconciler.reconcile(
                parse_result, mapping_result, triage_result, structured_data
            )
        except Exception as e:
            logger.warning(f"Stage 4: Cell reconciliation failed: {e}")
            cell_recon_summary = ReconciliationSummary(
                total_cells=0, matched=0, mismatched=0, unmatched=0,
                match_rate=1.0, mismatches=[], unmatched_items=[],
            )

        # --- Formula Verification ---
        try:
            formula_verifier = FormulaVerifier()
            formula_summary = formula_verifier.verify(
                parse_result, mapping_result, triage_result, structured_data
            )
        except Exception as e:
            logger.warning(f"Stage 4: Formula verification failed: {e}")
            formula_summary = FormulaVerificationSummary(
                total_formulas=0, verified=0, mismatched=0, unresolvable=0, results=[],
            )

        # Run deterministic checks via AccountingValidator
        # Use full taxonomy so sign convention checks can access typical_sign
        validator = AccountingValidator(ALL_TAXONOMY_ITEMS)
        period_results = {}
        all_flags = []

        for period, values in extracted_values.items():
            summary = validator.validate(values)

            # Sign convention checks (warning severity)
            sign_results = validator.validate_sign_conventions(values)
            sign_passed = sum(1 for r in sign_results if r.passed)

            period_results[period] = {
                "total_checks": summary.total_checks + len(sign_results),
                "passed": summary.passed + sign_passed,
                "failed": summary.failed + (len(sign_results) - sign_passed),
                "success_rate": round(
                    (summary.passed + sign_passed)
                    / max(summary.total_checks + len(sign_results), 1),
                    3,
                ),
            }
            for error in summary.errors:
                all_flags.append(
                    {
                        "period": period,
                        "severity": "error",
                        "item": error.item_name,
                        "rule": error.rule,
                        "message": error.message,
                        "actual": str(error.actual_value) if error.actual_value else None,
                        "expected": str(error.expected_value) if error.expected_value else None,
                    }
                )
            for warning in summary.warnings_list:
                all_flags.append(
                    {
                        "period": period,
                        "severity": "warning",
                        "item": warning.item_name,
                        "rule": warning.rule,
                        "message": warning.message,
                        "actual": str(warning.actual_value) if warning.actual_value else None,
                        "expected": str(warning.expected_value) if warning.expected_value else None,
                    }
                )
            # Sign convention violations (warnings only)
            for sr in sign_results:
                if not sr.passed:
                    all_flags.append(
                        {
                            "period": period,
                            "severity": sr.severity,
                            "item": sr.item_name,
                            "rule": sr.rule,
                            "message": sr.message,
                            "actual": str(sr.actual_value) if sr.actual_value else None,
                            "expected": str(sr.expected_value) if sr.expected_value else None,
                        }
                    )

        # --- Cross-Statement Validation ---
        try:
            cross_statement_results = validator.validate_cross_statement(extracted_values)
            for cs_result in cross_statement_results:
                if not cs_result.passed:
                    all_flags.append(
                        {
                            "period": "cross_statement",
                            "severity": cs_result.severity,
                            "item": cs_result.item_name,
                            "rule": cs_result.rule,
                            "message": cs_result.message,
                            "actual": str(cs_result.actual_value)
                            if cs_result.actual_value
                            else None,
                            "expected": str(cs_result.expected_value)
                            if cs_result.expected_value
                            else None,
                        }
                    )
        except Exception as e:
            logger.warning(f"Stage 4: Cross-statement validation failed: {e}")
            cross_statement_results = []

        # --- Lifecycle Detection (compute once, reuse for filtering + output) ---
        try:
            lifecycle_detector = LifecycleDetector()
            lifecycle_result = lifecycle_detector.detect(extracted_values)
        except Exception as e:
            logger.warning(f"Stage 4: Lifecycle detection failed: {e}")
            from src.validation.lifecycle_detector import LifecycleResult

            lifecycle_result = LifecycleResult(
                phases={},
                is_project_finance=False,
                confidence=0.0,
                signals_used=[],
            )

        # Filter out false-positive flags from project lifecycle phases
        # (construction / post-operations periods where zero revenue is expected)
        all_flags = self._filter_lifecycle_flags(all_flags, lifecycle_result)

        # --- Time-Series Validation ---
        try:
            ts_validator = TimeSeriesValidator(DERIVATION_RULES)
            ts_summary = ts_validator.validate(extracted_values)
        except Exception as e:
            logger.warning(f"Stage 4: Time-series validation failed: {e}")
            from src.validation.time_series_validator import TimeSeriesSummary

            ts_summary = TimeSeriesSummary(
                total_checks=0,
                flags=[],
                items_checked=0,
                periods_analyzed=0,
                consistency_score=1.0,
            )

        # --- Completeness Scoring ---
        model_type = None
        try:
            completeness_scorer = CompletenessScorer(taxonomy_items=ALL_TAXONOMY_ITEMS)
            extracted_names: set = set()
            for period_vals in extracted_values.values():
                extracted_names.update(period_vals.keys())
            model_type = completeness_scorer.detect_model_type(
                extracted_names,
                is_project_finance=lifecycle_result.is_project_finance,
            )
            if extracted_values:
                completeness_result = completeness_scorer.score_with_periods(
                    extracted_values, model_type=model_type
                )
            else:
                completeness_result = completeness_scorer.score(
                    extracted_names, model_type=model_type
                )
        except Exception as e:
            logger.warning(f"Stage 4: Completeness scoring failed: {e}")
            from src.validation.completeness_scorer import CompletenessResult

            completeness_result = CompletenessResult(
                overall_score=0.0,
                overall_raw_score=0.0,
                detected_statements=[],
            )

        # Use Claude to reason about anomalies (only if there are flags)
        claude_reasoning = {}
        tokens = 0
        input_tokens = 0
        output_tokens = 0
        if all_flags:
            (
                claude_reasoning,
                tokens,
                input_tokens,
                output_tokens,
            ) = await self._get_claude_reasoning(all_flags, extracted_values)

        # Build per-canonical-name validation provenance
        item_validation = self._build_item_validation(all_flags, extracted_values)

        duration = time.time() - start_time

        total_checks = sum(r["total_checks"] for r in period_results.values())
        total_passed = sum(r["passed"] for r in period_results.values())

        # Include cross-statement checks in totals
        total_cross_checks = len(cross_statement_results)
        total_cross_passed = sum(1 for r in cross_statement_results if r.passed)
        total_checks += total_cross_checks
        total_passed += total_cross_passed

        # --- Composite Quality Score ---
        # Compute formula mismatch rate (available for quality scoring and lineage)
        formula_mismatch_rate = None
        resolvable_formulas = formula_summary.verified + formula_summary.mismatched
        if resolvable_formulas > 0:
            formula_mismatch_rate = formula_summary.mismatched / resolvable_formulas

        try:
            avg_confidence = self._compute_avg_confidence(context)
            quality_scorer = QualityScorer(model_type=model_type)
            quality_result = quality_scorer.score(
                mapping_confidence=avg_confidence,
                validation_success_rate=total_passed / max(total_checks, 1),
                completeness_score=completeness_result.overall_score,
                time_series_consistency=ts_summary.consistency_score,
                cell_match_rate=cell_recon_summary.match_rate
                if cell_recon_summary.total_cells > 0
                else None,
                formula_mismatch_rate=formula_mismatch_rate,
            )
        except Exception as e:
            logger.warning(f"Stage 4: Quality scoring failed: {e}")
            quality_scorer = QualityScorer(model_type=model_type)
            quality_result = quality_scorer.score(0.0, 0.0, 0.0, 0.0)

        log_performance(
            logger,
            "stage_4_validation",
            duration,
            {
                "tokens": tokens,
                "periods": len(extracted_values),
                "total_checks": total_checks,
                "flags": len(all_flags),
            },
        )

        logger.info(
            f"Stage 4: Validation completed - "
            f"{total_checks} checks, {total_passed} passed, {len(all_flags)} flags"
        )

        return {
            "validation": {
                "period_results": period_results,
                "flags": all_flags,
                "claude_reasoning": claude_reasoning,
                "overall_confidence": round(total_passed / max(total_checks, 1), 3),
                "time_series": {
                    "total_checks": ts_summary.total_checks,
                    "flags": [
                        {
                            "check_type": f.check_type,
                            "canonical_name": f.canonical_name,
                            "period": f.period,
                            "severity": f.severity,
                            "message": f.message,
                            "details": f.details,
                        }
                        for f in ts_summary.flags
                    ],
                    "consistency_score": round(ts_summary.consistency_score, 3),
                    "items_checked": ts_summary.items_checked,
                    "periods_analyzed": ts_summary.periods_analyzed,
                },
                "completeness": {
                    "model_type": model_type,
                    "overall_score": round(completeness_result.overall_score, 3),
                    "detected_statements": completeness_result.detected_statements,
                    "total_expected": completeness_result.total_expected,
                    "total_found": completeness_result.total_found,
                    "total_missing": completeness_result.total_missing,
                    "missing_items": [
                        {
                            "canonical_name": m.canonical_name,
                            "category": m.category,
                            "weight": m.weight,
                            "is_core": m.is_core,
                        }
                        for m in completeness_result.missing_items
                    ],
                    "per_statement": {
                        name: {
                            "raw_score": round(stmt.raw_score, 3),
                            "weighted_score": round(stmt.weighted_score, 3),
                            "core_score": round(stmt.core_score, 3),
                            "found": stmt.found_items,
                            "missing": [mi.canonical_name for mi in stmt.missing_items],
                            "period_coverage": round(stmt.period_coverage, 3)
                            if stmt.period_coverage is not None
                            else None,
                            "total_periods": stmt.total_periods,
                            "sparse_items": stmt.sparse_items,
                        }
                        for name, stmt in completeness_result.per_statement.items()
                    },
                },
                "quality": quality_result.to_dict(),
                "lifecycle": {
                    "is_project_finance": lifecycle_result.is_project_finance,
                    "confidence": round(lifecycle_result.confidence, 3),
                    "signals_used": lifecycle_result.signals_used,
                    "phases": lifecycle_result.phases,
                },
                "cell_reconciliation": {
                    "total_cells": cell_recon_summary.total_cells,
                    "matched": cell_recon_summary.matched,
                    "mismatched": cell_recon_summary.mismatched,
                    "unmatched": cell_recon_summary.unmatched,
                    "match_rate": round(cell_recon_summary.match_rate, 3),
                    "mismatches": [
                        {
                            "canonical_name": m.canonical_name,
                            "period": m.period,
                            "extracted_value": str(m.extracted_value),
                            "source_cell_ref": m.source_cell_ref,
                            "source_raw_value": m.source_raw_value,
                            "delta": str(m.delta),
                            "delta_pct": m.delta_pct,
                        }
                        for m in cell_recon_summary.mismatches
                    ],
                },
                "formula_verification": {
                    "total_formulas": formula_summary.total_formulas,
                    "verified": formula_summary.verified,
                    "mismatched": formula_summary.mismatched,
                    "unresolvable": formula_summary.unresolvable,
                },
                "duplicate_conflicts": getattr(self, "_duplicate_conflicts", []),
                "unit_normalization": getattr(self, "_unit_normalization", {}),
            },
            "item_validation": item_validation,
            "tokens": tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "lineage_metadata": {
                "total_checks": total_checks,
                "total_passed": total_passed,
                "flags_count": len(all_flags),
                "error_count": sum(1 for f in all_flags if f["severity"] == "error"),
                "warning_count": sum(1 for f in all_flags if f["severity"] == "warning"),
                "time_series_flags": len(ts_summary.flags),
                "completeness_score": round(completeness_result.overall_score, 3),
                "quality_score": round(quality_result.numeric_score, 3),
                "quality_grade": quality_result.letter_grade,
                "cell_match_rate": round(cell_recon_summary.match_rate, 3),
                "formula_mismatch_rate": round(formula_mismatch_rate, 3)
                if formula_mismatch_rate is not None
                else None,
            },
        }

    @staticmethod
    def _compute_avg_confidence(context: PipelineContext) -> float:
        """Compute average mapping confidence from the mapping stage result."""
        try:
            mapping_result = context.get_result("mapping")
            mappings = mapping_result.get("mappings", [])
            if not mappings:
                return 0.0
            return sum(m.get("confidence", 0) for m in mappings) / len(mappings)
        except (KeyError, TypeError):
            return 0.0

    @staticmethod
    def _build_item_validation(
        flags: List[Dict],
        extracted_values: Dict[str, Dict],
    ) -> Dict[str, Dict[str, Any]]:
        """Build per-canonical-name validation provenance.

        Returns a dict keyed by canonical_name, each containing:
          - rules_applied: deduplicated list of rule names
          - all_passed: True if no error-severity flags for this item
          - flags: list of flag dicts for this item
        """
        item_val: Dict[str, Dict[str, Any]] = {}

        # Collect flags by canonical name
        for flag in flags:
            canonical = flag.get("item", "")
            if not canonical:
                continue
            if canonical not in item_val:
                item_val[canonical] = {
                    "rules_applied": [],
                    "all_passed": True,
                    "flags": [],
                }
            rule = flag.get("rule", "")
            if rule and rule not in item_val[canonical]["rules_applied"]:
                item_val[canonical]["rules_applied"].append(rule)
            if flag.get("severity") == "error":
                item_val[canonical]["all_passed"] = False
            item_val[canonical]["flags"].append(flag)

        # Add entries for canonicals that were validated but had no flags
        all_validated: set = set()
        for _period, values in extracted_values.items():
            all_validated.update(values.keys())

        for canonical in all_validated:
            if canonical not in item_val:
                item_val[canonical] = {
                    "rules_applied": [],
                    "all_passed": True,
                    "flags": [],
                }

        return item_val

    def _build_extracted_values(
        self,
        parsed: Dict,
        mappings: List[Dict],
        triage: List[Dict],
        structured: Optional[Dict] = None,
    ) -> Dict[str, Dict[str, Decimal]]:
        """Build per-period canonical-name → value dicts from parsed data + mappings.

        If ``structured`` is provided, applies per-sheet ``unit_multiplier``
        so that values from sheets expressed "in thousands" or "in millions"
        are normalised to absolute units before cross-sheet validation.
        """
        # Build mapping lookup
        mapping_lookup = {m["original_label"]: m["canonical_name"] for m in mappings}

        # Identify processable sheets (tier 1-3)
        processable = {t["sheet_name"] for t in triage if t.get("tier", 4) <= 3}

        # Build per-sheet unit multiplier lookup from structured parsing data
        multiplier_lookup: Dict[str, Decimal] = {}
        if structured:
            for sheet in structured.get("sheets", []):
                name = sheet.get("sheet_name", "")
                mult = sheet.get("unit_multiplier")
                if mult is not None and mult != 1 and mult != 1.0:
                    try:
                        multiplier_lookup[name] = Decimal(str(mult))
                    except (ValueError, ArithmeticError):
                        pass

        period_values: Dict[str, Dict[str, Decimal]] = {}
        self._unit_normalization: Dict[str, str] = {}  # provenance tracking

        # Build tier lookup for conflict resolution (lower tier = higher priority)
        tier_lookup = {t["sheet_name"]: t.get("tier", 4) for t in triage}

        # Track all candidates per (canonical, period) for conflict detection
        all_candidates: Dict[str, Dict[str, List]] = {}  # canonical -> period -> [...]

        for sheet in parsed.get("sheets", []):
            sheet_name = sheet.get("sheet_name", "")
            if sheet_name not in processable:
                continue

            sheet_multiplier = multiplier_lookup.get(sheet_name)
            if sheet_multiplier is not None:
                self._unit_normalization[sheet_name] = str(sheet_multiplier)

            sheet_tier = tier_lookup.get(sheet_name, 4)

            for row in sheet.get("rows", []):
                label = row.get("label", "")
                canonical = mapping_lookup.get(label)
                if not canonical or canonical == "unmapped":
                    continue

                values = row.get("values", {})
                for period, value in values.items():
                    if value is None:
                        continue
                    try:
                        decimal_val = Decimal(str(value))
                    except (ValueError, ArithmeticError, InvalidOperation) as e:
                        logger.warning(
                            f"Could not convert value to Decimal: {value!r}, "
                            f"label={label}, period={period}, error={e}"
                        )
                        continue

                    # Apply unit multiplier to normalise to absolute units
                    if sheet_multiplier is not None:
                        decimal_val *= sheet_multiplier

                    if period not in period_values:
                        period_values[period] = {}

                    # Track candidate for conflict detection
                    if canonical not in all_candidates:
                        all_candidates[canonical] = {}
                    if period not in all_candidates[canonical]:
                        all_candidates[canonical][period] = []
                    all_candidates[canonical][period].append({
                        "value": decimal_val,
                        "sheet": sheet_name,
                        "label": label,
                        "tier": sheet_tier,
                    })

                    # First-write-wins: keep the first value seen for each
                    # canonical+period (highest-tier sheet processed first)
                    if canonical not in period_values[period]:
                        period_values[period][canonical] = decimal_val

        # Resolve conflicts and record duplicate information
        self._duplicate_conflicts: List[Dict] = []
        for canonical, period_candidates in all_candidates.items():
            for period, candidates in period_candidates.items():
                if len(candidates) <= 1:
                    continue
                # Check if values agree within dual tolerance
                first_val = candidates[0]["value"]
                is_conflict = any(
                    not self._values_agree(first_val, c["value"])
                    for c in candidates[1:]
                )
                # If conflicting, use highest-tier (lowest tier number) value
                if is_conflict:
                    best = min(candidates, key=lambda c: c["tier"])
                    period_values[period][canonical] = best["value"]
                    chosen_sheet = best["sheet"]
                else:
                    chosen_sheet = candidates[0]["sheet"]

                self._duplicate_conflicts.append({
                    "canonical_name": canonical,
                    "period": period,
                    "values": [
                        {
                            "value": str(c["value"]),
                            "sheet": c["sheet"],
                            "label": c["label"],
                            "tier": c["tier"],
                        }
                        for c in candidates
                    ],
                    "chosen_value": str(period_values[period][canonical]),
                    "chosen_sheet": chosen_sheet,
                    "is_conflict": is_conflict,
                })

        return period_values

    def _values_agree(self, a: Decimal, b: Decimal) -> bool:
        """Check if two values agree within dual tolerance (absolute OR relative)."""
        delta = abs(a - b)
        if delta <= self.CONFLICT_ABSOLUTE_TOLERANCE:
            return True
        divisor = max(abs(a), Decimal("1"))
        return float(delta / divisor) <= self.CONFLICT_RELATIVE_TOLERANCE

    @staticmethod
    def _filter_lifecycle_flags(
        flags: List[Dict],
        lifecycle: LifecycleResult,
    ) -> List[Dict]:
        """Filter validation flags based on lifecycle phase context.

        Uses a pre-computed LifecycleResult to apply phase-specific
        suppression rules:
        - pre_construction / construction: suppress must_be_positive for ALL items
        - ramp_up: downgrade errors to warnings
        - maintenance_shutdown: suppress must_be_positive for revenue
        - post_operations: suppress must_be_positive for ALL items
        - operations / tail: keep all flags unchanged

        If no lifecycle phases can be detected, all flags pass through unchanged.
        """
        if not lifecycle.phases:
            return flags  # No lifecycle data — keep all flags

        filtered: List[Dict] = []
        for flag in flags:
            period = flag.get("period", "")
            phase = lifecycle.phases.get(period, "operations")
            rule = flag.get("rule", "")
            severity = flag.get("severity", "error")

            # Pre-construction / Construction: suppress must_be_positive for ALL items
            if phase in ("pre_construction", "construction"):
                if rule == "must_be_positive":
                    continue

            # Ramp-up: downgrade errors to warnings
            if phase == "ramp_up" and severity == "error":
                flag = dict(flag)  # shallow copy to avoid mutation
                flag["severity"] = "warning"
                flag["message"] = flag.get("message", "") + " [downgraded: ramp-up phase]"
                filtered.append(flag)
                continue

            # Maintenance shutdown: suppress zero-revenue flags
            if phase == "maintenance_shutdown":
                if rule == "must_be_positive" and flag.get("item") == "revenue":
                    continue

            # Post-operations: suppress must_be_positive for ALL items
            if phase == "post_operations":
                if rule == "must_be_positive":
                    continue

            filtered.append(flag)
        return filtered

    async def _get_claude_reasoning(
        self,
        flags: List[Dict],
        extracted_values: Dict[str, Dict[str, Decimal]],
    ) -> tuple:
        """Ask Claude to reason about validation flags."""
        try:
            # Serialize values for prompt (convert Decimal to float)
            values_for_prompt = {}
            for period, vals in extracted_values.items():
                values_for_prompt[period] = {k: float(v) for k, v in vals.items()}

            response = get_claude_client().messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                messages=[
                    {
                        "role": "user",
                        "content": get_prompt("validation").render(
                            flags=json.dumps(flags, indent=2),
                            extracted_values=json.dumps(values_for_prompt, indent=2),
                        ),
                    }
                ],
            )

            # Check for truncation — incomplete JSON causes silent data loss
            if response.stop_reason == "max_tokens":
                logger.warning(
                    f"Stage 4: Reasoning response truncated at max_tokens "
                    f"({response.usage.output_tokens} tokens)."
                )
                raise ExtractionError(
                    "Validation reasoning truncated: output exceeded token limit.",
                    stage="validation",
                )

            content = response.content[0].text  # type: ignore[union-attr]
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            tokens = input_tokens + output_tokens

            try:
                reasoning = extract_json(content)
            except ExtractionError:
                logger.warning(
                    f"Stage 4: Claude reasoning returned non-JSON, using raw text. "
                    f"Preview: {content[:200]}"
                )
                reasoning = {"raw_reasoning": content}
            return reasoning, tokens, input_tokens, output_tokens

        except anthropic.RateLimitError as e:
            retry_after = getattr(e.response, "headers", {}).get("retry-after")
            logger.warning(f"Stage 4: Rate limit hit (retry-after={retry_after})")
            raise RateLimitError(
                "Rate limit exceeded",
                stage="validation",
                retry_after=int(retry_after) if retry_after else None,
            )

        except anthropic.APIError as e:
            logger.error(f"Stage 4: Claude API error - {str(e)}")
            raise ClaudeAPIError(
                str(e),
                stage="validation",
                status_code=getattr(e, "status_code", None),
            )

        except Exception as e:
            logger.warning(f"Stage 4: Claude reasoning failed, continuing without it: {e}")
            return {}, 0, 0, 0


# Self-register at import time
from src.extraction.registry import registry  # noqa: E402

registry.register(ValidationStage())
