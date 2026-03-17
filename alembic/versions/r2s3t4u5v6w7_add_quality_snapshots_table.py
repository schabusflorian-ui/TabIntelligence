"""add quality_snapshots table

Revision ID: r2s3t4u5v6w7
Revises: q1r2s3t4u5v6
Create Date: 2026-03-17 17:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'r2s3t4u5v6w7'
down_revision: Union[str, Sequence[str], None] = 'q1r2s3t4u5v6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'quality_snapshots',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_id', UUID(as_uuid=True), sa.ForeignKey('entities.id', ondelete='CASCADE'),
                   nullable=False, index=True),
        sa.Column('snapshot_date', sa.String(10), nullable=False),
        sa.Column('avg_confidence', sa.Float, nullable=False),
        sa.Column('quality_grade', sa.String(2), nullable=False),
        sa.Column('total_facts', sa.Integer, nullable=False),
        sa.Column('total_jobs', sa.Integer, nullable=False),
        sa.Column('unmapped_label_count', sa.Integer, server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        'ix_quality_snapshot_entity_date',
        'quality_snapshots',
        ['entity_id', 'snapshot_date'],
    )


def downgrade() -> None:
    op.drop_index('ix_quality_snapshot_entity_date', table_name='quality_snapshots')
    op.drop_table('quality_snapshots')
