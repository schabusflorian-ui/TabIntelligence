"""add validation_rules to taxonomy and reseed

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-02-27 22:00:00.000000

Adds validation_rules JSON column to taxonomy table and reseeds
from the consolidated taxonomy.json (250 items with enhanced aliases
and validation rules).
"""
from typing import Sequence, Union
import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add validation_rules column and reseed taxonomy from consolidated JSON."""
    # Add validation_rules column
    op.add_column('taxonomy', sa.Column('validation_rules', sa.JSON(), nullable=True))

    # Reseed: delete old data and insert from consolidated taxonomy.json
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
    import uuid
    count = 0
    for category, items in taxonomy_data['categories'].items():
        for item in items:
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
                    'validation_rules': json.dumps(item['validation_rules']) if item.get('validation_rules') else None,
                }
            )
            count += 1

    print(f"Reseeded taxonomy with {count} items (including validation_rules)")


def downgrade() -> None:
    """Remove validation_rules column."""
    op.drop_column('taxonomy', 'validation_rules')
