"""add taxonomy governance

Revision ID: x8y9z0a1b2c3
Revises: w7x8y9z0a1b2
Create Date: 2026-03-18 18:00:00.000000

Adds deprecation fields to taxonomy table and creates taxonomy_changelog table
for governance audit trail.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "x8y9z0a1b2c3"
down_revision: str = "w7x8y9z0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add deprecation columns to taxonomy table
    op.add_column(
        "taxonomy",
        sa.Column("deprecated", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "taxonomy",
        sa.Column("deprecated_redirect", sa.String(200), nullable=True),
    )
    op.add_column(
        "taxonomy",
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create taxonomy_changelog table
    op.create_table(
        "taxonomy_changelog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_name", sa.String(200), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(100), nullable=False),
        sa.Column("taxonomy_version", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("taxonomy_changelog")
    op.drop_column("taxonomy", "deprecated_at")
    op.drop_column("taxonomy", "deprecated_redirect")
    op.drop_column("taxonomy", "deprecated")
