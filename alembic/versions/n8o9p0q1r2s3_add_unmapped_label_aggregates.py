"""Add unmapped_label_aggregates table for taxonomy gap analysis.

Tracks unmapped labels across entities with occurrence counts,
variants, and sheet context for identifying taxonomy gaps.

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-03-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "n8o9p0q1r2s3"
down_revision: Union[str, Sequence[str], None] = "m7n8o9p0q1r2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "unmapped_label_aggregates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("label_normalized", sa.String(500), nullable=False, index=True),
        sa.Column("original_labels", sa.JSON, nullable=False, server_default="[]"),
        sa.Column(
            "entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("occurrence_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("last_seen_job_id", UUID(as_uuid=True), nullable=True),
        sa.Column("sheet_names", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("taxonomy_category_hint", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("label_normalized", "entity_id", name="uq_unmapped_label_entity"),
    )


def downgrade() -> None:
    op.drop_table("unmapped_label_aggregates")
