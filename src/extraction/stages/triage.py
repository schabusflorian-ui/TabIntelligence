"""Stage 2: Guided Triage - Classify sheets into processing tiers."""

import json
import time
from typing import Any, Dict, List, Optional

import anthropic

from src.core.exceptions import ClaudeAPIError, ExtractionError, RateLimitError
from src.core.logging import extraction_logger as logger
from src.core.logging import log_performance
from src.extraction.base import ExtractionStage, PipelineContext
from src.extraction.claude_client import get_claude_client
from src.extraction.prompts import get_prompt
from src.extraction.section_detector import SectionDetector
from src.extraction.utils import extract_json

# Deterministic sheet classification rules (skip Claude when confident)
_TIER_1_PATTERNS = [
    "income statement", "p&l", "profit and loss", "profit & loss",
    "balance sheet", "statement of financial position",
    "cash flow", "cash flows", "cf statement",
]
_TIER_2_PATTERNS = [
    "debt schedule", "debt service", "debt summary", "debt_dsra",
    "depreciation", "d&a", "amortization", "amortisation",
    "working capital", "capex", "tax schedule", "tax provision",
    "revenue build", "opex build", "revenue_grants",
    "cfads", "waterfall", "debt tranche",
]
_TIER_3_PATTERNS = [
    "assumptions", "inputs", "sensitivity", "scenario",
    "cap table", "returns", "irr", "macro", "techspec",
    "commodity", "curves",
]
_TIER_4_PATTERNS = [
    "scratch", "draft", "old", "backup", "chart", "notes",
    "instructions", "template", "readme", "cover",
    "table of contents", "toc", "changelog",
]


