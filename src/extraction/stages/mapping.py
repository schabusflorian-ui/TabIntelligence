"""Stage 3: Guided Mapping - Map line items to canonical taxonomy."""

import json
import time
from typing import Any, Dict, List, Optional, Set

import anthropic
from rapidfuzz import fuzz

from src.core.config import get_settings
from src.core.exceptions import ClaudeAPIError, ExtractionError, RateLimitError
from src.core.logging import extraction_logger as logger
from src.core.logging import log_performance
from src.extraction.base import ExtractionStage, PipelineContext
from src.extraction.claude_client import get_claude_client
from src.extraction.prompts import get_prompt
from src.extraction.taxonomy_loader import (
    format_taxonomy_for_prompt,
    get_alias_to_canonicals_with_priority,
    get_alias_to_canonicals_with_promoted,
    get_canonical_to_category,
)
from src.extraction.utils import extract_json, validate_canonical_names


# Backward-compatible alias for tests that import this directly
def _load_taxonomy_for_prompt(
    include_aliases: bool = True,
    categories: Optional[Set[str]] = None,
) -> str:
    """Load taxonomy from JSON and format as a concise prompt string."""
    return format_taxonomy_for_prompt(
        include_aliases=include_aliases, categories=categories
    )


# Sheet name patterns -> taxonomy category
_SHEET_TO_CATEGORY = {
    "income statement": "income_statement",
    "p&l": "income_statement",
    "profit and loss": "income_statement",
    "profit & loss": "income_statement",
    "monthly p&l": "income_statement",
    "balance sheet": "balance_sheet",
    "statement of financial position": "balance_sheet",
    "cash flow": "cash_flow",
    "cash flow statement": "cash_flow",
    "debt schedule": "debt_schedule",
    "debt": "debt_schedule",
    "working capital": "balance_sheet",
    "d&a schedule": "income_statement",
    "depreciation": "income_statement",
    "tax schedule": "income_statement",
    "tax provision": "income_statement",
    "revenue build": "income_statement",
    "opex build": "income_statement",
    "assumptions": "metrics",
    "returns analysis": "metrics",
}


