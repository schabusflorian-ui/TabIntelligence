"""
Unit tests for database constraint violation handler.

Tests that SQLAlchemy IntegrityErrors are correctly mapped
to appropriate HTTP status codes.
"""
import pytest
from unittest.mock import MagicMock

from src.db.constraint_handler import (
    handle_integrity_error,
    _extract_constraint_name,
    _extract_column_name,
)


class TestHandleIntegrityError:
    """Tests for handle_integrity_error function."""

    def _make_integrity_error(self, message):
        """Create a mock IntegrityError with given message."""
        error = MagicMock()
        error.orig = Exception(message)
        return error

    def test_unique_constraint_returns_409(self):
        """Unique constraint violation should return 409 Conflict."""
        error = self._make_integrity_error(
            'duplicate key value violates unique constraint "taxonomy_canonical_name_key"'
        )
        result = handle_integrity_error(error)
        assert result.status_code == 409
        assert "already exists" in result.detail

    def test_unique_constraint_sqlite(self):
        """SQLite unique constraint should also return 409."""
        error = self._make_integrity_error(
            "UNIQUE constraint failed: taxonomy.canonical_name"
        )
        result = handle_integrity_error(error)
        assert result.status_code == 409

    def test_foreign_key_returns_400(self):
        """Foreign key violation should return 400."""
        error = self._make_integrity_error(
            'insert or update on table "files" violates foreign key constraint "fk_files_entity_id"'
        )
        result = handle_integrity_error(error)
        assert result.status_code == 400
        assert "Referenced resource not found" in result.detail

    def test_check_constraint_returns_422(self):
        """Check constraint violation should return 422."""
        error = self._make_integrity_error(
            'new row violates check constraint "ck_entity_patterns_confidence"'
        )
        result = handle_integrity_error(error)
        assert result.status_code == 422
        assert "Validation failed" in result.detail

    def test_not_null_returns_422(self):
        """Not-null violation should return 422."""
        error = self._make_integrity_error(
            'null value in column "name" violates not-null constraint'
        )
        result = handle_integrity_error(error)
        assert result.status_code == 422
        assert "Required field missing" in result.detail

    def test_generic_error_returns_400(self):
        """Unknown integrity error should return 400."""
        error = self._make_integrity_error("some unknown database error")
        result = handle_integrity_error(error)
        assert result.status_code == 400
        assert "Data integrity error" in result.detail

    def test_no_orig_attribute(self):
        """Should handle case where e.orig is None."""
        error = MagicMock()
        error.orig = None
        error.__str__ = MagicMock(return_value="some error")
        result = handle_integrity_error(error)
        assert result.status_code == 400


class TestExtractConstraintName:
    """Tests for _extract_constraint_name helper."""

    def test_postgresql_format(self):
        """Extract constraint name from PostgreSQL error."""
        result = _extract_constraint_name(
            'violates unique constraint "taxonomy_canonical_name_key"'
        )
        assert result == "taxonomy_canonical_name_key"

    def test_sqlite_format(self):
        """Extract constraint info from SQLite error."""
        result = _extract_constraint_name(
            "unique constraint failed: taxonomy.canonical_name"
        )
        assert result == "taxonomy.canonical_name"

    def test_no_match(self):
        """Return None when no constraint name found."""
        result = _extract_constraint_name("some random error")
        assert result is None


class TestExtractColumnName:
    """Tests for _extract_column_name helper."""

    def test_postgresql_format(self):
        """Extract column name from PostgreSQL not-null error."""
        result = _extract_column_name(
            'null value in column "name" violates not-null constraint'
        )
        assert result == "name"

    def test_sqlite_format(self):
        """Extract column name from SQLite not-null error."""
        result = _extract_column_name(
            "not null constraint failed: entities.name"
        )
        assert result == "name"

    def test_no_match(self):
        """Return None when no column name found."""
        result = _extract_column_name("some random error")
        assert result is None
