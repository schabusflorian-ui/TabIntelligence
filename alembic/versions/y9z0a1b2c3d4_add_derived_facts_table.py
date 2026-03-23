"""add derived_facts table for Stage 6 Derivation Engine

Revision ID: y9z0a1b2c3d4
Revises: x8y9z0a1b2c3
Create Date: 2026-03-22 10:00:00.000000

Creates the derived_facts table, which stores computed financial metrics
produced by the Stage 6 Derivation Engine. Each row represents one
(job_id, canonical_name, period) derived metric with:
  - uncertainty bands (value_range_low / value_range_high)
  - consistency check results vs. extracted values
  - covenant sensitivity context for coverage/leverage metrics
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "y9z0a1b2c3d4"
down_revision: str = "x8y9z0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "derived_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("canonical_name", sa.String(100), nullable=False),
        sa.Column("period", sa.String(50), nullable=False),
        sa.Column("computed_value", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("value_range_low", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("value_range_high", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("computation_rule_id", sa.String(20), nullable=False),
        sa.Column("formula", sa.String(200), nullable=False),
        sa.Column("source_canonicals", sa.JSON(), nullable=False),
        sa.Column("confidence_mode", sa.String(20), nullable=False),
        sa.Column("derivation_pass", sa.Integer(), nullable=False),
        sa.Column("is_gap_fill", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("consistency_check", sa.JSON(), nullable=True),
        sa.Column("covenant_context", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["extraction_jobs.job_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id", "canonical_name", "period", name="uq_derived_job_canonical_period"
        ),
    )
    op.create_index("ix_derived_facts_job_id", "derived_facts", ["job_id"])
    op.create_index("ix_derived_facts_entity_id", "derived_facts", ["entity_id"])
    op.create_index("ix_derived_facts_canonical_name", "derived_facts", ["canonical_name"])
    op.create_index("ix_derived_facts_period", "derived_facts", ["period"])
    op.create_index(
        "ix_derived_job_canonical", "derived_facts", ["job_id", "canonical_name"]
    )
    op.create_index(
        "ix_derived_entity_canonical", "derived_facts", ["entity_id", "canonical_name"]
    )


def downgrade() -> None:
    op.drop_index("ix_derived_entity_canonical", table_name="derived_facts")
    op.drop_index("ix_derived_job_canonical", table_name="derived_facts")
    op.drop_index("ix_derived_facts_period", table_name="derived_facts")
    op.drop_index("ix_derived_facts_canonical_name", table_name="derived_facts")
    op.drop_index("ix_derived_facts_entity_id", table_name="derived_facts")
    op.drop_index("ix_derived_facts_job_id", table_name="derived_facts")
    op.drop_table("derived_facts")
