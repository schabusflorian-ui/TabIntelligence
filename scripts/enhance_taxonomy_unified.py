#!/usr/bin/env python3
"""
Unified Taxonomy Enhancement Script (Phases 1-3)

Applies all Phase 1-3 enhancements to data/taxonomy.json (categories structure):
- Phase 1: OCR variants, format examples, industry tags
- Phase 2: Cross-item validation, confidence scoring, misspellings
- Phase 3: Industry-specific metrics, GAAP/IFRS, regulatory context

Usage:
    python scripts/enhance_taxonomy_unified.py
"""

import json
from pathlib import Path
from typing import Dict, List, Optional


def get_all_items(data: dict) -> list:
    """Extract flat list of items from categories structure."""
    items = []
    for cat_items in data['categories'].values():
        items.extend(cat_items)
    return items


def find_item(data: dict, canonical_name: str) -> Optional[dict]:
    """Find an item by canonical_name across all categories."""
    for cat_items in data['categories'].values():
        for item in cat_items:
            if item['canonical_name'] == canonical_name:
                return item
    return None


def item_exists(data: dict, canonical_name: str) -> bool:
    """Check if an item already exists."""
    return find_item(data, canonical_name) is not None


# ============================================================
# PHASE 1: OCR variants, format examples, industry tags
# ============================================================

