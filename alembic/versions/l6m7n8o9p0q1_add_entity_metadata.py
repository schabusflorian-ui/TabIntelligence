"""Add entity metadata columns for cross-company normalization.

Adds fiscal_year_end, default_currency, and reporting_standard to entities
table for period alignment, currency normalization, and standard tracking.

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-03-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l6m7n8o9p0q1"
down_revision: Union[str, Sequence[str], None] = "k5l6m7n8o9p0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("entities", sa.Column("fiscal_year_end", sa.Integer, nullable=True))
    op.add_column("entities", sa.Column("default_currency", sa.String(3), nullable=True))
    op.add_column("entities", sa.Column("reporting_standard", sa.String(20), nullable=True))

    op.create_check_constraint(
        "ck_entity_fiscal_year_end",
        "entities",
        "fiscal_year_end IS NULL OR (fiscal_year_end >= 1 AND fiscal_year_end <= 12)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_entity_fiscal_year_end", "entities")
    op.drop_column("entities", "reporting_standard")
    op.drop_column("entities", "default_currency")
    op.drop_column("entities", "fiscal_year_end")
