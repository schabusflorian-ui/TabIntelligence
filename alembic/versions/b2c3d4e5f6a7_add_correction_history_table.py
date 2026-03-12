"""Add correction_history table for tracking retroactive corrections.

Revision ID: b2c3d4e5f6a7
Revises: h2i3j4k5l6m7
Create Date: 2026-03-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'h2i3j4k5l6m7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'correction_history',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('job_id', UUID(as_uuid=True), sa.ForeignKey('extraction_jobs.job_id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('entity_id', UUID(as_uuid=True), sa.ForeignKey('entities.id', ondelete='SET NULL'), nullable=True),
        sa.Column('original_label', sa.String(500), nullable=False),
        sa.Column('sheet', sa.String(255), nullable=True),
        sa.Column('old_canonical_name', sa.String(100), nullable=False),
        sa.Column('new_canonical_name', sa.String(100), nullable=False),
        sa.Column('old_confidence', sa.Float, nullable=False),
        sa.Column('new_confidence', sa.Float, nullable=False, server_default='1.0'),
        sa.Column('old_line_item_snapshot', sa.JSON, nullable=True),
        sa.Column('reverted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('reverted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_correction_history_entity_id', 'correction_history', ['entity_id'])


def downgrade() -> None:
    op.drop_index('ix_correction_history_entity_id', table_name='correction_history')
    op.drop_table('correction_history')
