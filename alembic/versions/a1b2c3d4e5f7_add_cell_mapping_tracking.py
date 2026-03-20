"""add cell mapping tracking

Revision ID: a1b2c3d4e5f7
Revises: x8y9z0a1b2c3
Create Date: 2026-03-20 09:00:00.000000

Adds cell-level tracking columns to extraction_facts and correction_history,
and creates cell_mappings table for reverse lookup (cell -> canonical mapping).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: str = "x8y9z0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add cell reference columns to extraction_facts
    op.add_column(
        "extraction_facts",
        sa.Column("cell_ref", sa.String(20), nullable=True),
    )
    op.add_column(
        "extraction_facts",
        sa.Column("source_cell_refs", sa.JSON(), nullable=True),
    )

    # 2. Add cell reference columns to correction_history
    op.add_column(
        "correction_history",
        sa.Column("cell_ref", sa.String(20), nullable=True),
    )
    op.add_column(
        "correction_history",
        sa.Column("row_index", sa.Integer(), nullable=True),
    )

    # 3. Create cell_mappings table
    op.create_table(
        "cell_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("extraction_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("sheet_name", sa.String(255), nullable=False),
        sa.Column("cell_ref", sa.String(20), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("col_index", sa.Integer(), nullable=False),
        sa.Column("cell_role", sa.String(20), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("canonical_name", sa.String(100), nullable=True),
        sa.Column("original_label", sa.String(500), nullable=True),
        sa.Column("period", sa.String(50), nullable=True),
        sa.Column(
            "fact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("extraction_facts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("mapping_status", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("has_formula", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("formula_text", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("job_id", "sheet_name", "cell_ref", name="uq_cellmap_job_sheet_cell"),
    )

    # Indexes for cell_mappings
    op.create_index(
        "ix_cellmap_job_sheet_cell",
        "cell_mappings",
        ["job_id", "sheet_name", "cell_ref"],
    )
    op.create_index(
        "ix_cellmap_job_sheet_row",
        "cell_mappings",
        ["job_id", "sheet_name", "row_index"],
    )


def downgrade() -> None:
    op.drop_table("cell_mappings")
    op.drop_column("correction_history", "row_index")
    op.drop_column("correction_history", "cell_ref")
    op.drop_column("extraction_facts", "source_cell_refs")
    op.drop_column("extraction_facts", "cell_ref")
