"""Shared utilities for extraction pipeline."""
import json
import re
from typing import Union

from src.core.logging import extraction_logger as logger
from src.core.exceptions import ExtractionError


def extract_json(content: str) -> Union[dict, list]:
    """
    Extract JSON from Claude's response.

    Tries multiple strategies:
    1. Direct JSON parse
    2. Markdown code blocks (```json ... ```)
    3. Find first [ or { and parse from there

    Raises ExtractionError if JSON cannot be parsed, to trigger retry logic.
    """
    # Strategy 1: Direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Markdown code blocks
    if "```json" in content:
        block = content.split("```json")[1].split("```")[0]
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            pass
    elif "```" in content:
        block = content.split("```")[1].split("```")[0]
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find first JSON object or array in the text
    for match in re.finditer(r'[\[{]', content):
        try:
            return json.loads(content[match.start():])
        except json.JSONDecodeError:
            continue

    logger.error(f"Failed to parse Claude response as JSON")
    logger.error(f"Response content preview (first 500 chars): {content[:500]}")
    raise ExtractionError(
        f"Claude returned invalid JSON. This will trigger a retry.",
        stage="json_parsing",
    )
