"""Shared taxonomy JSON loader for extraction pipeline stages.

Provides a single source for loading taxonomy data from the JSON file,
used by Stage 3 (Mapping), Stage 4 (Validation), and Stage 5 (Enhanced Mapping).
Also merges promoted learned aliases from the database with TTL caching.
"""
import json
import time
from pathlib import Path
from typing import Dict, FrozenSet, List

from src.core.logging import extraction_logger as logger

TAXONOMY_PATH = Path(__file__).parent.parent.parent / "data" / "taxonomy.json"

# Module-level caches (loaded once per process)
_taxonomy_cache: Dict = {}
_canonical_names_cache: FrozenSet[str] = frozenset()


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
    Used for deterministic sheet-category disambiguation after Claude mapping.
    """
    data = load_taxonomy_json()
    lookup: Dict[str, List[tuple]] = {}
    for category, items in data.get("categories", {}).items():
        for item in items:
            canonical = item["canonical_name"]
            entry = (canonical, category)
            for alias in item.get("aliases", []):
                key = alias.lower().strip()
                lookup.setdefault(key, []).append(entry)
            display = item.get("display_name", "")
            if display:
                lookup.setdefault(display.lower().strip(), []).append(entry)
    return lookup


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
        from src.db.session import get_db_sync
        from src.db.crud import get_promoted_aliases_for_lookup
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
            rules.append({
                "canonical_name": item["canonical_name"],
                "validation_rules": {"cross_item_validation": vr["cross_item_validation"]},
            })
    return rules


def format_taxonomy_for_prompt(
    include_aliases: bool = True,
    include_learned: bool = True,
) -> str:
    """Format taxonomy as a concise prompt string for Claude.

    Args:
        include_aliases: If True, include top aliases for each item.
        include_learned: If True, append promoted learned aliases tagged [learned].
    """
    data = load_taxonomy_json()

    if not data.get("categories"):
        return _fallback_taxonomy()

    category_display = {
        "income_statement": "Income Statement",
        "balance_sheet": "Balance Sheet",
        "cash_flow": "Cash Flow",
        "debt_schedule": "Debt Schedule",
        "project_finance": "Project Finance",
        "metrics": "Metrics",
    }

    # Build reverse lookup: canonical -> list of promoted alias texts
    learned_by_canonical: dict[str, list[str]] = {}
    if include_learned:
        promoted = _load_promoted_aliases()
        for alias_key, entries in promoted.items():
            for canonical, _category in entries:
                learned_by_canonical.setdefault(canonical, []).append(alias_key)

    lines = []
    for category, items in data.get("categories", {}).items():
        display = category_display.get(category, category.replace("_", " ").title())
        if include_aliases:
            parts = []
            for item in items:
                name = item["canonical_name"]
                aliases = item.get("aliases", [])
                learned = learned_by_canonical.get(name, [])
                alias_parts = list(aliases[:5])
                for la in learned[:2]:
                    if la not in alias_parts:
                        alias_parts.append(f"{la} [learned]")
                if alias_parts:
                    parts.append(f"{name} ({', '.join(alias_parts)})")
                else:
                    parts.append(name)
            lines.append(f"{display}: {', '.join(parts)}")
        else:
            names = [item["canonical_name"] for item in items]
            lines.append(f"{display}: {', '.join(names)}")
    return "\n".join(lines)


def format_taxonomy_detailed() -> str:
    """Format taxonomy with full detail for enhanced mapping prompts."""
    data = load_taxonomy_json()
    lines = []
    for category, items in data.get("categories", {}).items():
        category_display = category.replace("_", " ").title()
        names = []
        for item in items:
            aliases_str = ""
            if item.get("aliases"):
                aliases_str = f" (aliases: {', '.join(item['aliases'][:5])})"
            names.append(f"  - {item['canonical_name']}: {item.get('display_name', '')}{aliases_str}")
        lines.append(f"{category_display}:")
        lines.extend(names)
    return "\n".join(lines)


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
