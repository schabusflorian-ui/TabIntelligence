"""
Unit tests for database CRUD operations.

Tests all CRUD operations for File, ExtractionJob, and LineageEvent models.
"""
import pytest
from uuid import uuid4

from src.database import crud
from src.database.models import JobStatusEnum
from src.core.exceptions import DatabaseError


# ============================================================================
# FILE OPERATIONS TESTS
# ============================================================================

def test_create_file(db_session):
    """Test creating a file record."""
    file = crud.create_file(
        db_session,
        filename="test.xlsx",
        file_size=1024,
    )

    assert file.file_id is not None
    assert file.filename == "test.xlsx"
    assert file.file_size == 1024
    assert file.uploaded_at is not None


def test_create_file_with_optional_fields(db_session):
    """Test creating a file with optional fields."""
    entity_id = uuid4()
    file = crud.create_file(
        db_session,
        filename="test.xlsx",
        file_size=2048,
        s3_key="files/test-key.xlsx",
        entity_id=entity_id,
    )

    assert file.file_id is not None
    assert file.filename == "test.xlsx"
    assert file.file_size == 2048
    assert file.s3_key == "files/test-key.xlsx"
    assert file.entity_id == entity_id


def test_get_file(db_session, sample_file):
    """Test retrieving a file by ID."""
    file = crud.get_file(db_session, sample_file.file_id)

    assert file is not None
    assert file.file_id == sample_file.file_id
    assert file.filename == sample_file.filename


def test_get_file_not_found(db_session):
    """Test retrieving non-existent file returns None."""
    file = crud.get_file(db_session, uuid4())
    assert file is None


# ============================================================================
# EXTRACTION JOB OPERATIONS TESTS
# ============================================================================

def test_create_extraction_job(db_session, sample_file):
    """Test creating an extraction job."""
    job = crud.create_extraction_job(
        db_session,
        file_id=sample_file.file_id,
    )

    assert job.job_id is not None
    assert job.file_id == sample_file.file_id
    assert job.status == JobStatusEnum.PENDING
    assert job.progress_percent == 0
    assert job.result is None
    assert job.error is None


def test_create_extraction_job_with_explicit_id(db_session, sample_file):
    """Test creating an extraction job with explicit job_id."""
    explicit_job_id = uuid4()
    job = crud.create_extraction_job(
        db_session,
        file_id=sample_file.file_id,
        job_id=explicit_job_id,
    )

    assert job.job_id == explicit_job_id
    assert job.file_id == sample_file.file_id


def test_get_job(db_session, sample_job):
    """Test retrieving a job by ID."""
    job = crud.get_job(db_session, sample_job.job_id)

    assert job is not None
    assert job.job_id == sample_job.job_id
    assert job.file is not None  # Relationship loaded


def test_get_job_not_found(db_session):
    """Test retrieving non-existent job returns None."""
    job = crud.get_job(db_session, uuid4())
    assert job is None


def test_update_job_status(db_session, sample_job):
    """Test updating job status."""
    updated_job = crud.update_job_status(
        db_session,
        sample_job.job_id,
        JobStatusEnum.PROCESSING,
        current_stage="parsing",
        progress_percent=25,
    )

    assert updated_job.status == JobStatusEnum.PROCESSING
    assert updated_job.current_stage == "parsing"
    assert updated_job.progress_percent == 25


def test_update_job_status_partial(db_session, sample_job):
    """Test updating job status with only some fields."""
    updated_job = crud.update_job_status(
        db_session,
        sample_job.job_id,
        JobStatusEnum.PROCESSING,
        progress_percent=50,
    )

    assert updated_job.status == JobStatusEnum.PROCESSING
    assert updated_job.current_stage is None  # Not updated
    assert updated_job.progress_percent == 50


def test_update_job_status_not_found(db_session):
    """Test updating non-existent job raises error."""
    with pytest.raises(DatabaseError) as exc_info:
        crud.update_job_status(
            db_session,
            uuid4(),
            JobStatusEnum.PROCESSING,
        )
    assert "not found" in str(exc_info.value)


def test_complete_job(db_session, sample_job):
    """Test completing a job with results."""
    result = {
        "sheets": ["Income Statement", "Balance Sheet"],
        "line_items": [{"label": "Revenue", "value": 100}],
    }

    completed_job = crud.complete_job(
        db_session,
        sample_job.job_id,
        result=result,
        tokens_used=1500,
        cost_usd=0.045,
    )

    assert completed_job.status == JobStatusEnum.COMPLETED
    assert completed_job.progress_percent == 100
    assert completed_job.result == result
    assert completed_job.tokens_used == 1500
    assert completed_job.cost_usd == 0.045


def test_complete_job_not_found(db_session):
    """Test completing non-existent job raises error."""
    with pytest.raises(DatabaseError) as exc_info:
        crud.complete_job(
            db_session,
            uuid4(),
            result={},
            tokens_used=0,
            cost_usd=0.0,
        )
    assert "not found" in str(exc_info.value)


def test_fail_job(db_session, sample_job):
    """Test marking a job as failed."""
    error_message = "Claude API rate limit exceeded"

    failed_job = crud.fail_job(
        db_session,
        sample_job.job_id,
        error=error_message,
    )

    assert failed_job.status == JobStatusEnum.FAILED
    assert failed_job.error == error_message


def test_fail_job_truncates_long_error(db_session, sample_job):
    """Test that long error messages are truncated."""
    long_error = "x" * 3000  # Longer than 2000 character limit

    failed_job = crud.fail_job(
        db_session,
        sample_job.job_id,
        error=long_error,
    )

    assert failed_job.status == JobStatusEnum.FAILED
    assert len(failed_job.error) == 2000
    assert failed_job.error == long_error[:2000]


