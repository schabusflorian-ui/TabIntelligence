"""Shared taxonomy JSON loader for extraction pipeline stages.

Provides a single source for loading taxonomy data from the JSON file,
used by Stage 3 (Mapping), Stage 4 (Validation), and Stage 5 (Enhanced Mapping).
Also merges promoted learned aliases from the database with TTL caching.
Supports priority-aware alias format and cross-canonical conflict detection.
"""

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set, Tuple, Union

from src.core.logging import extraction_logger as logger
from src.taxonomy_constants import CATEGORY_DISPLAY_NAMES

TAXONOMY_PATH = Path(__file__).parent.parent.parent / "data" / "taxonomy.json"

# Module-level caches (loaded once per process)
_taxonomy_cache: Dict = {}
_canonical_names_cache: FrozenSet[str] = frozenset()
_alias_conflicts_cache: Optional[Dict[str, List[Tuple[str, str]]]] = None


def _normalize_alias(alias: Union[str, Dict]) -> Tuple[str, int]:
    """Normalize an alias entry to (text, priority).

    Supports two formats:
    - String: "Revenue" -> ("Revenue", 1)   (implicit priority=1, highest)
    - Dict:   {"text": "Sls", "priority": 3} -> ("Sls", 3)

    Lower priority number = higher priority (1 is best).
    """
    if isinstance(alias, str):
        return (alias, 1)
    if isinstance(alias, dict):
        return (alias.get("text", ""), alias.get("priority", 1))
    # Fallback for unexpected types
    return (str(alias), 1)


def _get_alias_text(alias: Union[str, Dict]) -> str:
    """Extract the text portion of an alias entry (string or dict)."""
    if isinstance(alias, str):
        return alias
    if isinstance(alias, dict):
        return alias.get("text", "")
    return str(alias)


def _get_alias_priority(alias: Union[str, Dict]) -> int:
    """Extract the priority of an alias entry (1 = highest, default)."""
    if isinstance(alias, dict):
        return alias.get("priority", 1)
    return 1


def load_taxonomy_json() -> Dict:
    """Load the full taxonomy JSON file with caching.

    Returns:
        Dict with 'version', 'categories', etc. from taxonomy.json
    """
    global _taxonomy_cache
    if _taxonomy_cache:
        return _taxonomy_cache

    if not TAXONOMY_PATH.exists():
        logger.warning(f"Taxonomy file not found: {TAXONOMY_PATH}")
        return {"categories": {}}

    with open(TAXONOMY_PATH) as f:
        _taxonomy_cache = json.load(f)

    return _taxonomy_cache


def get_all_taxonomy_items() -> List[Dict]:
    """Flatten all taxonomy items across all categories."""
    data = load_taxonomy_json()
    items = []
    for cat_items in data.get("categories", {}).values():
        items.extend(cat_items)
    return items


def get_all_canonical_names() -> FrozenSet[str]:
    """Return the frozenset of all valid canonical_name values from taxonomy.

    Includes the sentinel value 'unmapped'. Cached after first call.
    """
    global _canonical_names_cache
    if _canonical_names_cache:
        return _canonical_names_cache
    names = {item["canonical_name"] for item in get_all_taxonomy_items()}
    names.add("unmapped")
    _canonical_names_cache = frozenset(names)
    return _canonical_names_cache


def get_canonical_to_category() -> Dict[str, str]:
    """Return a mapping of canonical_name -> category name.

    E.g., {"revenue": "income_statement", "total_assets": "balance_sheet", ...}
    Cached via load_taxonomy_json().
    """
    data = load_taxonomy_json()
    lookup: Dict[str, str] = {}
    for category, items in data.get("categories", {}).items():
        for item in items:
            lookup[item["canonical_name"]] = category
    return lookup


