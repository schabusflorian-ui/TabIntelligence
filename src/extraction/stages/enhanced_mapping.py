"""Stage 5: Enhanced Mapping - Re-map with full taxonomy context and entity patterns."""
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic

from src.core.exceptions import ClaudeAPIError, ExtractionError, RateLimitError
from src.core.logging import extraction_logger as logger, log_performance
from src.core.retry import retry
from src.extraction.base import ExtractionStage, PipelineContext
from src.extraction.claude_client import get_claude_client
from src.extraction.prompts import get_prompt
from src.extraction.utils import extract_json

# Path to full taxonomy JSON
TAXONOMY_PATH = Path(__file__).parent.parent.parent.parent / "data" / "taxonomy.json"


def _load_taxonomy() -> Dict:
    """Load the full taxonomy JSON file."""
    if TAXONOMY_PATH.exists():
        with open(TAXONOMY_PATH) as f:
            return json.load(f)
    return {"categories": {}}


def _format_taxonomy_for_prompt(taxonomy: Dict) -> str:
    """Format taxonomy into a concise prompt-ready string."""
    lines = []
    for category, items in taxonomy.get("categories", {}).items():
        category_display = category.replace("_", " ").title()
        names = []
        for item in items:
            aliases_str = ""
            if item.get("aliases"):
                aliases_str = f" (aliases: {', '.join(item['aliases'][:3])})"
            names.append(f"  - {item['canonical_name']}: {item.get('display_name', '')}{aliases_str}")
        lines.append(f"{category_display}:")
        lines.extend(names)
    return "\n".join(lines)


