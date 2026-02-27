"""Initial DebtFund schema with files, extraction_jobs, and lineage_events

Revision ID: 001_initial
Revises:
Create Date: 2026-02-24 14:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create files, extraction_jobs, and lineage_events tables."""

    # Create files table
    op.create_table(
        'files',
        sa.Column('file_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('s3_key', sa.String(length=512), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('file_id')
    )

    # Create extraction_jobs table
    op.create_table(
        'extraction_jobs',
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('current_stage', sa.String(length=50), nullable=True),
        sa.Column('progress_percent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('result', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.String(length=2000), nullable=True),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['file_id'], ['files.file_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('job_id')
    )

    # Create indexes for extraction_jobs
    op.create_index('ix_extraction_jobs_status', 'extraction_jobs', ['status'])
    op.create_index('ix_extraction_jobs_created_at', 'extraction_jobs', ['created_at'])

    # Create lineage_events table
    op.create_table(
        'lineage_events',
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('stage_name', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['extraction_jobs.job_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('event_id')
    )

    # Create index for lineage_events
    op.create_index('ix_lineage_events_job_id', 'lineage_events', ['job_id'])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_index('ix_lineage_events_job_id', table_name='lineage_events')
    op.drop_table('lineage_events')

    op.drop_index('ix_extraction_jobs_created_at', table_name='extraction_jobs')
    op.drop_index('ix_extraction_jobs_status', table_name='extraction_jobs')
    op.drop_table('extraction_jobs')

    op.drop_table('files')
