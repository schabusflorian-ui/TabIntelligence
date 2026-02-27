"""Add Entity, Taxonomy, and EntityPattern tables

Revision ID: 345956f5d313
Revises: 8a3ff594b45a
Create Date: 2026-02-24 15:43:56.693064

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '345956f5d313'
down_revision: Union[str, Sequence[str], None] = '8a3ff594b45a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Entity, Taxonomy, and EntityPattern tables."""

    # Create entities table
    op.create_table(
        'entities',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('industry', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_entities_name', 'entities', ['name'])

    # Create taxonomy table
    op.create_table(
        'taxonomy',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('canonical_name', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('aliases', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('definition', sa.Text(), nullable=True),
        sa.Column('typical_sign', sa.String(length=10), nullable=True),
        sa.Column('parent_canonical', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "typical_sign IN ('positive', 'negative', 'varies') OR typical_sign IS NULL",
            name='ck_taxonomy_typical_sign'
        ),
        sa.CheckConstraint(
            "category IN ('income_statement', 'balance_sheet', 'cash_flow', "
            "'debt_schedule', 'depreciation_amortization', 'working_capital', "
            "'assumptions', 'metrics')",
            name='ck_taxonomy_category'
        ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_taxonomy_canonical_name', 'taxonomy', ['canonical_name'], unique=True)
    op.create_index('ix_taxonomy_category', 'taxonomy', ['category'])

    # Create entity_patterns table
    op.create_table(
        'entity_patterns',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('original_label', sa.String(length=500), nullable=False),
        sa.Column('canonical_name', sa.String(length=100), nullable=False),
        sa.Column('confidence', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column('occurrence_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            'confidence >= 0.0 AND confidence <= 1.0',
            name='ck_entity_patterns_confidence'
        ),
        sa.CheckConstraint(
            "created_by IN ('claude', 'user_correction')",
            name='ck_entity_patterns_created_by'
        ),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_entity_patterns_entity_id', 'entity_patterns', ['entity_id'])
    op.create_index('ix_entity_patterns_canonical_name', 'entity_patterns', ['canonical_name'])
    op.create_index('ix_entity_patterns_original_label', 'entity_patterns', ['original_label'])
    op.create_index('ix_entity_patterns_entity_label', 'entity_patterns', ['entity_id', 'original_label'])


def downgrade() -> None:
    """Remove Entity, Taxonomy, and EntityPattern tables."""
    op.drop_index('ix_entity_patterns_entity_label', table_name='entity_patterns')
    op.drop_index('ix_entity_patterns_original_label', table_name='entity_patterns')
    op.drop_index('ix_entity_patterns_canonical_name', table_name='entity_patterns')
    op.drop_index('ix_entity_patterns_entity_id', table_name='entity_patterns')
    op.drop_table('entity_patterns')

    op.drop_index('ix_taxonomy_category', table_name='taxonomy')
    op.drop_index('ix_taxonomy_canonical_name', table_name='taxonomy')
    op.drop_table('taxonomy')

    op.drop_index('ix_entities_name', table_name='entities')
    op.drop_table('entities')
