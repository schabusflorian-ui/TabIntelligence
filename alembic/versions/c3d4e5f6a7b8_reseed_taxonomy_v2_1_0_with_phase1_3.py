"""reseed taxonomy v2.1.0 with Phase 1-3 enhancements

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-02-27 22:00:00.000000

Reseeds taxonomy table from data/taxonomy.json v2.1.0 which includes:
- Phase 1: OCR variants, format examples, industry tags
- Phase 2: Confidence scoring metadata
- Phase 3: GAAP/IFRS distinctions, regulatory context
All enhanced metadata stored in validation_rules JSON column.
"""
from typing import Sequence, Union
import json
import uuid
from pathlib import Path

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Reseed taxonomy from v2.1.0 JSON with Phase 1-3 enhancements."""
    taxonomy_path = Path(__file__).parent.parent.parent / 'data' / 'taxonomy.json'
    if not taxonomy_path.exists():
        print(f"Warning: {taxonomy_path} not found, skipping reseed")
        return

    with open(taxonomy_path, 'r') as f:
        taxonomy_data = json.load(f)

    conn = op.get_bind()

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

    print(f"Reseeded taxonomy v2.1.0 with {count} items (Phase 1-3 enhancements)")


def downgrade() -> None:
    """Reseed from previous taxonomy version (b7c8d9e0f1a2 will handle its own reseed)."""
    # The previous migration's upgrade also reseeds, so downgrade just clears.
    # Running the previous migration's upgrade will restore the old data.
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM taxonomy"))
    print("Cleared taxonomy table (run previous migration upgrade to restore)")
