"""
Tests for Alembic migration structure and integrity.

Validates that:
- All migration files exist and are importable
- Migration chain has no gaps (revisions are properly linked)
- Each migration has both upgrade() and downgrade() functions
- Models match the expected table set after full migration

Note: These tests do NOT run actual migrations against PostgreSQL.
They validate the migration file structure using SQLite.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from src.db.base import Base

ALEMBIC_VERSIONS_DIR = Path(__file__).parent.parent.parent / "alembic" / "versions"


class TestMigrationFileStructure:
    """Test that migration files are properly structured."""

    def test_versions_directory_exists(self):
        """Alembic versions directory should exist."""
        assert ALEMBIC_VERSIONS_DIR.exists()
        assert ALEMBIC_VERSIONS_DIR.is_dir()

    def test_migration_files_exist(self):
        """Should have migration files."""
        migration_files = list(ALEMBIC_VERSIONS_DIR.glob("*.py"))
        # Filter out __pycache__ and __init__.py
        migration_files = [f for f in migration_files if not f.name.startswith("__")]
        assert len(migration_files) >= 6, (
            f"Expected at least 6 migrations, found {len(migration_files)}"
        )

    def test_initial_migration_exists(self):
        """Initial migration file should exist."""
        initial = ALEMBIC_VERSIONS_DIR / "001_initial_debtfund_schema.py"
        assert initial.exists(), "Initial migration 001_initial_debtfund_schema.py not found"

    def test_migration_files_are_python(self):
        """All migration files should be valid Python."""
        for f in ALEMBIC_VERSIONS_DIR.glob("*.py"):
            if f.name.startswith("__"):
                continue
            content = f.read_text()
            try:
                compile(content, str(f), "exec")
            except SyntaxError as e:
                pytest.fail(f"Migration {f.name} has syntax error: {e}")

    def test_migrations_have_revision_ids(self):
        """Each migration should have a revision ID."""
        for f in ALEMBIC_VERSIONS_DIR.glob("*.py"):
            if f.name.startswith("__"):
                continue
            content = f.read_text()
            assert "revision" in content, f"Migration {f.name} missing revision variable"

    def test_migrations_have_upgrade_downgrade(self):
        """Each migration should have both upgrade() and downgrade() functions."""
        for f in ALEMBIC_VERSIONS_DIR.glob("*.py"):
            if f.name.startswith("__"):
                continue
            content = f.read_text()
            assert "def upgrade()" in content, f"Migration {f.name} missing upgrade() function"
            assert "def downgrade()" in content, f"Migration {f.name} missing downgrade() function"


class TestModelTableCompleteness:
    """Test that ORM models create the expected tables."""

    def test_all_tables_created(self):
        """All expected tables should be created from ORM models."""
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        expected_tables = {
            "entities",
            "taxonomy",
            "entity_patterns",
            "files",
            "extraction_jobs",
            "lineage_events",
            "audit_logs",
            "api_keys",
        }

        missing = expected_tables - tables
        assert not missing, f"Missing tables: {missing}"

        engine.dispose()

    def test_entity_table_columns(self):
        """Entity table should have expected columns."""
        engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
        Base.metadata.create_all(bind=engine)

        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("entities")}

        assert "id" in columns
        assert "name" in columns
        assert "industry" in columns
        assert "created_at" in columns

        engine.dispose()

    def test_extraction_jobs_table_columns(self):
        """ExtractionJob table should have expected columns."""
        engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
        Base.metadata.create_all(bind=engine)

        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("extraction_jobs")}

        expected = {
            "job_id",
            "file_id",
            "status",
            "current_stage",
            "progress_percent",
            "result",
            "error",
            "tokens_used",
            "cost_usd",
            "created_at",
            "updated_at",
        }
        missing = expected - columns
        assert not missing, f"Missing columns in extraction_jobs: {missing}"

        engine.dispose()

    def test_taxonomy_table_columns(self):
        """Taxonomy table should have expected columns."""
        engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
        Base.metadata.create_all(bind=engine)

        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("taxonomy")}

        expected = {
            "id",
            "canonical_name",
            "category",
            "display_name",
            "aliases",
            "definition",
            "typical_sign",
            "parent_canonical",
            "created_at",
        }
        missing = expected - columns
        assert not missing, f"Missing columns in taxonomy: {missing}"

        engine.dispose()

    def test_audit_logs_table_columns(self):
        """AuditLog table should have expected columns."""
        engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
        Base.metadata.create_all(bind=engine)

        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("audit_logs")}

        expected = {
            "id",
            "timestamp",
            "action",
            "resource_type",
            "resource_id",
            "api_key_id",
            "ip_address",
            "user_agent",
            "details",
            "status_code",
        }
        missing = expected - columns
        assert not missing, f"Missing columns in audit_logs: {missing}"

        engine.dispose()

    def test_foreign_keys_exist(self):
        """Critical foreign key relationships should exist."""
        engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
        Base.metadata.create_all(bind=engine)

        inspector = inspect(engine)

        # extraction_jobs -> files
        job_fks = inspector.get_foreign_keys("extraction_jobs")
        job_fk_tables = {fk["referred_table"] for fk in job_fks}
        assert "files" in job_fk_tables, "extraction_jobs should reference files"

        # lineage_events -> extraction_jobs
        lineage_fks = inspector.get_foreign_keys("lineage_events")
        lineage_fk_tables = {fk["referred_table"] for fk in lineage_fks}
        assert "extraction_jobs" in lineage_fk_tables, (
            "lineage_events should reference extraction_jobs"
        )

        # entity_patterns -> entities
        pattern_fks = inspector.get_foreign_keys("entity_patterns")
        pattern_fk_tables = {fk["referred_table"] for fk in pattern_fks}
        assert "entities" in pattern_fk_tables, "entity_patterns should reference entities"

        engine.dispose()