PHASE1_OCR_AND_FORMATS = {
    "revenue": {
        "ocr_variants": ["Rev enue", "Reyenue", "RevenUe", "REVENUE", "revenue.", "Reveπue", "Rev-enue"],
        "format_examples": [
            {"value": "1,234,567", "context": "US format with commas"},
            {"value": "1.234.567", "context": "European format"},
            {"value": "$1.2M", "context": "Abbreviated millions"},
            {"value": "1234567", "context": "No separators"}
        ]
    },
    "cogs": {
        "ocr_variants": ["COG S", "C0GS", "COGS.", "Co GS", "CDGS", "C O G S"],
        "format_examples": [
            {"value": "(234,567)", "context": "Parentheses for expense"},
            {"value": "234,567", "context": "Positive number"}
        ]
    },
    "gross_profit": {
        "ocr_variants": ["Gross Prof it", "Gr oss Profit", "GROSS PROFIT", "Gross-Profit", "GrossProfit"],
        "format_examples": [
            {"value": "1,000,000", "context": "Positive profit"},
            {"value": "(50,000)", "context": "Loss in parentheses"}
        ]
    },
    "ebitda": {
        "ocr_variants": ["EBIT DA", "E BITDA", "EB1TDA", "EBITDA.", "Ebitda", "EBlTDA", "E-BITDA"],
        "format_examples": [
            {"value": "5,000,000", "context": "Strong EBITDA"},
            {"value": "(500,000)", "context": "Negative EBITDA"}
        ]
    },
    "ebit": {
        "ocr_variants": ["EB IT", "E BIT", "EB1T", "EBIT.", "Ebit", "EBlT"],
        "format_examples": [{"value": "4,500,000", "context": "Operating profit"}]
    },
    "net_income": {
        "ocr_variants": ["Net Inc ome", "Net-Income", "NET INCOME", "Nɇt Income", "Net lncome"],
        "format_examples": [
            {"value": "3,150,000", "context": "After-tax profit"},
            {"value": "(250,000)", "context": "Net loss"}
        ]
    },
    "total_assets": {
        "ocr_variants": ["Total Ass ets", "Total-Assets", "TOTAL ASSETS", "Totɑl Assets"],
        "format_examples": [{"value": "50,000,000", "context": "Enterprise balance sheet"}]
    },
    "total_liabilities": {
        "ocr_variants": ["Total Liabil ities", "Total-Liabilities", "TOTAL LIABILITIES"],
        "format_examples": [{"value": "30,000,000", "context": "All obligations"}]
    },
    "total_equity": {
        "ocr_variants": ["Total Equ ity", "Total-Equity", "TOTAL EQUITY", "Totɑl Equity"],
        "format_examples": [{"value": "20,000,000", "context": "Shareholder equity"}]
    },
    "cash": {
        "ocr_variants": ["Ca sh", "C ash", "CASH", "Cash.", "Cɑsh"],
        "format_examples": [{"value": "5,000,000", "context": "Cash on hand"}, {"value": "$5.0M", "context": "Millions"}]
    },
    "accounts_receivable": {
        "ocr_variants": ["Accounts Receiv able", "Accounts-Receivable", "ACCOUNTS RECEIVABLE", "A/R"],
        "format_examples": [{"value": "2,500,000", "context": "Trade receivables"}]
    },
    "inventory": {
        "ocr_variants": ["Invent ory", "Inven tory", "INVENTORY", "lnventory"],
        "format_examples": [{"value": "3,000,000", "context": "Finished goods + WIP"}]
    },
    "accounts_payable": {
        "ocr_variants": ["Accounts Pay able", "Accounts-Payable", "ACCOUNTS PAYABLE", "A/P"],
        "format_examples": [{"value": "1,800,000", "context": "Trade payables"}]
    },
    "depreciation": {
        "ocr_variants": ["Depreciat ion", "Depre ciation", "DEPRECIATION", "Depreciaƫon"],
        "format_examples": [{"value": "(100,000)", "context": "Non-cash expense"}]
    },
    "amortization": {
        "ocr_variants": ["Amort ization", "Amorti zation", "AMORTIZATION"],
        "format_examples": [{"value": "(50,000)", "context": "Intangible amortization"}]
    },
    "interest_expense": {
        "ocr_variants": ["Interest Exp ense", "Interest-Expense", "INTEREST EXPENSE", "lnterest Expense"],
        "format_examples": [{"value": "(250,000)", "context": "Debt servicing cost"}]
    },
    "capex": {
        "ocr_variants": ["Cap ex", "CAPEX", "CapEx", "Cap-Ex", "Cɑpex"],
        "format_examples": [{"value": "(2,500,000)", "context": "Capital investments"}, {"value": "2,500,000", "context": "Positive format"}]
    },
    "fcf": {
        "ocr_variants": ["FC F", "F CF", "FCF.", "FCƑ"],
        "format_examples": [{"value": "3,500,000", "context": "CFO - Capex"}]
    },
    "ebitda_margin": {
        "ocr_variants": ["EBITDA Mar gin", "EBITDA-Margin", "EBITDA MARGIN", "EB1TDA Margin"],
        "format_examples": [
            {"value": "0.25", "context": "25% as decimal"},
            {"value": "25%", "context": "Percentage"},
            {"value": "25.0", "context": "Percentage without symbol"}
        ]
    },
    "debt_to_ebitda": {
        "ocr_variants": ["Debt / EB ITDA", "Debt-to-EBITDA", "DEBT TO EBITDA", "Debt/EB1TDA"],
        "format_examples": [{"value": "3.5", "context": "3.5x leverage"}, {"value": "3.5x", "context": "With x suffix"}]
    },
    "interest_rate": {
        "ocr_variants": ["Interest Ra te", "Interest-Rate", "INTEREST RATE", "lnterest Rate"],
        "format_examples": [
            {"value": "0.065", "context": "6.5% as decimal"},
            {"value": "6.5%", "context": "Percentage format"},
            {"value": "650 bps", "context": "Basis points"}
        ]
    },
}

# Industry tags by category default
DEFAULT_INDUSTRY_TAGS = {
    "income_statement": ["all", "corporate"],
    "balance_sheet": ["all", "corporate"],
    "cash_flow": ["all", "corporate"],
    "debt_schedule": ["all", "leveraged"],
    "metrics": ["all", "corporate"],
}

