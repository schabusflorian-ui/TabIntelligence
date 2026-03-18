"""reseed taxonomy v3.1.0 with hierarchy fixes

Revision ID: u5v6w7x8y9z0
Revises: t4u5v6w7x8y9
Create Date: 2026-03-18 10:00:00.000000

Reseeds taxonomy table from data/taxonomy.json v3.1.0 which includes:
- 15 new metrics subcategory parent items (profitability, leverage, coverage, etc.)
- parent_canonical set on 75+ orphan items across all categories
- Hierarchy coverage improved from ~52% to ~87% overall
- balance_sheet: 94%, cash_flow: 86%, debt_schedule: 93%,
  income_statement: 85%, project_finance: 76%, metrics: 83%
"""
from typing import Sequence, Union
import json
import uuid
from pathlib import Path

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'u5v6w7x8y9z0'
down_revision: Union[str, Sequence[str], None] = 't4u5v6w7x8y9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Reseed taxonomy from v3.1.0 JSON with hierarchy fixes."""
    taxonomy_path = Path(__file__).parent.parent.parent / 'data' / 'taxonomy.json'
    if not taxonomy_path.exists():
        print(f"Warning: {taxonomy_path} not found, skipping reseed")
        return

    with open(taxonomy_path, 'r') as f:
        taxonomy_data = json.load(f)

    conn = op.get_bind()

    # Update category check constraint to include project_finance
    conn.execute(sa.text("ALTER TABLE taxonomy DROP CONSTRAINT IF EXISTS ck_taxonomy_category"))
    conn.execute(sa.text(
        "ALTER TABLE taxonomy ADD CONSTRAINT ck_taxonomy_category "
        "CHECK (category IN ("
        "'income_statement', 'balance_sheet', 'cash_flow', 'debt_schedule', "
        "'metrics', 'project_finance'"
        "))"
    ))

    # Delete existing seed data
    conn.execute(sa.text("DELETE FROM taxonomy"))

    # Insert all items from consolidated file
    count = 0
    for category, items in taxonomy_data['categories'].items():
        for item in items:
            # Build validation_rules JSON combining base rules with enhanced metadata
            validation_rules = item.get('validation_rules', {})

            # Merge Phase 1-3 enhanced fields into validation_rules for DB storage
            if 'ocr_variants' in item:
                validation_rules['ocr_variants'] = item['ocr_variants']
            if 'format_examples' in item:
                validation_rules['format_examples'] = item['format_examples']
            if 'industry_tags' in item:
                validation_rules['industry_tags'] = item['industry_tags']
            if 'confidence_scoring' in item:
                validation_rules['confidence_scoring'] = item['confidence_scoring']
            if 'accounting_standards' in item:
                validation_rules['accounting_standards'] = item['accounting_standards']
            if 'regulatory_context' in item:
                validation_rules['regulatory_context'] = item['regulatory_context']

            conn.execute(
                sa.text(
                    "INSERT INTO taxonomy (id, canonical_name, category, display_name, "
                    "aliases, definition, typical_sign, parent_canonical, validation_rules) "
                    "VALUES (:id, :canonical_name, :category, :display_name, "
                    ":aliases, :definition, :typical_sign, :parent_canonical, :validation_rules)"
                ),
                {
                    'id': str(uuid.uuid4()),
                    'canonical_name': item['canonical_name'],
                    'category': item.get('category', category),
                    'display_name': item.get('display_name', ''),
                    'aliases': json.dumps(item.get('aliases', [])),
                    'definition': item.get('definition', ''),
                    'typical_sign': item.get('typical_sign'),
                    'parent_canonical': item.get('parent_canonical'),
                    'validation_rules': json.dumps(validation_rules) if validation_rules else None,
                }
            )
            count += 1

    print(f"Reseeded taxonomy v3.1.0 with {count} items (hierarchy fixes)")


def downgrade() -> None:
    """Reseed from previous taxonomy version."""
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM taxonomy"))
    # Restore old category constraint without project_finance
    conn.execute(sa.text("ALTER TABLE taxonomy DROP CONSTRAINT IF EXISTS ck_taxonomy_category"))
    conn.execute(sa.text(
        "ALTER TABLE taxonomy ADD CONSTRAINT ck_taxonomy_category "
        "CHECK (category IN ("
        "'income_statement', 'balance_sheet', 'cash_flow', 'debt_schedule', "
        "'depreciation_amortization', 'working_capital', 'assumptions', 'metrics'"
        "))"
    ))
    print("Cleared taxonomy table (run previous migration upgrade to restore)")