def _normalize_label(label: str) -> str:
    """Normalize a financial label for alias lookup.

    Strips whitespace, removes leading numbering/bullets/dashes, trailing
    colons, and unit parentheticals like '($M)' or '(EUR)'.

    IMPORTANT: does NOT strip semantic qualifiers like '(Adjusted)', '(Pro Forma)',
    or '(Net)'.  These change the meaning of the metric and must be preserved so
    that Claude can map 'EBITDA (Adjusted)' → adjusted_ebitda rather than ebitda.
    Only truly noise-generating qualifiers (excl./incl./before/after) are stripped
    because they prevent any alias match and Claude handles the nuance.
    """
    import re

    s = label.strip()
    # Remove leading bullets, dashes, or numbering: "- Revenue", "1. Revenue", "1) Revenue"
    s = re.sub(r"^[\-\u2022\u2013\u2014]\s*", "", s)
    s = re.sub(r"^\d{1,3}[.)]\s*", "", s)
    # Remove trailing colon
    s = re.sub(r"\s*:\s*$", "", s)
    # Remove unit parentheticals at end: ($M), (EUR), (€M), (in thousands), (£m)
    s = re.sub(
        r"\s*\((?:in\s+)?"
        r"(?:\$|€|£|USD|EUR|GBP|CHF|JPY|AUD|CAD|NOK|SEK|DKK|ISK)?"
        r"\s*(?:M|m|MM|mm|k|K|000s?|thousands?|millions?|billions?|mn|bn)?"
        r"\s*\)\s*$",
        "",
        s,
        flags=re.IGNORECASE,
    )
    # Strip only noise-generating exclusion/inclusion qualifiers that prevent alias matching
    # but carry no semantic meaning (e.g. "(excl. lease payments)", "(before tax)")
    # DO NOT strip: (Adjusted), (Net), (Gross), (Restated), (Pro Forma), (Normalized) —
    # these are meaningful and allow mapping to adjusted_ebitda, adjusted_ebit, etc.
    s = re.sub(
        r"\s*\("
        r"(?:excl\.?\s+[^)]{1,40}|incl\.?\s+[^)]{1,40}|"
        r"excluding\s+[^)]{1,40}|including\s+[^)]{1,40}|"
        r"before\s+[^)]{1,40}|after\s+[^)]{1,40})"
        r"\)",
        "",
        s,
        flags=re.IGNORECASE,
    )
    # Collapse multiple spaces
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def _disambiguate_by_sheet_category(
    mappings: list,
    grouped_items: list,
    alias_lookup: dict,
) -> int:
    """Override mappings where an exact alias match exists in the sheet's category.

    When Claude picks a canonical from the wrong category (e.g., cash_flow instead
    of income_statement) but the label is an exact alias for a canonical in the
    correct sheet category, override deterministically.

    Uses section_category from triage when available, falling back to sheet name
    pattern matching.

    When multiple alias matches exist for the same category, prefers the match
    with the lowest priority number (1 = highest priority, default for string aliases).

    Mutates mappings in-place. Returns count of overrides applied.
    """
    # Build multi-value lookups: same label can appear on multiple sheets
    from collections import defaultdict

    # Load priority-aware lookup for multi-match tiebreaking
    priority_lookup = get_alias_to_canonicals_with_priority()

    label_to_sheets: dict[str, list[str]] = defaultdict(list)
    label_to_section_categories: dict[str, list[str | None]] = defaultdict(list)
    for item in grouped_items:
        lbl = item["label"]
        label_to_sheets[lbl].append(item["sheet"])
        label_to_section_categories[lbl].append(item.get("section_category"))

    def _resolve_categories(label: str) -> list[tuple[str, str]]:
        """Return list of (sheet, expected_category) for a label."""
        sheets = label_to_sheets.get(label, [])
        section_cats = label_to_section_categories.get(label, [])
        results = []
        for sheet, sec_cat in zip(sheets, section_cats):
            if sec_cat:
                results.append((sheet, sec_cat))
            else:
                sheet_lower = sheet.lower()
                for pattern, cat in _SHEET_TO_CATEGORY.items():
                    if pattern in sheet_lower:
                        results.append((sheet, cat))
                        break
        return results

    def _resolve_multi_match_by_priority(
        label_key: str,
        matching_canonicals: list[tuple[str, str]],
        expected_category: str,
    ) -> tuple[str, str] | None:
        """Resolve a multi-match conflict using alias priority.

        When the same alias text maps to multiple canonicals in the expected
        category, prefer the one with the lowest priority number (1 = highest).
        Falls back to name-matching heuristic if priorities are equal.

        Args:
            label_key: lowercased alias text
            matching_canonicals: list of (canonical_name, category) in expected category
            expected_category: the target category

        Returns:
            (canonical_name, category) of the best match, or None if no resolution.
        """
        priority_entries = priority_lookup.get(label_key, [])
        if not priority_entries:
            return None

        # Build priority map: canonical -> best (lowest) priority for this alias
        canonical_priority: dict[str, int] = {}
        for canonical, category, priority in priority_entries:
            if category == expected_category:
                if canonical not in canonical_priority or priority < canonical_priority[canonical]:
                    canonical_priority[canonical] = priority

        if not canonical_priority:
            return None

        # Find the minimum priority among matching canonicals
        best_priority = min(
            canonical_priority.get(c, 999) for c, _ in matching_canonicals
        )
        priority_winners = [
            (c, cat) for c, cat in matching_canonicals
            if canonical_priority.get(c, 999) == best_priority
        ]

        if len(priority_winners) == 1:
            return priority_winners[0]

        # Still tied — return None to fall through to name heuristic
        return None

    overrides = 0
    for m in mappings:
        label = m.get("original_label", "")
        current_canonical = m.get("canonical_name", "unmapped")
        if current_canonical == "unmapped":
            continue

        candidates = alias_lookup.get(label.lower().strip(), [])
        if not candidates:
            continue

        # Try each sheet context this label appears on
        sheet_categories = _resolve_categories(label)
        if not sheet_categories:
            continue

        # Check if current canonical already matches one of the expected categories
        current_cat = next((cat for c, cat in candidates if c == current_canonical), None)
        current_matches_sheet = current_cat and any(ec == current_cat for _, ec in sheet_categories)

        if not current_matches_sheet:
            # Current canonical is in the WRONG category — find the right one
            best_override = None
            for sheet, expected_category in sheet_categories:
                matching = [c for c in candidates if c[1] == expected_category]
                if len(matching) == 1 and matching[0][0] != current_canonical:
                    best_override = (matching[0][0], matching[0][1], sheet)
                    break  # First valid single match wins

            if best_override:
                correct_canonical, correct_category, sheet = best_override
                logger.info(
                    f"Stage 3: Disambiguation override: '{label}' on '{sheet}' "
                    f"changed from {current_canonical} to {correct_canonical} "
                    f"(exact alias match in {correct_category})"
                )
                m["canonical_name"] = correct_canonical
                m["disambiguation_override"] = {
                    "original": current_canonical,
                    "reason": f"exact alias match in {correct_category} category",
                }
                overrides += 1
                continue

        # Multi-match: try across all sheet categories (even if current is valid,
        # there might be a BETTER canonical in the same category)
        for sheet, expected_category in sheet_categories:
            matching = [c for c in candidates if c[1] == expected_category]
            if len(matching) > 1:
                label_key = label.lower().strip()

                # First: try resolving by alias priority (lower number wins)
                priority_winner = _resolve_multi_match_by_priority(
                    label_key, matching, expected_category,
                )
                if priority_winner and priority_winner[0] != current_canonical:
                    logger.info(
                        f"Stage 3: Priority override: '{label}' on '{sheet}' "
                        f"changed from {current_canonical} to {priority_winner[0]} "
                        f"(highest priority alias in {expected_category})"
                    )
                    m["canonical_name"] = priority_winner[0]
                    m["disambiguation_override"] = {
                        "original": current_canonical,
                        "reason": f"highest priority alias of {len(matching)} in {expected_category}",
                    }
                    overrides += 1
                    break

                # Fallback: prefer closest canonical name match
                label_normalized = label.lower().replace("&", "and").replace("-", " ").strip()
                best, best_score = None, -1
                for canonical, category in matching:
                    canonical_words = canonical.replace("_", " ")
                    if canonical_words == label_normalized:
                        score = 100
                    elif canonical_words in label_normalized or label_normalized in canonical_words:
                        score = 50 + len(canonical_words)
                    else:
                        score = 0
                    if score > best_score:
                        best_score = score
                        best = (canonical, category)
                if best and best_score > 0 and best[0] != current_canonical:
                    logger.info(
                        f"Stage 3: Multi-match override: '{label}' on '{sheet}' "
                        f"changed from {current_canonical} to {best[0]} "
                        f"(best of {len(matching)} in {expected_category})"
                    )
                    m["canonical_name"] = best[0]
                    m["disambiguation_override"] = {
                        "original": current_canonical,
                        "reason": f"best of {len(matching)} candidates in {expected_category}",
                    }
                    overrides += 1
                    break  # Applied override, stop trying other sheet categories

    # Second pass: rescue unmapped items via exact alias match
    for m in mappings:
        if m.get("canonical_name", "unmapped") != "unmapped":
            continue
        label = m.get("original_label", "")
        candidates = alias_lookup.get(label.lower().strip(), [])
        if not candidates:
            continue

        # Try each sheet context for this label
        sheet_categories = _resolve_categories(label)
        for sheet, expected_category in sheet_categories:
            matching = [c for c in candidates if c[1] == expected_category]
            if len(matching) == 1:
                logger.info(
                    f"Stage 3: Unmapped rescue: '{label}' on '{sheet}' "
                    f"resolved to {matching[0][0]} "
                    f"(exact alias in {expected_category})"
                )
                m["canonical_name"] = matching[0][0]
                m["disambiguation_override"] = {
                    "original": "unmapped",
                    "reason": f"rescued: exact alias in {expected_category}",
                }
                overrides += 1
                break
            elif len(matching) > 1:
                # Multiple matches for unmapped — try priority-based resolution
                label_key = label.lower().strip()
                priority_winner = _resolve_multi_match_by_priority(
                    label_key, matching, expected_category,
                )
                if priority_winner:
                    logger.info(
                        f"Stage 3: Unmapped rescue (priority): '{label}' on '{sheet}' "
                        f"resolved to {priority_winner[0]} "
                        f"(highest priority of {len(matching)} in {expected_category})"
                    )
                    m["canonical_name"] = priority_winner[0]
                    m["disambiguation_override"] = {
                        "original": "unmapped",
                        "reason": f"rescued: highest priority alias in {expected_category}",
                    }
                    overrides += 1
                    break
        else:
            # No category context or no category match: use unique global match
            if len(candidates) == 1:
                logger.info(
                    f"Stage 3: Unmapped rescue: '{label}' "
                    f"resolved to {candidates[0][0]} (unique global alias)"
                )
                m["canonical_name"] = candidates[0][0]
                m["disambiguation_override"] = {
                    "original": "unmapped",
                    "reason": "rescued: unique global alias match",
                }
                overrides += 1

    return overrides


