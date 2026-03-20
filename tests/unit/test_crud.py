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


# ============================================================================
# TAXONOMY SUGGESTION TESTS
# ============================================================================


class TestTaxonomySuggestions:
    """Tests for taxonomy suggestion CRUD operations."""

    def test_generate_taxonomy_suggestions_creates_from_unmapped(self, db_session):
        """Seed UnmappedLabelAggregate rows with high occurrence, call generate, verify suggestions created."""
        from src.db.models import Taxonomy, UnmappedLabelAggregate

        # Seed taxonomy
        db_session.add(
            Taxonomy(
                canonical_name="revenue",
                category="income_statement",
                display_name="Revenue",
                aliases=["Sales"],
            )
        )

        # Seed unmapped labels with high occurrence
        db_session.add(
            UnmappedLabelAggregate(
                label_normalized="special income item",
                original_labels=["Special Income Item"],
                occurrence_count=5,
                sheet_names=["IS"],
            )
        )
        db_session.add(
            UnmappedLabelAggregate(
                label_normalized="other charges",
                original_labels=["Other Charges"],
                occurrence_count=4,
                sheet_names=["IS"],
            )
        )
        db_session.commit()

        suggestions = crud.generate_taxonomy_suggestions(db_session, min_occurrences=3)
        assert len(suggestions) == 2
        texts = {s.suggested_text for s in suggestions}
        assert "special income item" in texts
        assert "other charges" in texts
        # Both should be new_item (no close match to "revenue")
        for s in suggestions:
            assert s.suggestion_type == "new_item"
            assert s.status == "pending"

    def test_generate_taxonomy_suggestions_detects_close_alias(self, db_session):
        """When unmapped label closely matches a canonical_name, suggest as new_alias."""
        from src.db.models import Taxonomy, UnmappedLabelAggregate

        db_session.add(
            Taxonomy(
                canonical_name="total_revenue",
                category="income_statement",
                display_name="Total Revenue",
                aliases=[],
            )
        )
        # This label differs from "total_revenue" only by spaces vs underscores
        db_session.add(
            UnmappedLabelAggregate(
                label_normalized="total revenue",
                original_labels=["Total Revenue"],
                occurrence_count=10,
                sheet_names=["IS"],
            )
        )
        db_session.commit()

        suggestions = crud.generate_taxonomy_suggestions(db_session, min_occurrences=3)
        assert len(suggestions) == 1
        assert suggestions[0].suggestion_type == "new_alias"
        assert suggestions[0].canonical_name == "total_revenue"

    def test_generate_taxonomy_suggestions_skips_existing(self, db_session):
        """Calling generate twice should not create duplicate suggestions."""
        from src.db.models import Taxonomy, UnmappedLabelAggregate

        db_session.add(
            Taxonomy(
                canonical_name="revenue",
                category="income_statement",
                display_name="Revenue",
                aliases=[],
            )
        )
        db_session.add(
            UnmappedLabelAggregate(
                label_normalized="special item",
                original_labels=["Special Item"],
                occurrence_count=5,
                sheet_names=["IS"],
            )
        )
        db_session.commit()

        first = crud.generate_taxonomy_suggestions(db_session, min_occurrences=3)
        assert len(first) == 1

        second = crud.generate_taxonomy_suggestions(db_session, min_occurrences=3)
        assert len(second) == 0

    def test_accept_suggestion_new_alias(self, db_session):
        """Accepting a new_alias suggestion adds alias to Taxonomy and updates status."""
        from src.db.models import Taxonomy, TaxonomySuggestion

        tax = Taxonomy(
            canonical_name="revenue",
            category="income_statement",
            display_name="Revenue",
            aliases=["Sales"],
        )
        db_session.add(tax)

        suggestion = TaxonomySuggestion(
            suggestion_type="new_alias",
            canonical_name="revenue",
            suggested_text="net turnover",
            evidence_count=5,
            status="pending",
        )
        db_session.add(suggestion)
        db_session.commit()
        db_session.refresh(suggestion)

        result = crud.accept_taxonomy_suggestion(db_session, suggestion.id)
        assert result.status == "accepted"
        assert result.resolved_at is not None
        assert result.resolved_by == "api"

        # Verify alias was added to taxonomy
        db_session.refresh(tax)
        assert "net turnover" in tax.aliases

    def test_reject_suggestion(self, db_session):
        """Rejecting a suggestion updates status without modifying taxonomy."""
        from src.db.models import TaxonomySuggestion

        suggestion = TaxonomySuggestion(
            suggestion_type="new_item",
            canonical_name=None,
            suggested_text="mysterious item",
            evidence_count=3,
            status="pending",
        )
        db_session.add(suggestion)
        db_session.commit()
        db_session.refresh(suggestion)

        result = crud.reject_taxonomy_suggestion(db_session, suggestion.id)
        assert result.status == "rejected"
        assert result.resolved_at is not None
        assert result.resolved_by == "api"

    def test_suggestions_below_threshold_ignored(self, db_session):
        """UnmappedLabelAggregate rows with low occurrence_count are not turned into suggestions."""
        from src.db.models import Taxonomy, UnmappedLabelAggregate

        db_session.add(
            Taxonomy(
                canonical_name="revenue",
                category="income_statement",
                display_name="Revenue",
                aliases=[],
            )
        )
        db_session.add(
            UnmappedLabelAggregate(
                label_normalized="rare item",
                original_labels=["Rare Item"],
                occurrence_count=1,
                sheet_names=["IS"],
            )
        )
        db_session.commit()

        suggestions = crud.generate_taxonomy_suggestions(db_session, min_occurrences=3)
        assert len(suggestions) == 0

    def test_generate_taxonomy_suggestions_fuzzy_match(self, db_session):
        """Fuzzy matching detects labels similar to canonical names (minor typos, reordering)."""
        from src.db.models import Taxonomy, UnmappedLabelAggregate

        db_session.add(
            Taxonomy(
                canonical_name="net_income",
                category="income_statement",
                display_name="Net Income",
                aliases=["net profit", "bottom line"],
            )
        )
        # "net incme" has a typo (missing 'o') — should still match with fuzzy
        db_session.add(
            UnmappedLabelAggregate(
                label_normalized="net incme",
                original_labels=["Net Incme"],
                occurrence_count=5,
                sheet_names=["IS"],
            )
        )
        db_session.commit()

        suggestions = crud.generate_taxonomy_suggestions(db_session, min_occurrences=3)
        assert len(suggestions) == 1
        assert suggestions[0].suggestion_type == "new_alias"
        assert suggestions[0].canonical_name == "net_income"

    def test_generate_taxonomy_suggestions_alias_match(self, db_session):
        """Fuzzy matching also checks taxonomy aliases, not just canonical names."""
        from src.db.models import Taxonomy, UnmappedLabelAggregate

        db_session.add(
            Taxonomy(
                canonical_name="accounts_receivable",
                category="balance_sheet",
                display_name="Accounts Receivable",
                aliases=["trade receivables", "A/R", "accts receivable"],
            )
        )
        # "trade receivable" (missing 's') should match alias "trade receivables"
        db_session.add(
            UnmappedLabelAggregate(
                label_normalized="trade receivable",
                original_labels=["Trade Receivable"],
                occurrence_count=4,
                sheet_names=["BS"],
            )
        )
        db_session.commit()

        suggestions = crud.generate_taxonomy_suggestions(db_session, min_occurrences=3)
        assert len(suggestions) == 1
        assert suggestions[0].suggestion_type == "new_alias"
        assert suggestions[0].canonical_name == "accounts_receivable"

    def test_accept_nonexistent_raises(self, db_session):
        """Accepting a nonexistent suggestion raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            crud.accept_taxonomy_suggestion(db_session, uuid4())

    def test_reject_already_accepted_raises(self, db_session):
        """Rejecting an already-accepted suggestion raises ValueError."""
        from src.db.models import TaxonomySuggestion

        suggestion = TaxonomySuggestion(
            suggestion_type="new_item",
            canonical_name=None,
            suggested_text="some item",
            evidence_count=3,
            status="accepted",
        )
        db_session.add(suggestion)
        db_session.commit()
        db_session.refresh(suggestion)

        with pytest.raises(ValueError, match="not pending"):
            crud.reject_taxonomy_suggestion(db_session, suggestion.id)

    def test_list_taxonomy_suggestions_filters_by_status(self, db_session):
        """list_taxonomy_suggestions with status filter returns only matching."""
        from src.db.models import TaxonomySuggestion

        db_session.add(
            TaxonomySuggestion(
                suggestion_type="new_item",
                suggested_text="item1",
                evidence_count=3,
                status="pending",
            )
        )
        db_session.add(
            TaxonomySuggestion(
                suggestion_type="new_item",
                suggested_text="item2",
                evidence_count=4,
                status="accepted",
            )
        )
        db_session.commit()

        pending = crud.list_taxonomy_suggestions(db_session, status="pending")
        assert len(pending) == 1
        assert pending[0].suggested_text == "item1"

        all_suggestions = crud.list_taxonomy_suggestions(db_session)
        assert len(all_suggestions) == 2


# ============================================================================
# TAXONOMY SUGGESTION API TESTS
# ============================================================================


class TestTaxonomySuggestionsAPI:
    """API-level tests for taxonomy suggestion endpoints."""

    def test_get_suggestions_returns_list(self, test_client_with_db, test_db):
        """GET /api/v1/taxonomy/suggestions returns a list of suggestions."""
        from src.db.models import TaxonomySuggestion

        db = test_db()
        db.add(
            TaxonomySuggestion(
                suggestion_type="new_item",
                suggested_text="test label",
                evidence_count=5,
                status="pending",
            )
        )
        db.commit()
        db.close()

        resp = test_client_with_db.get("/api/v1/taxonomy/suggestions")
        assert resp.status_code == 200
        body = resp.json()
        assert "count" in body
        assert "suggestions" in body
        assert body["count"] >= 1

    def test_get_suggestions_filter_by_status(self, test_client_with_db, test_db):
        """GET /api/v1/taxonomy/suggestions?status=pending filters correctly."""
        from src.db.models import TaxonomySuggestion

        db = test_db()
        db.add(
            TaxonomySuggestion(
                suggestion_type="new_item",
                suggested_text="pending item",
                evidence_count=3,
                status="pending",
            )
        )
        db.add(
            TaxonomySuggestion(
                suggestion_type="new_item",
                suggested_text="accepted item",
                evidence_count=4,
                status="accepted",
            )
        )
        db.commit()
        db.close()

        resp = test_client_with_db.get("/api/v1/taxonomy/suggestions?status=pending")
        assert resp.status_code == 200
        body = resp.json()
        for s in body["suggestions"]:
            assert s["status"] == "pending"

    def test_accept_suggestion_endpoint(self, test_client_with_db, test_db):
        """POST /api/v1/taxonomy/suggestions/{id}/accept works."""
        from src.db.models import TaxonomySuggestion

        db = test_db()
        suggestion = TaxonomySuggestion(
            suggestion_type="new_item",
            suggested_text="accept me",
            evidence_count=5,
            status="pending",
        )
        db.add(suggestion)
        db.commit()
        db.refresh(suggestion)
        sid = str(suggestion.id)
        db.close()

        resp = test_client_with_db.post(f"/api/v1/taxonomy/suggestions/{sid}/accept")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    def test_reject_suggestion_endpoint(self, test_client_with_db, test_db):
        """POST /api/v1/taxonomy/suggestions/{id}/reject works."""
        from src.db.models import TaxonomySuggestion

        db = test_db()
        suggestion = TaxonomySuggestion(
            suggestion_type="new_item",
            suggested_text="reject me",
            evidence_count=3,
            status="pending",
        )
        db.add(suggestion)
        db.commit()
        db.refresh(suggestion)
        sid = str(suggestion.id)
        db.close()

        resp = test_client_with_db.post(f"/api/v1/taxonomy/suggestions/{sid}/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_accept_nonexistent_returns_400(self, test_client_with_db):
        """POST accept on nonexistent suggestion returns 400."""
        fake_id = str(uuid4())
        resp = test_client_with_db.post(f"/api/v1/taxonomy/suggestions/{fake_id}/accept")
        assert resp.status_code == 400


# ============================================================================
# TAXONOMY GOVERNANCE (DEPRECATION & CHANGELOG) TESTS
# ============================================================================


class TestTaxonomyGovernance:
    """Tests for taxonomy deprecation and changelog CRUD operations."""

    def _seed_taxonomy(self, db_session, canonical_name="revenue", category="income_statement"):
        """Helper to seed a taxonomy item."""
        from src.db.models import Taxonomy

        item = Taxonomy(
            canonical_name=canonical_name,
            category=category,
            display_name=canonical_name.replace("_", " ").title(),
            aliases=[],
        )
        db_session.add(item)
        db_session.commit()
        return item

    def test_deprecate_taxonomy_item(self, db_session):
        """Deprecate an item, verify fields are set."""
        self._seed_taxonomy(db_session, "old_revenue")

        result = crud.deprecate_taxonomy_item(db_session, "old_revenue")

        assert result.deprecated is True
        assert result.deprecated_at is not None
        assert result.deprecated_redirect is None

    def test_deprecate_with_redirect(self, db_session):
        """Deprecate with redirect, verify both fields."""
        self._seed_taxonomy(db_session, "old_metric")
        self._seed_taxonomy(db_session, "new_metric", category="metrics")

        result = crud.deprecate_taxonomy_item(
            db_session, "old_metric", redirect_to="new_metric"
        )

        assert result.deprecated is True
        assert result.deprecated_redirect == "new_metric"
        assert result.deprecated_at is not None

    def test_deprecate_nonexistent_raises(self, db_session):
        """ValueError for missing item."""
        with pytest.raises(ValueError, match="not found"):
            crud.deprecate_taxonomy_item(db_session, "nonexistent_item")

    def test_deprecate_redirect_to_deprecated_raises(self, db_session):
        """Cannot redirect to a deprecated item."""
        self._seed_taxonomy(db_session, "item_a")
        self._seed_taxonomy(db_session, "item_b")

        # First deprecate item_b
        crud.deprecate_taxonomy_item(db_session, "item_b")

        # Now try to deprecate item_a with redirect to deprecated item_b
        with pytest.raises(ValueError, match="Cannot redirect to deprecated"):
            crud.deprecate_taxonomy_item(
                db_session, "item_a", redirect_to="item_b"
            )

    def test_record_taxonomy_change(self, db_session):
        """Create a changelog entry, verify fields."""
        entry = crud.record_taxonomy_change(
            db_session,
            canonical_name="revenue",
            field_name="display_name",
            old_value="Revenue",
            new_value="Total Revenue",
            changed_by="admin",
            taxonomy_version="3.1.0",
        )

        assert entry.id is not None
        assert entry.canonical_name == "revenue"
        assert entry.field_name == "display_name"
        assert entry.old_value == "Revenue"
        assert entry.new_value == "Total Revenue"
        assert entry.changed_by == "admin"
        assert entry.taxonomy_version == "3.1.0"
        assert entry.created_at is not None

    def test_get_taxonomy_changelog_filtered(self, db_session):
        """Filter changelog by canonical_name."""
        crud.record_taxonomy_change(
            db_session, "revenue", "display_name", "A", "B", "admin"
        )
        crud.record_taxonomy_change(
            db_session, "cogs", "display_name", "X", "Y", "admin"
        )
        crud.record_taxonomy_change(
            db_session, "revenue", "aliases", "[]", '["Sales"]', "admin"
        )

        entries = crud.get_taxonomy_changelog(db_session, canonical_name="revenue")
        assert len(entries) == 2
        assert all(e.canonical_name == "revenue" for e in entries)

    def test_get_taxonomy_changelog_all(self, db_session):
        """Get all changelog entries without filter."""
        crud.record_taxonomy_change(
            db_session, "revenue", "display_name", "A", "B", "admin"
        )
        crud.record_taxonomy_change(
            db_session, "cogs", "display_name", "X", "Y", "admin"
        )

        entries = crud.get_taxonomy_changelog(db_session)
        assert len(entries) == 2

    def test_deprecate_creates_changelog_entries(self, db_session):
        """Deprecating an item also creates changelog entries."""
        self._seed_taxonomy(db_session, "old_item")
        self._seed_taxonomy(db_session, "new_item")

        crud.deprecate_taxonomy_item(
            db_session, "old_item", redirect_to="new_item", deprecated_by="admin"
        )

        entries = crud.get_taxonomy_changelog(db_session, canonical_name="old_item")
        assert len(entries) >= 2
        field_names = {e.field_name for e in entries}
        assert "deprecated" in field_names
        assert "deprecated_redirect" in field_names

    def test_deprecated_excluded_from_prompt(self, db_session):
        """Verify format_taxonomy_for_prompt skips deprecated items."""
        # format_taxonomy_for_prompt uses JSON taxonomy, not DB.
        # To test deprecation filtering, we test with a dict-based approach.
        # We'll mock load_taxonomy_json to return items with deprecated flag.
        from unittest.mock import patch

        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        fake_data = {
            "categories": {
                "income_statement": [
                    {
                        "canonical_name": "revenue",
                        "display_name": "Revenue",
                        "aliases": ["Sales"],
                    },
                    {
                        "canonical_name": "old_metric",
                        "display_name": "Old Metric",
                        "aliases": [],
                        "deprecated": True,
                    },
                ]
            }
        }

        with patch("src.extraction.taxonomy_loader.load_taxonomy_json", return_value=fake_data):
            result = format_taxonomy_for_prompt(include_aliases=True, include_learned=False)

        assert "revenue" in result
        assert "old_metric" not in result


class TestTaxonomyGovernanceAPI:
    """API tests for taxonomy deprecation and changelog endpoints."""

    def test_deprecate_endpoint(self, test_client_with_db, db_session):
        """POST /{canonical_name}/deprecate deprecates the item."""
        from src.db.models import Taxonomy

        db = db_session
        db.add(
            Taxonomy(
                canonical_name="api_deprecate_test",
                category="income_statement",
                display_name="API Test",
                aliases=[],
            )
        )
        db.commit()
        db.close()

        resp = test_client_with_db.post(
            "/api/v1/taxonomy/api_deprecate_test/deprecate"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["deprecated"] is True
        assert data["canonical_name"] == "api_deprecate_test"

    def test_deprecate_nonexistent_returns_400(self, test_client_with_db):
        """POST deprecate on nonexistent item returns 400."""
        resp = test_client_with_db.post(
            "/api/v1/taxonomy/does_not_exist/deprecate"
        )
        assert resp.status_code == 400

    def test_changelog_endpoint_empty(self, test_client_with_db):
        """GET /changelog with no entries returns empty list."""
        resp = test_client_with_db.get("/api/v1/taxonomy/changelog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["entries"] == []

    def test_changelog_endpoint_with_entries(self, test_client_with_db, db_session):
        """GET /changelog returns recorded entries."""
        crud.record_taxonomy_change(
            db_session, "revenue", "display_name", "Rev", "Revenue", "test"
        )
        db_session.close()

        resp = test_client_with_db.get("/api/v1/taxonomy/changelog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["entries"][0]["canonical_name"] == "revenue"
        assert data["entries"][0]["field_name"] == "display_name"

    def test_changelog_endpoint_filtered(self, test_client_with_db, db_session):
        """GET /changelog?canonical_name=X filters correctly."""
        crud.record_taxonomy_change(
            db_session, "revenue", "display_name", "A", "B", "test"
        )
        crud.record_taxonomy_change(
            db_session, "cogs", "display_name", "X", "Y", "test"
        )
        db_session.close()

        resp = test_client_with_db.get(
            "/api/v1/taxonomy/changelog?canonical_name=revenue"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["entries"][0]["canonical_name"] == "revenue"
