"""
Unit tests for file deduplication (idempotent uploads).

Tests content hash storage, lookup, and duplicate detection.
"""

import hashlib

from src.db import crud
from src.db.models import File


class TestGetFileByHash:
    """Test the get_file_by_hash CRUD function."""

    def test_returns_none_when_no_match(self, db_session):
        """Should return None when no file matches the hash."""
        result = crud.get_file_by_hash(db_session, "deadbeef" * 8)
        assert result is None

    def test_returns_file_when_match(self, db_session):
        """Should return the file when hash matches."""
        test_hash = hashlib.sha256(b"test content").hexdigest()
        file = crud.create_file(
            db_session,
            filename="test.xlsx",
            file_size=1024,
            content_hash=test_hash,
        )

        result = crud.get_file_by_hash(db_session, test_hash)
        assert result is not None
        assert result.file_id == file.file_id
        assert result.content_hash == test_hash

    def test_different_hash_no_match(self, db_session):
        """Different hash should not match."""
        hash1 = hashlib.sha256(b"content A").hexdigest()
        hash2 = hashlib.sha256(b"content B").hexdigest()

        crud.create_file(
            db_session,
            filename="test.xlsx",
            file_size=1024,
            content_hash=hash1,
        )

        result = crud.get_file_by_hash(db_session, hash2)
        assert result is None


class TestCreateFileWithHash:
    """Test that create_file properly stores content_hash."""

    def test_hash_stored_correctly(self, db_session):
        """Content hash should be stored and retrievable."""
        test_hash = hashlib.sha256(b"excel content").hexdigest()
        file = crud.create_file(
            db_session,
            filename="model.xlsx",
            file_size=2048,
            content_hash=test_hash,
        )

        assert file.content_hash == test_hash

        # Verify via direct query
        retrieved = db_session.query(File).filter(File.file_id == file.file_id).first()
        assert retrieved.content_hash == test_hash

    def test_hash_optional(self, db_session):
        """File should be creatable without content_hash (backward compat)."""
        file = crud.create_file(
            db_session,
            filename="old_file.xlsx",
            file_size=512,
        )

        assert file.content_hash is None

    def test_different_files_different_hashes(self, db_session):
        """Different file contents should produce different hashes."""
        hash1 = hashlib.sha256(b"file one").hexdigest()
        hash2 = hashlib.sha256(b"file two").hexdigest()

        file1 = crud.create_file(db_session, filename="a.xlsx", file_size=100, content_hash=hash1)
        file2 = crud.create_file(db_session, filename="b.xlsx", file_size=200, content_hash=hash2)

        assert file1.content_hash != file2.content_hash


class TestContentHashProperties:
    """Test SHA-256 hash properties."""

    def test_sha256_length(self):
        """SHA-256 hex digest should be 64 characters."""
        content_hash = hashlib.sha256(b"some content").hexdigest()
        assert len(content_hash) == 64

    def test_deterministic(self):
        """Same content should always produce same hash."""
        content = b"deterministic content"
        hash1 = hashlib.sha256(content).hexdigest()
        hash2 = hashlib.sha256(content).hexdigest()
        assert hash1 == hash2

    def test_different_content_different_hash(self):
        """Different content should produce different hashes."""
        hash1 = hashlib.sha256(b"content A").hexdigest()
        hash2 = hashlib.sha256(b"content B").hexdigest()
        assert hash1 != hash2


class TestDuplicateFileError:
    """Test the DuplicateFileError exception."""

    def test_exception_creation(self):
        from src.core.exceptions import DuplicateFileError

        err = DuplicateFileError(
            "Duplicate file",
            content_hash="abc123",
            existing_file_id="file-001",
        )
        assert "Duplicate file" in str(err)
        assert err.details["content_hash"] == "abc123"
        assert err.details["existing_file_id"] == "file-001"

    def test_exception_without_details(self):
        from src.core.exceptions import DuplicateFileError

        err = DuplicateFileError("Duplicate")
        assert err.details == {}