def _fuzzy_rescue_unmapped(
    mappings: list,
    grouped_items: list,
    alias_lookup: dict,
    threshold: int = 80,
) -> int:
    """Rescue unmapped items via fuzzy alias matching (rapidfuzz).

    For each mapping still marked 'unmapped' after exact-alias passes,
    score the normalized label against all alias keys using token_sort_ratio.
    If the best score >= threshold and the match is unambiguous for the
    expected sheet category, override to that canonical.

    Mutates mappings in-place. Returns count of rescues.
    """
    from collections import defaultdict

    # Build label -> sheet lookup for category resolution
    label_to_sheets: dict[str, list[str]] = defaultdict(list)
    label_to_section_categories: dict[str, list[str | None]] = defaultdict(list)
    for item in grouped_items:
        lbl = item["label"]
        label_to_sheets[lbl].append(item["sheet"])
        label_to_section_categories[lbl].append(item.get("section_category"))

    def _resolve_category(label: str) -> str | None:
        """Return the expected taxonomy category for a label based on sheet context."""
        sheets = label_to_sheets.get(label, [])
        section_cats = label_to_section_categories.get(label, [])
        for sheet, sec_cat in zip(sheets, section_cats):
            if sec_cat:
                return sec_cat
            sheet_lower = sheet.lower()
            for pattern, cat in _SHEET_TO_CATEGORY.items():
                if pattern in sheet_lower:
                    return cat
        return None

    # Pre-compute normalized alias keys for scoring
    alias_keys = list(alias_lookup.keys())

    rescues = 0
    for m in mappings:
        if m.get("canonical_name", "unmapped") != "unmapped":
            continue

        label = m.get("original_label", "")
        normalized = _normalize_label(label).lower().strip()
        if not normalized:
            continue

        # Score against all alias keys
        best_score = 0
        best_key = None
        for alias_key in alias_keys:
            score = fuzz.token_sort_ratio(normalized, alias_key)
            if score > best_score:
                best_score = score
                best_key = alias_key

        if best_score < threshold or best_key is None:
            continue

        candidates = alias_lookup[best_key]
        expected_cat = _resolve_category(label)

        # Filter to expected category if known
        if expected_cat:
            cat_matches = [c for c in candidates if c[1] == expected_cat]
            if len(cat_matches) == 1:
                chosen = cat_matches[0]
            elif len(cat_matches) > 1:
                # Multiple matches in same category — skip (ambiguous)
                continue
            else:
                # No match in expected category — try unique global
                if len(candidates) == 1:
                    chosen = candidates[0]
                else:
                    continue
        else:
            # No category context — only accept unique global match
            if len(candidates) == 1:
                chosen = candidates[0]
            else:
                continue

        logger.info(
            f"Stage 3: Fuzzy rescue: '{label}' -> {chosen[0]} "
            f"(score={best_score}, alias='{best_key}')"
        )
        m["canonical_name"] = chosen[0]
        m["confidence"] = round(best_score / 100.0, 3)
        m["method"] = "fuzzy_alias"
        m["disambiguation_override"] = {
            "original": "unmapped",
            "reason": f"fuzzy alias match '{best_key}' (score={best_score})",
        }
        rescues += 1

    return rescues


