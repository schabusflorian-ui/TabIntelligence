#!/usr/bin/env python3
"""
Phase 1 Taxonomy Enhancement Script

Adds OCR robustness, format examples, and industry tags to top 50 items.

Usage:
    python scripts/enhance_taxonomy_phase1.py
"""

import json
from pathlib import Path
from typing import Dict, List

# Enhanced metadata for top 50 most common items
ENHANCEMENTS = {
    # INCOME STATEMENT
    "revenue": {
        "ocr_variants": [
            "Rev enue", "Reyenue", "RevenUe", "REVENUE", "revenue.",
            "Reveπue", "Rev-enue", "Rɇvenue", "Revenuɇ"
        ],
        "format_examples": [
            {"value": "1,234,567", "context": "US format with commas"},
            {"value": "1.234.567", "context": "European format"},
            {"value": "$1.2M", "context": "Abbreviated millions"},
            {"value": "1234567", "context": "No separators"}
        ],
        "industry_tags": ["all", "saas", "manufacturing", "retail", "services", "real_estate"]
    },
    "cogs": {
        "ocr_variants": [
            "COG S", "C0GS", "COGS.", "cogs", "Co GS",
            "CDGS", "COGS:", "C O G S"
        ],
        "format_examples": [
            {"value": "(234,567)", "context": "Parentheses for expense"},
            {"value": "234,567", "context": "Positive number"},
            {"value": "($234.5K)", "context": "Abbreviated with currency"}
        ],
        "industry_tags": ["manufacturing", "retail", "ecommerce", "wholesale"]
    },
    "gross_profit": {
        "ocr_variants": [
            "Gross Prof it", "Gr oss Profit", "GROSS PROFIT",
            "Gross-Profit", "GrossProfit", "Gross Proϐt"
        ],
        "format_examples": [
            {"value": "1,000,000", "context": "Positive profit"},
            {"value": "(50,000)", "context": "Loss shown in parentheses"}
        ],
        "industry_tags": ["all", "manufacturing", "retail", "services"]
    },
    "opex": {
        "ocr_variants": [
            "Op ex", "OPEX", "0pex", "OpEx", "Op-Ex", "ΟpEx"
        ],
        "format_examples": [
            {"value": "(500,000)", "context": "Expense in parentheses"},
            {"value": "500,000", "context": "Positive number"}
        ],
        "industry_tags": ["all", "saas", "technology", "services"]
    },
    "sga": {
        "ocr_variants": [
            "SG A", "S G A", "SGA.", "S&G&A", "SG&A", "SGA:", "5GA"
        ],
        "format_examples": [
            {"value": "(1,234,567)", "context": "Expense format"},
            {"value": "$1.2M", "context": "Abbreviated"}
        ],
        "industry_tags": ["all", "corporate", "public_companies"]
    },
    "rd_expense": {
        "ocr_variants": [
            "R&D", "R &D", "R&D.", "R & D", "RandD", "RɁD", "R+D"
        ],
        "format_examples": [
            {"value": "(2,500,000)", "context": "High R&D spend"},
            {"value": "0", "context": "No R&D"}
        ],
        "industry_tags": ["technology", "biotech", "pharma", "manufacturing", "saas"]
    },
    "depreciation": {
        "ocr_variants": [
            "Depreciat ion", "Depre ciation", "DEPRECIATION",
            "Depreciaƫon", "Dep reciation", "Depreciation."
        ],
        "format_examples": [
            {"value": "(100,000)", "context": "Non-cash expense"},
            {"value": "100,000", "context": "Positive format"}
        ],
        "industry_tags": ["all", "manufacturing", "real_estate", "capital_intensive"]
    },
    "amortization": {
        "ocr_variants": [
            "Amort ization", "Amorti zation", "AMORTIZATION",
            "Amortizaƫon", "Amor tization", "Amortization."
        ],
        "format_examples": [
            {"value": "(50,000)", "context": "Intangible amortization"}
        ],
        "industry_tags": ["all", "technology", "saas", "media"]
    },
    "ebitda": {
        "ocr_variants": [
            "EBIT DA", "E BITDA", "EB1TDA", "EBITDA.", "Ebitda",
            "EBlTDA", "EBITDA:", "E-BITDA"
        ],
        "format_examples": [
            {"value": "5,000,000", "context": "Strong EBITDA"},
            {"value": "(500,000)", "context": "Negative EBITDA"}
        ],
        "industry_tags": ["all", "private_equity", "leveraged_finance"]
    },
    "ebit": {
        "ocr_variants": [
            "EB IT", "E BIT", "EB1T", "EBIT.", "Ebit", "EBlT", "EBIT:"
        ],
        "format_examples": [
            {"value": "4,500,000", "context": "Operating profit"}
        ],
        "industry_tags": ["all", "corporate", "public_companies"]
    },
    "operating_income": {
        "ocr_variants": [
            "Operating Inc ome", "Operating-Income", "OPERATING INCOME",
            "Operaƫng Income", "Operating lncome"
        ],
        "format_examples": [
            {"value": "3,000,000", "context": "Positive operating income"}
        ],
        "industry_tags": ["all", "public_companies"]
    },
    "interest_expense": {
        "ocr_variants": [
            "Interest Exp ense", "Interest-Expense", "INTEREST EXPENSE",
            "lnterest Expense", "Interest Expɇnse"
        ],
        "format_examples": [
            {"value": "(250,000)", "context": "Debt servicing cost"}
        ],
        "industry_tags": ["all", "leveraged", "real_estate"]
    },
    "interest_income": {
        "ocr_variants": [
            "Interest Inc ome", "Interest-Income", "INTEREST INCOME",
            "lnterest Income"
        ],
        "format_examples": [
            {"value": "10,000", "context": "Cash interest earned"}
        ],
        "industry_tags": ["all", "financial_services", "cash_rich"]
    },
    "ebt": {
        "ocr_variants": [
            "E BT", "EB T", "EBT.", "Ebt", "EBT:", "ΕBT"
        ],
        "format_examples": [
            {"value": "4,200,000", "context": "Pre-tax earnings"}
        ],
        "industry_tags": ["all", "corporate"]
    },
    "tax_expense": {
        "ocr_variants": [
            "Tax Exp ense", "Tax-Expense", "TAX EXPENSE",
            "Ƭax Expense", "Tax Expɇnse"
        ],
        "format_examples": [
            {"value": "(1,050,000)", "context": "25% effective rate"},
            {"value": "1,050,000", "context": "Positive format"}
        ],
        "industry_tags": ["all", "corporate", "public_companies"]
    },
    "net_income": {
        "ocr_variants": [
            "Net Inc ome", "Net-Income", "NET INCOME",
            "Nɇt Income", "Net lncome", "Netincome"
        ],
        "format_examples": [
            {"value": "3,150,000", "context": "After-tax profit"},
            {"value": "(250,000)", "context": "Net loss"}
        ],
        "industry_tags": ["all", "corporate", "public_companies"]
    },

    # BALANCE SHEET
    "cash": {
        "ocr_variants": [
            "Ca sh", "C ash", "CASH", "Cash.", "Cɑsh", "Cash:"
        ],
        "format_examples": [
            {"value": "5,000,000", "context": "Cash on hand"},
            {"value": "$5.0M", "context": "Millions"}
        ],
        "industry_tags": ["all"]
    },
    "accounts_receivable": {
        "ocr_variants": [
            "Accounts Receiv able", "Accounts-Receivable", "ACCOUNTS RECEIVABLE",
            "Accounts Rɇceivable", "Accts Receivable", "A/R"
        ],
        "format_examples": [
            {"value": "2,500,000", "context": "Trade receivables"}
        ],
        "industry_tags": ["all", "manufacturing", "services", "wholesale"]
    },
    "inventory": {
        "ocr_variants": [
            "Invent ory", "Inven tory", "INVENTORY",
            "lnventory", "Inventοry", "Inventory."
        ],
        "format_examples": [
            {"value": "3,000,000", "context": "Finished goods + WIP"}
        ],
        "industry_tags": ["manufacturing", "retail", "wholesale", "ecommerce"]
    },
    "current_assets": {
        "ocr_variants": [
            "Current Ass ets", "Current-Assets", "CURRENT ASSETS",
            "Currɇnt Assets", "Current Assɇts"
        ],
        "format_examples": [
            {"value": "12,000,000", "context": "Liquid assets"}
        ],
        "industry_tags": ["all"]
    },
    "total_assets": {
        "ocr_variants": [
            "Total Ass ets", "Total-Assets", "TOTAL ASSETS",
            "Totɑl Assets", "Total Assɇts", "Total Assets."
        ],
        "format_examples": [
            {"value": "50,000,000", "context": "Enterprise balance sheet"}
        ],
        "industry_tags": ["all"]
    },
    "ppe": {
        "ocr_variants": [
            "PP E", "P P E", "PP&E", "PPE.", "PPɆ", "PP+E"
        ],
        "format_examples": [
            {"value": "15,000,000", "context": "Net property value"}
        ],
        "industry_tags": ["manufacturing", "real_estate", "capital_intensive"]
    },
    "intangibles": {
        "ocr_variants": [
            "Intang ibles", "Intangi bles", "INTANGIBLES",
            "lntangibles", "Intɑngibles"
        ],
        "format_examples": [
            {"value": "5,000,000", "context": "Patents, trademarks"}
        ],
        "industry_tags": ["technology", "pharma", "biotech", "media"]
    },
    "goodwill": {
        "ocr_variants": [
            "Good will", "Good-will", "GOODWILL", "Goodwill.", "Gοodwill"
        ],
        "format_examples": [
            {"value": "20,000,000", "context": "Acquisition premium"}
        ],
        "industry_tags": ["all", "rollup", "private_equity"]
    },
    "accounts_payable": {
        "ocr_variants": [
            "Accounts Pay able", "Accounts-Payable", "ACCOUNTS PAYABLE",
            "Accounts Pɑyable", "Accts Payable", "A/P"
        ],
        "format_examples": [
            {"value": "1,800,000", "context": "Trade payables"}
        ],
        "industry_tags": ["all", "manufacturing", "retail"]
    },
    "accrued_expenses": {
        "ocr_variants": [
            "Accrued Exp enses", "Accrued-Expenses", "ACCRUED EXPENSES",
            "Accruɇd Expenses", "Accrued Expɇnses"
        ],
        "format_examples": [
            {"value": "500,000", "context": "Wages, interest accrued"}
        ],
        "industry_tags": ["all"]
    },
    "current_liabilities": {
        "ocr_variants": [
            "Current Liabil ities", "Current-Liabilities", "CURRENT LIABILITIES",
            "Currɇnt Liabilities", "Current Liɑbilities"
        ],
        "format_examples": [
            {"value": "8,000,000", "context": "Short-term obligations"}
        ],
        "industry_tags": ["all"]
    },
    "total_liabilities": {
        "ocr_variants": [
            "Total Liabil ities", "Total-Liabilities", "TOTAL LIABILITIES",
            "Totɑl Liabilities", "Total Liɑbilities"
        ],
        "format_examples": [
            {"value": "30,000,000", "context": "All obligations"}
        ],
        "industry_tags": ["all"]
    },
    "short_term_debt": {
        "ocr_variants": [
            "Short-Term De bt", "Short Term Debt", "SHORT-TERM DEBT",
            "Shοrt-Term Debt", "ST Debt"
        ],
        "format_examples": [
            {"value": "2,000,000", "context": "Debt due within 1 year"}
        ],
        "industry_tags": ["all", "leveraged"]
    },
    "long_term_debt": {
        "ocr_variants": [
            "Long-Term De bt", "Long Term Debt", "LONG-TERM DEBT",
            "Lοng-Term Debt", "LT Debt"
        ],
        "format_examples": [
            {"value": "15,000,000", "context": "Debt due after 1 year"}
        ],
        "industry_tags": ["all", "leveraged", "real_estate"]
    },
    "total_debt": {
        "ocr_variants": [
            "Total De bt", "Total-Debt", "TOTAL DEBT",
            "Totɑl Debt", "Total Debt."
        ],
        "format_examples": [
            {"value": "17,000,000", "context": "ST + LT debt"}
        ],
        "industry_tags": ["all", "leveraged"]
    },
    "common_stock": {
        "ocr_variants": [
            "Common St ock", "Common-Stock", "COMMON STOCK",
            "Commοn Stock", "Common Stοck"
        ],
        "format_examples": [
            {"value": "1,000,000", "context": "Par value"}
        ],
        "industry_tags": ["all", "public_companies"]
    },
    "retained_earnings": {
        "ocr_variants": [
            "Retained Earn ings", "Retained-Earnings", "RETAINED EARNINGS",
            "Retɑined Earnings", "Retained Ɇarnings"
        ],
        "format_examples": [
            {"value": "8,000,000", "context": "Accumulated profits"},
            {"value": "(2,000,000)", "context": "Accumulated deficit"}
        ],
        "industry_tags": ["all"]
    },
    "total_equity": {
        "ocr_variants": [
            "Total Equ ity", "Total-Equity", "TOTAL EQUITY",
            "Totɑl Equity", "Total Equiƭy"
        ],
        "format_examples": [
            {"value": "20,000,000", "context": "Shareholder equity"}
        ],
        "industry_tags": ["all"]
    },

    # CASH FLOW
    "cfo": {
        "ocr_variants": [
            "CF O", "C FO", "CFO.", "CF0", "CƑO", "CFO:"
        ],
        "format_examples": [
            {"value": "6,000,000", "context": "Positive operating cash"},
            {"value": "(500,000)", "context": "Cash burn"}
        ],
        "industry_tags": ["all"]
    },
    "cfi": {
        "ocr_variants": [
            "CF I", "C FI", "CFI.", "CFl", "CƑI", "CFI:"
        ],
        "format_examples": [
            {"value": "(3,000,000)", "context": "Capex outflow"}
        ],
        "industry_tags": ["all"]
    },
    "cff": {
        "ocr_variants": [
            "CF F", "C FF", "CFF.", "CƑF", "CFF:"
        ],
        "format_examples": [
            {"value": "5,000,000", "context": "Debt issuance"},
            {"value": "(1,000,000)", "context": "Debt repayment"}
        ],
        "industry_tags": ["all"]
    },
    "capex": {
        "ocr_variants": [
            "Cap ex", "CAPEX", "CapEx", "Cap-Ex", "Cɑpex", "CAPEX."
        ],
        "format_examples": [
            {"value": "(2,500,000)", "context": "Capital investments"},
            {"value": "2,500,000", "context": "Positive format"}
        ],
        "industry_tags": ["all", "manufacturing", "real_estate", "capital_intensive"]
    },
    "fcf": {
        "ocr_variants": [
            "FC F", "F CF", "FCF.", "FCƑ", "FCF:"
        ],
        "format_examples": [
            {"value": "3,500,000", "context": "CFO - Capex"}
        ],
        "industry_tags": ["all", "private_equity", "valuation"]
    },
    "change_working_capital": {
        "ocr_variants": [
            "Change in Work ing Capital", "Change-WC", "CHANGE IN WC",
            "ΔWC", "Working Capital Change"
        ],
        "format_examples": [
            {"value": "(500,000)", "context": "WC increase (use of cash)"},
            {"value": "200,000", "context": "WC decrease (source of cash)"}
        ],
        "industry_tags": ["all", "manufacturing", "retail"]
    },
    "net_change_cash": {
        "ocr_variants": [
            "Net Change in Ca sh", "Net-Change-Cash", "NET CHANGE IN CASH",
            "Net Δ Cash", "Change in Cash"
        ],
        "format_examples": [
            {"value": "2,500,000", "context": "Cash increased"}
        ],
        "industry_tags": ["all"]
    },
    "beginning_cash": {
        "ocr_variants": [
            "Beginning Ca sh", "Beginning-Cash", "BEGINNING CASH",
            "Cash - Beginning", "Beg. Cash"
        ],
        "format_examples": [
            {"value": "3,000,000", "context": "Starting balance"}
        ],
        "industry_tags": ["all"]
    },
    "ending_cash": {
        "ocr_variants": [
            "Ending Ca sh", "Ending-Cash", "ENDING CASH",
            "Cash - Ending", "End. Cash"
        ],
        "format_examples": [
            {"value": "5,500,000", "context": "Ending balance"}
        ],
        "industry_tags": ["all"]
    },

    # DEBT SCHEDULE
    "net_debt": {
        "ocr_variants": [
            "Net De bt", "Net-Debt", "NET DEBT", "Nɇt Debt"
        ],
        "format_examples": [
            {"value": "12,000,000", "context": "Total debt - cash"}
        ],
        "industry_tags": ["all", "leveraged", "private_equity"]
    },
    "interest_rate": {
        "ocr_variants": [
            "Interest Ra te", "Interest-Rate", "INTEREST RATE",
            "lnterest Rate", "Int. Rate"
        ],
        "format_examples": [
            {"value": "0.065", "context": "6.5% as decimal"},
            {"value": "6.5%", "context": "Percentage format"},
            {"value": "650 bps", "context": "Basis points"}
        ],
        "industry_tags": ["all", "leveraged", "banking"]
    },
    "principal_payment": {
        "ocr_variants": [
            "Principal Pay ment", "Principal-Payment", "PRINCIPAL PAYMENT",
            "Principɑl Payment", "Prin. Payment"
        ],
        "format_examples": [
            {"value": "1,000,000", "context": "Annual amortization"}
        ],
        "industry_tags": ["all", "leveraged", "real_estate"]
    },
    "interest_payment": {
        "ocr_variants": [
            "Interest Pay ment", "Interest-Payment", "INTEREST PAYMENT",
            "lnterest Payment", "Int. Payment"
        ],
        "format_examples": [
            {"value": "780,000", "context": "Annual interest"}
        ],
        "industry_tags": ["all", "leveraged"]
    },

    # METRICS
    "ebitda_margin": {
        "ocr_variants": [
            "EBITDA Mar gin", "EBITDA-Margin", "EBITDA MARGIN",
            "EB1TDA Margin", "EBITDA %"
        ],
        "format_examples": [
            {"value": "0.25", "context": "25% as decimal"},
            {"value": "25%", "context": "Percentage"},
            {"value": "25.0", "context": "Percentage without symbol"}
        ],
        "industry_tags": ["all", "private_equity", "valuation"]
    },
    "operating_margin": {
        "ocr_variants": [
            "Operating Mar gin", "Operating-Margin", "OPERATING MARGIN",
            "Op. Margin", "Operating %"
        ],
        "format_examples": [
            {"value": "0.18", "context": "18% as decimal"},
            {"value": "18%", "context": "Percentage"}
        ],
        "industry_tags": ["all", "public_companies"]
    },
    "net_margin": {
        "ocr_variants": [
            "Net Mar gin", "Net-Margin", "NET MARGIN",
            "Net Profit Margin", "Net %"
        ],
        "format_examples": [
            {"value": "0.12", "context": "12% as decimal"},
            {"value": "12%", "context": "Percentage"}
        ],
        "industry_tags": ["all"]
    },
    "gross_margin": {
        "ocr_variants": [
            "Gross Mar gin", "Gross-Margin", "GROSS MARGIN",
            "Gross Profit Margin", "Gross %"
        ],
        "format_examples": [
            {"value": "0.65", "context": "65% as decimal"},
            {"value": "65%", "context": "Percentage"}
        ],
        "industry_tags": ["all", "saas", "software"]
    },
    "debt_to_ebitda": {
        "ocr_variants": [
            "Debt / EB ITDA", "Debt-to-EBITDA", "DEBT TO EBITDA",
            "Debt/EB1TDA", "Leverage"
        ],
        "format_examples": [
            {"value": "3.5", "context": "3.5x leverage"},
            {"value": "3.5x", "context": "With 'x' suffix"}
        ],
        "industry_tags": ["all", "private_equity", "leveraged_finance"]
    },
    "interest_coverage": {
        "ocr_variants": [
            "Interest Cover age", "Interest-Coverage", "INTEREST COVERAGE",
            "lnterest Coverage", "ICR"
        ],
        "format_examples": [
            {"value": "5.5", "context": "5.5x coverage"},
            {"value": "5.5x", "context": "With 'x' suffix"}
        ],
        "industry_tags": ["all", "leveraged", "credit_analysis"]
    },
}


