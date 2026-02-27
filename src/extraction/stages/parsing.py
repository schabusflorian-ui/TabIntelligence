"""Stage 1: Guided Parsing - Extract structured data from Excel files."""
import asyncio
import io
import time
from typing import Any, Dict

import anthropic
import openpyxl

from src.core.exceptions import ClaudeAPIError, ExtractionError, RateLimitError
from src.core.logging import extraction_logger as logger, log_performance, log_exception
from src.extraction.base import ExtractionStage, PipelineContext
from src.extraction.claude_client import get_claude_client
from src.extraction.prompts import get_prompt
from src.extraction.utils import extract_json


class ParsingStage(ExtractionStage):
    """Stage 1: Parse Excel with Claude."""

    @property
    def name(self) -> str:
        return "parsing"

    @property
    def stage_number(self) -> int:
        return 1

    async def execute(self, context: PipelineContext) -> Dict[str, Any]:
        """
        Parse Excel file bytes using Claude vision.

        Uses manual retry logic with exponential backoff for rate limits.
        """
        max_retries = 3
        retry_count = 0
        backoff_base = 2

        logger.info("Stage 1: Parsing started")
        start_time = time.time()

        # Pre-process Excel to text using openpyxl (Claude document API only supports PDFs)
        excel_text = self._excel_to_text(context.file_bytes)
        logger.debug(f"Converted Excel to text ({len(excel_text)} chars)")

        while retry_count < max_retries:
            try:
                logger.debug(f"Calling Claude API (attempt {retry_count + 1}/{max_retries})")

                prompt_text = get_prompt("parsing").content
                full_prompt = (
                    f"Below is the content of an Excel file, with each sheet shown separately.\n\n"
                    f"{excel_text}\n\n"
                    f"{prompt_text}"
                )

                response = get_claude_client().messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=8192,
                    messages=[{
                        "role": "user",
                        "content": full_prompt,
                    }],
                )

                content = response.content[0].text
                parsed = extract_json(content)

                tokens = response.usage.input_tokens + response.usage.output_tokens
                duration = time.time() - start_time

                log_performance(
                    logger,
                    "stage_1_parsing",
                    duration,
                    {"tokens": tokens, "sheets": len(parsed.get("sheets", []))},
                )

                sheets_count = len(parsed.get("sheets", []))
                logger.info(f"Stage 1: Parsing completed - {sheets_count} sheets found")

                return {
                    "parsed": parsed,
                    "tokens": tokens,
                    "lineage_metadata": {
                        "sheets_count": sheets_count,
                        "file_size_bytes": len(context.file_bytes),
                    },
                }

            except anthropic.RateLimitError:
                retry_count += 1
                wait_time = backoff_base ** retry_count

                logger.warning(
                    f"Stage 1: Rate limit hit (attempt {retry_count}/{max_retries}), "
                    f"waiting {wait_time}s before retry"
                )

                if retry_count >= max_retries:
                    error = RateLimitError(
                        "Rate limit exceeded after retries",
                        stage="parsing",
                        retry_after=wait_time,
                    )
                    log_exception(logger, error, {"retry_count": retry_count})
                    raise error

                await asyncio.sleep(wait_time)

            except anthropic.APIError as e:
                logger.error(f"Stage 1: Claude API error - {str(e)}")
                error = ClaudeAPIError(
                    str(e),
                    stage="parsing",
                    retry_count=retry_count,
                    status_code=getattr(e, "status_code", None),
                )
                log_exception(logger, error)
                raise error

            except ExtractionError:
                raise

            except Exception as e:
                logger.error(f"Stage 1: Unexpected error - {str(e)}")
                error = ExtractionError(f"Parsing failed: {str(e)}", stage="parsing")
                log_exception(logger, error)
                raise error

        raise ClaudeAPIError("Max retries exceeded", stage="parsing", retry_count=max_retries)

    @staticmethod
    def _excel_to_text(file_bytes: bytes) -> str:
        """Convert Excel file bytes to a text representation for Claude."""
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
        parts = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            parts.append(f"=== Sheet: {sheet_name} ===")
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                # Skip fully empty rows
                if any(cells):
                    parts.append("\t".join(cells))
            parts.append("")  # blank line between sheets
        wb.close()
        return "\n".join(parts)


# Self-register at import time
from src.extraction.registry import registry  # noqa: E402
registry.register(ParsingStage())
