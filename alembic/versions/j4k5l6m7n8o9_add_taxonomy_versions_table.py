"""Add taxonomy_versions table for version tracking.

Tracks taxonomy.json versions applied to the database with version string,
item count, SHA-256 checksum, and category distribution.

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-03-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "j4k5l6m7n8o9"
down_revision: Union[str, Sequence[str], None] = "i3j4k5l6m7n8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "taxonomy_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("item_count", sa.Integer, nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("categories", sa.JSON, nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("applied_by", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("taxonomy_versions")
