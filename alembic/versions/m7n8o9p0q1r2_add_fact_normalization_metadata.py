"""Add normalization metadata columns to extraction_facts.

Adds currency_code, source_unit, and source_scale for tracking
what normalization was applied to each fact value.

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-03-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m7n8o9p0q1r2"
down_revision: Union[str, Sequence[str], None] = "l6m7n8o9p0q1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("extraction_facts", sa.Column("currency_code", sa.String(3), nullable=True))
    op.add_column("extraction_facts", sa.Column("source_unit", sa.String(20), nullable=True))
    op.add_column("extraction_facts", sa.Column("source_scale", sa.Float, nullable=True))
    op.create_index("ix_fact_currency", "extraction_facts", ["currency_code"])


def downgrade() -> None:
    op.drop_index("ix_fact_currency", table_name="extraction_facts")
    op.drop_column("extraction_facts", "source_scale")
    op.drop_column("extraction_facts", "source_unit")
    op.drop_column("extraction_facts", "currency_code")
