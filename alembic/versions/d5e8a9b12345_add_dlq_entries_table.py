"""add dlq_entries table

Revision ID: d5e8a9b12345
Revises: c2dcf17a60da
Create Date: 2026-02-24 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd5e8a9b12345'
down_revision: Union[str, Sequence[str], None] = 'c2dcf17a60da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add dlq_entries table for Dead Letter Queue."""

    # Create dlq_entries table
    op.create_table(
        'dlq_entries',
        sa.Column('dlq_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('task_id', sa.String(length=255), nullable=False, comment='Celery task ID'),
        sa.Column('task_name', sa.String(length=255), nullable=False, comment='Task name'),
        sa.Column('task_args', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='Task arguments'),
        sa.Column('task_kwargs', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='Task keyword arguments'),
        sa.Column('error', sa.Text(), nullable=False, comment='Error message'),
        sa.Column('traceback', sa.Text(), nullable=True, comment='Full traceback'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='When DLQ entry was created'
        ),
        sa.Column('replayed', sa.Integer(), nullable=False, server_default='0', comment='Replay count'),
        sa.Column(
            'replayed_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='When task was replayed'
        ),
        sa.Column('replayed_task_id', sa.String(length=255), nullable=True, comment='New task ID after replay'),
        sa.PrimaryKeyConstraint('dlq_id'),
        comment='Dead Letter Queue entries for failed tasks'
    )

    # Create indexes on dlq_entries
    op.create_index('ix_dlq_entries_task_id', 'dlq_entries', ['task_id'])
    op.create_index('ix_dlq_entries_created_at', 'dlq_entries', ['created_at'])


def downgrade() -> None:
    """Downgrade schema: Remove dlq_entries table."""

    # Drop dlq_entries table and its indexes
    op.drop_index('ix_dlq_entries_created_at', table_name='dlq_entries')
    op.drop_index('ix_dlq_entries_task_id', table_name='dlq_entries')
    op.drop_table('dlq_entries')
