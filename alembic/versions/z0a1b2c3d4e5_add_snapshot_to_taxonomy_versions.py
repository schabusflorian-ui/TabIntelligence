"""Add snapshot JSON column to taxonomy_versions table

Revision ID: z0a1b2c3d4e5
Revises: y9z0a1b2c3d4
Create Date: 2026-03-24 09:00:00.000000

Adds a nullable JSON column `snapshot` to taxonomy_versions.
When populated it stores the full taxonomy.json content at the time
the version was applied, enabling diff and audit queries.
"""

from alembic import op
import sqlalchemy as sa

revision = "z0a1b2c3d4e5"
down_revision = "y9z0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "taxonomy_versions",
        sa.Column("snapshot", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("taxonomy_versions", "snapshot")
