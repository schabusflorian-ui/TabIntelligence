"""add api_keys table and files FK

Revision ID: c2dcf17a60da
Revises: f9417a796465
Create Date: 2026-02-24 21:51:26.772420

NOTE: The entities table was already created in migration 345956f5d313.
This migration only creates api_keys and adds the FK from files to entities.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c2dcf17a60da'
down_revision: Union[str, Sequence[str], None] = 'f9417a796465'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add api_keys table and foreign key from files to entities."""

    # Add foreign key from files.entity_id to entities.id
    op.create_foreign_key(
        'fk_files_entity_id',
        'files', 'entities',
        ['entity_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_files_entity_id', 'files', ['entity_id'])

    # Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False, comment='SHA256 hash of API key'),
        sa.Column('name', sa.String(length=100), nullable=False, comment='Human-readable key name'),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True, comment='Optional entity scope'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true', comment='Whether key is active'),
        sa.Column('rate_limit_per_minute', sa.Integer(), nullable=False, server_default='60', comment='Max requests per minute'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='When key was created'
        ),
        sa.Column(
            'last_used_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Last successful use'
        ),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash'),
        comment='API keys for authentication'
    )

    # Create indexes on api_keys
    op.create_index('ix_api_keys_key_hash', 'api_keys', ['key_hash'])
    op.create_index('ix_api_keys_is_active', 'api_keys', ['is_active'])
    op.create_index('ix_api_keys_entity_id', 'api_keys', ['entity_id'])


def downgrade() -> None:
    """Remove api_keys table and files FK."""

    # Drop api_keys table and its indexes
    op.drop_index('ix_api_keys_entity_id', table_name='api_keys')
    op.drop_index('ix_api_keys_is_active', table_name='api_keys')
    op.drop_index('ix_api_keys_key_hash', table_name='api_keys')
    op.drop_table('api_keys')

    # Remove foreign key from files to entities
    op.drop_index('ix_files_entity_id', table_name='files')
    op.drop_constraint('fk_files_entity_id', 'files', type_='foreignkey')
