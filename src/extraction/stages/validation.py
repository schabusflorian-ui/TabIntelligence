"""Stage 4: Validation - Verify extracted data against accounting rules."""
import json
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

import anthropic

from src.core.exceptions import ClaudeAPIError, ExtractionError, RateLimitError
from src.core.logging import extraction_logger as logger, log_performance
from src.core.retry import retry
from src.extraction.base import ExtractionStage, PipelineContext
from src.extraction.claude_client import get_claude_client
from src.extraction.prompts import get_prompt
from src.extraction.utils import extract_json
from src.extraction.taxonomy_loader import get_validation_rules
from src.validation.accounting_validator import AccountingValidator, ValidationSummary


# Load validation rules from taxonomy.json (29 rules vs. old 7 hardcoded)
DERIVATION_RULES = get_validation_rules()


class ValidationStage(ExtractionStage):
    """Stage 4: Validate extracted data against accounting rules."""

    @property
    def name(self) -> str:
        return "validation"

    @property
    def stage_number(self) -> int:
        return 4

    @retry(max_attempts=2, backoff_seconds=2)
    async def execute(self, context: PipelineContext, attempt: int = 1) -> Dict[str, Any]:
        """Run deterministic validation checks, then Claude for anomaly reasoning."""
        logger.info(f"Stage 4: Validation - Attempt {attempt}/2")
        start_time = time.time()

        # Get data from previous stages
        parse_result = context.get_result("parsing")["parsed"]
        mapping_result = context.get_result("mapping")["mappings"]
        triage_result = context.get_result("triage")["triage"]

        # Build per-period data for validation
        extracted_values = self._build_extracted_values(
            parse_result, mapping_result, triage_result
        )

        # Run deterministic checks via AccountingValidator
        validator = AccountingValidator(DERIVATION_RULES)
        period_results = {}
        all_flags = []

        for period, values in extracted_values.items():
            summary = validator.validate(values)
            period_results[period] = {
                "total_checks": summary.total_checks,
                "passed": summary.passed,
                "failed": summary.failed,
                "success_rate": round(summary.success_rate, 3),
            }
            for error in summary.errors:
                all_flags.append({
                    "period": period,
                    "severity": "error",
                    "item": error.item_name,
                    "rule": error.rule,
                    "message": error.message,
                    "actual": str(error.actual_value) if error.actual_value else None,
                    "expected": str(error.expected_value) if error.expected_value else None,
                })
            for warning in summary.warnings_list:
                all_flags.append({
                    "period": period,
                    "severity": "warning",
                    "item": warning.item_name,
                    "rule": warning.rule,
                    "message": warning.message,
                    "actual": str(warning.actual_value) if warning.actual_value else None,
                    "expected": str(warning.expected_value) if warning.expected_value else None,
                })

        # Use Claude to reason about anomalies (only if there are flags)
        claude_reasoning = {}
        tokens = 0
        if all_flags:
            claude_reasoning, tokens = await self._get_claude_reasoning(
                all_flags, extracted_values, attempt
            )

        duration = time.time() - start_time

        total_checks = sum(r["total_checks"] for r in period_results.values())
        total_passed = sum(r["passed"] for r in period_results.values())

        log_performance(
            logger,
            "stage_4_validation",
            duration,
            {
                "tokens": tokens,
                "periods": len(extracted_values),
                "total_checks": total_checks,
                "flags": len(all_flags),
                "attempt": attempt,
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
                "overall_confidence": round(
                    total_passed / max(total_checks, 1), 3
                ),
            },
            "tokens": tokens,
            "lineage_metadata": {
                "total_checks": total_checks,
                "total_passed": total_passed,
                "flags_count": len(all_flags),
                "error_count": sum(1 for f in all_flags if f["severity"] == "error"),
                "warning_count": sum(1 for f in all_flags if f["severity"] == "warning"),
            },
        }

    def _build_extracted_values(
        self,
        parsed: Dict,
        mappings: List[Dict],
        triage: List[Dict],
    ) -> Dict[str, Dict[str, Decimal]]:
        """Build per-period canonical-name → value dicts from parsed data + mappings."""
        # Build mapping lookup
        mapping_lookup = {m["original_label"]: m["canonical_name"] for m in mappings}

        # Identify processable sheets (tier 1-3)
        processable = {
            t["sheet_name"] for t in triage if t.get("tier", 4) <= 3
        }

        period_values: Dict[str, Dict[str, Decimal]] = {}

        for sheet in parsed.get("sheets", []):
            if sheet.get("sheet_name") not in processable:
                continue

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

                    if period not in period_values:
                        period_values[period] = {}
                    period_values[period][canonical] = decimal_val

        return period_values

    async def _get_claude_reasoning(
        self,
        flags: List[Dict],
        extracted_values: Dict[str, Dict[str, Decimal]],
        attempt: int,
    ) -> tuple:
        """Ask Claude to reason about validation flags."""
        try:
            # Serialize values for prompt (convert Decimal to float)
            values_for_prompt = {}
            for period, vals in extracted_values.items():
                values_for_prompt[period] = {k: float(v) for k, v in vals.items()}

            response = get_claude_client().messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                messages=[{
                    "role": "user",
                    "content": get_prompt("validation").render(
                        flags=json.dumps(flags, indent=2),
                        extracted_values=json.dumps(values_for_prompt, indent=2),
                    ),
                }],
            )

            content = response.content[0].text  # type: ignore[union-attr]
            tokens = response.usage.input_tokens + response.usage.output_tokens

            reasoning = extract_json(content)
            return reasoning, tokens

        except anthropic.RateLimitError:
            logger.warning(f"Stage 4: Rate limit hit on Claude reasoning (attempt {attempt})")
            raise RateLimitError("Rate limit exceeded", stage="validation")

        except anthropic.APIError as e:
            logger.error(f"Stage 4: Claude API error - {str(e)}")
            raise ClaudeAPIError(
                str(e), stage="validation", retry_count=attempt,
                status_code=getattr(e, "status_code", None),
            )

        except ExtractionError:
            raise

        except Exception as e:
            logger.warning(f"Stage 4: Claude reasoning failed, continuing without it: {e}")
            return {}, 0


# Self-register at import time
from src.extraction.registry import registry  # noqa: E402
registry.register(ValidationStage())
