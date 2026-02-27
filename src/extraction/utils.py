"""Shared utilities for extraction pipeline."""
import json
from typing import Union

from src.core.logging import extraction_logger as logger
from src.core.exceptions import ExtractionError


def extract_json(content: str) -> Union[dict, list]:
    """
    Extract JSON from Claude's response.

    Raises ExtractionError if JSON cannot be parsed, to trigger retry logic.

    Args:
        content: Raw text response from Claude

    Returns:
        Parsed JSON dict or list

    Raises:
        ExtractionError: If JSON parsing fails after all attempts
    """
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try to extract from markdown code blocks
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    try:
        return json.loads(content.strip())
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {str(e)}")
        logger.error(f"Response content preview (first 500 chars): {content[:500]}")
        raise ExtractionError(
            f"Claude returned invalid JSON: {str(e)}. This will trigger a retry.",
            stage="json_parsing",
        )
