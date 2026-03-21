"""Add benchmark_runs and benchmark_category_metrics tables

Revision ID: 39758e78eed4
Revises: a1b2c3d4e5f7
Create Date: 2026-03-21 11:59:00.449594

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '39758e78eed4'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create benchmark tracking tables."""
    op.create_table(
        'benchmark_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('fixture_name', sa.String(200), nullable=False),
        sa.Column('run_date', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('taxonomy_version', sa.String(20), nullable=True),

        # Mapping accuracy
        sa.Column('mapping_precision', sa.Float(), server_default='0.0'),
        sa.Column('mapping_recall', sa.Float(), server_default='0.0'),
        sa.Column('mapping_f1', sa.Float(), server_default='0.0'),
        sa.Column('mapping_accuracy', sa.Float(), server_default='0.0'),

        # Value accuracy
        sa.Column('value_exact_match_rate', sa.Float(), server_default='0.0'),
        sa.Column('value_tolerance_match_rate', sa.Float(), server_default='0.0'),
        sa.Column('value_mae', sa.Float(), server_default='0.0'),
        sa.Column('value_mape', sa.Float(), server_default='0.0'),

        # Triage accuracy
        sa.Column('triage_accuracy', sa.Float(), server_default='0.0'),

        # Extraction metrics
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('total_line_items', sa.Integer(), nullable=True),

        # Full detail JSON
        sa.Column('full_result', sa.JSON(), nullable=True),
    )
    op.create_index('ix_benchmark_fixture_date', 'benchmark_runs', ['fixture_name', 'run_date'])

    op.create_table(
        'benchmark_category_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('benchmark_run_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('benchmark_runs.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('precision', sa.Float(), server_default='0.0'),
        sa.Column('recall', sa.Float(), server_default='0.0'),
        sa.Column('f1', sa.Float(), server_default='0.0'),
        sa.Column('total_items', sa.Integer(), server_default='0'),
        sa.Column('true_positives', sa.Integer(), server_default='0'),
    )
    op.create_index('ix_benchcat_run_category', 'benchmark_category_metrics',
                    ['benchmark_run_id', 'category'])


def downgrade() -> None:
    """Drop benchmark tracking tables."""
    op.drop_index('ix_benchcat_run_category', 'benchmark_category_metrics')
    op.drop_table('benchmark_category_metrics')
    op.drop_index('ix_benchmark_fixture_date', 'benchmark_runs')
    op.drop_table('benchmark_runs')
