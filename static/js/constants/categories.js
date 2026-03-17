/**
 * Single source of truth for taxonomy category constants.
 *
 * All frontend code should import from here rather than defining inline objects.
 * Backend equivalent: src/taxonomy_constants.py
 */

export const CATEGORY_LABELS = {
  income_statement: 'Income Statement',
  balance_sheet: 'Balance Sheet',
  cash_flow: 'Cash Flow',
  debt_schedule: 'Debt Schedule',
  metrics: 'Metrics',
  project_finance: 'Project Finance',
};

export const CATEGORY_BADGE_CLASS = {
  income_statement: 'b-blue',
  balance_sheet: 'b-ok',
  cash_flow: 'b-warn',
  debt_schedule: 'b-gray',
  metrics: 'b-blue',
  project_finance: 'b-gray',
};
