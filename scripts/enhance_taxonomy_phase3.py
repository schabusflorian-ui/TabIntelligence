#!/usr/bin/env python3
"""
Phase 3 Taxonomy Enhancement Script - Domain Expansion

Adds:
1. Industry-specific metrics (SaaS, retail, manufacturing, real estate)
2. GAAP vs IFRS accounting standard distinctions
3. Regulatory context metadata
4. Sector-specific validation rules

Usage:
    python scripts/enhance_taxonomy_phase3.py
"""

import json

# Industry-specific metrics to add
INDUSTRY_METRICS = {
    # SAAS METRICS (15+ items)
    "saas": [
        {
            "canonical_name": "arr",
            "category": "metrics",
            "display_name": "Annual Recurring Revenue",
            "aliases": [
                "ARR",
                "Annualized Recurring Revenue",
                "Annual Contract Value",
                "Recurring Revenue ARR",
            ],
            "definition": "Annualized value of active recurring revenue contracts",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas", "subscription", "technology"],
            "validation_rules": {
                "type": "currency",
                "min_value": 0,
                "derivation": "mrr * 12",
                "cross_item_validation": {
                    "relationships": [
                        {"rule": "arr == mrr * 12", "tolerance": 0.02, "optional": True}
                    ]
                },
            },
            "format_examples": [
                {"value": "12,000,000", "context": "ARR in dollars"},
                {"value": "$12M ARR", "context": "Abbreviated format"},
            ],
        },
        {
            "canonical_name": "mrr",
            "category": "metrics",
            "display_name": "Monthly Recurring Revenue",
            "aliases": ["MRR", "Monthly Recurring Rev", "Recurring Revenue MRR"],
            "definition": "Monthly value of recurring revenue from active subscriptions",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas", "subscription", "technology"],
            "validation_rules": {"type": "currency", "min_value": 0},
        },
        {
            "canonical_name": "cac",
            "category": "metrics",
            "display_name": "Customer Acquisition Cost",
            "aliases": ["CAC", "Acquisition Cost", "Cost per Acquisition", "CPA"],
            "definition": "Average cost to acquire a new customer (sales & marketing expense / new customers)",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas", "subscription", "ecommerce", "technology"],
            "validation_rules": {
                "type": "currency",
                "min_value": 0,
                "derivation": "sales_marketing_expense / new_customers_acquired",
            },
        },
        {
            "canonical_name": "ltv",
            "category": "metrics",
            "display_name": "Customer Lifetime Value",
            "aliases": ["LTV", "CLV", "Customer LTV", "Lifetime Value", "CLTV"],
            "definition": "Total revenue expected from a customer over their lifetime",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas", "subscription", "ecommerce"],
            "validation_rules": {
                "type": "currency",
                "min_value": 0,
                "derivation": "arpu / churn_rate",
            },
        },
        {
            "canonical_name": "ltv_cac_ratio",
            "category": "metrics",
            "display_name": "LTV to CAC Ratio",
            "aliases": ["LTV/CAC", "LTV:CAC", "Lifetime Value to CAC"],
            "definition": "Ratio of customer lifetime value to acquisition cost; healthy SaaS target is 3:1",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas", "subscription"],
            "validation_rules": {"type": "ratio", "min_value": 0, "derivation": "ltv / cac"},
        },
        {
            "canonical_name": "churn_rate",
            "category": "metrics",
            "display_name": "Churn Rate",
            "aliases": ["Churn", "Customer Churn", "Attrition Rate", "Logo Churn"],
            "definition": "Percentage of customers who cancel subscriptions in a period",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas", "subscription"],
            "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1},
        },
        {
            "canonical_name": "net_revenue_retention",
            "category": "metrics",
            "display_name": "Net Revenue Retention",
            "aliases": ["NRR", "Net Retention", "NDR", "Net Dollar Retention"],
            "definition": "Revenue retention from existing customers including expansions and downgrades; >100% indicates growth from existing base",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas", "subscription"],
            "validation_rules": {"type": "percentage", "min_value": 0},
        },
        {
            "canonical_name": "magic_number",
            "category": "metrics",
            "display_name": "Magic Number",
            "aliases": ["SaaS Magic Number", "Sales Efficiency"],
            "definition": "Net new ARR / sales & marketing spend; measures sales efficiency",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas"],
            "validation_rules": {"type": "ratio", "min_value": 0},
        },
        {
            "canonical_name": "rule_of_40",
            "category": "metrics",
            "display_name": "Rule of 40",
            "aliases": ["Rule of 40 Score", "R40"],
            "definition": "Growth rate + profit margin; healthy SaaS companies should exceed 40%",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas"],
            "validation_rules": {
                "type": "percentage",
                "derivation": "revenue_growth_rate + ebitda_margin",
            },
        },
        {
            "canonical_name": "arpu",
            "category": "metrics",
            "display_name": "Average Revenue Per User",
            "aliases": ["ARPU", "Revenue per Customer", "ARPC", "Average Revenue per Customer"],
            "definition": "Average monthly or annual revenue per active user/customer",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas", "subscription", "technology"],
            "validation_rules": {
                "type": "currency",
                "min_value": 0,
                "derivation": "mrr / active_customers",
            },
        },
        {
            "canonical_name": "gross_retention",
            "category": "metrics",
            "display_name": "Gross Revenue Retention",
            "aliases": ["GRR", "Gross Retention"],
            "definition": "Revenue retention from existing customers excluding expansions; measures pure retention",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas", "subscription"],
            "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1},
        },
        {
            "canonical_name": "cac_payback_period",
            "category": "metrics",
            "display_name": "CAC Payback Period",
            "aliases": ["Payback Period", "Months to Recover CAC"],
            "definition": "Months required to recover customer acquisition cost from gross margin",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas", "subscription"],
            "validation_rules": {"type": "months", "min_value": 0},
        },
        {
            "canonical_name": "expansion_revenue",
            "category": "metrics",
            "display_name": "Expansion Revenue",
            "aliases": ["Upsell Revenue", "Cross-sell Revenue", "Expansion MRR"],
            "definition": "Additional revenue from existing customers through upsells, cross-sells, or usage growth",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas", "subscription"],
            "validation_rules": {"type": "currency", "min_value": 0},
        },
        {
            "canonical_name": "quick_ratio_saas",
            "category": "metrics",
            "display_name": "Quick Ratio (SaaS)",
            "aliases": ["SaaS Quick Ratio", "Growth Efficiency"],
            "definition": "(New MRR + Expansion MRR) / (Churned MRR + Contraction MRR); measures growth efficiency",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas"],
            "validation_rules": {"type": "ratio", "min_value": 0},
        },
        {
            "canonical_name": "burn_multiple",
            "category": "metrics",
            "display_name": "Burn Multiple",
            "aliases": ["Cash Burn Multiple", "Efficiency Score"],
            "definition": "Net burn / net new ARR; measures capital efficiency",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["saas", "venture"],
            "validation_rules": {"type": "ratio", "min_value": 0},
        },
    ],
    # RETAIL METRICS (10+ items)
    "retail": [
        {
            "canonical_name": "same_store_sales",
            "category": "metrics",
            "display_name": "Same Store Sales",
            "aliases": ["SSS", "Comp Store Sales", "Comparable Store Sales", "Like-for-Like Sales"],
            "definition": "Revenue from stores open for at least one year; excludes new store growth",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["retail"],
            "validation_rules": {"type": "currency", "min_value": 0},
        },
        {
            "canonical_name": "inventory_turnover",
            "category": "metrics",
            "display_name": "Inventory Turnover",
            "aliases": ["Inventory Turns", "Stock Turnover", "Turns"],
            "definition": "COGS / average inventory; measures how quickly inventory is sold",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["retail", "wholesale", "manufacturing"],
            "validation_rules": {
                "type": "ratio",
                "min_value": 0,
                "derivation": "cogs / average_inventory",
            },
        },
        {
            "canonical_name": "gmroi",
            "category": "metrics",
            "display_name": "Gross Margin Return on Investment",
            "aliases": ["GMROI", "GMROII", "Gross Margin ROI"],
            "definition": "Gross margin / average inventory cost; measures profitability of inventory investment",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["retail"],
            "validation_rules": {
                "type": "ratio",
                "min_value": 0,
                "derivation": "gross_profit / average_inventory_cost",
            },
        },
        {
            "canonical_name": "sell_through_rate",
            "category": "metrics",
            "display_name": "Sell-Through Rate",
            "aliases": ["Sell Through", "STR", "Sell Through Percentage"],
            "definition": "Units sold / units received; measures product demand",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["retail", "ecommerce"],
            "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1},
        },
        {
            "canonical_name": "sales_per_square_foot",
            "category": "metrics",
            "display_name": "Sales per Square Foot",
            "aliases": ["Revenue per Sq Ft", "Sales/SF", "Productivity per Sq Ft"],
            "definition": "Annual sales / retail square footage; measures store productivity",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["retail"],
            "validation_rules": {"type": "currency", "min_value": 0},
        },
        {
            "canonical_name": "basket_size",
            "category": "metrics",
            "display_name": "Average Basket Size",
            "aliases": ["Average Transaction Value", "ATV", "Basket Value"],
            "definition": "Total sales / number of transactions; average purchase amount per customer visit",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["retail", "ecommerce"],
            "validation_rules": {"type": "currency", "min_value": 0},
        },
        {
            "canonical_name": "conversion_rate",
            "category": "metrics",
            "display_name": "Conversion Rate",
            "aliases": ["Sales Conversion", "Traffic Conversion"],
            "definition": "Transactions / store traffic; percentage of visitors who make a purchase",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["retail", "ecommerce"],
            "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1},
        },
        {
            "canonical_name": "shrinkage_rate",
            "category": "metrics",
            "display_name": "Shrinkage Rate",
            "aliases": ["Inventory Shrink", "Shrink", "Loss Rate"],
            "definition": "Value of inventory lost to theft, damage, or error / total inventory value",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["retail"],
            "validation_rules": {"type": "percentage", "min_value": 0},
        },
        {
            "canonical_name": "days_inventory_outstanding",
            "category": "metrics",
            "display_name": "Days Inventory Outstanding",
            "aliases": ["DIO", "Days in Inventory", "Inventory Days"],
            "definition": "(Average inventory / COGS) * 365; days to sell inventory",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["retail", "manufacturing", "wholesale"],
            "validation_rules": {
                "type": "days",
                "min_value": 0,
                "derivation": "(average_inventory / cogs) * 365",
            },
        },
        {
            "canonical_name": "markdown_rate",
            "category": "metrics",
            "display_name": "Markdown Rate",
            "aliases": ["Discount Rate", "Promotional Discount %"],
            "definition": "Value of markdowns / total sales; measures promotional intensity",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["retail"],
            "validation_rules": {"type": "percentage", "min_value": 0},
        },
    ],
    # MANUFACTURING METRICS (10+ items)
    "manufacturing": [
        {
            "canonical_name": "capacity_utilization",
            "category": "metrics",
            "display_name": "Capacity Utilization",
            "aliases": ["Plant Utilization", "Utilization Rate"],
            "definition": "Actual output / maximum potential output; measures efficiency of production capacity",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["manufacturing", "capital_intensive"],
            "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1},
        },
        {
            "canonical_name": "oee",
            "category": "metrics",
            "display_name": "Overall Equipment Effectiveness",
            "aliases": ["OEE", "Equipment Effectiveness"],
            "definition": "Availability × Performance × Quality; measures manufacturing productivity",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["manufacturing"],
            "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1},
        },
        {
            "canonical_name": "cycle_time",
            "category": "metrics",
            "display_name": "Cycle Time",
            "aliases": ["Production Cycle Time", "Manufacturing Lead Time"],
            "definition": "Total time from start to finish of production process",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["manufacturing"],
            "validation_rules": {"type": "time", "min_value": 0},
        },
        {
            "canonical_name": "scrap_rate",
            "category": "metrics",
            "display_name": "Scrap Rate",
            "aliases": ["Waste Rate", "Defect Rate"],
            "definition": "Value of scrapped materials / total production value; measures quality and waste",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["manufacturing"],
            "validation_rules": {"type": "percentage", "min_value": 0},
        },
        {
            "canonical_name": "first_pass_yield",
            "category": "metrics",
            "display_name": "First Pass Yield",
            "aliases": ["FPY", "Quality Yield", "Right First Time"],
            "definition": "Units passing quality inspection without rework / total units produced",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["manufacturing"],
            "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1},
        },
        {
            "canonical_name": "direct_labor_efficiency",
            "category": "metrics",
            "display_name": "Direct Labor Efficiency",
            "aliases": ["Labor Productivity", "Workforce Efficiency"],
            "definition": "Standard hours / actual hours worked; measures labor productivity",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["manufacturing"],
            "validation_rules": {"type": "percentage", "min_value": 0},
        },
        {
            "canonical_name": "material_yield",
            "category": "metrics",
            "display_name": "Material Yield",
            "aliases": ["Raw Material Efficiency", "Material Utilization"],
            "definition": "Usable output / raw material input; measures material efficiency",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["manufacturing"],
            "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1},
        },
        {
            "canonical_name": "production_volume",
            "category": "metrics",
            "display_name": "Production Volume",
            "aliases": ["Units Produced", "Output Volume", "Manufacturing Output"],
            "definition": "Total units manufactured in a period",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["manufacturing"],
            "validation_rules": {"type": "units", "min_value": 0},
        },
        {
            "canonical_name": "cost_per_unit",
            "category": "metrics",
            "display_name": "Cost per Unit",
            "aliases": ["Unit Cost", "Per Unit Cost", "Manufacturing Cost per Unit"],
            "definition": "Total production cost / units produced",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["manufacturing"],
            "validation_rules": {
                "type": "currency",
                "min_value": 0,
                "derivation": "total_production_cost / production_volume",
            },
        },
        {
            "canonical_name": "wip_inventory",
            "category": "balance_sheet",
            "display_name": "Work in Process Inventory",
            "aliases": ["WIP", "Work in Progress", "In-Process Inventory"],
            "definition": "Value of partially completed goods in production",
            "typical_sign": "positive",
            "parent_canonical": "inventory",
            "industry_tags": ["manufacturing"],
            "validation_rules": {"type": "currency", "min_value": 0},
        },
    ],
    # REAL ESTATE METRICS (10+ items)
    "real_estate": [
        {
            "canonical_name": "noi",
            "category": "metrics",
            "display_name": "Net Operating Income",
            "aliases": ["NOI", "Operating Income (RE)", "Net Operating Profit"],
            "definition": "Rental income minus operating expenses; excludes financing and depreciation",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["real_estate"],
            "validation_rules": {
                "type": "currency",
                "derivation": "rental_income - operating_expenses",
            },
        },
        {
            "canonical_name": "cap_rate",
            "category": "metrics",
            "display_name": "Capitalization Rate",
            "aliases": ["Cap Rate", "NOI Yield"],
            "definition": "NOI / property value; measures return on real estate investment",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["real_estate"],
            "validation_rules": {
                "type": "percentage",
                "min_value": 0,
                "derivation": "noi / property_value",
            },
        },
        {
            "canonical_name": "occupancy_rate",
            "category": "metrics",
            "display_name": "Occupancy Rate",
            "aliases": ["Physical Occupancy", "Leased Percentage"],
            "definition": "Occupied units / total units; measures property utilization",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["real_estate"],
            "validation_rules": {"type": "percentage", "min_value": 0, "max_value": 1},
        },
        {
            "canonical_name": "ffo",
            "category": "metrics",
            "display_name": "Funds from Operations",
            "aliases": ["FFO", "REIT FFO"],
            "definition": "Net income + depreciation + amortization - gains on sales; REIT earnings metric",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["real_estate", "reit"],
            "validation_rules": {
                "type": "currency",
                "derivation": "net_income + depreciation + amortization - gains_on_property_sales",
            },
        },
        {
            "canonical_name": "affo",
            "category": "metrics",
            "display_name": "Adjusted Funds from Operations",
            "aliases": ["AFFO", "Cash Available for Distribution", "CAD"],
            "definition": "FFO - recurring capex; measures cash available for dividends",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["real_estate", "reit"],
            "validation_rules": {"type": "currency", "derivation": "ffo - maintenance_capex"},
        },
        {
            "canonical_name": "dscr_real_estate",
            "category": "metrics",
            "display_name": "Debt Service Coverage Ratio (RE)",
            "aliases": ["DSCR", "NOI / Debt Service"],
            "definition": "NOI / total debt service; measures ability to service property debt",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["real_estate"],
            "validation_rules": {
                "type": "ratio",
                "min_value": 0,
                "derivation": "noi / debt_service",
            },
        },
        {
            "canonical_name": "ltv_real_estate",
            "category": "metrics",
            "display_name": "Loan to Value Ratio",
            "aliases": ["LTV", "Loan-to-Value"],
            "definition": "Loan amount / property value; measures leverage",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["real_estate"],
            "validation_rules": {
                "type": "percentage",
                "min_value": 0,
                "max_value": 1.5,
                "derivation": "loan_balance / property_value",
            },
        },
        {
            "canonical_name": "rent_per_square_foot",
            "category": "metrics",
            "display_name": "Rent per Square Foot",
            "aliases": ["Rent/SF", "Rental Rate per Sq Ft"],
            "definition": "Annual rent / rentable square feet; measures rental rates",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["real_estate"],
            "validation_rules": {"type": "currency", "min_value": 0},
        },
        {
            "canonical_name": "operating_expense_ratio",
            "category": "metrics",
            "display_name": "Operating Expense Ratio",
            "aliases": ["OER", "OpEx Ratio (RE)"],
            "definition": "Operating expenses / gross operating income; measures efficiency",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["real_estate"],
            "validation_rules": {
                "type": "percentage",
                "min_value": 0,
                "max_value": 1,
                "derivation": "operating_expenses / gross_operating_income",
            },
        },
        {
            "canonical_name": "cash_on_cash_return",
            "category": "metrics",
            "display_name": "Cash on Cash Return",
            "aliases": ["CoC Return", "Cash Yield"],
            "definition": "Annual pre-tax cash flow / total cash invested; measures equity return",
            "typical_sign": "positive",
            "parent_canonical": None,
            "industry_tags": ["real_estate"],
            "validation_rules": {
                "type": "percentage",
                "min_value": -1,
                "derivation": "annual_cash_flow / cash_invested",
            },
        },
    ],
}