def get_alias_to_canonicals() -> Dict[str, List[tuple]]:
    """Reverse alias lookup: lowercased alias -> [(canonical_name, category), ...].

    Indexes aliases, display_name, and canonical_name for each taxonomy item.
    Supports both string aliases and priority-aware dict aliases:
      - "Revenue" (string, implicit priority=1)
      - {"text": "Sls", "priority": 3} (dict with explicit priority)
    Used for deterministic sheet-category disambiguation after Claude mapping.
    """
    data = load_taxonomy_json()
    lookup: Dict[str, List[tuple]] = {}
    for category, items in data.get("categories", {}).items():
        for item in items:
            canonical = item["canonical_name"]
            entry = (canonical, category)
            for alias in item.get("aliases", []):
                alias_text = _get_alias_text(alias)
                key = alias_text.lower().strip()
                if key:
                    lookup.setdefault(key, []).append(entry)
            display = item.get("display_name", "")
            if display:
                lookup.setdefault(display.lower().strip(), []).append(entry)
    return lookup


def get_alias_to_canonicals_with_priority() -> Dict[str, List[Tuple[str, str, int]]]:
    """Reverse alias lookup with priority: lowercased alias -> [(canonical_name, category, priority), ...].

    Like get_alias_to_canonicals() but includes the priority value for each alias entry.
    Priority 1 = highest (default for string aliases).
    Used by disambiguation to prefer higher-priority (lower number) alias matches.
    """
    data = load_taxonomy_json()
    lookup: Dict[str, List[Tuple[str, str, int]]] = {}
    for category, items in data.get("categories", {}).items():
        for item in items:
            canonical = item["canonical_name"]
            for alias in item.get("aliases", []):
                alias_text, priority = _normalize_alias(alias)
                key = alias_text.lower().strip()
                if key:
                    lookup.setdefault(key, []).append((canonical, category, priority))
            display = item.get("display_name", "")
            if display:
                lookup.setdefault(display.lower().strip(), []).append(
                    (canonical, category, 1)
                )
    return lookup


# ---------------------------------------------------------------------------
# Alias conflict detection
# ---------------------------------------------------------------------------


def detect_alias_conflicts() -> Dict[str, List[Tuple[str, str]]]:
    """Detect cross-canonical alias conflicts in the taxonomy.

    Scans all aliases across all categories and finds cases where the same
    alias text (case-insensitive) maps to multiple distinct canonical names.

    Logs warnings for cross-category conflicts (same alias, different categories).
    Results are cached at module level after first call.

    Returns:
        Dict mapping conflicting alias text to list of (canonical_name, category)
        tuples. Only aliases that map to 2+ different canonical names are included.
    """
    global _alias_conflicts_cache
    if _alias_conflicts_cache is not None:
        return _alias_conflicts_cache

    data = load_taxonomy_json()
    alias_map: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

    for category, items in data.get("categories", {}).items():
        for item in items:
            canonical = item["canonical_name"]
            for alias in item.get("aliases", []):
                alias_text = _get_alias_text(alias)
                key = alias_text.lower().strip()
                if key:
                    alias_map[key].append((canonical, category))

    # Filter to only conflicts (same alias -> multiple distinct canonicals)
    conflicts: Dict[str, List[Tuple[str, str]]] = {}
    cross_category_count = 0
    same_category_count = 0

    for alias_key, entries in alias_map.items():
        distinct_canonicals = {c for c, _ in entries}
        if len(distinct_canonicals) > 1:
            conflicts[alias_key] = entries
            # Check if this is a cross-category conflict
            distinct_categories = {cat for _, cat in entries}
            if len(distinct_categories) > 1:
                cross_category_count += 1
                canonical_list = [f"{c} ({cat})" for c, cat in entries]
                logger.warning(
                    f"Taxonomy alias conflict (cross-category): "
                    f"'{alias_key}' maps to: {', '.join(canonical_list)}"
                )
            else:
                same_category_count += 1

    if conflicts:
        logger.info(
            f"Taxonomy alias conflicts detected: {len(conflicts)} total "
            f"({cross_category_count} cross-category, {same_category_count} same-category)"
        )
    else:
        logger.info("No taxonomy alias conflicts detected")

    _alias_conflicts_cache = conflicts
    return conflicts


def get_alias_conflicts() -> Dict[str, List[Tuple[str, str]]]:
    """Return cached alias conflicts, running detection if needed.

    This is the public API for accessing conflict data at runtime.
    """
    return detect_alias_conflicts()


def invalidate_alias_conflicts_cache() -> None:
    """Invalidate the alias conflicts cache (e.g., after taxonomy reload)."""
    global _alias_conflicts_cache
    _alias_conflicts_cache = None


