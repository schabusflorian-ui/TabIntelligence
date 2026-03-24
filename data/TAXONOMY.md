# Taxonomy Reference

The canonical financial taxonomy lives in `data/taxonomy.json` (v3.0.0). It defines every financial line item the extraction pipeline can recognize and map to.

## Structure

```json
{
  "version": "3.0.0",
  "description": "Consolidated canonical financial taxonomy...",
  "categories": {
    "income_statement": [...],
    "balance_sheet": [...],
    "cash_flow": [...],
    "debt_schedule": [...],
    "metrics": [...],
    "project_finance": [...]
  }
}
```

## Categories

369 items across 6 categories:

| Category | Description | Examples |
|----------|-------------|---------|
| `income_statement` | Revenue, expenses, profit items | revenue, cost_of_goods_sold, ebitda, net_income |
| `balance_sheet` | Assets, liabilities, equity | cash_and_equivalents, total_debt, total_equity |
| `cash_flow` | Operating, investing, financing flows | operating_cash_flow, capital_expenditures |
| `debt_schedule` | Debt-specific items | senior_secured_debt, term_loan, revolving_credit |
| `metrics` | Financial health ratios and KPIs | debt_to_equity, current_ratio, interest_coverage_ratio |
| `project_finance` | Project finance model items | cfads, cfae, equity_contribution, dscr |

## Item Fields

Each taxonomy item has these fields:

```json
{
  "canonical_name": "revenue",
  "category": "income_statement",
  "display_name": "Revenue",
  "aliases": ["Sales", "Net Sales", "Total Revenue", "Turnover", "Net Revenue"],
  "definition": "Total income from core business activities",
  "typical_sign": "positive",
  "parent_canonical": "null",
  "validation_rules": {
    "type": "currency",
    "min_value": 0,
    "cross_item_validation": {
      "must_be_positive": true,
      "relationships": [
        "revenue - cost_of_goods_sold == gross_profit"
      ]
    }
  },
  "ocr_variants": ["Rcvenue", "Reuenue"],
  "format_examples": [{"value": "125,000,000", "context": "Annual revenue"}],
  "industry_tags": ["all"]
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `canonical_name` | Yes | Unique snake_case identifier used throughout the system |
| `category` | Yes | Which financial statement category it belongs to |
| `display_name` | Yes | Human-readable name |
| `aliases` | Yes | Alternative labels the pipeline should recognize (case-insensitive) |
| `definition` | Yes | Plain English description for Claude prompts |
| `typical_sign` | Yes | `positive`, `negative`, or `varies` — used for sign convention validation |
| `parent_canonical` | No | Parent item for hierarchy (e.g., `current_assets` is parent of `cash_and_equivalents`) |
| `validation_rules` | No | Type, range, and cross-item accounting rules |
| `ocr_variants` | No | Common OCR misreadings |
| `format_examples` | No | Real-world formatting examples |
| `industry_tags` | No | Industries where this item is relevant (`all`, `corporate`, `saas`, etc.) |

## How the Pipeline Uses Taxonomy

1. **Stage 3 (Mapping):** Claude receives `format_taxonomy_for_prompt()` — a condensed view with aliases. It maps Excel labels to `canonical_name` values.

2. **Pattern shortcircuit:** If an `EntityPattern` exists for `(entity_id, original_label)`, Stage 3 skips Claude and uses the cached mapping.

3. **Stage 4 (Validation):** Uses `validation_rules.cross_item_validation.relationships` to check accounting identities (e.g., `revenue - cogs == gross_profit`).

4. **Stage 5 (Enhanced Mapping):** Re-maps low-confidence items using `format_taxonomy_detailed()` — a full view with definitions and parent hierarchy.

5. **Learned aliases:** When extraction discovers a new alias (e.g., "Biz Rev" → revenue), it's stored as a `LearnedAlias`. After promotion, it's merged into the alias lookup via `get_alias_to_canonicals_with_promoted()`.

## Adding a New Item

1. Add to the appropriate category array in `data/taxonomy.json`:
   ```json
   {
     "canonical_name": "my_new_item",
     "category": "income_statement",
     "display_name": "My New Item",
     "aliases": ["Alternative Name 1", "Alt Name 2"],
     "definition": "Description for Claude",
     "typical_sign": "positive",
     "parent_canonical": "revenue"
   }
   ```

2. Validate:
   ```bash
   python scripts/validate_taxonomy.py
   ```

3. If the item participates in accounting identities, add `validation_rules.cross_item_validation.relationships`.

4. The pipeline will pick it up automatically on next extraction (taxonomy is loaded at runtime).

## Validation Rules Format

### Simple rules
```json
"validation_rules": {
  "type": "currency",
  "min_value": 0
}
```

### Cross-item relationships
```json
"cross_item_validation": {
  "must_be_positive": true,
  "relationships": [
    "revenue - cost_of_goods_sold == gross_profit",
    "gross_profit - operating_expenses == operating_income"
  ]
}
```

Relationship syntax: `item_a {+,-} item_b == item_c` (evaluated by `accounting_validator.py`).

## Alias Strategy

- Include the most common variations first
- Include abbreviations (e.g., "COGS", "A/P", "D&A")
- Include full formal names ("Cost of Goods Sold")
- Include regional variants ("Turnover" for UK revenue)
- OCR variants go in `ocr_variants`, not `aliases`
- Learned aliases from production are promoted via the `/learned-aliases` API

## Key Files

| File | Purpose |
|------|---------|
| `data/taxonomy.json` | The taxonomy definition (source of truth) |
| `src/extraction/taxonomy_loader.py` | Loads JSON, builds alias index, merges promoted aliases |
| `src/validation/accounting_validator.py` | Evaluates cross-item validation rules |
| `src/guidelines/taxonomy.py` | TaxonomyManager for guideline-based queries |
| `scripts/validate_taxonomy.py` | Schema and consistency validation |