# GAAP vs IFRS distinctions for existing items
GAAP_IFRS_DISTINCTIONS = {
    "revenue": {
        "us_gaap": {
            "guidance": "ASC 606 - Revenue from Contracts with Customers",
            "key_principles": [
                "Five-step model for revenue recognition",
                "Performance obligations must be distinct",
            ],
        },
        "ifrs": {
            "guidance": "IFRS 15 - Revenue from Contracts with Customers",
            "key_principles": [
                "Converged with US GAAP in 2018",
                "Minor differences in implementation",
            ],
            "differences": "Largely aligned with US GAAP; minor differences in disclosure requirements",
        },
    },
    "goodwill": {
        "us_gaap": {
            "guidance": "ASC 350-20 - Goodwill",
            "treatment": "Impairment testing only (no amortization)",
            "testing_frequency": "Annual or when triggering event occurs",
        },
        "ifrs": {
            "guidance": "IAS 36 - Impairment of Assets",
            "treatment": "Impairment testing only (no amortization)",
            "testing_frequency": "Annual",
            "differences": "IFRS prohibits reversal of goodwill impairment; US GAAP also prohibits reversal",
        },
    },
    "inventory": {
        "us_gaap": {
            "guidance": "ASC 330 - Inventory",
            "valuation_methods": ["FIFO", "LIFO", "Weighted Average"],
            "lower_of": "cost or market (NRV after 2015)",
        },
        "ifrs": {
            "guidance": "IAS 2 - Inventories",
            "valuation_methods": ["FIFO", "Weighted Average"],
            "lower_of": "cost or net realizable value",
            "differences": "IFRS prohibits LIFO; US GAAP allows LIFO",
        },
    },
    "depreciation": {
        "us_gaap": {
            "guidance": "ASC 360 - Property, Plant, and Equipment",
            "methods": ["Straight-line", "Declining balance", "Units of production"],
            "component_depreciation": "Optional",
        },
        "ifrs": {
            "guidance": "IAS 16 - Property, Plant and Equipment",
            "methods": ["Straight-line", "Declining balance", "Units of production"],
            "component_depreciation": "Required",
            "differences": "IFRS requires component depreciation; US GAAP is optional",
        },
    },
    "lease_expense": {
        "us_gaap": {
            "guidance": "ASC 842 - Leases",
            "operating_leases": "On balance sheet as ROU asset + liability",
            "effective_date": "2019 for public companies",
        },
        "ifrs": {
            "guidance": "IFRS 16 - Leases",
            "operating_leases": "On balance sheet (similar to finance lease)",
            "effective_date": "2019",
            "differences": "Minor differences in exemptions and measurement",
        },
    },
}