# ---------------------------------------------------------------------------
# Promoted alias cache (TTL-based, loads from DB)
# ---------------------------------------------------------------------------

_promoted_cache: Dict[str, List[tuple]] = {}
_promoted_cache_time: float = 0.0
_PROMOTED_TTL: float = 300.0  # 5 minutes


def _load_promoted_aliases() -> Dict[str, List[tuple]]:
    """Load promoted aliases from DB with TTL cache. Graceful on DB errors."""
    global _promoted_cache, _promoted_cache_time
    now = time.time()
    if _promoted_cache and (now - _promoted_cache_time) < _PROMOTED_TTL:
        return _promoted_cache
    try:
        from src.db.crud import get_promoted_aliases_for_lookup
        from src.db.session import get_db_sync

        cat_lookup = get_canonical_to_category()
        with get_db_sync() as db:
            aliases = get_promoted_aliases_for_lookup(db)
        result: Dict[str, List[tuple]] = {}
        for a in aliases:
            key = a["alias_text"].lower().strip()
            category = cat_lookup.get(a["canonical_name"], "unknown")
            result.setdefault(key, []).append((a["canonical_name"], category))
        _promoted_cache = result
        _promoted_cache_time = now
        return result
    except Exception as e:
        logger.warning(f"Could not load promoted aliases: {e}")
        return _promoted_cache  # return stale cache on failure


def invalidate_promoted_cache():
    """Invalidate the promoted alias cache (call after promotion)."""
    global _promoted_cache, _promoted_cache_time
    _promoted_cache = {}
    _promoted_cache_time = 0.0


def get_alias_to_canonicals_with_promoted() -> Dict[str, List[tuple]]:
    """Return alias lookup merged with promoted learned aliases.

    Taxonomy aliases take precedence — promoted aliases are appended only if
    the (canonical_name, category) pair doesn't already exist for that key.
    """
    base = get_alias_to_canonicals()
    promoted = _load_promoted_aliases()
    if not promoted:
        return base
    merged = {k: list(v) for k, v in base.items()}
    for key, entries in promoted.items():
        if key in merged:
            existing = set(merged[key])
            for entry in entries:
                if entry not in existing:
                    merged[key].append(entry)
        else:
            merged[key] = list(entries)
    return merged


def get_validation_rules() -> List[Dict]:
    """Extract taxonomy items that have cross_item_validation rules.

    Returns items in the same format AccountingValidator expects:
    [{"canonical_name": ..., "validation_rules": {"cross_item_validation": {...}}}, ...]
    """
    items = get_all_taxonomy_items()
    rules = []
    for item in items:
        vr = item.get("validation_rules", {})
        if vr.get("cross_item_validation"):
            rules.append(
                {
                    "canonical_name": item["canonical_name"],
                    "validation_rules": {"cross_item_validation": vr["cross_item_validation"]},
                }
            )
    return rules


def format_taxonomy_for_prompt(
    include_aliases: bool = True,
    include_learned: bool = True,
    categories: Optional[Set[str]] = None,
) -> str:
    """Format taxonomy as a concise prompt string for Claude.

    Args:
        include_aliases: If True, include top aliases for each item.
        include_learned: If True, append promoted learned aliases tagged [learned].
        categories: If provided, only include items from these categories plus
            "metrics" (ratios/KPIs apply everywhere). If None or empty, include all.
    """
    data = load_taxonomy_json()

    if not data.get("categories"):
        return _fallback_taxonomy()

    category_display = CATEGORY_DISPLAY_NAMES

    # Filter categories if a filter set is provided
    all_categories = data.get("categories", {})
    if categories:
        # Always include "metrics" — ratios/KPIs apply to every statement type
        filter_set = set(categories) | {"metrics"}
        filtered_categories = {
            k: v for k, v in all_categories.items() if k in filter_set
        }
    else:
        filtered_categories = all_categories

    # Build reverse lookup: canonical -> list of promoted alias texts
    learned_by_canonical: dict[str, list[str]] = {}
    if include_learned:
        promoted = _load_promoted_aliases()
        for alias_key, entries in promoted.items():
            for canonical, _category in entries:
                learned_by_canonical.setdefault(canonical, []).append(alias_key)

    lines = []
    for category, items in filtered_categories.items():
        display = category_display.get(category, category.replace("_", " ").title())
        if include_aliases:
            parts = []
            for item in items:
                if item.get("deprecated", False) if isinstance(item, dict) else getattr(item, "deprecated", False):
                    continue
                name = item["canonical_name"]
                raw_aliases = item.get("aliases", [])
                learned = learned_by_canonical.get(name, [])
                # Extract text from aliases (supports both string and dict formats)
                alias_texts = [_get_alias_text(a) for a in raw_aliases[:5]]
                alias_parts = list(alias_texts)
                for la in learned[:2]:
                    if la not in alias_parts:
                        alias_parts.append(f"{la} [learned]")
                if alias_parts:
                    parts.append(f"{name} ({', '.join(alias_parts)})")
                else:
                    parts.append(name)
            lines.append(f"{display}: {', '.join(parts)}")
        else:
            names = [
                item["canonical_name"] for item in items
                if not (item.get("deprecated", False) if isinstance(item, dict) else getattr(item, "deprecated", False))
            ]
            lines.append(f"{display}: {', '.join(names)}")
    return "\n".join(lines)


