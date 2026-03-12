"""Add is_active to entity_patterns and create learned_aliases table.

Revision ID: e4f5a6b7c8d9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_active column and learned_aliases table."""
    conn = op.get_bind()

    # Add is_active to entity_patterns (idempotent)
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='entity_patterns' AND column_name='is_active'"
    ))
    if not result.fetchone():
        op.add_column(
            'entity_patterns',
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        )

    # Create learned_aliases table (idempotent)
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name='learned_aliases'"
    ))
    if not result.fetchone():
        op.create_table(
            'learned_aliases',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('canonical_name', sa.String(100), nullable=False, index=True),
            sa.Column('alias_text', sa.String(500), nullable=False, index=True),
            sa.Column('occurrence_count', sa.Integer(), server_default='1', nullable=False),
            sa.Column('source_entities', sa.JSON(), server_default='[]', nullable=False),
            sa.Column('promoted', sa.Boolean(), server_default='false', nullable=False),
            sa.Column(
                'created_at',
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint('canonical_name', 'alias_text', name='uq_learned_aliases_canonical_alias'),
        )


def downgrade() -> None:
    """Remove is_active column and learned_aliases table."""
    op.drop_table('learned_aliases')
    op.drop_column('entity_patterns', 'is_active')