class EnhancedMappingStage(ExtractionStage):
    """Stage 5: Re-map unmapped/low-confidence items using full taxonomy + entity context."""

    @property
    def name(self) -> str:
        return "enhanced_mapping"

    @property
    def stage_number(self) -> int:
        return 5

    @retry(max_attempts=2, backoff_seconds=2)
    async def execute(self, context: PipelineContext, attempt: int = 1) -> Dict[str, Any]:
        """Re-map items that Stage 3 couldn't confidently map."""
        logger.info(f"Stage 5: Enhanced Mapping - Attempt {attempt}/2")
        start_time = time.time()

        parse_result = context.get_result("parsing")["parsed"]
        basic_mappings = context.get_result("mapping")["mappings"]

        # Identify items that need re-mapping
        items_to_remap = self._find_remapping_candidates(basic_mappings)

        if not items_to_remap:
            logger.info("Stage 5: No items need re-mapping, all confidently mapped")
            return {
                "enhanced_mappings": basic_mappings,
                "remapped_count": 0,
                "tokens": 0,
                "lineage_metadata": {
                    "candidates": 0,
                    "remapped": 0,
                    "skipped": True,
                },
            }

        # Load full taxonomy for context
        taxonomy = _load_taxonomy()
        taxonomy_str = _format_taxonomy_for_prompt(taxonomy)

        # Build entity context if available
        entity_context = self._build_entity_context(context, basic_mappings)

        # Build hierarchy context from parsed data
        hierarchy_context = self._build_hierarchy_context(parse_result, items_to_remap)

        try:
            response = get_claude_client().messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": get_prompt("enhanced_mapping").render(
                        items_to_remap=json.dumps(items_to_remap, indent=2),
                        taxonomy=taxonomy_str,
                        entity_context=entity_context,
                        hierarchy_context=json.dumps(hierarchy_context, indent=2),
                    ),
                }],
            )

            content = response.content[0].text
            enhanced = extract_json(content)
            tokens = response.usage.input_tokens + response.usage.output_tokens

            # Merge enhanced mappings back into the full list
            enhanced_lookup = {}
            if isinstance(enhanced, list):
                enhanced_lookup = {e["original_label"]: e for e in enhanced}

            final_mappings = []
            remapped_count = 0
            for m in basic_mappings:
                label = m["original_label"]
                if label in enhanced_lookup:
                    new_mapping = enhanced_lookup[label]
                    # Only accept if confidence improved
                    if new_mapping.get("confidence", 0) > m.get("confidence", 0):
                        new_mapping["method"] = new_mapping.get("method", "enhanced")
                        final_mappings.append(new_mapping)
                        remapped_count += 1
                        continue
                final_mappings.append(m)

            duration = time.time() - start_time

            log_performance(
                logger,
                "stage_5_enhanced_mapping",
                duration,
                {
                    "tokens": tokens,
                    "candidates": len(items_to_remap),
                    "remapped": remapped_count,
                    "attempt": attempt,
                },
            )

            logger.info(
                f"Stage 5: Enhanced Mapping completed - "
                f"{len(items_to_remap)} candidates, {remapped_count} improved"
            )

            return {
                "enhanced_mappings": final_mappings,
                "remapped_count": remapped_count,
                "tokens": tokens,
                "lineage_metadata": {
                    "candidates": len(items_to_remap),
                    "remapped": remapped_count,
                    "avg_confidence_before": round(
                        sum(m.get("confidence", 0) for m in items_to_remap) / max(len(items_to_remap), 1), 3
                    ),
                    "avg_confidence_after": round(
                        sum(m.get("confidence", 0) for m in final_mappings) / max(len(final_mappings), 1), 3
                    ),
                },
            }

        except anthropic.RateLimitError:
            logger.warning(f"Stage 5: Rate limit hit (attempt {attempt})")
            raise RateLimitError("Rate limit exceeded", stage="enhanced_mapping")

        except anthropic.APIError as e:
            logger.error(f"Stage 5: Claude API error - {str(e)}")
            raise ClaudeAPIError(
                str(e), stage="enhanced_mapping", retry_count=attempt,
                status_code=getattr(e, "status_code", None),
            )

        except ExtractionError:
            raise

        except Exception as e:
            logger.error(f"Stage 5: Unexpected error - {str(e)}")
            raise ExtractionError(f"Enhanced mapping failed: {str(e)}", stage="enhanced_mapping")

    def _find_remapping_candidates(self, mappings: List[Dict]) -> List[Dict]:
        """Find items that are unmapped or have low confidence."""
        candidates = []
        for m in mappings:
            confidence = m.get("confidence", 0)
            canonical = m.get("canonical_name", "")
            if canonical == "unmapped" or confidence < 0.7:
                candidates.append(m)
        return candidates

    def _build_entity_context(
        self, context: PipelineContext, mappings: List[Dict]
    ) -> str:
        """Build entity context string for the prompt."""
        # Summarize what we already know about this entity's naming patterns
        high_conf = [m for m in mappings if m.get("confidence", 0) >= 0.85]
        if not high_conf:
            return "No entity-specific patterns available."

        patterns = []
        for m in high_conf[:10]:  # Top 10 confident mappings as context
            patterns.append(f"  '{m['original_label']}' -> {m['canonical_name']} ({m['confidence']:.0%})")

        return (
            f"Known patterns from this entity (high-confidence mappings):\n"
            + "\n".join(patterns)
        )

    def _build_hierarchy_context(
        self, parsed: Dict, candidates: List[Dict]
    ) -> List[Dict]:
        """Build hierarchy context for unmapped items (surrounding rows)."""
        candidate_labels = {c["original_label"] for c in candidates}
        context_items = []

        for sheet in parsed.get("sheets", []):
            rows = sheet.get("rows", [])
            for i, row in enumerate(rows):
                if row.get("label") in candidate_labels:
                    # Get surrounding rows for context
                    neighbors = []
                    for j in range(max(0, i - 2), min(len(rows), i + 3)):
                        if j != i:
                            neighbors.append(rows[j].get("label", ""))

                    context_items.append({
                        "label": row.get("label"),
                        "sheet": sheet.get("sheet_name"),
                        "hierarchy_level": row.get("hierarchy_level", 1),
                        "is_subtotal": row.get("is_subtotal", False),
                        "is_formula": row.get("is_formula", False),
                        "nearby_labels": neighbors,
                    })

        return context_items


# Self-register at import time
from src.extraction.registry import registry  # noqa: E402
registry.register(EnhancedMappingStage())