def _handle_deprecated_redirect(canonical_name: str, db) -> str:
    """If canonical_name is deprecated, return its redirect target."""
    from src.db.models import Taxonomy

    item = db.query(Taxonomy).filter_by(canonical_name=canonical_name, deprecated=True).first()
    if item and item.deprecated_redirect:
        return item.deprecated_redirect
    return canonical_name


class MappingStage(ExtractionStage):
    """Stage 3: Map line items to canonical taxonomy."""

    @property
    def name(self) -> str:
        return "mapping"

    @property
    def stage_number(self) -> int:
        return 3

    @staticmethod
    def _build_section_lookup(
        triage_list: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Build a lookup from sheet_name -> list of section entries.

        Returns only entries that have section data (section_start_row is not
        None). For sheets without sections, the lookup will have no entry.
        Each sheet's sections are sorted by start_row.
        """
        lookup: Dict[str, List[Dict[str, Any]]] = {}
        for entry in triage_list:
            if entry.get("section_start_row") is not None:
                sheet_name = entry.get("sheet_name", "")
                lookup.setdefault(sheet_name, []).append(entry)
        for sections in lookup.values():
            sections.sort(key=lambda s: s.get("section_start_row", 0))
        return lookup

    @staticmethod
    def _build_grouped_line_items(
        parsed_result: Dict[str, Any],
        section_lookup: Dict[str, List[Dict[str, Any]]] | None = None,
    ) -> List[Dict[str, Any]]:
        """Build line items grouped by sheet with hierarchy and formula context.

        Returns a list of dicts, each with:
          - sheet: sheet name
          - label: row label
          - hierarchy_level: 0-3
          - is_formula: bool
          - is_subtotal: bool
          - section_category: optional category from triage section

        This gives Claude structural context to improve mapping accuracy.
        """
        items: List[Dict[str, Any]] = []

        for sheet in parsed_result.get("sheets", []):
            sheet_name = sheet.get("sheet_name", "Unknown")
            sheet_sections = section_lookup.get(sheet_name, []) if section_lookup else []

            for row in sheet.get("rows", []):
                label = row.get("label")
                if not label:
                    continue
                item: Dict[str, Any] = {
                    "sheet": sheet_name,
                    "label": label,
                    "hierarchy_level": row.get("hierarchy_level", 1),
                    "is_formula": row.get("is_formula", False),
                    "is_subtotal": row.get("is_subtotal", False),
                }

                # Attach section category if row falls within a triage section
                if sheet_sections:
                    row_index = row.get("row_index", 0)
                    for section in sheet_sections:
                        start = section.get("section_start_row", 0)
                        end = section.get("section_end_row", float("inf"))
                        if start <= row_index <= end:
                            # Use category_hint from the triage section
                            cat = section.get("category_hint")
                            if cat:
                                item["section_category"] = cat
                            break

                items.append(item)

        return items

    def _lookup_patterns(self, context: PipelineContext, labels: set) -> tuple:
        """Look up high-confidence entity patterns for shortcircuiting Claude calls.

        Uses effective confidence (with time-based decay) for threshold checks.
        Only active patterns are considered.

        Returns:
            (pre_mapped, remaining_labels): pre_mapped is a dict of label -> mapping dict,
            remaining_labels is a set of labels not matched by patterns.
        """
        settings = get_settings()
        pre_mapped: Dict[str, Dict[str, Any]] = {}
        entity_id = getattr(context, "entity_id", None)

        if not entity_id:
            return pre_mapped, labels

        try:
            from uuid import UUID

            from src.db import crud
            from src.db.session import get_db_sync

            with get_db_sync() as db:
                # Query with stored confidence >= 0.8 (decay could bring it below threshold)
                patterns = crud.get_entity_patterns(
                    db,
                    UUID(entity_id),
                    min_confidence=0.8,
                    limit=500,
                    active_only=True,
                )
                pattern_lookup = {p.original_label: p for p in patterns}

            remaining_labels = set()
            for label in labels:
                match = pattern_lookup.get(label)
                if match:
                    eff_conf = crud.compute_effective_confidence(
                        float(match.confidence),
                        match.last_seen,
                        match.created_by,
                    )
                    if eff_conf >= settings.taxonomy_pattern_shortcircuit_confidence:
                        pre_mapped[label] = {
                            "original_label": label,
                            "canonical_name": match.canonical_name,
                            "confidence": eff_conf,
                            "method": "entity_pattern",
                            "reasoning": f"Matched entity pattern (seen {match.occurrence_count}x)",
                        }
                    else:
                        remaining_labels.add(label)
                else:
                    remaining_labels.add(label)

            return pre_mapped, remaining_labels

        except Exception as e:
            logger.warning(f"Stage 3: Pattern lookup failed: {e}")
            return pre_mapped, labels

    @property
    def timeout_seconds(self):
        return 90.0

    def get_timeout(self, context):
        """Scale timeout with label count: 60s base + 0.2s per label."""
        try:
            parsed = context.get_result("parsing").get("parsed", {})
            total_rows = sum(len(s.get("rows", [])) for s in parsed.get("sheets", []))
            return max(60.0, 60.0 + total_rows * 0.2)
        except KeyError:
            return self.timeout_seconds

    @property
    def max_retries(self):
        return 3

    def validate_output(self, result):
        mappings = result.get("mappings", [])
        if not mappings:
            return "Mapping produced zero mappings"
        return None

    async def execute(self, context: PipelineContext) -> Dict[str, Any]:
        """Map extracted line items to canonical financial taxonomy."""
        logger.info("Stage 3: Mapping started")
        start_time = time.time()

        parsed_result = context.get_result("parsing")["parsed"]

        # Build section lookup from triage results (WS-3)
        try:
            triage_result = context.get_result("triage")
            triage_list = triage_result.get("triage", [])
        except KeyError:
            triage_list = []
        section_lookup = self._build_section_lookup(triage_list)

        # Build grouped line items with hierarchy and section context
        grouped_items = self._build_grouped_line_items(
            parsed_result,
            section_lookup,
        )

        # Extract unique labels for counting
        labels = {item["label"] for item in grouped_items}

        if not labels:
            logger.warning("Stage 3: No labels found to map")
            return {
                "mappings": [],
                "tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "lineage_metadata": {},
            }

        # --- Pattern-based shortcircuit ---
        # Check entity patterns BEFORE calling Claude to save tokens
        pre_mapped, remaining_labels = self._lookup_patterns(context, labels)

        if pre_mapped:
            logger.info(
                f"Stage 3: {len(pre_mapped)} of {len(labels)}"
                " labels resolved from entity patterns, "
                f"sending {len(remaining_labels)} to Claude"
            )

        # If ALL labels resolved from patterns, skip Claude entirely
        if not remaining_labels:
            logger.info(f"Stage 3: All {len(pre_mapped)} labels resolved from entity patterns")
            mappings_list = list(pre_mapped.values())
            # Attach taxonomy_category for provenance
            cat_lookup = get_canonical_to_category()
            for m in mappings_list:
                m["taxonomy_category"] = cat_lookup.get(m.get("canonical_name", ""), "unknown")
            return {
                "mappings": mappings_list,
                "tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "lineage_metadata": {
                    "mappings_count": len(mappings_list),
                    "unmapped_count": 0,
                    "avg_confidence": 1.0,
                    "pattern_matched": len(pre_mapped),
                    "claude_mapped": 0,
                },
            }

        # --- Embedding-based pre-filter ---
        embedding_matched: Dict[str, Any] = {}
        embedding_hints: Dict[str, list] = {}
        try:
            from src.extraction.embeddings import filter_remaining_labels

            embedding_matched, remaining_labels, embedding_hints = (
                filter_remaining_labels(remaining_labels)
            )
            if embedding_matched:
                pre_mapped.update(embedding_matched)
                logger.info(
                    f"Stage 3: Embedding pre-filter resolved "
                    f"{len(embedding_matched)} labels, "
                    f"{len(remaining_labels)} still need Claude"
                )

            # If ALL labels now resolved, skip Claude entirely
            if not remaining_labels:
                logger.info(
                    f"Stage 3: All labels resolved "
                    f"({len(pre_mapped)} total: patterns + embeddings)"
                )
                mappings_list = list(pre_mapped.values())
                cat_lookup = get_canonical_to_category()
                for m in mappings_list:
                    if "taxonomy_category" not in m:
                        m["taxonomy_category"] = cat_lookup.get(
                            m.get("canonical_name", ""), "unknown"
                        )
                return {
                    "mappings": mappings_list,
                    "tokens": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "lineage_metadata": {
                        "mappings_count": len(mappings_list),
                        "unmapped_count": 0,
                        "avg_confidence": 1.0,
                        "pattern_matched": len(pre_mapped) - len(embedding_matched),
                        "embedding_matched": len(embedding_matched),
                        "claude_mapped": 0,
                    },
                }
        except Exception as e:
            logger.warning(f"Stage 3: Embedding pre-filter unavailable: {e}")

        # Filter grouped_items to only include remaining (unmatched) labels
        remaining_grouped_items = [
            item for item in grouped_items if item["label"] in remaining_labels
        ]

        # Extract relevant categories from triage results and section context
        # to filter taxonomy and reduce token usage
        relevant_categories: Set[str] = set()
        for entry in triage_list:
            cat = entry.get("category_hint") or entry.get("category")
            if cat:
                relevant_categories.add(cat)
        for item in remaining_grouped_items:
            cat = item.get("section_category")
            if cat:
                relevant_categories.add(cat)

        # Load taxonomy dynamically from JSON (filtered by category if available)
        taxonomy_str = _load_taxonomy_for_prompt(
            categories=relevant_categories if relevant_categories else None
        )
        if relevant_categories:
            logger.info(
                f"Stage 3: Filtered taxonomy to categories: {relevant_categories}"
            )

        # Inject entity-specific pattern hints if available
        entity_hints = self._build_entity_hints(context)
        if entity_hints:
            taxonomy_str = taxonomy_str + "\n\n" + entity_hints

        try:
            settings = get_settings()
            BATCH_SIZE = settings.taxonomy_mapping_batch_size

            if len(remaining_grouped_items) <= BATCH_SIZE:
                # Single pass (existing behavior)
                claude_mappings_list, input_tokens, output_tokens = (
                    self._call_claude_mapping(remaining_grouped_items, taxonomy_str)
                )
                tokens = input_tokens + output_tokens
                batch_count = 1
            else:
                # Batched: split items into chunks
                batches = [
                    remaining_grouped_items[i : i + BATCH_SIZE]
                    for i in range(0, len(remaining_grouped_items), BATCH_SIZE)
                ]
                batch_count = len(batches)
                logger.info(
                    f"Stage 3: Splitting {len(remaining_grouped_items)} items "
                    f"into {batch_count} batches"
                )

                claude_mappings_list = []
                total_input = 0
                total_output = 0
                for i, batch in enumerate(batches):
                    logger.info(
                        f"Stage 3: Mapping batch {i + 1}/{batch_count} "
                        f"({len(batch)} items)"
                    )
                    batch_mappings, inp, out = self._call_claude_mapping(
                        batch, taxonomy_str
                    )
                    claude_mappings_list.extend(batch_mappings)
                    total_input += inp
                    total_output += out

                input_tokens = total_input
                output_tokens = total_output
                tokens = total_input + total_output

            duration = time.time() - start_time

            # Validate canonical names against taxonomy
            validate_canonical_names(claude_mappings_list, stage="3")

            # Deterministic sheet-category disambiguation (includes promoted learned aliases)
            alias_lookup = get_alias_to_canonicals_with_promoted()
            override_count = _disambiguate_by_sheet_category(
                claude_mappings_list,
                remaining_grouped_items,
                alias_lookup,
            )
            if override_count:
                logger.info(
                    f"Stage 3: {override_count} mapping(s) overridden by "
                    f"sheet-category disambiguation"
                )

            # Fuzzy alias rescue for still-unmapped items
            fuzzy_count = _fuzzy_rescue_unmapped(
                claude_mappings_list,
                remaining_grouped_items,
                alias_lookup,
                threshold=settings.taxonomy_fuzzy_rescue_threshold,
            )
            if fuzzy_count:
                logger.info(
                    f"Stage 3: {fuzzy_count} unmapped item(s) rescued via fuzzy matching"
                )

            # Tag Claude mappings with method (skip items already tagged by fuzzy rescue)
            for m in claude_mappings_list:
                if "method" not in m:
                    m["method"] = "claude"

            # Merge pre-mapped patterns + Claude results
            final_mappings = list(pre_mapped.values()) + claude_mappings_list

            # Handle deprecated taxonomy redirects
            try:
                from src.db.session import get_db_sync

                with get_db_sync() as db:
                    for m in final_mappings:
                        cn = m.get("canonical_name", "unmapped")
                        if cn != "unmapped":
                            redirected = _handle_deprecated_redirect(cn, db)
                            if redirected != cn:
                                logger.info(
                                    f"Stage 3: Deprecated redirect: "
                                    f"'{cn}' -> '{redirected}'"
                                )
                                m["canonical_name"] = redirected
                                m["deprecated_redirect_from"] = cn
            except Exception as e:
                logger.warning(f"Stage 3: Deprecated redirect check failed: {e}")

            # Attach taxonomy_category to each mapping for provenance
            cat_lookup = get_canonical_to_category()
            for m in final_mappings:
                m["taxonomy_category"] = cat_lookup.get(m.get("canonical_name", ""), "unknown")

            unmapped = sum(1 for m in final_mappings if m.get("canonical_name") == "unmapped")
            avg_conf = (
                sum(m.get("confidence", 0) for m in final_mappings) / len(final_mappings)
                if final_mappings
                else 0
            )

            n_embedding = len(embedding_matched)
            n_pattern = len(pre_mapped) - n_embedding

            log_performance(
                logger,
                "stage_3_mapping",
                duration,
                {
                    "tokens": tokens,
                    "labels": len(labels),
                    "mappings": len(final_mappings),
                    "pattern_matched": n_pattern,
                    "embedding_matched": n_embedding,
                    "claude_mapped": len(claude_mappings_list),
                },
            )

            logger.info(
                f"Stage 3: Mapping completed - {len(final_mappings)} items mapped "
                f"({n_pattern} patterns, {n_embedding} embeddings, "
                f"{len(claude_mappings_list)} Claude)"
            )

            return {
                "mappings": final_mappings,
                "tokens": tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "lineage_metadata": {
                    "mappings_count": len(final_mappings),
                    "unmapped_count": unmapped,
                    "avg_confidence": round(avg_conf, 3),
                    "pattern_matched": n_pattern,
                    "embedding_matched": n_embedding,
                    "claude_mapped": len(claude_mappings_list),
                    "fuzzy_rescued": fuzzy_count,
                    "batched": batch_count > 1,
                    "batch_count": batch_count,
                },
            }

        except anthropic.RateLimitError as e:
            retry_after = getattr(e.response, "headers", {}).get("retry-after")
            logger.warning(f"Stage 3: Rate limit hit (retry-after={retry_after})")
            raise RateLimitError(
                "Rate limit exceeded",
                stage="mapping",
                retry_after=int(retry_after) if retry_after else None,
            )

        except anthropic.APIError as e:
            logger.error(f"Stage 3: Claude API error - {str(e)}")
            raise ClaudeAPIError(
                str(e),
                stage="mapping",
                status_code=getattr(e, "status_code", None),
            )

        except ExtractionError:
            raise

        except Exception as e:
            logger.error(f"Stage 3: Unexpected error - {str(e)}")
            raise ExtractionError(f"Mapping failed: {str(e)}", stage="mapping")

    def _call_claude_mapping(
        self,
        items: list,
        taxonomy_str: str,
    ) -> tuple[list, int, int]:
        """Call Claude to map a batch of items.

        Returns (mappings, input_tokens, output_tokens).
        """
        response = get_claude_client().messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            messages=[
                {
                    "role": "user",
                    "content": get_prompt("mapping").render(
                        line_items=json.dumps(items, indent=2),
                        taxonomy=taxonomy_str,
                    ),
                }
            ],
        )

        # Check for truncation — incomplete JSON causes silent data loss
        if response.stop_reason == "max_tokens":
            logger.warning(
                f"Stage 3: Response truncated at max_tokens "
                f"({response.usage.output_tokens} tokens). "
                f"Batch had {len(items)} items."
            )
            raise ExtractionError(
                "Mapping response truncated: output exceeded token limit. "
                f"Tried to map {len(items)} items in one pass.",
                stage="mapping",
            )

        content = response.content[0].text  # type: ignore[union-attr]
        mappings = extract_json(content)
        return (
            mappings if isinstance(mappings, list) else [],
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

    def _build_entity_hints(self, context: PipelineContext) -> str:
        """Load learned entity patterns from DB as mapping hints.

        Uses effective confidence (with time-based decay) for display.
        Also loads industry patterns if the entity has few of its own.
        Gracefully returns empty string if no entity_id or DB unavailable.
        """
        entity_id = getattr(context, "entity_id", None)
        if not entity_id:
            return ""

        try:
            from uuid import UUID

            from src.db import crud
            from src.db.session import get_db_sync

            entity_uuid = UUID(entity_id)

            with get_db_sync() as db:
                patterns = crud.get_entity_patterns(
                    db,
                    entity_uuid,
                    min_confidence=0.8,
                    limit=15,
                    active_only=True,
                )

                # Always load entity for industry context
                entity = crud.get_entity(db, entity_uuid)

                # Load industry patterns if entity has few of its own
                industry_patterns = []
                if len(patterns) < 5 and entity and entity.industry:
                    industry_patterns = crud.get_industry_patterns(
                        db,
                        entity.industry,
                        entity_uuid,
                        min_confidence=0.8,
                        limit=10,
                    )

            lines = []

            # Prepend industry context if available
            if entity and entity.industry:
                lines.append(
                    f"This entity is in the {entity.industry} industry. "
                    f"Focus on industry-specific line items and terminology."
                )

            for p in patterns:
                eff_conf = crud.compute_effective_confidence(
                    float(p.confidence),
                    p.last_seen,
                    p.created_by,
                )
                lines.append(
                    f"  '{p.original_label}' -> {p.canonical_name} "
                    f"({eff_conf:.0%}, seen {p.occurrence_count}x)"
                )

            # Add industry patterns with reduced confidence
            for p in industry_patterns:
                eff_conf = crud.compute_effective_confidence(
                    float(p.confidence),
                    p.last_seen,
                    p.created_by,
                )
                reduced_conf = eff_conf * 0.7
                lines.append(
                    f"  '{p.original_label}' -> {p.canonical_name} "
                    f"({reduced_conf:.0%}, industry pattern)"
                )

            if not lines:
                return ""

            logger.info(
                f"Stage 3: Loaded {len(patterns)} entity + "
                f"{len(industry_patterns)} industry pattern hints"
            )
            return "Known patterns from prior extractions for this entity:\n" + "\n".join(lines)

        except Exception as e:
            logger.warning(f"Stage 3: Could not load entity patterns: {e}")
            return ""


# Self-register at import time
from src.extraction.registry import registry  # noqa: E402

registry.register(MappingStage())
