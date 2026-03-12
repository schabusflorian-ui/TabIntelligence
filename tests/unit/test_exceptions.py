"""
Unit tests for the custom exception hierarchy.

Tests all exception classes, their attributes, and string representations.
"""

import pytest

from src.core.exceptions import (
    AuthenticationError,
    ClaudeAPIError,
    ConfigurationError,
    DatabaseError,
    DebtFundError,
    ExtractionError,
    FileStorageError,
    InvalidFileError,
    LineageError,
    LineageIncompleteError,
    RateLimitError,
    ValidationError,
)


class TestDebtFundError:
    def test_basic_creation(self):
        e = DebtFundError("something failed")
        assert str(e) == "something failed"
        assert e.message == "something failed"
        assert e.details == {}

    def test_with_details(self):
        e = DebtFundError("failed", details={"key": "value"})
        assert "Details:" in str(e)
        assert e.details == {"key": "value"}

    def test_is_exception(self):
        with pytest.raises(DebtFundError):
            raise DebtFundError("test")


class TestConfigurationError:
    def test_basic(self):
        e = ConfigurationError("missing config")
        assert isinstance(e, DebtFundError)
        assert e.details == {}

    def test_with_missing_vars(self):
        e = ConfigurationError("missing", missing_vars=["DB_URL", "SECRET"])
        assert e.details["missing_vars"] == ["DB_URL", "SECRET"]


class TestExtractionError:
    def test_basic(self):
        e = ExtractionError("extraction failed")
        assert isinstance(e, DebtFundError)
        assert e.details == {}

    def test_with_stage_and_file(self):
        e = ExtractionError("failed", stage="parsing", file_id="abc-123")
        assert e.details["stage"] == "parsing"
        assert e.details["file_id"] == "abc-123"


class TestClaudeAPIError:
    def test_basic(self):
        e = ClaudeAPIError("API error", stage="triage")
        assert isinstance(e, ExtractionError)
        assert e.stage == "triage"
        assert e.retry_count == 0

    def test_with_all_fields(self):
        e = ClaudeAPIError(
            "timeout", stage="mapping", retry_count=3, status_code=429, file_id="file-1"
        )
        assert e.stage == "mapping"
        assert e.retry_count == 3
        assert e.status_code == 429
        assert "[mapping]" in str(e)
        assert "retries: 3" in str(e)


class TestValidationError:
    def test_basic(self):
        e = ValidationError("invalid data")
        assert isinstance(e, ExtractionError)
        assert e.details.get("stage") == "validation"

    def test_with_validation_type(self):
        e = ValidationError("bad sum", validation_type="balance_check")
        assert e.details["validation_type"] == "balance_check"


class TestLineageError:
    def test_basic(self):
        e = LineageError("lineage broken")
        assert isinstance(e, DebtFundError)

    def test_with_job_id(self):
        e = LineageError("broken", job_id="job-123")
        assert e.details["job_id"] == "job-123"


class TestLineageIncompleteError:
    def test_basic(self):
        e = LineageIncompleteError(["triage", "mapping"])
        assert isinstance(e, LineageError)
        assert e.missing_events == ["triage", "mapping"]
        assert "2 missing events" in str(e)

    def test_with_job_id(self):
        e = LineageIncompleteError(["parsing"], job_id="j-1")
        assert e.details["job_id"] == "j-1"
        assert e.details["missing_events"] == ["parsing"]


class TestDatabaseError:
    def test_basic(self):
        e = DatabaseError("db failed")
        assert isinstance(e, DebtFundError)

    def test_with_operation_and_table(self):
        e = DatabaseError("insert failed", operation="create", table="files")
        assert e.details["operation"] == "create"
        assert e.details["table"] == "files"


class TestFileStorageError:
    def test_basic(self):
        e = FileStorageError("s3 failed")
        assert isinstance(e, DebtFundError)

    def test_with_bucket_and_key(self):
        e = FileStorageError("upload failed", bucket="my-bucket", key="path/to/file")
        assert e.details["bucket"] == "my-bucket"
        assert e.details["key"] == "path/to/file"


class TestAuthenticationError:
    def test_basic(self):
        e = AuthenticationError("unauthorized")
        assert isinstance(e, DebtFundError)

    def test_with_user_id(self):
        e = AuthenticationError("forbidden", user_id="user-1")
        assert e.details["user_id"] == "user-1"


class TestRateLimitError:
    def test_basic(self):
        e = RateLimitError("rate limited", stage="parsing")
        assert isinstance(e, ClaudeAPIError)
        assert e.status_code == 429

    def test_with_retry_after(self):
        e = RateLimitError("slow down", stage="triage", retry_after=60)
        assert e.details["retry_after"] == 60


class TestInvalidFileError:
    def test_basic(self):
        e = InvalidFileError("bad file")
        assert isinstance(e, DebtFundError)

    def test_with_filename(self):
        e = InvalidFileError("corrupt", filename="bad.xlsx", file_type="xlsx")
        assert e.details["filename"] == "bad.xlsx"
        assert e.details["file_type"] == "xlsx"


class TestInheritanceChain:
    """Verify the exception hierarchy is correct."""

    def test_all_inherit_from_debtfund_error(self):
        """All custom exceptions should inherit from DebtFundError."""
        exceptions = [
            ConfigurationError("x"),
            ExtractionError("x"),
            ClaudeAPIError("x", stage="s"),
            ValidationError("x"),
            LineageError("x"),
            LineageIncompleteError(["x"]),
            DatabaseError("x"),
            FileStorageError("x"),
            AuthenticationError("x"),
            RateLimitError("x", stage="s"),
            InvalidFileError("x"),
        ]
        for exc in exceptions:
            assert isinstance(exc, DebtFundError), (
                f"{type(exc).__name__} doesn't inherit DebtFundError"
            )

    def test_claude_api_error_is_extraction_error(self):
        assert isinstance(ClaudeAPIError("x", stage="s"), ExtractionError)

    def test_rate_limit_error_is_claude_api_error(self):
        assert isinstance(RateLimitError("x", stage="s"), ClaudeAPIError)

    def test_lineage_incomplete_is_lineage_error(self):
        assert isinstance(LineageIncompleteError(["x"]), LineageError)