# Specific industry tag overrides for key items
INDUSTRY_TAG_OVERRIDES = {
    "revenue": ["all", "saas", "manufacturing", "retail", "services", "real_estate"],
    "cogs": ["manufacturing", "retail", "ecommerce", "wholesale"],
    "ebitda": ["all", "private_equity", "leveraged_finance"],
    "ebit": ["all", "corporate", "public_companies"],
    "capex": ["all", "manufacturing", "real_estate", "capital_intensive"],
    "fcf": ["all", "private_equity", "valuation"],
    "depreciation": ["all", "manufacturing", "real_estate", "capital_intensive"],
    "inventory": ["manufacturing", "retail", "wholesale", "ecommerce"],
    "goodwill": ["all", "rollup", "private_equity"],
    "ppe": ["manufacturing", "real_estate", "capital_intensive"],
    "total_debt": ["all", "leveraged"],
    "net_debt": ["all", "leveraged", "private_equity"],
    "debt_to_ebitda": ["all", "private_equity", "leveraged_finance"],
    "interest_coverage": ["all", "leveraged", "credit_analysis"],
    "interest_rate": ["all", "leveraged", "banking"],
    "rd_expense": ["technology", "biotech", "pharma", "manufacturing", "saas"],
    "sga": ["all", "corporate", "public_companies"],
}


# ============================================================
# PHASE 2: Confidence scoring metadata
# ============================================================

CONFIDENCE_METADATA = {
    "revenue": {
        "high_confidence_signals": [
            "Appears in income statement header",
            "Labeled as 'Revenue', 'Sales', or 'Turnover'",
            "First line item in P&L",
            "Largest positive income statement value"
        ],
        "medium_confidence_signals": [
            "Labeled generically as 'Income'",
            "In operating section but not at top"
        ],
        "low_confidence_signals": [
            "Unlabeled number",
            "Appears outside standard income statement"
        ],
        "validation_boosters": [
            "Can derive gross_profit = revenue - cogs",
            "Consistent with prior period trends"
        ],
        "common_errors": [
            "Confusing gross revenue with net revenue",
            "Including other income in revenue"
        ]
    },
    "ebitda": {
        "high_confidence_signals": [
            "Explicitly labeled as 'EBITDA' or 'Adjusted EBITDA'",
            "Can derive from EBIT + D&A",
            "Appears in management discussion section"
        ],
        "validation_boosters": [
            "Matches EBIT + depreciation + amortization",
            "Consistent EBITDA margin with prior periods"
        ],
        "ambiguity_notes": "EBITDA is non-GAAP; definitions vary by company. Always check footnotes for adjustments."
    },
    "net_income": {
        "high_confidence_signals": [
            "Last line of income statement",
            "Labeled as 'Net Income' or 'Net Profit'",
            "Can derive from EBT - taxes"
        ],
        "validation_boosters": [
            "Matches EBT - tax_expense",
            "Ties to retained earnings change on balance sheet"
        ]
    },
    "total_assets": {
        "high_confidence_signals": [
            "Labeled as 'Total Assets'",
            "Last line of assets section",
            "Equals liabilities + equity"
        ],
        "validation_boosters": [
            "Satisfies A = L + E equation",
            "Equals sum of current + non-current assets"
        ]
    },
    "fcf": {
        "high_confidence_signals": [
            "Explicitly labeled as 'Free Cash Flow' or 'FCF'",
            "Can derive from CFO - capex",
            "Disclosed in management discussion"
        ],
        "validation_boosters": [
            "Matches CFO - capex calculation",
            "Consistent FCF conversion with prior periods"
        ],
        "ambiguity_notes": "Some companies use levered vs unlevered FCF; check definition"
    },
    "debt_to_ebitda": {
        "high_confidence_signals": [
            "Labeled as 'Leverage' or 'Debt/EBITDA'",
            "Can calculate from balance sheet and P&L",
            "Disclosed in debt covenants section"
        ],
        "validation_boosters": [
            "Matches total_debt / ebitda calculation",
            "Consistent with bank covenant definitions"
        ]
    },
}


# ============================================================
# PHASE 3: GAAP/IFRS and regulatory context
# ============================================================

