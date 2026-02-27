#!/usr/bin/env python3
"""
Phase 2 Taxonomy Enhancement Script - Robustness

Adds:
1. Cross-item validation rules (accounting identities, range checks)
2. Confidence scoring metadata for Agent 7
3. Common misspellings to aliases
4. Time-series validation rules

Usage:
    python scripts/enhance_taxonomy_phase2.py
"""

import json
from pathlib import Path
from typing import Dict, List

# Cross-item validation rules and confidence metadata
PHASE2_ENHANCEMENTS = {
    # INCOME STATEMENT
    "revenue": {
        "misspellings": ["revenu", "reveneu", "revanue", "reveue", "revnue"],
        "cross_item_validation": {
            "must_be_positive": True,
            "relationships": [
                {
                    "rule": "revenue >= gross_profit",
                    "error_message": "Revenue cannot be less than gross profit"
                },
                {
                    "rule": "revenue >= cogs",
                    "error_message": "Revenue should typically exceed COGS (check for negative margins)"
                }
            ],
            "time_series": {
                "max_yoy_change_pct": 300,
                "description": "Flag if revenue changes by >300% year-over-year (likely data error)"
            }
        },
        "confidence_scoring": {
            "high_confidence_signals": [
                "Appears in income statement header",
                "Labeled as 'Revenue', 'Sales', or 'Turnover'",
                "First line item in P&L",
                "Largest positive income statement value"
            ],
            "medium_confidence_signals": [
                "Labeled generically as 'Income'",
                "In operating section but not at top",
                "Requires inference from context"
            ],
            "low_confidence_signals": [
                "Unlabeled number",
                "Appears outside standard income statement",
                "Similar magnitude to other items"
            ],
            "validation_boosters": [
                "Can derive gross_profit = revenue - cogs",
                "Consistent with prior period trends",
                "Matches reported total revenue"
            ],
            "common_errors": [
                "Confusing gross revenue with net revenue",
                "Including other income in revenue",
                "Missing revenue from discontinued operations"
            ]
        }
    },
    "cogs": {
        "misspellings": ["cog", "cosg", "cogss", "cost of good sold"],
        "cross_item_validation": {
            "must_be_positive": True,
            "relationships": [
                {
                    "rule": "cogs <= revenue",
                    "error_message": "COGS cannot exceed revenue (check for negative gross margin)"
                },
                {
                    "rule": "gross_profit == revenue - cogs",
                    "tolerance": 0.01,
                    "error_message": "Gross profit should equal revenue minus COGS"
                }
            ]
        },
        "confidence_scoring": {
            "high_confidence_signals": [
                "Labeled as 'COGS' or 'Cost of Sales'",
                "Directly below revenue in income statement",
                "Can derive gross_profit from revenue - cogs"
            ],
            "ambiguity_notes": "Some companies include D&A in COGS, others exclude it"
        }
    },
    "gross_profit": {
        "misspellings": ["gros profit", "gross profi", "grofit"],
        "cross_item_validation": {
            "relationships": [
                {
                    "rule": "gross_profit == revenue - cogs",
                    "tolerance": 0.01,
                    "error_message": "Gross profit must equal revenue minus COGS"
                },
                {
                    "rule": "gross_profit <= revenue",
                    "error_message": "Gross profit cannot exceed revenue"
                }
            ]
        },
        "confidence_scoring": {
            "validation_boosters": [
                "Matches revenue - cogs calculation",
                "Consistent gross margin with prior periods"
            ]
        }
    },
    "ebitda": {
        "misspellings": ["ebitada", "ebida", "ebtda", "ebitdaa"],
        "cross_item_validation": {
            "relationships": [
                {
                    "rule": "ebitda == ebit + depreciation + amortization",
                    "tolerance": 0.02,
                    "error_message": "EBITDA should equal EBIT + D&A",
                    "optional": True  # D&A might not be separately stated
                }
            ]
        },
        "confidence_scoring": {
            "high_confidence_signals": [
                "Explicitly labeled as 'EBITDA' or 'Adjusted EBITDA'",
                "Can derive from EBIT + D&A",
                "Appears in management discussion section"
            ],
            "medium_confidence_signals": [
                "Labeled as 'Operating Profit before D&A'",
                "Requires adding back D&A from notes"
            ],
            "ambiguity_notes": "EBITDA is non-GAAP; definitions vary. Always check footnotes for adjustments."
        }
    },
    "ebit": {
        "misspellings": ["ebt", "ebitt", "eibt"],
        "cross_item_validation": {
            "relationships": [
                {
                    "rule": "ebit == ebitda - depreciation - amortization",
                    "tolerance": 0.02,
                    "optional": True
                },
                {
                    "rule": "ebit == operating_income",
                    "tolerance": 0.01,
                    "error_message": "EBIT should equal operating income"
                }
            ]
        }
    },
    "net_income": {
        "misspellings": ["net incom", "net incme", "netincome", "net inncome"],
        "cross_item_validation": {
            "relationships": [
                {
                    "rule": "net_income == ebt - tax_expense",
                    "tolerance": 0.01,
                    "error_message": "Net income should equal EBT minus taxes"
                },
                {
                    "rule": "net_income <= revenue",
                    "error_message": "Net income cannot exceed revenue"
                }
            ],
            "time_series": {
                "max_yoy_change_pct": 500,
                "description": "Flag if net income changes by >500% YoY"
            }
        },
        "confidence_scoring": {
            "high_confidence_signals": [
                "Last line of income statement",
                "Labeled as 'Net Income' or 'Net Profit'",
                "Can derive from EBT - taxes"
            ],
            "validation_boosters": [
                "Matches EBT - tax_expense",
                "Ties to retained earnings change on balance sheet"
            ]
        }
    },

    # BALANCE SHEET
    "total_assets": {
        "misspellings": ["total asset", "toal assets", "totl assets"],
        "cross_item_validation": {
            "must_be_positive": True,
            "relationships": [
                {
                    "rule": "total_assets == current_assets + non_current_assets",
                    "tolerance": 0.01,
                    "error_message": "Total assets must equal current + non-current assets"
                },
                {
                    "rule": "total_assets == total_liabilities + total_equity",
                    "tolerance": 0.01,
                    "error_message": "Fundamental accounting equation: Assets = Liabilities + Equity",
                    "critical": True
                }
            ]
        },
        "confidence_scoring": {
            "high_confidence_signals": [
                "Labeled as 'Total Assets'",
                "Last line of assets section",
                "Equals liabilities + equity"
            ],
            "validation_boosters": [
                "Satisfies A = L + E equation",
                "Equals sum of current + non-current assets"
            ]
        }
    },
    "total_liabilities": {
        "misspellings": ["total liabilites", "total liabilitie", "toal liabilities"],
        "cross_item_validation": {
            "must_be_positive": True,
            "relationships": [
                {
                    "rule": "total_liabilities == current_liabilities + non_current_liabilities",
                    "tolerance": 0.01
                }
            ]
        }
    },
    "total_equity": {
        "misspellings": ["total equty", "toal equity", "total equiity"],
        "cross_item_validation": {
            "relationships": [
                {
                    "rule": "total_equity == total_assets - total_liabilities",
                    "tolerance": 0.01,
                    "error_message": "Equity must equal assets minus liabilities",
                    "critical": True
                }
            ]
        },
        "confidence_scoring": {
            "validation_boosters": [
                "Satisfies A = L + E equation",
                "Change in equity matches net income - dividends"
            ]
        }
    },
    "cash": {
        "misspellings": ["cahs", "cashs", "csh"],
        "cross_item_validation": {
            "must_be_positive": True,
            "relationships": [
                {
                    "rule": "cash <= current_assets",
                    "error_message": "Cash cannot exceed current assets"
                }
            ]
        }
    },
    "accounts_receivable": {
        "misspellings": ["accounts recievable", "account receivable", "accts receivable"],
        "cross_item_validation": {
            "must_be_positive": True,
            "relationships": [
                {
                    "rule": "accounts_receivable <= revenue * 0.5",
                    "error_message": "AR >50% of revenue may indicate collection issues",
                    "warning_only": True
                }
            ]
        }
    },
    "inventory": {
        "misspellings": ["inventroy", "inventry", "inventoyr"],
        "cross_item_validation": {
            "must_be_positive": True,
            "relationships": [
                {
                    "rule": "inventory <= current_assets",
                    "error_message": "Inventory cannot exceed current assets"
                }
            ]
        }
    },

    # CASH FLOW
    "fcf": {
        "misspellings": ["free cash flow", "freecashflow", "fcff"],
        "cross_item_validation": {
            "relationships": [
                {
                    "rule": "fcf == cfo - capex",
                    "tolerance": 0.02,
                    "error_message": "FCF should equal CFO minus capex"
                }
            ]
        },
        "confidence_scoring": {
            "high_confidence_signals": [
                "Explicitly labeled as 'Free Cash Flow' or 'FCF'",
                "Can derive from CFO - capex",
                "Disclosed in management discussion"
            ],
            "validation_boosters": [
                "Matches CFO - capex calculation",
                "Consistent FCF conversion with prior periods"
            ],
            "ambiguity_notes": "Some companies use unlevered FCF; check definition"
        }
    },
    "cfo": {
        "misspellings": ["cash from operation", "operating cash", "cash flow operations"],
        "cross_item_validation": {
            "relationships": [
                {
                    "rule": "net_change_cash == cfo + cfi + cff",
                    "tolerance": 0.01,
                    "error_message": "Net change in cash should equal sum of CFO + CFI + CFF"
                }
            ]
        }
    },
    "ending_cash": {
        "misspellings": ["ending cahs", "end cash"],
        "cross_item_validation": {
            "relationships": [
                {
                    "rule": "ending_cash == beginning_cash + net_change_cash",
                    "tolerance": 0.01,
                    "error_message": "Ending cash must equal beginning cash + net change"
                },
                {
                    "rule": "ending_cash == cash",
                    "tolerance": 0.01,
                    "error_message": "Ending cash on cash flow should equal cash on balance sheet"
                }
            ]
        }
    },

    # METRICS
    "gross_margin": {
        "misspellings": ["gros margin", "gross margen"],
        "cross_item_validation": {
            "relationships": [
                {
                    "rule": "gross_margin == gross_profit / revenue",
                    "tolerance": 0.005,
                    "error_message": "Gross margin should equal gross profit / revenue"
                },
                {
                    "rule": "0 <= gross_margin <= 1",
                    "error_message": "Gross margin should be between 0 and 1 (or 0-100%)"
                }
            ]
        }
    },
    "ebitda_margin": {
        "misspellings": ["ebitda margen", "ebitda margn"],
        "cross_item_validation": {
            "relationships": [
                {
                    "rule": "ebitda_margin == ebitda / revenue",
                    "tolerance": 0.005
                },
                {
                    "rule": "-1 <= ebitda_margin <= 1",
                    "error_message": "EBITDA margin typically between -100% and 100%"
                }
            ]
        }
    },
    "debt_to_ebitda": {
        "misspellings": ["debt to ebitada", "debt/ebitda"],
        "cross_item_validation": {
            "relationships": [
                {
                    "rule": "debt_to_ebitda == total_debt / ebitda",
                    "tolerance": 0.1,
                    "error_message": "Debt/EBITDA should equal total debt / EBITDA"
                }
            ]
        },
        "confidence_scoring": {
            "high_confidence_signals": [
                "Labeled as 'Leverage' or 'Debt/EBITDA'",
                "Can calculate from balance sheet and P&L",
                "Disclosed in debt covenants section"
            ],
            "validation_boosters": [
                "Matches total_debt / ebitda calculation",
                "Consistent with bank covenant definitions"
            ]
        }
    },
    "interest_coverage": {
        "misspellings": ["intrest coverage", "interest coverge"],
        "cross_item_validation": {
            "relationships": [
                {
                    "rule": "interest_coverage == ebit / interest_expense",
                    "tolerance": 0.1
                },
                {
                    "rule": "interest_coverage >= 1",
                    "error_message": "Interest coverage <1x indicates inability to service debt",
                    "warning_only": True
                }
            ]
        }
    },
}


