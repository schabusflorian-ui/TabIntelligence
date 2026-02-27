"""
Unit tests for CRUD error paths (SQLAlchemy exception handling).

Tests that each CRUD function properly handles SQLAlchemy errors by rolling back
and raising DatabaseError.
"""
import pytest
from uuid import uuid4
from unittest.mock import patch, MagicMock, PropertyMock

from sqlalchemy.exc import SQLAlchemyError

from src.db import crud
from src.db.models import File, ExtractionJob, JobStatusEnum
from src.core.exceptions import DatabaseError


# ============================================================================
# FILE ERROR PATHS
# ============================================================================


class TestCreateFileError:

    def test_raises_database_error_on_sqlalchemy_failure(self, db_session):
        """Should rollback and raise DatabaseError on SQLAlchemy error."""
        with patch.object(db_session, "commit", side_effect=SQLAlchemyError("disk full")):
            with pytest.raises(DatabaseError) as exc_info:
                crud.create_file(db_session, filename="test.xlsx", file_size=100)

            assert "Failed to create file" in str(exc_info.value)
            assert exc_info.value.details["operation"] == "create"
            assert exc_info.value.details["table"] == "files"


class TestGetFileError:

    def test_raises_database_error_on_query_failure(self, db_session):
        """Should raise DatabaseError when query fails."""
        with patch.object(db_session, "query", side_effect=SQLAlchemyError("connection lost")):
            with pytest.raises(DatabaseError) as exc_info:
                crud.get_file(db_session, uuid4())

            assert "Failed to get file" in str(exc_info.value)
            assert exc_info.value.details["operation"] == "read"


class TestUpdateFileS3KeyError:

    def test_file_not_found_raises_database_error(self, db_session):
        """Should raise DatabaseError when file not found."""
        with pytest.raises(DatabaseError) as exc_info:
            crud.update_file_s3_key(db_session, uuid4(), "some/s3/key")

        assert "not found" in str(exc_info.value)
        assert exc_info.value.details["operation"] == "update"

    def test_sqlalchemy_error_on_commit(self, db_session, sample_file):
        """Should rollback and raise DatabaseError on commit failure."""
        with patch.object(db_session, "commit", side_effect=SQLAlchemyError("write conflict")):
            with pytest.raises(DatabaseError) as exc_info:
                crud.update_file_s3_key(db_session, sample_file.file_id, "new/key")

            assert "Failed to update file" in str(exc_info.value)


# ============================================================================
# EXTRACTION JOB ERROR PATHS
# ============================================================================


class TestCreateExtractionJobError:

    def test_raises_database_error_on_sqlalchemy_failure(self, db_session, sample_file):
        """Should rollback and raise DatabaseError on SQLAlchemy error."""
        with patch.object(db_session, "commit", side_effect=SQLAlchemyError("constraint")):
            with pytest.raises(DatabaseError) as exc_info:
                crud.create_extraction_job(db_session, file_id=sample_file.file_id)

            assert "Failed to create job" in str(exc_info.value)
            assert exc_info.value.details["table"] == "extraction_jobs"


class TestGetJobError:

    def test_raises_database_error_on_query_failure(self, db_session):
        """Should raise DatabaseError when query fails."""
        with patch.object(db_session, "query", side_effect=SQLAlchemyError("timeout")):
            with pytest.raises(DatabaseError) as exc_info:
                crud.get_job(db_session, uuid4())

            assert "Failed to get job" in str(exc_info.value)


class TestUpdateJobStatusError:

    def test_sqlalchemy_error_on_commit(self, db_session, sample_job):
        """Should rollback and raise DatabaseError on commit failure."""
        with patch.object(db_session, "commit", side_effect=SQLAlchemyError("deadlock")):
            with pytest.raises(DatabaseError) as exc_info:
                crud.update_job_status(
                    db_session, sample_job.job_id, JobStatusEnum.PROCESSING
                )

            assert "Failed to update job" in str(exc_info.value)


class TestCompleteJobError:

    def test_sqlalchemy_error_on_commit(self, db_session, sample_job):
        """Should rollback and raise DatabaseError on commit failure."""
        with patch.object(db_session, "commit", side_effect=SQLAlchemyError("serialization")):
            with pytest.raises(DatabaseError) as exc_info:
                crud.complete_job(
                    db_session, sample_job.job_id,
                    result={"data": "test"}, tokens_used=100, cost_usd=0.01,
                )

            assert "Failed to complete job" in str(exc_info.value)


class TestFailJobError:

    def test_sqlalchemy_error_on_commit(self, db_session, sample_job):
        """Should rollback and raise DatabaseError on commit failure."""
        with patch.object(db_session, "commit", side_effect=SQLAlchemyError("connection reset")):
            with pytest.raises(DatabaseError) as exc_info:
                crud.fail_job(db_session, sample_job.job_id, error="some error")

            assert "Failed to update job" in str(exc_info.value)


class TestListJobsError:

    def test_raises_database_error_on_query_failure(self, db_session):
        """Should raise DatabaseError when query fails."""
        with patch.object(db_session, "query", side_effect=SQLAlchemyError("pool exhausted")):
            with pytest.raises(DatabaseError) as exc_info:
                crud.list_jobs(db_session)

            assert "Failed to list jobs" in str(exc_info.value)
            assert exc_info.value.details["table"] == "extraction_jobs"


# ============================================================================
# LINEAGE EVENT ERROR PATHS
# ============================================================================


class TestCreateLineageEventError:

    def test_raises_database_error_on_sqlalchemy_failure(self, db_session, sample_job):
        """Should rollback and raise DatabaseError on SQLAlchemy error."""
        with patch.object(db_session, "commit", side_effect=SQLAlchemyError("fk violation")):
            with pytest.raises(DatabaseError) as exc_info:
                crud.create_lineage_event(
                    db_session, job_id=sample_job.job_id, stage_name="parsing"
                )

            assert "Failed to create lineage event" in str(exc_info.value)
            assert exc_info.value.details["table"] == "lineage_events"


class TestGetJobLineageError:

    def test_raises_database_error_on_query_failure(self, db_session):
        """Should raise DatabaseError when query fails."""
        with patch.object(db_session, "query", side_effect=SQLAlchemyError("network error")):
            with pytest.raises(DatabaseError) as exc_info:
                crud.get_job_lineage(db_session, uuid4())

            assert "Failed to get lineage" in str(exc_info.value)
