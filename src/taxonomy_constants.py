"""
Single source of truth for taxonomy category constants.

All backend code should import from here rather than defining inline dicts.
Frontend equivalent: static/js/constants/categories.js
"""

VALID_CATEGORIES = (
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "debt_schedule",
    "metrics",
    "project_finance",
)

CATEGORY_DISPLAY_NAMES = {
    "income_statement": "Income Statement",
    "balance_sheet": "Balance Sheet",
    "cash_flow": "Cash Flow",
    "debt_schedule": "Debt Schedule",
    "metrics": "Metrics",
    "project_finance": "Project Finance",
}

CATEGORY_BADGE_CLASSES = {
    "income_statement": "b-blue",
    "balance_sheet": "b-ok",
    "cash_flow": "b-warn",
    "debt_schedule": "b-gray",
    "metrics": "b-blue",
    "project_finance": "b-gray",
}
