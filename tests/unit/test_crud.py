"""
Unit tests for database CRUD operations.

Tests all CRUD operations for File, ExtractionJob, and LineageEvent models.
Also tests LearnedAlias lifecycle: last_seen_at, archival, and taxonomy persistence.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.core.exceptions import DatabaseError
from src.db import crud
from src.db.models import JobStatusEnum

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


def test_complete_job_with_taxonomy_tracking(db_session, sample_job):
    """Test completing a job with taxonomy version and checksum persisted."""
    result = {
        "sheets": ["Income Statement"],
        "line_items": [{"label": "Revenue", "value": 100}],
    }

    completed_job = crud.complete_job(
        db_session,
        sample_job.job_id,
        result=result,
        tokens_used=800,
        cost_usd=0.02,
        taxonomy_version="3.0.0",
        taxonomy_checksum="abc123def456" * 4,  # 48-char hex string
    )

    assert completed_job.taxonomy_version == "3.0.0"
    assert completed_job.taxonomy_checksum == "abc123def456" * 4

    # Verify persistence by re-querying
    refreshed_job = crud.get_job(db_session, sample_job.job_id)
    assert refreshed_job.taxonomy_version == "3.0.0"
    assert refreshed_job.taxonomy_checksum == "abc123def456" * 4


def test_extraction_job_taxonomy_fields_default_null(db_session, sample_file):
    """Test that taxonomy fields are None by default on new jobs."""
    job = crud.create_extraction_job(
        db_session,
        file_id=sample_file.file_id,
    )

    assert job.taxonomy_version is None
    assert job.taxonomy_checksum is None


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
    crud.create_extraction_job(db_session, sample_file.file_id)
    job2 = crud.create_extraction_job(db_session, sample_file.file_id)
    crud.create_extraction_job(db_session, sample_file.file_id)

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
    crud.create_lineage_event(db_session, sample_job.job_id, "parsing", {"step": 1})
    crud.create_lineage_event(db_session, sample_job.job_id, "triage", {"step": 2})
    crud.create_lineage_event(db_session, sample_job.job_id, "mapping", {"step": 3})

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
    crud.create_lineage_event(db_session, job.job_id, "parsing")

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
    crud.create_lineage_event(db_session, sample_job.job_id, "parsing")
    crud.create_lineage_event(db_session, sample_job.job_id, "triage")

    # Verify they exist
    assert len(crud.get_job_lineage(db_session, sample_job.job_id)) == 2

    # Delete job
    db_session.delete(sample_job)
    db_session.commit()

    # Verify lineage events are deleted
    assert len(crud.get_job_lineage(db_session, sample_job.job_id)) == 0


# ============================================================================
# LEARNED ALIAS LIFECYCLE TESTS (Agent 2B)
# ============================================================================


class TestLearnedAliasLifecycle:
    """Test learned alias lifecycle: last_seen_at tracking, archival, and taxonomy persistence."""

    def test_last_seen_at_set_on_create(self, db_session):
        """Recording a new alias sets last_seen_at to approximately now."""
        alias = crud.record_learned_alias(db_session, "revenue", "Net Revenue", "entity-1")
        assert alias.last_seen_at is not None
        # Should be within the last few seconds
        delta = datetime.now(timezone.utc) - alias.last_seen_at.replace(tzinfo=timezone.utc)
        assert delta.total_seconds() < 5

    def test_last_seen_at_updated_on_reoccurrence(self, db_session):
        """Recording the same alias again updates last_seen_at."""
        alias1 = crud.record_learned_alias(db_session, "revenue", "Net Revenue", "entity-1")
        first_seen = alias1.last_seen_at

        # Record again (same canonical + alias text)
        alias2 = crud.record_learned_alias(db_session, "revenue", "Net Revenue", "entity-2")
        assert alias2.last_seen_at is not None
        assert alias2.last_seen_at >= first_seen
        assert alias2.occurrence_count == 2

    def test_archived_defaults_to_false(self, db_session):
        """New aliases have archived=False by default."""
        alias = crud.record_learned_alias(db_session, "revenue", "Total Sales", "entity-1")
        assert alias.archived is False
        assert alias.archived_reason is None

    def test_archive_stale_aliases_archives_old(self, db_session):
        """Aliases with last_seen_at older than stale_days get archived."""
        from src.db.models import LearnedAlias

        # Create an alias and manually set last_seen_at to 200 days ago
        alias = crud.record_learned_alias(db_session, "revenue", "Old Revenue", "entity-1")
        alias.last_seen_at = datetime.now(timezone.utc) - timedelta(days=200)
        db_session.commit()

        archived_count = crud.archive_stale_aliases(db_session, stale_days=180)
        assert archived_count == 1

        db_session.refresh(alias)
        assert alias.archived is True
        assert alias.archived_reason == "stale_180d"

    def test_archive_stale_aliases_skips_recent(self, db_session):
        """Aliases seen recently are not archived."""
        alias = crud.record_learned_alias(db_session, "revenue", "Fresh Revenue", "entity-1")
        # last_seen_at is set to now by record_learned_alias

        archived_count = crud.archive_stale_aliases(db_session, stale_days=180)
        assert archived_count == 0

        db_session.refresh(alias)
        assert alias.archived is False

    def test_archive_stale_aliases_skips_promoted(self, db_session):
        """Promoted aliases are not archived regardless of age."""
        alias = crud.record_learned_alias(db_session, "revenue", "Promoted Revenue", "entity-1")
        alias.promoted = True
        alias.last_seen_at = datetime.now(timezone.utc) - timedelta(days=365)
        db_session.commit()

        archived_count = crud.archive_stale_aliases(db_session, stale_days=180)
        assert archived_count == 0

        db_session.refresh(alias)
        assert alias.archived is False

    def test_archive_stale_aliases_skips_already_archived(self, db_session):
        """Already-archived aliases are not re-archived."""
        alias = crud.record_learned_alias(db_session, "revenue", "Old Revenue", "entity-1")
        alias.last_seen_at = datetime.now(timezone.utc) - timedelta(days=365)
        alias.archived = True
        alias.archived_reason = "stale_180d"
        db_session.commit()

        archived_count = crud.archive_stale_aliases(db_session, stale_days=180)
        assert archived_count == 0

    def test_archive_stale_with_null_last_seen_at(self, db_session):
        """Aliases with last_seen_at=None are treated as stale."""
        alias = crud.record_learned_alias(db_session, "revenue", "Null Seen", "entity-1")
        # Manually set last_seen_at to None to simulate old data
        alias.last_seen_at = None
        db_session.commit()

        archived_count = crud.archive_stale_aliases(db_session, stale_days=180)
        assert archived_count == 1

        db_session.refresh(alias)
        assert alias.archived is True

    def test_persist_promoted_to_taxonomy_adds_alias(self, db_session):
        """Promoted alias text is added to Taxonomy.aliases JSON column."""
        from src.db.models import Taxonomy

        # Create a taxonomy entry
        taxonomy = Taxonomy(
            canonical_name="revenue",
            category="income_statement",
            aliases=["sales", "turnover"],
        )
        db_session.add(taxonomy)
        db_session.commit()

        # Create a promoted alias
        alias = crud.record_learned_alias(db_session, "revenue", "Total Net Sales", "entity-1")
        alias.promoted = True
        db_session.commit()

        added = crud.persist_promoted_to_taxonomy(db_session)
        assert added == 1

        db_session.refresh(taxonomy)
        assert "Total Net Sales" in taxonomy.aliases
        # Original aliases still present
        assert "sales" in taxonomy.aliases
        assert "turnover" in taxonomy.aliases

    def test_persist_promoted_idempotent(self, db_session):
        """If alias text already in Taxonomy.aliases, it is not duplicated."""
        from src.db.models import Taxonomy

        taxonomy = Taxonomy(
            canonical_name="revenue",
            category="income_statement",
            aliases=["sales", "Total Net Sales"],
        )
        db_session.add(taxonomy)
        db_session.commit()

        alias = crud.record_learned_alias(db_session, "revenue", "Total Net Sales", "entity-1")
        alias.promoted = True
        db_session.commit()

        added = crud.persist_promoted_to_taxonomy(db_session)
        assert added == 0

        db_session.refresh(taxonomy)
        assert taxonomy.aliases.count("Total Net Sales") == 1

    def test_persist_promoted_no_taxonomy_match(self, db_session):
        """Promoted alias for nonexistent taxonomy entry is silently skipped."""
        alias = crud.record_learned_alias(
            db_session, "revenue", "Orphan Alias", "entity-1"
        )
        alias.promoted = True
        db_session.commit()

        added = crud.persist_promoted_to_taxonomy(db_session)
        assert added == 0

    def test_persist_promoted_null_aliases(self, db_session):
        """Taxonomy with aliases=None gets alias list initialized."""
        from src.db.models import Taxonomy

        taxonomy = Taxonomy(
            canonical_name="revenue",
            category="income_statement",
            aliases=None,
        )
        db_session.add(taxonomy)
        db_session.commit()

        alias = crud.record_learned_alias(db_session, "revenue", "New Alias", "entity-1")
        alias.promoted = True
        db_session.commit()

        added = crud.persist_promoted_to_taxonomy(db_session)
        assert added == 1

        db_session.refresh(taxonomy)
        assert taxonomy.aliases == ["New Alias"]

    def test_check_auto_promotions_excludes_archived(self, db_session):
        """Archived aliases are excluded from auto-promotion candidates."""
        from unittest.mock import patch

        # Create alias meeting promotion thresholds
        alias = crud.record_learned_alias(db_session, "revenue", "Archived Revenue", "e1")
        for i in range(2, 6):
            crud.record_learned_alias(db_session, "revenue", "Archived Revenue", f"e{i}")

        # Mark as archived
        alias = (
            db_session.query(crud.LearnedAlias)
            .filter(crud.LearnedAlias.alias_text == "Archived Revenue")
            .first()
        )
        alias.archived = True
        alias.archived_reason = "stale_180d"
        db_session.commit()

        with patch("src.db.crud.archive_stale_aliases"):
            promoted_count = crud.check_auto_promotions(db_session)

        assert promoted_count == 0
        db_session.refresh(alias)
        assert alias.promoted is False

    def test_backward_compat_record_learned_alias(self, db_session):
        """Existing record_learned_alias calls still work (backward compat)."""
        alias = crud.record_learned_alias(db_session, "revenue", "Net Sales", "entity-1")
        assert alias is not None
        assert alias.canonical_name == "revenue"
        assert alias.alias_text == "Net Sales"
        assert alias.occurrence_count == 1
        assert alias.source_entities == ["entity-1"]
        assert alias.promoted is False
        # New fields are populated with sensible defaults
        assert alias.last_seen_at is not None
        assert alias.archived is False
        assert alias.archived_reason is None

    def test_backward_compat_get_learned_aliases(self, db_session):
        """Existing get_learned_aliases still returns all aliases including new fields."""
        crud.record_learned_alias(db_session, "revenue", "Net Sales", "entity-1")
        aliases = crud.get_learned_aliases(db_session)
        assert len(aliases) == 1
        assert aliases[0].alias_text == "Net Sales"
        # Verify new fields are accessible
        assert hasattr(aliases[0], "last_seen_at")
        assert hasattr(aliases[0], "archived")
        assert hasattr(aliases[0], "archived_reason")
