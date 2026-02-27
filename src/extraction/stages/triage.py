"""Stage 2: Guided Triage - Classify sheets into processing tiers."""
import json
import time
from typing import Any, Dict

import anthropic

from src.core.exceptions import ClaudeAPIError, ExtractionError, RateLimitError
from src.core.logging import extraction_logger as logger, log_performance
from src.core.retry import retry
from src.extraction.base import ExtractionStage, PipelineContext
from src.extraction.claude_client import get_claude_client
from src.extraction.prompts import get_prompt
from src.extraction.utils import extract_json


class TriageStage(ExtractionStage):
    """Stage 2: Triage sheets into processing tiers."""

    @property
    def name(self) -> str:
        return "triage"

    @property
    def stage_number(self) -> int:
        return 2

    @retry(max_attempts=3, backoff_seconds=2)
    async def execute(self, context: PipelineContext, attempt: int = 1) -> Dict[str, Any]:
        """Classify sheets into processing tiers using Claude."""
        logger.info(f"Stage 2: Triage - Attempt {attempt}/3")
        start_time = time.time()

        parsed_result = context.get_result("parsing")["parsed"]

        sheets_summary = [
            {
                "name": s.get("sheet_name", "Unknown"),
                "type_guess": s.get("sheet_type", "unknown"),
                "row_count": len(s.get("rows", [])),
                "sample_labels": [r.get("label", "") for r in s.get("rows", [])[:5]],
            }
            for s in parsed_result.get("sheets", [])
        ]

        try:
            logger.debug(f"Calling Claude API for triage (attempt {attempt}/3)")

            response = get_claude_client().messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                messages=[{
                    "role": "user",
                    "content": get_prompt("triage").render(
                        sheets=json.dumps(sheets_summary, indent=2)
                    ),
                }],
            )

            content = response.content[0].text  # type: ignore[union-attr]
            triage = extract_json(content)

            duration = time.time() - start_time
            tokens = response.usage.input_tokens + response.usage.output_tokens

            log_performance(
                logger,
                "stage_2_triage",
                duration,
                {"tokens": tokens, "sheets": len(sheets_summary), "attempt": attempt},
            )

            triage_list = triage if isinstance(triage, list) else []
            logger.info(f"Stage 2: Triage completed - {len(triage_list)} sheets classified")

            # Build tier counts for lineage metadata
            tier_counts = {f"tier_{i}_count": 0 for i in range(1, 5)}
            for t in triage_list:
                tier = t.get("tier", 4)
                tier_counts[f"tier_{tier}_count"] += 1

            return {
                "triage": triage_list,
                "tokens": tokens,
                "lineage_metadata": tier_counts,
            }

        except anthropic.RateLimitError:
            logger.warning(f"Stage 2: Rate limit hit on attempt {attempt}/3")
            raise RateLimitError("Rate limit exceeded", stage="triage")

        except anthropic.APIError as e:
            logger.error(f"Stage 2: Claude API error on attempt {attempt}/3 - {str(e)}")
            raise ClaudeAPIError(
                str(e),
                stage="triage",
                retry_count=attempt,
                status_code=getattr(e, "status_code", None),
            )

        except ExtractionError:
            raise

        except Exception as e:
            logger.error(f"Stage 2: Unexpected error on attempt {attempt}/3 - {str(e)}")
            raise ExtractionError(f"Triage failed: {str(e)}", stage="triage")


# Self-register at import time
from src.extraction.registry import registry  # noqa: E402
registry.register(TriageStage())
