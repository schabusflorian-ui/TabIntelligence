"""add taxonomy_suggestions table

Revision ID: w7x8y9z0a1b2
Revises: v6w7x8y9z0a1
Create Date: 2026-03-18 16:00:00.000000

Creates the taxonomy_suggestions table for tracking taxonomy improvement
suggestions generated from frequently unmapped labels.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# revision identifiers, used by Alembic.
revision: str = 'w7x8y9z0a1b2'
down_revision: str = 'v6w7x8y9z0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'taxonomy_suggestions',
        sa.Column('id', PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('suggestion_type', sa.String(20), nullable=False),
        sa.Column('canonical_name', sa.String(200), nullable=True),
        sa.Column('suggested_text', sa.String(500), nullable=False),
        sa.Column('evidence_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('evidence_jobs', sa.JSON, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('resolved_at', sa.DateTime, nullable=True),
        sa.Column('resolved_by', sa.String(100), nullable=True),
    )
    op.create_index('ix_taxonomy_suggestions_status', 'taxonomy_suggestions', ['status'])
    op.create_index('ix_taxonomy_suggestions_suggested_text', 'taxonomy_suggestions', ['suggested_text'])


def downgrade() -> None:
    op.drop_index('ix_taxonomy_suggestions_suggested_text', table_name='taxonomy_suggestions')
    op.drop_index('ix_taxonomy_suggestions_status', table_name='taxonomy_suggestions')
    op.drop_table('taxonomy_suggestions')
