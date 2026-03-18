"""add taxonomy version and checksum to extraction_jobs

Revision ID: t4u5v6w7x8y9
Revises: s3t4u5v6w7x8
Create Date: 2026-03-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 't4u5v6w7x8y9'
down_revision: Union[str, Sequence[str], None] = 's3t4u5v6w7x8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('extraction_jobs', sa.Column('taxonomy_version', sa.String(20), nullable=True))
    op.add_column('extraction_jobs', sa.Column('taxonomy_checksum', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('extraction_jobs', 'taxonomy_checksum')
    op.drop_column('extraction_jobs', 'taxonomy_version')
