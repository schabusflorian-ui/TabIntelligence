"""Stage 3: Guided Mapping - Map line items to canonical taxonomy."""
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


class MappingStage(ExtractionStage):
    """Stage 3: Map line items to canonical taxonomy."""

    @property
    def name(self) -> str:
        return "mapping"

    @property
    def stage_number(self) -> int:
        return 3

    @retry(max_attempts=3, backoff_seconds=2)
    async def execute(self, context: PipelineContext, attempt: int = 1) -> Dict[str, Any]:
        """Map extracted line items to canonical financial taxonomy."""
        logger.info(f"Stage 3: Mapping - Attempt {attempt}/3")
        start_time = time.time()

        parsed_result = context.get_result("parsing")["parsed"]

        # Extract unique labels
        labels = set()
        for sheet in parsed_result.get("sheets", []):
            for row in sheet.get("rows", []):
                if row.get("label"):
                    labels.add(row["label"])

        if not labels:
            logger.warning("Stage 3: No labels found to map")
            return {"mappings": [], "tokens": 0, "lineage_metadata": {}}

        try:
            logger.debug(
                f"Calling Claude API for mapping {len(labels)} items (attempt {attempt}/3)"
            )

            response = get_claude_client().messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": get_prompt("mapping").render(
                        line_items=json.dumps(list(labels), indent=2)
                    ),
                }],
            )

            content = response.content[0].text
            mappings = extract_json(content)

            duration = time.time() - start_time
            tokens = response.usage.input_tokens + response.usage.output_tokens

            mappings_list = mappings if isinstance(mappings, list) else []
            unmapped = sum(
                1 for m in mappings_list if m.get("canonical_name") == "unmapped"
            )
            avg_conf = (
                sum(m.get("confidence", 0) for m in mappings_list) / len(mappings_list)
                if mappings_list
                else 0
            )

            log_performance(
                logger,
                "stage_3_mapping",
                duration,
                {
                    "tokens": tokens,
                    "labels": len(labels),
                    "mappings": len(mappings_list),
                    "attempt": attempt,
                },
            )

            logger.info(
                f"Stage 3: Mapping completed - {len(mappings_list)} items mapped"
            )

            return {
                "mappings": mappings_list,
                "tokens": tokens,
                "lineage_metadata": {
                    "mappings_count": len(mappings_list),
                    "unmapped_count": unmapped,
                    "avg_confidence": round(avg_conf, 3),
                },
            }

        except anthropic.RateLimitError:
            logger.warning(f"Stage 3: Rate limit hit on attempt {attempt}/3")
            raise RateLimitError("Rate limit exceeded", stage="mapping")

        except anthropic.APIError as e:
            logger.error(
                f"Stage 3: Claude API error on attempt {attempt}/3 - {str(e)}"
            )
            raise ClaudeAPIError(
                str(e),
                stage="mapping",
                retry_count=attempt,
                status_code=getattr(e, "status_code", None),
            )

        except ExtractionError:
            raise

        except Exception as e:
            logger.error(
                f"Stage 3: Unexpected error on attempt {attempt}/3 - {str(e)}"
            )
            raise ExtractionError(f"Mapping failed: {str(e)}", stage="mapping")


# Self-register at import time
from src.extraction.registry import registry  # noqa: E402
registry.register(MappingStage())
