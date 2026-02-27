"""Shared taxonomy JSON loader for extraction pipeline stages.

Provides a single source for loading taxonomy data from the JSON file,
used by Stage 3 (Mapping), Stage 4 (Validation), and Stage 5 (Enhanced Mapping).
"""
import json
from pathlib import Path
from typing import Dict, List

from src.core.logging import extraction_logger as logger

TAXONOMY_PATH = Path(__file__).parent.parent.parent / "data" / "taxonomy.json"

# Module-level cache (loaded once per process)
_taxonomy_cache: Dict = {}


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


def format_taxonomy_for_prompt(include_aliases: bool = True) -> str:
    """Format taxonomy as a concise prompt string for Claude.

    Args:
        include_aliases: If True, include top aliases for each item.
    """
    data = load_taxonomy_json()

    if not data.get("categories"):
        return _fallback_taxonomy()

    category_display = {
        "income_statement": "Income Statement",
        "balance_sheet": "Balance Sheet",
        "cash_flow": "Cash Flow",
        "debt_schedule": "Debt Schedule",
        "metrics": "Metrics",
    }

    lines = []
    for category, items in data.get("categories", {}).items():
        display = category_display.get(category, category.replace("_", " ").title())
        if include_aliases:
            parts = []
            for item in items:
                name = item["canonical_name"]
                aliases = item.get("aliases", [])
                if aliases:
                    parts.append(f"{name} ({', '.join(aliases[:3])})")
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
                aliases_str = f" (aliases: {', '.join(item['aliases'][:3])})"
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
