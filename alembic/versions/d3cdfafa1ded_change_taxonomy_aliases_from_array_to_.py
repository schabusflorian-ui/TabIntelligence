"""change taxonomy aliases from array to json

Revision ID: d3cdfafa1ded
Revises: 96e5108af909
Create Date: 2026-02-27 14:54:46.504198

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3cdfafa1ded'
down_revision: Union[str, Sequence[str], None] = '96e5108af909'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Change taxonomy.aliases from ARRAY(Text) to JSON for SQLite compatibility."""
    # Convert ARRAY to JSON (PostgreSQL handles this automatically since data is already list-like)
    op.alter_column(
        'taxonomy',
        'aliases',
        type_=sa.JSON(),
        existing_type=sa.ARRAY(sa.Text()),
        postgresql_using='to_json(aliases)',
    )


def downgrade() -> None:
    """Revert taxonomy.aliases from JSON back to ARRAY(Text)."""
    op.alter_column(
        'taxonomy',
        'aliases',
        type_=sa.ARRAY(sa.Text()),
        existing_type=sa.JSON(),
        postgresql_using='ARRAY(SELECT jsonb_array_elements_text(aliases::jsonb))',
    )