GAAP_IFRS = {
    "revenue": {
        "us_gaap": {"guidance": "ASC 606 - Revenue from Contracts with Customers"},
        "ifrs": {"guidance": "IFRS 15 - Revenue from Contracts with Customers", "differences": "Largely aligned; minor disclosure differences"}
    },
    "inventory": {
        "us_gaap": {"guidance": "ASC 330 - Inventory", "methods": ["FIFO", "LIFO", "Weighted Average"]},
        "ifrs": {"guidance": "IAS 2 - Inventories", "methods": ["FIFO", "Weighted Average"], "differences": "IFRS prohibits LIFO"}
    },
    "depreciation": {
        "us_gaap": {"guidance": "ASC 360 - Property, Plant, and Equipment", "component_depreciation": "optional"},
        "ifrs": {"guidance": "IAS 16 - Property, Plant and Equipment", "component_depreciation": "required", "differences": "IFRS requires component depreciation"}
    },
    "goodwill": {
        "us_gaap": {"guidance": "ASC 350-20 - Goodwill", "treatment": "Impairment testing only"},
        "ifrs": {"guidance": "IAS 36 - Impairment of Assets", "differences": "IFRS prohibits reversal of goodwill impairment"}
    },
}

REGULATORY_CONTEXT = {
    "revenue": {"sec_forms": ["10-K", "10-Q", "8-K"], "audit_sensitivity": "high", "common_fraud_area": True},
    "net_income": {"sec_forms": ["10-K", "10-Q"], "audit_sensitivity": "critical"},
    "ebitda": {"sec_forms": ["8-K", "10-K"], "is_non_gaap": True, "disclosure_requirements": ["Must reconcile to GAAP net income"]},
    "goodwill": {"sec_forms": ["10-K"], "audit_sensitivity": "high"},
}


# ============================================================
# PHASE 3: Industry-specific metrics
# ============================================================