def enhance_taxonomy_phase2(input_path: str = "data/taxonomy_seed.json",
                             output_path: str = "data/taxonomy_seed.json"):
    """Add Phase 2 robustness enhancements."""

    # Load existing taxonomy
    with open(input_path, 'r') as f:
        data = json.load(f)

    # Track enhancements
    enhanced_count = 0
    misspelling_count = 0
    validation_rules_count = 0
    confidence_metadata_count = 0

    # Enhance each item
    for item in data['items']:
        canonical_name = item['canonical_name']

        if canonical_name in PHASE2_ENHANCEMENTS:
            enhancement = PHASE2_ENHANCEMENTS[canonical_name]

            # Add misspellings to aliases
            if 'misspellings' in enhancement:
                misspellings = enhancement['misspellings']
                existing_aliases = item.get('aliases', [])

                # Add misspellings that aren't already aliases
                for misspelling in misspellings:
                    if misspelling not in existing_aliases:
                        existing_aliases.append(misspelling)
                        misspelling_count += 1

                item['aliases'] = existing_aliases

            # Add cross-item validation rules
            if 'cross_item_validation' in enhancement:
                # Store in validation_rules
                if 'validation_rules' not in item:
                    item['validation_rules'] = {}

                item['validation_rules']['cross_item_validation'] = enhancement['cross_item_validation']
                validation_rules_count += 1

            # Add confidence scoring metadata
            if 'confidence_scoring' in enhancement:
                item['confidence_scoring'] = enhancement['confidence_scoring']
                confidence_metadata_count += 1

            enhanced_count += 1

    # Update version
    data['version'] = "1.4.0"
    data['last_updated'] = "2026-02-24"

    # Write enhanced taxonomy
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✅ Enhanced {enhanced_count}/{len(data['items'])} items")
    print(f"✅ Added {misspelling_count} misspellings to aliases")
    print(f"✅ Added {validation_rules_count} cross-item validation rules")
    print(f"✅ Added {confidence_metadata_count} confidence scoring metadata")
    print(f"✅ Version updated to {data['version']}")
    print(f"✅ Saved to {output_path}")

    return {
        'enhanced': enhanced_count,
        'misspellings': misspelling_count,
        'validation_rules': validation_rules_count,
        'confidence_metadata': confidence_metadata_count
    }


if __name__ == "__main__":
    enhance_taxonomy_phase2()