def test_fail_job_not_found(db_session):
    """Test failing non-existent job raises error."""
    with pytest.raises(DatabaseError) as exc_info:
        crud.fail_job(
            db_session,
            uuid4(),
            error="Some error",
        )
    assert "not found" in str(exc_info.value)


def test_list_jobs(db_session, sample_file):
    """Test listing jobs with filtering."""
    # Create multiple jobs
    job1 = crud.create_extraction_job(db_session, sample_file.file_id)
    job2 = crud.create_extraction_job(db_session, sample_file.file_id)
    job3 = crud.create_extraction_job(db_session, sample_file.file_id)

    # Update job2 to completed status
    crud.update_job_status(db_session, job2.job_id, JobStatusEnum.COMPLETED)

    # List all jobs
    all_jobs = crud.list_jobs(db_session)
    assert len(all_jobs) >= 3

    # Filter by status - pending
    pending_jobs = crud.list_jobs(db_session, status=JobStatusEnum.PENDING)
    assert len(pending_jobs) >= 2
    assert all(job.status == JobStatusEnum.PENDING for job in pending_jobs)

    # Filter by status - completed
    completed_jobs = crud.list_jobs(db_session, status=JobStatusEnum.COMPLETED)
    assert len(completed_jobs) >= 1
    assert completed_jobs[0].job_id == job2.job_id


def test_list_jobs_with_limit_offset(db_session, sample_file):
    """Test listing jobs with limit and offset."""
    # Create multiple jobs
    for _ in range(5):
        crud.create_extraction_job(db_session, sample_file.file_id)

    # Test limit
    jobs_limit_2 = crud.list_jobs(db_session, limit=2)
    assert len(jobs_limit_2) == 2

    # Test offset
    jobs_offset_2 = crud.list_jobs(db_session, offset=2, limit=2)
    assert len(jobs_offset_2) == 2
    assert jobs_offset_2[0].job_id != jobs_limit_2[0].job_id


def test_list_jobs_ordered_by_created_at(db_session, sample_file):
    """Test that jobs are ordered by created_at descending."""
    job1 = crud.create_extraction_job(db_session, sample_file.file_id)
    job2 = crud.create_extraction_job(db_session, sample_file.file_id)
    job3 = crud.create_extraction_job(db_session, sample_file.file_id)

    jobs = crud.list_jobs(db_session)

    # Most recent should be first
    assert jobs[0].job_id == job3.job_id
    assert jobs[1].job_id == job2.job_id
    assert jobs[2].job_id == job1.job_id


# ============================================================================
# LINEAGE EVENT OPERATIONS TESTS
# ============================================================================

def test_create_lineage_event(db_session, sample_job):
    """Test creating a lineage event."""
    event = crud.create_lineage_event(
        db_session,
        job_id=sample_job.job_id,
        stage_name="parsing",
        data={"sheets_found": 3, "rows_parsed": 150},
    )

    assert event.event_id is not None
    assert event.job_id == sample_job.job_id
    assert event.stage_name == "parsing"
    assert event.data["sheets_found"] == 3


def test_create_lineage_event_without_data(db_session, sample_job):
    """Test creating a lineage event without metadata."""
    event = crud.create_lineage_event(
        db_session,
        job_id=sample_job.job_id,
        stage_name="triage",
    )

    assert event.event_id is not None
    assert event.job_id == sample_job.job_id
    assert event.stage_name == "triage"
    assert event.data is None


def test_get_job_lineage(db_session, sample_job):
    """Test retrieving job lineage."""
    # Create multiple events
    event1 = crud.create_lineage_event(db_session, sample_job.job_id, "parsing", {"step": 1})
    event2 = crud.create_lineage_event(db_session, sample_job.job_id, "triage", {"step": 2})
    event3 = crud.create_lineage_event(db_session, sample_job.job_id, "mapping", {"step": 3})

    events = crud.get_job_lineage(db_session, sample_job.job_id)

    assert len(events) == 3
    # Events should be ordered by timestamp ascending
    assert events[0].stage_name == "parsing"
    assert events[1].stage_name == "triage"
    assert events[2].stage_name == "mapping"


def test_get_job_lineage_empty(db_session, sample_job):
    """Test retrieving lineage for job with no events."""
    events = crud.get_job_lineage(db_session, sample_job.job_id)
    assert len(events) == 0


# ============================================================================
# CASCADE DELETE TESTS
# ============================================================================

def test_cascade_delete_file(db_session, sample_file):
    """Test that deleting a file cascades to jobs and lineage."""
    # Create job and lineage
    job = crud.create_extraction_job(db_session, sample_file.file_id)
    event = crud.create_lineage_event(db_session, job.job_id, "parsing")

    # Verify they exist
    assert crud.get_job(db_session, job.job_id) is not None
    assert len(crud.get_job_lineage(db_session, job.job_id)) == 1

    # Delete file
    db_session.delete(sample_file)
    db_session.commit()

    # Verify job and lineage are deleted
    assert crud.get_job(db_session, job.job_id) is None
    assert len(crud.get_job_lineage(db_session, job.job_id)) == 0


def test_cascade_delete_job(db_session, sample_job):
    """Test that deleting a job cascades to lineage events."""
    # Create lineage events
    event1 = crud.create_lineage_event(db_session, sample_job.job_id, "parsing")
    event2 = crud.create_lineage_event(db_session, sample_job.job_id, "triage")

    # Verify they exist
    assert len(crud.get_job_lineage(db_session, sample_job.job_id)) == 2

    # Delete job
    db_session.delete(sample_job)
    db_session.commit()

    # Verify lineage events are deleted
    assert len(crud.get_job_lineage(db_session, sample_job.job_id)) == 0