INDUSTRY_METRICS = {
    "metrics": [
        # SaaS
        {"canonical_name": "arr", "category": "metrics", "display_name": "Annual Recurring Revenue",
         "aliases": ["ARR", "Annualized Recurring Revenue", "Annual Contract Value"],
         "definition": "Annualized value of active recurring revenue contracts",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["saas", "subscription", "technology"],
         "validation_rules": {"type": "currency", "min_value": 0, "derivation": "mrr * 12"}},
        {"canonical_name": "mrr", "category": "metrics", "display_name": "Monthly Recurring Revenue",
         "aliases": ["MRR", "Monthly Recurring Rev"],
         "definition": "Monthly value of recurring revenue from active subscriptions",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["saas", "subscription", "technology"],
         "validation_rules": {"type": "currency", "min_value": 0}},
        {"canonical_name": "cac", "category": "metrics", "display_name": "Customer Acquisition Cost",
         "aliases": ["CAC", "Acquisition Cost", "Cost per Acquisition", "CPA"],
         "definition": "Average cost to acquire a new customer",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["saas", "subscription", "ecommerce"],
         "validation_rules": {"type": "currency", "min_value": 0}},
        {"canonical_name": "ltv", "category": "metrics", "display_name": "Customer Lifetime Value",
         "aliases": ["LTV", "CLV", "Customer LTV", "CLTV", "Lifetime Value"],
         "definition": "Total revenue expected from a customer over their lifetime",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["saas", "subscription", "ecommerce"],
         "validation_rules": {"type": "currency", "min_value": 0}},
        {"canonical_name": "ltv_cac_ratio", "category": "metrics", "display_name": "LTV to CAC Ratio",
         "aliases": ["LTV/CAC", "LTV:CAC"],
         "definition": "Customer lifetime value divided by acquisition cost; healthy target is 3:1",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["saas", "subscription"],
         "validation_rules": {"type": "ratio", "min_value": 0, "derivation": "ltv / cac"}},
        {"canonical_name": "churn_rate", "category": "metrics", "display_name": "Churn Rate",
         "aliases": ["Churn", "Customer Churn", "Attrition Rate", "Logo Churn"],
         "definition": "Percentage of customers who cancel subscriptions in a period",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["saas", "subscription"],
         "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1}},
        {"canonical_name": "net_revenue_retention", "category": "metrics", "display_name": "Net Revenue Retention",
         "aliases": ["NRR", "Net Retention", "NDR", "Net Dollar Retention"],
         "definition": "Revenue retention from existing customers including expansions; >100% indicates growth from existing base",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["saas", "subscription"],
         "validation_rules": {"type": "percentage", "min_value": 0}},
        {"canonical_name": "rule_of_40", "category": "metrics", "display_name": "Rule of 40",
         "aliases": ["Rule of 40 Score", "R40"],
         "definition": "Growth rate + profit margin; healthy SaaS companies should exceed 40%",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["saas"],
         "validation_rules": {"type": "percentage"}},
        {"canonical_name": "burn_multiple", "category": "metrics", "display_name": "Burn Multiple",
         "aliases": ["Cash Burn Multiple", "Efficiency Score"],
         "definition": "Net burn / net new ARR; measures capital efficiency",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["saas", "venture"],
         "validation_rules": {"type": "ratio", "min_value": 0}},
        # Retail
        {"canonical_name": "same_store_sales", "category": "metrics", "display_name": "Same Store Sales",
         "aliases": ["SSS", "Comp Store Sales", "Comparable Store Sales", "Like-for-Like Sales"],
         "definition": "Revenue from stores open for at least one year",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["retail"],
         "validation_rules": {"type": "currency", "min_value": 0}},
        {"canonical_name": "inventory_turnover", "category": "metrics", "display_name": "Inventory Turnover",
         "aliases": ["Inventory Turns", "Stock Turnover", "Turns"],
         "definition": "COGS / average inventory; measures how quickly inventory is sold",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["retail", "wholesale", "manufacturing"],
         "validation_rules": {"type": "ratio", "min_value": 0, "derivation": "cogs / average_inventory"}},
        {"canonical_name": "gmroi", "category": "metrics", "display_name": "Gross Margin Return on Investment",
         "aliases": ["GMROI", "Gross Margin ROI"],
         "definition": "Gross margin / average inventory cost; measures profitability of inventory",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["retail"],
         "validation_rules": {"type": "ratio", "min_value": 0}},
        {"canonical_name": "sales_per_square_foot", "category": "metrics", "display_name": "Sales per Square Foot",
         "aliases": ["Revenue per Sq Ft", "Sales/SF", "Productivity per Sq Ft"],
         "definition": "Annual sales / retail square footage; measures store productivity",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["retail"],
         "validation_rules": {"type": "currency", "min_value": 0}},
        # Manufacturing
        {"canonical_name": "capacity_utilization", "category": "metrics", "display_name": "Capacity Utilization",
         "aliases": ["Plant Utilization", "Utilization Rate"],
         "definition": "Actual output / maximum potential output",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["manufacturing", "capital_intensive"],
         "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1}},
        {"canonical_name": "oee", "category": "metrics", "display_name": "Overall Equipment Effectiveness",
         "aliases": ["OEE", "Equipment Effectiveness"],
         "definition": "Availability x Performance x Quality; measures manufacturing productivity",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["manufacturing"],
         "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1}},
        {"canonical_name": "scrap_rate", "category": "metrics", "display_name": "Scrap Rate",
         "aliases": ["Waste Rate", "Defect Rate"],
         "definition": "Value of scrapped materials / total production value",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["manufacturing"],
         "validation_rules": {"type": "percentage", "min_value": 0}},
        {"canonical_name": "first_pass_yield", "category": "metrics", "display_name": "First Pass Yield",
         "aliases": ["FPY", "Quality Yield", "Right First Time"],
         "definition": "Units passing quality without rework / total units produced",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["manufacturing"],
         "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1}},
        # Real Estate
        {"canonical_name": "noi", "category": "metrics", "display_name": "Net Operating Income",
         "aliases": ["NOI", "Operating Income (RE)", "Net Operating Profit"],
         "definition": "Rental income minus operating expenses; excludes financing and depreciation",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["real_estate"],
         "validation_rules": {"type": "currency", "derivation": "rental_income - operating_expenses"}},
        {"canonical_name": "cap_rate", "category": "metrics", "display_name": "Capitalization Rate",
         "aliases": ["Cap Rate", "NOI Yield"],
         "definition": "NOI / property value; measures return on real estate investment",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["real_estate"],
         "validation_rules": {"type": "percentage", "min_value": 0, "derivation": "noi / property_value"}},
        {"canonical_name": "occupancy_rate", "category": "metrics", "display_name": "Occupancy Rate",
         "aliases": ["Physical Occupancy", "Leased Percentage"],
         "definition": "Occupied units / total units; measures property utilization",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["real_estate"],
         "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1}},
        {"canonical_name": "ffo", "category": "metrics", "display_name": "Funds from Operations",
         "aliases": ["FFO", "REIT FFO"],
         "definition": "Net income + depreciation + amortization - gains on sales; REIT earnings metric",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["real_estate", "reit"],
         "validation_rules": {"type": "currency"}},
        {"canonical_name": "affo", "category": "metrics", "display_name": "Adjusted Funds from Operations",
         "aliases": ["AFFO", "Cash Available for Distribution", "CAD"],
         "definition": "FFO minus recurring capex; measures cash available for dividends",
         "typical_sign": "positive", "parent_canonical": None,
         "industry_tags": ["real_estate", "reit"],
         "validation_rules": {"type": "currency", "derivation": "ffo - maintenance_capex"}},
    ]
}


def enhance(input_path: str = "data/taxonomy.json",
            output_path: str = "data/taxonomy.json"):
    """Apply all Phase 1-3 enhancements to taxonomy.json."""

    with open(input_path, 'r') as f:
        data = json.load(f)

    stats = {"ocr": 0, "format": 0, "industry": 0, "confidence": 0, "gaap": 0, "regulatory": 0, "new_items": 0}

    # PHASE 1: OCR variants + format examples for key items
    for canonical_name, enhancements in PHASE1_OCR_AND_FORMATS.items():
        item = find_item(data, canonical_name)
        if item:
            if 'ocr_variants' in enhancements:
                item['ocr_variants'] = enhancements['ocr_variants']
                stats['ocr'] += 1
            if 'format_examples' in enhancements:
                item['format_examples'] = enhancements['format_examples']
                stats['format'] += 1

    # PHASE 1: Industry tags for ALL items
    for cat_name, cat_items in data['categories'].items():
        for item in cat_items:
            cn = item['canonical_name']
            if cn in INDUSTRY_TAG_OVERRIDES:
                item['industry_tags'] = INDUSTRY_TAG_OVERRIDES[cn]
            elif 'industry_tags' not in item:
                item['industry_tags'] = DEFAULT_INDUSTRY_TAGS.get(cat_name, ["all"])
            stats['industry'] += 1

    # PHASE 2: Confidence scoring
    for canonical_name, metadata in CONFIDENCE_METADATA.items():
        item = find_item(data, canonical_name)
        if item:
            item['confidence_scoring'] = metadata
            stats['confidence'] += 1

    # PHASE 3: GAAP/IFRS
    for canonical_name, standards in GAAP_IFRS.items():
        item = find_item(data, canonical_name)
        if item:
            item['accounting_standards'] = standards
            stats['gaap'] += 1

    # PHASE 3: Regulatory context
    for canonical_name, context in REGULATORY_CONTEXT.items():
        item = find_item(data, canonical_name)
        if item:
            item['regulatory_context'] = context
            stats['regulatory'] += 1

    # PHASE 3: Industry-specific metrics
    for category, metrics in INDUSTRY_METRICS.items():
        if category not in data['categories']:
            data['categories'][category] = []
        for metric in metrics:
            if not item_exists(data, metric['canonical_name']):
                data['categories'][category].append(metric)
                stats['new_items'] += 1

    # Update version
    data['version'] = "2.1.0"

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    total_items = sum(len(items) for items in data['categories'].values())

    print(f"✅ Phase 1: {stats['ocr']} OCR variants, {stats['format']} format examples, {stats['industry']} industry tags")
    print(f"✅ Phase 2: {stats['confidence']} confidence scoring items")
    print(f"✅ Phase 3: {stats['gaap']} GAAP/IFRS, {stats['regulatory']} regulatory, {stats['new_items']} new industry metrics")
    print(f"✅ Total items: {total_items}")
    print(f"✅ Version: {data['version']}")
    return stats


if __name__ == "__main__":
    enhance()