# Regulatory context for key items
REGULATORY_CONTEXT = {
    "revenue": {
        "sec_forms": ["10-K", "10-Q", "8-K"],
        "required_for": ["public_companies"],
        "audit_sensitivity": "high",
        "common_fraud_area": True,
        "footnote_triggers": [
            "Revenue recognition policy changes",
            "Multiple performance obligations",
            "Variable consideration",
        ],
    },
    "net_income": {
        "sec_forms": ["10-K", "10-Q"],
        "required_for": ["public_companies"],
        "audit_sensitivity": "critical",
        "reconciliation_requirements": {
            "gaap_to_non_gaap": "Must reconcile adjusted net income to GAAP net income in MD&A"
        },
    },
    "ebitda": {
        "sec_forms": ["8-K", "10-K (MD&A)"],
        "required_for": [],
        "is_non_gaap": True,
        "disclosure_requirements": [
            "Must reconcile to GAAP net income",
            "Must explain why management uses this metric",
            "Cannot be more prominent than GAAP measures",
        ],
    },
    "goodwill": {
        "sec_forms": ["10-K"],
        "required_for": ["public_companies", "companies_with_acquisitions"],
        "audit_sensitivity": "high",
        "footnote_triggers": [
            "Goodwill impairment",
            "Acquisitions",
            "Annual impairment testing results",
        ],
    },
}


