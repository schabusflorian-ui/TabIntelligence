"""Add composite performance indexes for common query patterns."""

from alembic import op

# revision identifiers
revision = "o9p0q1r2s3t4"
down_revision = "n8o9p0q1r2s3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Composite index for list_jobs() which filters by status + orders by created_at
    op.create_index(
        "ix_extraction_jobs_status_created_at",
        "extraction_jobs",
        ["status", "created_at"],
    )
    # Index for stale job health check queries
    op.create_index(
        "ix_extraction_jobs_updated_at",
        "extraction_jobs",
        ["updated_at"],
    )
    # Composite index for pattern upsert lookup
    op.create_index(
        "ix_entity_patterns_entity_id_original_label",
        "entity_patterns",
        ["entity_id", "original_label"],
    )


def downgrade() -> None:
    op.drop_index("ix_entity_patterns_entity_id_original_label", table_name="entity_patterns")
    op.drop_index("ix_extraction_jobs_updated_at", table_name="extraction_jobs")
    op.drop_index("ix_extraction_jobs_status_created_at", table_name="extraction_jobs")
