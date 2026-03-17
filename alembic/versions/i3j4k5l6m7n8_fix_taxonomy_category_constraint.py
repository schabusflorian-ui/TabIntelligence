"""Fix taxonomy category CHECK constraint to match actual categories.

Drops deprecated categories (depreciation_amortization, working_capital,
assumptions) and adds project_finance which has 13 items in taxonomy.json.

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-03-17
"""
from typing import Sequence, Union

from alembic import op


revision: str = "i3j4k5l6m7n8"
down_revision: Union[str, Sequence[str], None] = "h2i3j4k5l6m7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_taxonomy_category", "taxonomy", type_="check")
    op.create_check_constraint(
        "ck_taxonomy_category",
        "taxonomy",
        "category IN ('income_statement', 'balance_sheet', 'cash_flow', "
        "'debt_schedule', 'metrics', 'project_finance')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_taxonomy_category", "taxonomy", type_="check")
    op.create_check_constraint(
        "ck_taxonomy_category",
        "taxonomy",
        "category IN ('income_statement', 'balance_sheet', 'cash_flow', "
        "'debt_schedule', 'depreciation_amortization', 'working_capital', "
        "'assumptions', 'metrics')",
    )