def enhance_taxonomy_phase3(
    input_path: str = "data/taxonomy_seed.json", output_path: str = "data/taxonomy_seed.json"
):
    """Add Phase 3 domain expansion enhancements."""

    # Load existing taxonomy
    with open(input_path, "r") as f:
        data = json.load(f)

    # Track additions
    items_added = 0
    gaap_ifrs_added = 0
    regulatory_added = 0

    # Add industry-specific metrics
    for industry, metrics in INDUSTRY_METRICS.items():
        for metric in metrics:
            # Check if already exists
            if not any(
                item["canonical_name"] == metric["canonical_name"] for item in data["items"]
            ):
                data["items"].append(metric)
                items_added += 1

    # Add GAAP/IFRS distinctions to existing items
    for canonical_name, distinctions in GAAP_IFRS_DISTINCTIONS.items():
        for item in data["items"]:
            if item["canonical_name"] == canonical_name:
                item["accounting_standards"] = distinctions
                gaap_ifrs_added += 1
                break

    # Add regulatory context to existing items
    for canonical_name, context in REGULATORY_CONTEXT.items():
        for item in data["items"]:
            if item["canonical_name"] == canonical_name:
                item["regulatory_context"] = context
                regulatory_added += 1
                break

    # Update version
    data["version"] = "1.5.0"
    data["last_updated"] = "2026-02-24"

    # Write enhanced taxonomy
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"✅ Added {items_added} industry-specific metrics")
    print(f"   - SaaS: {len(INDUSTRY_METRICS['saas'])} items")
    print(f"   - Retail: {len(INDUSTRY_METRICS['retail'])} items")
    print(f"   - Manufacturing: {len(INDUSTRY_METRICS['manufacturing'])} items")
    print(f"   - Real Estate: {len(INDUSTRY_METRICS['real_estate'])} items")
    print(f"✅ Added GAAP/IFRS distinctions to {gaap_ifrs_added} items")
    print(f"✅ Added regulatory context to {regulatory_added} items")
    print(f"✅ Total items now: {len(data['items'])}")
    print(f"✅ Version updated to {data['version']}")
    print(f"✅ Saved to {output_path}")

    return {
        "items_added": items_added,
        "gaap_ifrs_added": gaap_ifrs_added,
        "regulatory_added": regulatory_added,
        "total_items": len(data["items"]),
    }


if __name__ == "__main__":
    enhance_taxonomy_phase3()
