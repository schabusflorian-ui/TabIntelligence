"""add line_items table

Revision ID: 8a3ff594b45a
Revises: 001_initial
Create Date: 2026-02-24 15:37:53.416790

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8a3ff594b45a'
down_revision: Union[str, Sequence[str], None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add line_items table for storing individual extracted financial line items."""

    # Create line_items table
    op.create_table(
        'line_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sheet_name', sa.String(length=255), nullable=False),
        sa.Column('row_index', sa.Integer(), nullable=True),
        sa.Column('original_label', sa.String(length=500), nullable=False),
        sa.Column('canonical_name', sa.String(length=100), nullable=False),
        sa.Column('hierarchy_level', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_subtotal', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_formula', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('values', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('confidence', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column('mapping_reasoning', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('confidence >= 0.0 AND confidence <= 1.0', name='ck_line_items_confidence'),
        sa.CheckConstraint('hierarchy_level >= 0.0 AND hierarchy_level <= 5', name='ck_line_items_hierarchy_level'),
        sa.ForeignKeyConstraint(['job_id'], ['extraction_jobs.job_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['file_id'], ['files.file_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes for performance
    op.create_index('ix_line_items_job_id', 'line_items', ['job_id'])
    op.create_index('ix_line_items_file_id', 'line_items', ['file_id'])
    op.create_index('ix_line_items_canonical_name', 'line_items', ['canonical_name'])
    op.create_index('ix_line_items_sheet_name', 'line_items', ['sheet_name'])
    op.create_index('ix_line_items_job_canonical', 'line_items', ['job_id', 'canonical_name'])


def downgrade() -> None:
    """Remove line_items table."""
    # Drop indexes first
    op.drop_index('ix_line_items_job_canonical', table_name='line_items')
    op.drop_index('ix_line_items_sheet_name', table_name='line_items')
    op.drop_index('ix_line_items_canonical_name', table_name='line_items')
    op.drop_index('ix_line_items_file_id', table_name='line_items')
    op.drop_index('ix_line_items_job_id', table_name='line_items')

    # Drop table
    op.drop_table('line_items')
