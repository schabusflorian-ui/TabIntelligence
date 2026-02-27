"""seed_taxonomy_from_json

Revision ID: f9417a796465
Revises: 345956f5d313
Create Date: 2026-02-24 21:16:02.209587

"""
from typing import Sequence, Union
import json
import uuid
from pathlib import Path

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f9417a796465'
down_revision: Union[str, Sequence[str], None] = '345956f5d313'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Seed taxonomy table from data/taxonomy.json."""
    # Load taxonomy JSON file
    taxonomy_path = Path(__file__).parent.parent.parent / 'data' / 'taxonomy.json'
    with open(taxonomy_path, 'r') as f:
        taxonomy_data = json.load(f)

    # Get database connection
    conn = op.get_bind()

    # Define taxonomy table for insertions
    # Note: aliases is ARRAY here; migration d3cdfafa1ded later converts to JSON
    taxonomy_table = sa.table(
        'taxonomy',
        sa.column('id', postgresql.UUID),
        sa.column('canonical_name', sa.String),
        sa.column('display_name', sa.String),
        sa.column('aliases', postgresql.ARRAY(sa.String)),
        sa.column('definition', sa.Text),
        sa.column('typical_sign', sa.String),
        sa.column('parent_canonical', sa.String),
        sa.column('category', sa.String),
    )

    # Insert all taxonomy items
    items_to_insert = []
    for category, items in taxonomy_data['categories'].items():
        for item in items:
            items_to_insert.append({
                'id': uuid.uuid4(),
                'canonical_name': item['canonical_name'],
                'display_name': item.get('display_name', ''),
                'aliases': item.get('aliases', []),
                'definition': item.get('definition', ''),
                'typical_sign': item.get('typical_sign'),
                'parent_canonical': item.get('parent_canonical'),
                'category': item.get('category', category),
            })

    # Bulk insert all items
    op.bulk_insert(taxonomy_table, items_to_insert)

    print(f"Inserted {len(items_to_insert)} taxonomy items from {taxonomy_path}")


def downgrade() -> None:
    """Remove all taxonomy seed data."""
    # Delete all rows from taxonomy table
    op.execute("DELETE FROM taxonomy")
    print("Removed all taxonomy seed data")
