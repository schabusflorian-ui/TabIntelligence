"""Stage 5: Enhanced Mapping - Re-map with full taxonomy context and entity patterns."""

import json
import time
from typing import Any, Dict, List, Optional

import anthropic

from src.core.config import get_settings
from src.core.exceptions import ClaudeAPIError, ExtractionError, RateLimitError
from src.core.logging import extraction_logger as logger
from src.core.logging import log_performance
from src.extraction.base import ExtractionStage, PipelineContext
from src.extraction.claude_client import get_claude_client
from src.extraction.prompts import get_prompt
from src.extraction.taxonomy_loader import (
    TAXONOMY_PATH,  # Re-exported for backward compat with tests that patch it
    format_taxonomy_detailed,
    load_taxonomy_json,
)
from src.extraction.utils import extract_json, validate_canonical_names


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
                aliases_str = f" (aliases: {', '.join(item['aliases'][:5])})"
            names.append(
                f"  - {item['canonical_name']}: {item.get('display_name', '')}{aliases_str}"
            )
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

    @property
    def timeout_seconds(self):
        return 90.0

    def should_skip(self, context: PipelineContext) -> bool:
        """Skip if no candidates need re-mapping."""
        try:
            basic_mappings = context.get_result("mapping")["mappings"]
            validation_result = context.results.get("validation", {})
            candidates = self._find_remapping_candidates(basic_mappings, validation_result)
            if not candidates:
                logger.info("Stage 5: Skipping enhanced mapping (no candidates)")
                return True
            return False
        except KeyError:
            return False

    async def execute(self, context: PipelineContext) -> Dict[str, Any]:
        """Re-map items that Stage 3 couldn't confidently map."""
        logger.info("Stage 5: Enhanced Mapping started")
        start_time = time.time()

        parse_result = context.get_result("parsing")["parsed"]
        basic_mappings = context.get_result("mapping")["mappings"]
        validation_result = context.results.get("validation", {})

        # Identify items that need re-mapping (including validation failures)
        items_to_remap = self._find_remapping_candidates(basic_mappings, validation_result)

        if not items_to_remap:
            logger.info("Stage 5: No items need re-mapping, all confidently mapped")
            # Still persist patterns even when no remapping needed
            self._persist_entity_patterns(context, basic_mappings)
            return {
                "enhanced_mappings": basic_mappings,
                "remapped_count": 0,
                "tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
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
            # Annotate validation-failed items for the prompt
            items_for_prompt = []
            for item in items_to_remap:
                item_copy = dict(item)
                vc = item_copy.pop("validation_context", None)
                if vc and vc.get("validation_failed"):
                    item_copy["original_label"] = (
                        f"{item_copy['original_label']} [VALIDATION FAILED: {vc['failed_rule']}]"
                    )
                items_for_prompt.append(item_copy)

            response = get_claude_client().messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                messages=[
                    {
                        "role": "user",
                        "content": get_prompt("enhanced_mapping").render(
                            items_to_remap=json.dumps(items_for_prompt, indent=2),
                            taxonomy=taxonomy_str,
                            entity_context=entity_context,
                            hierarchy_context=json.dumps(hierarchy_context, indent=2),
                        ),
                    }
                ],
            )

            # Check for truncation — incomplete JSON causes silent data loss
            if response.stop_reason == "max_tokens":
                logger.warning(
                    f"Stage 5: Response truncated at max_tokens "
                    f"({response.usage.output_tokens} tokens)."
                )
                raise ExtractionError(
                    "Enhanced mapping response truncated: output exceeded token limit. "
                    f"Tried to re-map {len(items_to_remap)} items in one pass.",
                    stage="enhanced_mapping",
                )

            content = response.content[0].text  # type: ignore[union-attr]
            enhanced = extract_json(content)
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            tokens = input_tokens + output_tokens

            # Validate canonical names against taxonomy
            if isinstance(enhanced, list):
                validate_canonical_names(enhanced, stage="5")

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
                        new_mapping["enhanced_mapping_provenance"] = {
                            "was_remapped": True,
                            "old_canonical": m.get("canonical_name"),
                            "old_confidence": m.get("confidence"),
                            "new_canonical": new_mapping.get("canonical_name"),
                            "new_confidence": new_mapping.get("confidence"),
                            "stage": 5,
                        }
                        final_mappings.append(new_mapping)
                        remapped_count += 1
                        continue
                m["enhanced_mapping_provenance"] = None
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
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "lineage_metadata": {
                    "candidates": len(items_to_remap),
                    "remapped": remapped_count,
                    "avg_confidence_before": round(
                        sum(m.get("confidence", 0) for m in items_to_remap)
                        / max(len(items_to_remap), 1),
                        3,
                    ),
                    "avg_confidence_after": round(
                        sum(m.get("confidence", 0) for m in final_mappings)
                        / max(len(final_mappings), 1),
                        3,
                    ),
                },
            }

        except anthropic.RateLimitError as e:
            retry_after = getattr(e.response, "headers", {}).get("retry-after")
            logger.warning(f"Stage 5: Rate limit hit (retry-after={retry_after})")
            raise RateLimitError(
                "Rate limit exceeded",
                stage="enhanced_mapping",
                retry_after=int(retry_after) if retry_after else None,
            )

        except anthropic.APIError as e:
            logger.error(f"Stage 5: Claude API error - {str(e)}")
            raise ClaudeAPIError(
                str(e),
                stage="enhanced_mapping",
                status_code=getattr(e, "status_code", None),
            )

        except ExtractionError:
            raise

        except Exception as e:
            logger.error(f"Stage 5: Unexpected error - {str(e)}")
            raise ExtractionError(f"Enhanced mapping failed: {str(e)}", stage="enhanced_mapping")

    def _find_remapping_candidates(
        self,
        mappings: List[Dict],
        validation_result: Optional[Dict] = None,
    ) -> List[Dict]:
        """Find items that are unmapped, have low confidence, or failed validation.

        Items with error-severity validation flags become candidates with
        a validation_context dict attached.
        """
        # Build set of canonical names with error-severity validation failures
        validation_failed: Dict[str, str] = {}  # canonical -> rule
        if validation_result:
            flags = validation_result.get("validation", {}).get("flags", [])
            for flag in flags:
                if flag.get("severity") == "error":
                    canonical = flag.get("item", "")
                    rule = flag.get("rule", "")
                    if canonical and canonical not in validation_failed:
                        validation_failed[canonical] = rule

        candidates = []
        seen_labels = set()
        for m in mappings:
            confidence = m.get("confidence", 0)
            canonical = m.get("canonical_name", "")
            label = m.get("original_label", "")

            if canonical == "unmapped" or confidence < 0.8:
                if label not in seen_labels:
                    candidates.append(dict(m))
                    seen_labels.add(label)
            elif canonical in validation_failed:
                if label not in seen_labels:
                    candidate = dict(m)
                    candidate["validation_context"] = {
                        "validation_failed": True,
                        "failed_rule": validation_failed[canonical],
                    }
                    candidates.append(candidate)
                    seen_labels.add(label)
        return candidates

    def _build_entity_context(self, context: PipelineContext, mappings: List[Dict]) -> str:
        """Build entity context string from DB patterns + current high-confidence mappings."""
        patterns = []

        # Load learned patterns from database if entity_id is available
        entity_id = getattr(context, "entity_id", None)
        if entity_id:
            try:
                from uuid import UUID

                from src.db import crud
                from src.db.session import get_db_sync

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

        return "Known patterns from this entity (high-confidence mappings):\n" + "\n".join(
            patterns[:20]
        )

    def _persist_entity_patterns(self, context: PipelineContext, final_mappings: List[Dict]) -> int:
        """Persist high-confidence mappings as entity patterns for future use.

        Also resolves pattern conflicts (deactivates losing patterns) and
        records learned aliases for taxonomy enrichment.
        """
        settings = get_settings()
        entity_id = getattr(context, "entity_id", None)
        if not entity_id:
            return 0

        try:
            from uuid import UUID

            from src.db import crud
            from src.db.session import get_db_sync

            entity_uuid = UUID(context.entity_id)

            with get_db_sync() as db:
                count = crud.bulk_upsert_entity_patterns(
                    db=db,
                    entity_id=entity_uuid,
                    mappings=final_mappings,
                    min_confidence=settings.taxonomy_pattern_persist_confidence,
                    created_by="claude",
                )

                # Resolve any conflicting patterns
                deactivated = crud.resolve_pattern_conflicts(db, entity_uuid)
                if deactivated:
                    logger.info(f"Stage 5: Resolved {deactivated} conflicting patterns")

            # Record learned aliases (separate DB session for isolation)
            aliases_recorded = self._record_learned_aliases(context, final_mappings)

            # Check for auto-promotions if aliases were recorded
            if aliases_recorded > 0:
                try:
                    from src.db import crud as crud_module
                    from src.db.session import get_db_sync

                    with get_db_sync() as db:
                        promoted = crud_module.check_auto_promotions(db)
                        if promoted:
                            logger.info(f"Stage 5: Auto-promoted {promoted} learned aliases")
                except Exception as e:
                    logger.warning(f"Stage 5: Auto-promotion check failed: {e}")

            logger.info(f"Stage 5: Persisted {count} entity patterns to DB")
            return count
        except Exception as e:
            logger.warning(f"Stage 5: Could not persist entity patterns: {e}")
            return 0

    def _record_learned_aliases(self, context: PipelineContext, mappings: List[Dict]) -> int:
        """Record high-confidence mappings as learned aliases if not in taxonomy.

        When Claude maps a label to a canonical name with high confidence
        and the label is not already in the taxonomy's aliases, record it
        as a learned alias for potential future promotion to the taxonomy.
        """
        settings = get_settings()
        entity_id = getattr(context, "entity_id", None)
        if not entity_id:
            return 0

        try:
            from src.db import crud
            from src.db.session import get_db_sync

            # Load taxonomy aliases for lookup
            taxonomy = load_taxonomy_json()
            alias_lookup: dict[str, set] = {}
            for category_items in taxonomy.get("categories", {}).values():
                for item in category_items:
                    canonical = item.get("canonical_name", "")
                    aliases = set(item.get("aliases", []))
                    aliases.add(canonical)
                    if item.get("display_name"):
                        aliases.add(item["display_name"])
                    alias_lookup[canonical] = {a.lower() for a in aliases}

            count = 0
            with get_db_sync() as db:
                for m in mappings:
                    confidence = m.get("confidence", 0)
                    canonical = m.get("canonical_name", "")
                    label = m.get("original_label", "")

                    if confidence < settings.taxonomy_learned_alias_confidence or canonical == "unmapped" or not label:
                        continue

                    # Check if label is already a known alias
                    known_aliases = alias_lookup.get(canonical, set())
                    if label.lower() in known_aliases:
                        continue

                    crud.record_learned_alias(db, canonical, label, entity_id)
                    count += 1

            if count:
                logger.info(f"Stage 5: Recorded {count} learned aliases")
            return count

        except Exception as e:
            logger.warning(f"Stage 5: Could not record learned aliases: {e}")
            return 0

    def _build_hierarchy_context(self, parsed: Dict, candidates: List[Dict]) -> List[Dict]:
        """Build hierarchy context for unmapped items (surrounding rows)."""
        candidate_labels = {c["original_label"] for c in candidates}
        context_items = []

        for sheet in parsed.get("sheets", []):
            rows = sheet.get("rows", [])
            for i, row in enumerate(rows):
                if row.get("label") in candidate_labels:
                    # Get surrounding rows for context (±3 window)
                    neighbors = []
                    section_header = None
                    for j in range(max(0, i - 3), min(len(rows), i + 4)):
                        if j != i:
                            neighbor = rows[j]
                            neighbors.append(neighbor.get("label", ""))
                            # Detect section headers (rows above with
                            # hierarchy_level 0 that aren't subtotals)
                            if (
                                j < i
                                and neighbor.get("hierarchy_level", 1) == 0
                                and not neighbor.get("is_subtotal", False)
                            ):
                                section_header = neighbor.get("label", "")

                    context_items.append(
                        {
                            "label": row.get("label"),
                            "sheet": sheet.get("sheet_name"),
                            "hierarchy_level": row.get("hierarchy_level", 1),
                            "is_subtotal": row.get("is_subtotal", False),
                            "is_formula": row.get("is_formula", False),
                            "nearby_labels": neighbors,
                            "section_header": section_header,
                        }
                    )

        return context_items


# Self-register at import time
from src.extraction.registry import registry  # noqa: E402

registry.register(EnhancedMappingStage())
