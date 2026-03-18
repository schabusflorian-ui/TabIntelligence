"""add extraction_facts detail columns

Revision ID: s3t4u5v6w7x8
Revises: r2s3t4u5v6w7
Create Date: 2026-03-17 18:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 's3t4u5v6w7x8'
down_revision: Union[str, Sequence[str], None] = 'r2s3t4u5v6w7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('extraction_facts', sa.Column('currency_code', sa.String(3), nullable=True))
    op.add_column('extraction_facts', sa.Column('source_unit', sa.String(20), nullable=True))
    op.add_column('extraction_facts', sa.Column('source_scale', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('extraction_facts', 'source_scale')
    op.drop_column('extraction_facts', 'source_unit')
    op.drop_column('extraction_facts', 'currency_code')
