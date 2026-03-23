"""Stage 6: Derivation Engine — compute financial metrics from extracted facts.

Runs after Stage 5 (enhanced mapping).  For each period in the extraction:
  1. Gap-fill  — compute metrics absent from the source Excel (e.g. DSCR when
                  CFADS + debt_service are extracted but DSCR is not)
  2. Consistency — compare extracted vs. computed when both are available
  3. Uncertainty — attach confidence bands and covenant sensitivity flags

Derived facts are stored in the derived_facts table (separate from extraction_facts)
and are also attached to the ExtractionResult under the key "derived_facts".
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from src.core.logging import extraction_logger as logger
from src.extraction.base import ExtractionStage, PipelineContext
from src.extraction.registry import registry


class DerivationStage(ExtractionStage):
    """Stage 6: Post-extraction derivation of computed financial metrics."""

    @property
    def name(self) -> str:
        return "derivation"

    @property
    def stage_number(self) -> int:
        return 6

    @property
    def timeout_seconds(self) -> float:
        return 30.0

    @property
    def max_retries(self) -> int:
        return 1  # deterministic — no benefit from retrying

    def should_skip(self, context: PipelineContext) -> bool:
        """Skip if no extraction facts exist (pipeline failed or no line items)."""
        mapping_result = context.results.get("mapping") or {}
        mappings = mapping_result.get("mappings", [])
        if not mappings:
            logger.info("Stage 6: Skipping derivation (no mappings produced)")
            return True
        return False

    async def execute(self, context: PipelineContext) -> Dict[str, Any]:
        """Run derivation engine over extracted facts from all prior stages."""
        from src.derivation.engine import run_derivation

        logger.info("Stage 6: Derivation Engine started")
        start = time.time()

        # Gather line items (prefer enhanced mappings)
        enhanced_result = context.results.get("enhanced_mapping") or {}
        mapping_result = context.results.get("mapping") or {}
        mappings = enhanced_result.get("enhanced_mappings") or mapping_result.get("mappings", [])
        parse_result = context.results.get("parsing") or {}

        # Build per-sheet unit multipliers from structured parsing data
        structured = parse_result.get("structured") or {}
        multiplier_lookup: Dict[str, Decimal] = {}
        for s in structured.get("sheets", []):
            sname = s.get("sheet_name", "")
            mult = s.get("unit_multiplier")
            if mult and mult not in (1, 1.0):
                try:
                    multiplier_lookup[sname] = Decimal(str(mult))
                except (ValueError, InvalidOperation):
                    pass

        # Build {canonical_name: {period: (value, confidence)}} from line_items
        parsed_data = parse_result.get("parsed") or {}
        mapping_lookup = {m["original_label"]: m for m in mappings}
        triage_result = context.results.get("triage") or {}
        triage_list = triage_result.get("triage", [])
        processable_sheets = {
            t["sheet_name"] for t in triage_list if t.get("tier", 4) <= 2
        }

        # Detect label_value (static) sheets to skip
        label_value_sheets = {
            t["sheet_name"]
            for t in triage_list
            if t.get("layout_type") == "label_value"
        }

        # Aggregate values per canonical + period (first-write-wins, highest-tier sheet first)
        canonical_values: Dict[str, Dict[str, Decimal]] = {}
        canonical_confs: Dict[str, Dict[str, float]] = {}

        for sheet in parsed_data.get("sheets", []):
            sheet_name = sheet.get("sheet_name", "")
            if sheet_name not in processable_sheets:
                continue
            if sheet_name in label_value_sheets:
                continue  # static parameters, not time-series
            sheet_multiplier = multiplier_lookup.get(sheet_name)

            for row in sheet.get("rows", []):
                label = row.get("label", "")
                m = mapping_lookup.get(label)
                if not m:
                    continue
                canonical = m.get("canonical_name", "unmapped")
                if canonical == "unmapped":
                    continue
                conf = float(m.get("confidence", 0.5))

                for period, raw_val in row.get("values", {}).items():
                    if raw_val is None:
                        continue
                    try:
                        val = Decimal(str(raw_val))
                    except (ValueError, InvalidOperation):
                        continue
                    if sheet_multiplier is not None:
                        val = val * sheet_multiplier

                    # First-write-wins per canonical+period
                    canonical_values.setdefault(canonical, {})
                    canonical_confs.setdefault(canonical, {})
                    if period not in canonical_values[canonical]:
                        canonical_values[canonical][period] = val
                        canonical_confs[canonical][period] = conf

        # Detect model type from validation stage
        validation_result = context.results.get("validation") or {}
        from src.validation.completeness_scorer import CompletenessScorer
        extracted_canonicals = set(canonical_values.keys())
        is_pf_hint = (
            validation_result.get("validation", {}).get("lifecycle", {}).get("is_project_finance")
        )
        model_type = CompletenessScorer().detect_model_type(
            extracted_canonicals, is_project_finance=is_pf_hint
        )

        # Run derivation engine
        derived_facts = run_derivation(
            extracted_facts=[
                {
                    "canonical_name": cn,
                    "period": period,
                    "value": val,
                    "confidence": canonical_confs.get(cn, {}).get(period, 0.5),
                }
                for cn, period_map in canonical_values.items()
                for period, val in period_map.items()
            ],
            model_type=model_type,
        )

        elapsed = time.time() - start
        logger.info(
            f"Stage 6: Derivation complete — {len(derived_facts)} derived facts "
            f"from {sum(len(pm) for pm in canonical_values.values())} extracted facts "
            f"({elapsed:.2f}s)"
        )

        # Serialise to JSON-safe dicts
        serialised = [_serialise_derived_fact(f) for f in derived_facts]

        return {
            "derived_facts": serialised,
            "derived_count": len(derived_facts),
            "model_type": model_type,
            "lineage_metadata": {
                "derived_count": len(derived_facts),
                "model_type": model_type,
                "elapsed_seconds": round(elapsed, 3),
            },
        }


def _serialise_derived_fact(fact) -> Dict[str, Any]:
    """Convert a DerivedFact dataclass to a JSON-safe dict."""
    d: Dict[str, Any] = {
        "canonical_name": fact.canonical_name,
        "period": fact.period,
        "computed_value": float(fact.computed_value),
        "confidence": fact.confidence,
        "value_range_low": float(fact.value_range_low) if fact.value_range_low is not None else None,
        "value_range_high": float(fact.value_range_high) if fact.value_range_high is not None else None,
        "computation_rule_id": fact.computation_rule_id,
        "formula": fact.formula,
        "source_canonicals": fact.source_canonicals,
        "confidence_mode": fact.confidence_mode,
        "derivation_pass": fact.derivation_pass,
        "is_gap_fill": fact.is_gap_fill,
        "consistency": None,
        "covenant": None,
    }
    if fact.consistency is not None:
        c = fact.consistency
        d["consistency"] = {
            "extracted_value": float(c.extracted_value) if c.extracted_value is not None else None,
            "computed_value": float(c.computed_value),
            "divergence_pct": c.divergence_pct,
            "passed": c.passed,
            "threshold_pct": c.threshold_pct,
        }
    if fact.covenant is not None:
        cv = fact.covenant
        d["covenant"] = {
            "threshold": float(cv.threshold) if cv.threshold is not None else None,
            "headroom": float(cv.headroom) if cv.headroom is not None else None,
            "headroom_range_low": float(cv.headroom_range_low) if cv.headroom_range_low is not None else None,
            "headroom_range_high": float(cv.headroom_range_high) if cv.headroom_range_high is not None else None,
            "is_sensitive": cv.is_sensitive,
            "flag_message": cv.flag_message,
        }
    return d


# Self-register into global stage registry
registry.register(DerivationStage())