def enhance_taxonomy(input_path: str = "data/taxonomy_seed.json",
                     output_path: str = "data/taxonomy_seed.json"):
    """Add Phase 1 enhancements to taxonomy."""

    # Load existing taxonomy
    with open(input_path, 'r') as f:
        data = json.load(f)

    # Track enhancements
    enhanced_count = 0

    # Enhance each item
    for item in data['items']:
        canonical_name = item['canonical_name']

        if canonical_name in ENHANCEMENTS:
            enhancement = ENHANCEMENTS[canonical_name]

            # Add OCR variants
            if 'ocr_variants' in enhancement:
                item['ocr_variants'] = enhancement['ocr_variants']

            # Add format examples
            if 'format_examples' in enhancement:
                item['format_examples'] = enhancement['format_examples']

            # Add industry tags
            if 'industry_tags' in enhancement:
                item['industry_tags'] = enhancement['industry_tags']

            enhanced_count += 1

    # Update version and last_updated
    data['version'] = "1.3.0"
    data['last_updated'] = "2026-02-24"

    # Write enhanced taxonomy
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✅ Enhanced {enhanced_count}/{len(data['items'])} items")
    print(f"✅ Version updated to {data['version']}")
    print(f"✅ Saved to {output_path}")

    return enhanced_count


if __name__ == "__main__":
    enhance_taxonomy()
