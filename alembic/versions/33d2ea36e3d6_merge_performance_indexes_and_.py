"""merge_performance_indexes_and_corrections

Revision ID: 33d2ea36e3d6
Revises: b2c3d4e5f6a7, o9p0q1r2s3t4
Create Date: 2026-03-17 15:49:29.713189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '33d2ea36e3d6'
down_revision: Union[str, Sequence[str], None] = ('b2c3d4e5f6a7', 'o9p0q1r2s3t4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
