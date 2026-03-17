"""add fx_rate_cache table

Revision ID: q1r2s3t4u5v6
Revises: p0q1r2s3t4u5
Create Date: 2026-03-17 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'q1r2s3t4u5v6'
down_revision: Union[str, Sequence[str], None] = 'p0q1r2s3t4u5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fx_rate_cache',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('from_currency', sa.String(3), nullable=False, index=True),
        sa.Column('to_currency', sa.String(3), nullable=False, index=True),
        sa.Column('rate_date', sa.String(10), nullable=False, index=True),
        sa.Column('rate', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('source', sa.String(50), server_default='alpha_vantage', nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('from_currency', 'to_currency', 'rate_date', name='uq_fx_rate'),
    )


def downgrade() -> None:
    op.drop_table('fx_rate_cache')
