"""Add extraction_facts table for decomposed extraction results.

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-03-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = 'h2i3j4k5l6m7'
down_revision: Union[str, Sequence[str], None] = 'g1h2i3j4k5l6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'extraction_facts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('job_id', UUID(as_uuid=True),
                   sa.ForeignKey('extraction_jobs.job_id', ondelete='CASCADE'),
                   nullable=False, index=True),
        sa.Column('entity_id', UUID(as_uuid=True),
                   sa.ForeignKey('entities.id', ondelete='SET NULL'),
                   nullable=True, index=True),
        sa.Column('canonical_name', sa.String(100), nullable=False, index=True),
        sa.Column('original_label', sa.String(500), nullable=True),
        sa.Column('period', sa.String(50), nullable=False, index=True),
        sa.Column('period_normalized', sa.String(50), nullable=True),
        sa.Column('value', sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column('confidence', sa.Float, nullable=True),
        sa.Column('sheet_name', sa.String(255), nullable=True),
        sa.Column('row_index', sa.Integer, nullable=True),
        sa.Column('hierarchy_level', sa.Integer, nullable=True),
        sa.Column('mapping_method', sa.String(50), nullable=True),
        sa.Column('taxonomy_category', sa.String(50), nullable=True),
        sa.Column('validation_passed', sa.Boolean, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                   server_default=sa.func.now()),
    )

    # Composite indexes for common query patterns
    op.create_index(
        'ix_extraction_facts_entity_canonical_period',
        'extraction_facts',
        ['entity_id', 'canonical_name', 'period'],
    )
    op.create_index(
        'ix_extraction_facts_job_canonical',
        'extraction_facts',
        ['job_id', 'canonical_name'],
    )


def downgrade() -> None:
    op.drop_index('ix_extraction_facts_job_canonical', table_name='extraction_facts')
    op.drop_index('ix_extraction_facts_entity_canonical_period', table_name='extraction_facts')
    op.drop_table('extraction_facts')
