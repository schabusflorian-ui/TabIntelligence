"""Shared utilities for extraction pipeline."""

import json
import re
from typing import List, Union

from src.core.exceptions import ExtractionError
from src.core.logging import extraction_logger as logger


def validate_canonical_names(mappings: List[dict], stage: str) -> List[dict]:
    """Validate canonical_names in mapping results against taxonomy.

    Invalid (hallucinated) names are replaced with 'unmapped' at confidence 0.0
    so Stage 5 can re-attempt the mapping.

    Args:
        mappings: List of mapping dicts with canonical_name keys
        stage: Stage identifier for logging (e.g. "3", "5")

    Returns:
        The (mutated) mappings list
    """
    from src.extraction.taxonomy_loader import get_all_canonical_names

    valid = get_all_canonical_names()
    for m in mappings:
        canonical = m.get("canonical_name", "")
        if canonical and canonical not in valid:
            logger.warning(
                f"Stage {stage}: Hallucinated canonical_name '{canonical}' "
                f"for label '{m.get('original_label', '?')}', resetting to unmapped"
            )
            m["canonical_name"] = "unmapped"
            m["confidence"] = 0.0
    return mappings


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
    for match in re.finditer(r"[\[{]", content):
        try:
            return json.loads(content[match.start() :])
        except json.JSONDecodeError:
            continue

    logger.error("Failed to parse Claude response as JSON")
    logger.error(f"Response content preview (first 500 chars): {content[:500]}")
    raise ExtractionError(
        "Claude returned invalid JSON. This will trigger a retry.",
        stage="json_parsing",
    )
