"""add entity detail columns

Revision ID: p0q1r2s3t4u5
Revises: 33d2ea36e3d6
Create Date: 2026-03-17 16:32:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'p0q1r2s3t4u5'
down_revision: Union[str, Sequence[str], None] = '33d2ea36e3d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('entities', sa.Column('fiscal_year_end', sa.Integer(), nullable=True))
    op.add_column('entities', sa.Column('default_currency', sa.String(3), nullable=True))
    op.add_column('entities', sa.Column('reporting_standard', sa.String(20), nullable=True))
    op.create_check_constraint(
        'ck_entity_fiscal_year_end',
        'entities',
        'fiscal_year_end IS NULL OR (fiscal_year_end >= 1 AND fiscal_year_end <= 12)',
    )


def downgrade() -> None:
    op.drop_constraint('ck_entity_fiscal_year_end', 'entities', type_='check')
    op.drop_column('entities', 'reporting_standard')
    op.drop_column('entities', 'default_currency')
    op.drop_column('entities', 'fiscal_year_end')
