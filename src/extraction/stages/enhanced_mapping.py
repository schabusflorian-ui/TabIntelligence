"""Stage 5: Enhanced Mapping - Re-map with full taxonomy context and entity patterns."""
import json
import time
from typing import Any, Dict, List, Optional

import anthropic

from src.core.exceptions import ClaudeAPIError, ExtractionError, RateLimitError
from src.core.logging import extraction_logger as logger, log_performance
from src.core.retry import retry
from src.extraction.base import ExtractionStage, PipelineContext
from src.extraction.claude_client import get_claude_client
from src.extraction.prompts import get_prompt
from src.extraction.utils import extract_json
from src.extraction.taxonomy_loader import (
    load_taxonomy_json,
    format_taxonomy_detailed,
    TAXONOMY_PATH,  # Re-exported for backward compat with tests that patch it
)


# Backward-compatible aliases for tests
def _load_taxonomy() -> Dict:
    """Load the full taxonomy JSON file."""
    # Check module-level TAXONOMY_PATH to support test patching
    import src.extraction.stages.enhanced_mapping as _self
    path = getattr(_self, "TAXONOMY_PATH", TAXONOMY_PATH)
    if not path.exists():
        return {"categories": {}}
    return load_taxonomy_json()


def _format_taxonomy_for_prompt(taxonomy: Dict) -> str:
    """Format taxonomy dict into a concise prompt-ready string.

    Args:
        taxonomy: Dict with 'categories' key mapping to lists of items.
    """
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
            # Still persist patterns even when no remapping needed
            self._persist_entity_patterns(context, basic_mappings)
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
        taxonomy_str = format_taxonomy_detailed()

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

            # Persist learned patterns for future entity extractions
            patterns_saved = self._persist_entity_patterns(context, final_mappings)

            logger.info(
                f"Stage 5: Enhanced Mapping completed - "
                f"{len(items_to_remap)} candidates, {remapped_count} improved, "
                f"{patterns_saved} patterns saved"
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
        """Build entity context string from DB patterns + current high-confidence mappings."""
        patterns = []

        # Load learned patterns from database if entity_id is available
        entity_id = getattr(context, "entity_id", None)
        if entity_id:
            try:
                from src.db.session import get_db_sync
                from src.db import crud
                from uuid import UUID

                with get_db_sync() as db:
                    db_patterns = crud.get_entity_patterns(
                        db, UUID(context.entity_id), min_confidence=0.7, limit=20
                    )
                    for p in db_patterns:
                        patterns.append(
                            f"  '{p.original_label}' -> {p.canonical_name} "
                            f"({float(p.confidence):.0%}, seen {p.occurrence_count}x)"
                        )
                if patterns:
                    logger.info(f"Stage 5: Loaded {len(patterns)} learned patterns from DB")
            except Exception as e:
                logger.warning(f"Stage 5: Could not load entity patterns from DB: {e}")

        # Supplement with high-confidence mappings from current extraction
        high_conf = [m for m in mappings if m.get("confidence", 0) >= 0.85]
        existing_labels = {line.split("'")[1] for line in patterns if "'" in line}

        for m in high_conf[:10]:
            if m["original_label"] not in existing_labels:
                patterns.append(
                    f"  '{m['original_label']}' -> {m['canonical_name']} ({m['confidence']:.0%})"
                )

        if not patterns:
            return "No entity-specific patterns available."

        return (
            f"Known patterns from this entity (high-confidence mappings):\n"
            + "\n".join(patterns[:20])
        )

    def _persist_entity_patterns(
        self, context: PipelineContext, final_mappings: List[Dict]
    ) -> int:
        """Persist high-confidence mappings as entity patterns for future use."""
        entity_id = getattr(context, "entity_id", None)
        if not entity_id:
            return 0

        try:
            from src.db.session import get_db_sync
            from src.db import crud
            from uuid import UUID

            with get_db_sync() as db:
                count = crud.bulk_upsert_entity_patterns(
                    db=db,
                    entity_id=UUID(context.entity_id),
                    mappings=final_mappings,
                    min_confidence=0.8,
                    created_by="claude",
                )
            logger.info(f"Stage 5: Persisted {count} entity patterns to DB")
            return count
        except Exception as e:
            logger.warning(f"Stage 5: Could not persist entity patterns: {e}")
            return 0

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
