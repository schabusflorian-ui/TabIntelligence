"""add learned alias lifecycle fields

Revision ID: v6w7x8y9z0a1
Revises: u5v6w7x8y9z0
Create Date: 2026-03-18 14:00:00.000000

Adds lifecycle management columns to learned_aliases table:
- last_seen_at: timestamp updated on every occurrence
- archived: boolean flag for stale aliases
- archived_reason: why the alias was archived
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'v6w7x8y9z0a1'
down_revision: str = 'u5v6w7x8y9z0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'learned_aliases',
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'learned_aliases',
        sa.Column('archived', sa.Boolean(), server_default='false', nullable=False),
    )
    op.add_column(
        'learned_aliases',
        sa.Column('archived_reason', sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('learned_aliases', 'archived_reason')
    op.drop_column('learned_aliases', 'archived')
    op.drop_column('learned_aliases', 'last_seen_at')
