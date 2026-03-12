"""Add quality_grade column and NEEDS_REVIEW status to extraction_jobs.

Revision ID: g1h2i3j4k5l6
Revises: f1a2b3c4d5e6
Create Date: 2026-03-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'g1h2i3j4k5l6'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add quality_grade column (letter grade from quality scorer)
    op.add_column(
        'extraction_jobs',
        sa.Column(
            'quality_grade',
            sa.String(2),
            nullable=True,
            comment='Letter grade (A/B/C/D/F) from quality scorer',
        ),
    )
    # Add NEEDS_REVIEW to the PostgreSQL enum type
    op.execute("ALTER TYPE jobstatusenum ADD VALUE IF NOT EXISTS 'needs_review'")


def downgrade() -> None:
    # Move NEEDS_REVIEW jobs back to COMPLETED before dropping the column
    op.execute(
        "UPDATE extraction_jobs SET status = 'completed' "
        "WHERE status = 'needs_review'"
    )
    op.drop_column('extraction_jobs', 'quality_grade')
    # Note: PostgreSQL does not support removing enum values.
    # The 'needs_review' value will remain in the enum type but won't be used.