def _rule_based_triage(sheet_summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Attempt deterministic triage from sheet name and structural signals.

    Returns a triage entry dict if confident, None if ambiguous (defer to Claude).
    """
    name = sheet_summary.get("name", "").lower().strip()
    row_count = sheet_summary.get("row_count", 0)
    has_numeric = any(
        isinstance(r, (int, float)) for r in sheet_summary.get("sample_labels", [])
    )

    # Very few rows or no data → skip
    if row_count < 3:
        return {
            "sheet_name": sheet_summary["name"],
            "tier": 4,
            "decision": "SKIP",
            "reasoning": "Too few rows for meaningful content",
        }

    # Check patterns in priority order
    for pattern in _TIER_1_PATTERNS:
        if pattern in name:
            category = None
            if any(p in name for p in ["income", "p&l", "profit"]):
                category = "income_statement"
            elif "balance" in name or "financial position" in name:
                category = "balance_sheet"
            elif "cash flow" in name or "cf " in name:
                category = "cash_flow"
            return {
                "sheet_name": sheet_summary["name"],
                "tier": 1,
                "decision": "PROCESS",
                "reasoning": f"Rule-based: sheet name matches '{pattern}'",
                "category_hint": category,
            }

    for pattern in _TIER_2_PATTERNS:
        if pattern in name:
            category = None
            if any(p in name for p in ["debt", "dsra", "tranche"]):
                category = "debt_schedule"
            return {
                "sheet_name": sheet_summary["name"],
                "tier": 2,
                "decision": "PROCESS",
                "reasoning": f"Rule-based: sheet name matches '{pattern}'",
                "category_hint": category,
            }

    for pattern in _TIER_3_PATTERNS:
        if pattern in name:
            return {
                "sheet_name": sheet_summary["name"],
                "tier": 3,
                "decision": "PROCESS",
                "reasoning": f"Rule-based: sheet name matches '{pattern}'",
            }

    for pattern in _TIER_4_PATTERNS:
        if pattern in name:
            return {
                "sheet_name": sheet_summary["name"],
                "tier": 4,
                "decision": "SKIP",
                "reasoning": f"Rule-based: sheet name matches '{pattern}'",
            }

    # Ambiguous — defer to Claude
    return None


class TriageStage(ExtractionStage):
    """Stage 2: Triage sheets into processing tiers."""

    @property
    def name(self) -> str:
        return "triage"

    @property
    def stage_number(self) -> int:
        return 2

    @staticmethod
    def _build_sheet_summary(
        parsed_result: Dict[str, Any],
        structured: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Build enriched sheet summaries using both parsed and structured data.

        Falls back gracefully to parsed-only data when structured data is
        unavailable (e.g. in tests that don't provide it).
        """
        # Build a lookup from sheet name -> structured sheet data
        structured_lookup: Dict[str, Dict[str, Any]] = {}
        if structured:
            for s in structured.get("sheets", []):
                structured_lookup[s.get("sheet_name", "")] = s

        summaries: List[Dict[str, Any]] = []
        for s in parsed_result.get("sheets", []):
            sheet_name = s.get("sheet_name", "Unknown")
            summary: Dict[str, Any] = {
                "name": sheet_name,
                "type_guess": s.get("sheet_type", "unknown"),
                "row_count": len(s.get("rows", [])),
                "sample_labels": [r.get("label", "") for r in s.get("rows", [])[:5]],
            }

            # Enrich from structured data if available
            struct_sheet = structured_lookup.get(sheet_name)
            if struct_sheet:
                rows = struct_sheet.get("rows", [])
                bold_labels: List[str] = []
                formula_count = 0
                has_subtotals = False

                for row in rows:
                    cells = row.get("cells", [])
                    if not cells:
                        continue
                    first_cell = cells[0]
                    # Collect bold labels (section headers)
                    if first_cell.get("is_bold") and isinstance(first_cell.get("value"), str):
                        bold_labels.append(first_cell["value"])
                    # Count formulas across all cells
                    for cell in cells:
                        if cell.get("formula"):
                            formula_count += 1
                    # Detect subtotals
                    if first_cell.get("is_subtotal") or row.get("is_subtotal"):
                        has_subtotals = True

                summary["bold_labels"] = bold_labels[:10]  # Limit for token efficiency
                summary["formula_count"] = formula_count
                summary["has_subtotals"] = has_subtotals
                summary["merged_count"] = len(struct_sheet.get("merged_regions", []))

                # Detect sections for multi-statement sheets (WS-3)
                detector = SectionDetector()
                sections = detector.detect_sections(struct_sheet)
                if len(sections) > 1:
                    summary["sections"] = [
                        {
                            "label": sec.label,
                            "start_row": sec.start_row,
                            "end_row": sec.end_row,
                            "row_count": sec.row_count,
                            "category_hint": sec.category_hint,
                            "sample_labels": sec.sample_labels,
                            "bold_labels": sec.bold_labels[:5],
                            "has_subtotals": sec.has_subtotals,
                            "formula_count": sec.formula_count,
                        }
                        for sec in sections
                    ]

            # Propagate label→value layout flag from parsing stage
            if struct_sheet and struct_sheet.get("is_label_value"):
                summary["is_label_value"] = True

            summaries.append(summary)

        return summaries

    @property
    def timeout_seconds(self):
        return 60.0

    @property
    def max_retries(self):
        return 3

    def validate_output(self, result):
        triage_list = result.get("triage", [])
        if not triage_list:
            return "Triage produced zero sheet classifications"
        valid_tiers = {1, 2, 3, 4}
        for entry in triage_list:
            if entry.get("tier") not in valid_tiers:
                return f"Triage entry missing valid tier: {entry.get('sheet_name', '?')}"
        return None

    async def execute(self, context: PipelineContext) -> Dict[str, Any]:
        """Classify sheets into processing tiers using Claude."""
        logger.info("Stage 2: Triage started")
        start_time = time.time()

        parsing_result = context.get_result("parsing")
        parsed_result = parsing_result["parsed"]
        structured = parsing_result.get("structured", {})

        sheets_summary = self._build_sheet_summary(parsed_result, structured)

        try:
            logger.debug("Calling Claude API for triage")

            response = get_claude_client().messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                messages=[
                    {
                        "role": "user",
                        "content": get_prompt("triage").render(
                            sheets=json.dumps(sheets_summary, indent=2)
                        ),
                    }
                ],
            )

            # Check for truncation — incomplete JSON causes silent data loss
            if response.stop_reason == "max_tokens":
                logger.warning(
                    f"Stage 2: Response truncated at max_tokens "
                    f"({response.usage.output_tokens} tokens)."
                )
                raise ExtractionError(
                    "Triage response truncated: output exceeded token limit.",
                    stage="triage",
                )

            content = response.content[0].text  # type: ignore[union-attr]
            triage = extract_json(content)

            duration = time.time() - start_time
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            tokens = input_tokens + output_tokens

            log_performance(
                logger,
                "stage_2_triage",
                duration,
                {"tokens": tokens, "sheets": len(sheets_summary)},
            )

            triage_list = triage if isinstance(triage, list) else []

            # Normalize section entries: ensure all have section fields (WS-3)
            for entry in triage_list:
                entry.setdefault("section", None)
                entry.setdefault("section_start_row", None)
                entry.setdefault("section_end_row", None)

            # Annotate triage entries from label→value sheets
            label_value_names = {
                s["name"] for s in sheets_summary if s.get("is_label_value")
            }
            label_value_count = 0
            for entry in triage_list:
                if entry.get("sheet_name") in label_value_names:
                    entry["layout_type"] = "label_value"
                    label_value_count += 1
                else:
                    entry.setdefault("layout_type", "time_series")

            if label_value_count:
                logger.info(
                    f"Stage 2: {label_value_count} sheet(s) tagged as "
                    f"label→value layout (static parameters)"
                )

            logger.info(f"Stage 2: Triage completed - {len(triage_list)} entries classified")

            # Build tier counts for lineage metadata
            tier_counts = {f"tier_{i}_count": 0 for i in range(1, 5)}
            for t in triage_list:
                tier = t.get("tier", 4)
                tier_counts[f"tier_{tier}_count"] += 1

            # Section detection metrics
            total_sections = sum(len(s.get("sections", [])) for s in sheets_summary)
            multi_section_sheets = sum(1 for s in sheets_summary if "sections" in s)

            return {
                "triage": triage_list,
                "tokens": tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "lineage_metadata": {
                    **tier_counts,
                    "total_sections_detected": total_sections,
                    "multi_section_sheets": multi_section_sheets,
                    "label_value_sheets": label_value_count,
                },
            }

        except anthropic.RateLimitError as e:
            retry_after = getattr(e.response, "headers", {}).get("retry-after")
            logger.warning(f"Stage 2: Rate limit hit (retry-after={retry_after})")
            raise RateLimitError(
                "Rate limit exceeded",
                stage="triage",
                retry_after=int(retry_after) if retry_after else None,
            )

        except anthropic.APIError as e:
            logger.error(f"Stage 2: Claude API error - {str(e)}")
            raise ClaudeAPIError(
                str(e),
                stage="triage",
                status_code=getattr(e, "status_code", None),
            )

        except ExtractionError:
            raise

        except Exception as e:
            logger.error(f"Stage 2: Unexpected error - {str(e)}")
            raise ExtractionError(f"Triage failed: {str(e)}", stage="triage")


# Self-register at import time
from src.extraction.registry import registry  # noqa: E402

registry.register(TriageStage())
