"""add content_hash to files for deduplication

Revision ID: a1b2c3d4e5f6
Revises: d3cdfafa1ded
Create Date: 2026-02-27 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd3cdfafa1ded'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('files', sa.Column('content_hash', sa.String(64), nullable=True))
    op.create_index('ix_files_content_hash', 'files', ['content_hash'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_files_content_hash', table_name='files')
    op.drop_column('files', 'content_hash')