def format_taxonomy_detailed(
    categories: Optional[Set[str]] = None,
) -> str:
    """Format taxonomy with full detail for enhanced mapping prompts.

    Args:
        categories: If provided, only include items from these categories plus
            "metrics". If None or empty, include all.
    """
    data = load_taxonomy_json()
    all_categories = data.get("categories", {})
    if categories:
        filter_set = set(categories) | {"metrics"}
        filtered_categories = {
            k: v for k, v in all_categories.items() if k in filter_set
        }
    else:
        filtered_categories = all_categories

    lines = []
    for category, items in filtered_categories.items():
        category_display = category.replace("_", " ").title()
        names = []
        for item in items:
            if item.get("deprecated", False) if isinstance(item, dict) else getattr(item, "deprecated", False):
                continue
            aliases_str = ""
            raw_aliases = item.get("aliases", [])
            if raw_aliases:
                alias_texts = [_get_alias_text(a) for a in raw_aliases[:5]]
                aliases_str = f" (aliases: {', '.join(alias_texts)})"
            names.append(
                f"  - {item['canonical_name']}: {item.get('display_name', '')}{aliases_str}"
            )
        lines.append(f"{category_display}:")
        lines.extend(names)
    return "\n".join(lines)


def record_taxonomy_version(session, applied_by: str = "manual") -> None:
    """Record the current taxonomy.json version in the database.

    Computes SHA-256 checksum and category distribution, then inserts
    a row into taxonomy_versions for audit trail.
    """
    import hashlib
    from uuid import uuid4

    from src.db.models import TaxonomyVersion

    if not TAXONOMY_PATH.exists():
        logger.warning("taxonomy.json not found — skipping version recording")
        return

    content = TAXONOMY_PATH.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()

    data = load_taxonomy_json()
    version = data.get("version", "unknown")
    categories_dict = data.get("categories", {})
    category_counts = {cat: len(items) for cat, items in categories_dict.items()}
    total = sum(category_counts.values())

    tv = TaxonomyVersion(
        id=uuid4(),
        version=version,
        item_count=total,
        checksum=checksum,
        categories=category_counts,
        snapshot=data,
        applied_by=applied_by,
    )
    session.add(tv)
    session.commit()
    logger.info(f"Recorded taxonomy version {version} ({total} items, checksum={checksum[:12]}...)")


def _fallback_taxonomy() -> str:
    """Hardcoded fallback if taxonomy.json is missing."""
    return (
        "Income Statement: revenue, cogs, gross_profit, opex, sga, rd_expense, "
        "ebitda, depreciation, amortization, ebit, interest_expense, ebt, "
        "tax_expense, net_income\n"
        "Balance Sheet: cash, accounts_receivable, inventory, current_assets, "
        "ppe, intangibles, goodwill, total_assets, accounts_payable, "
        "short_term_debt, current_liabilities, long_term_debt, total_liabilities, "
        "total_equity\n"
        "Cash Flow: cfo, capex, cfi, cff, fcf, net_change_cash"
    )
