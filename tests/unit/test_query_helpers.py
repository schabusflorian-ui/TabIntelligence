"""
Unit tests for database query helpers.

Tests all query helper functions using sync SQLite sessions.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.db.models import (
    AuditLog,
    Entity,
    EntityPattern,
    ExtractionJob,
    File,
    JobStatusEnum,
    LineageEvent,
)
from src.db.query_helpers import (
    bulk_create_lineage_events,
    bulk_update_pattern_confidence,
    find_pattern_match,
    get_audit_log,
    get_entity_with_files,
    get_job_statistics,
    get_job_with_lineage,
    get_jobs_by_status,
    get_lineage_chain,
    get_or_create_entity,
    get_patterns_by_confidence,
    get_recent_jobs,
    validate_lineage_completeness,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def entity(db_session):
    """Create a test entity."""
    e = Entity(id=uuid4(), name="Test Corp", industry="Technology")
    db_session.add(e)
    db_session.commit()
    return e


@pytest.fixture
def file_record(db_session, entity):
    """Create a test file record."""
    f = File(
        file_id=uuid4(),
        filename="test.xlsx",
        file_size=1024,
        entity_id=entity.id,
    )
    db_session.add(f)
    db_session.commit()
    return f


@pytest.fixture
def job(db_session, file_record):
    """Create a test extraction job."""
    j = ExtractionJob(
        job_id=uuid4(),
        file_id=file_record.file_id,
        status=JobStatusEnum.COMPLETED,
        progress_percent=100,
    )
    db_session.add(j)
    db_session.commit()
    return j


@pytest.fixture
def job_with_lineage(db_session, file_record):
    """Create a job with lineage events for all 3 stages."""
    j = ExtractionJob(
        job_id=uuid4(),
        file_id=file_record.file_id,
        status=JobStatusEnum.COMPLETED,
        progress_percent=100,
    )
    db_session.add(j)
    db_session.flush()

    for stage in ["parsing", "triage", "mapping"]:
        event = LineageEvent(
            event_id=uuid4(),
            job_id=j.job_id,
            stage_name=stage,
            data={"stage": stage},
        )
        db_session.add(event)

    db_session.commit()
    return j


@pytest.fixture
def patterns(db_session, entity):
    """Create test entity patterns with varying confidence."""
    items = []
    for label, canonical, confidence in [
        ("Net Sales", "revenue", Decimal("0.9500")),
        ("Cost of Rev", "cogs", Decimal("0.8500")),
        ("Gross Margin", "gross_profit", Decimal("0.7000")),
        ("Operating Income", "ebit", Decimal("0.6000")),
    ]:
        p = EntityPattern(
            id=uuid4(),
            entity_id=entity.id,
            original_label=label,
            canonical_name=canonical,
            confidence=confidence,
            created_by="claude",
        )
        db_session.add(p)
        items.append(p)

    db_session.commit()
    return items


# ============================================================================
# ENTITY QUERIES
# ============================================================================


class TestEntityQueries:
    def test_get_entity_with_files(self, db_session, entity, patterns):
        """Should return entity with patterns eagerly loaded."""
        result = get_entity_with_files(db_session, entity.id)
        assert result is not None
        assert result.id == entity.id
        assert len(result.entity_patterns) == 4

    def test_get_entity_with_files_not_found(self, db_session):
        """Should return None for non-existent entity."""
        result = get_entity_with_files(db_session, uuid4())
        assert result is None

    def test_get_or_create_entity_creates(self, db_session):
        """Should create new entity when not found."""
        e = get_or_create_entity(db_session, "New Corp", industry="Finance")
        assert e.name == "New Corp"
        assert e.industry == "Finance"
        assert e.id is not None

    def test_get_or_create_entity_finds_existing(self, db_session, entity):
        """Should return existing entity by name."""
        e = get_or_create_entity(db_session, "Test Corp")
        assert e.id == entity.id

    def test_get_or_create_entity_no_industry(self, db_session):
        """Should create entity without industry."""
        e = get_or_create_entity(db_session, "No Industry Corp")
        assert e.name == "No Industry Corp"
        assert e.industry is None


# ============================================================================
# JOB QUERIES
# ============================================================================


class TestJobQueries:
    def test_get_job_with_lineage(self, db_session, job_with_lineage):
        """Should return job with lineage events loaded."""
        result = get_job_with_lineage(db_session, job_with_lineage.job_id)
        assert result is not None
        assert len(result.lineage_events) == 3

    def test_get_job_with_lineage_not_found(self, db_session):
        """Should return None for non-existent job."""
        result = get_job_with_lineage(db_session, uuid4())
        assert result is None

    def test_get_jobs_by_status(self, db_session, file_record):
        """Should filter jobs by status."""
        for status in [JobStatusEnum.COMPLETED, JobStatusEnum.COMPLETED, JobStatusEnum.FAILED]:
            j = ExtractionJob(
                job_id=uuid4(),
                file_id=file_record.file_id,
                status=status,
            )
            db_session.add(j)
        db_session.commit()

        completed = get_jobs_by_status(db_session, JobStatusEnum.COMPLETED)
        assert len(completed) == 2

        failed = get_jobs_by_status(db_session, JobStatusEnum.FAILED)
        assert len(failed) == 1

        pending = get_jobs_by_status(db_session, JobStatusEnum.PENDING)
        assert len(pending) == 0

    def test_get_jobs_by_status_with_limit(self, db_session, file_record):
        """Should respect limit parameter."""
        for _ in range(5):
            db_session.add(
                ExtractionJob(
                    job_id=uuid4(),
                    file_id=file_record.file_id,
                    status=JobStatusEnum.PENDING,
                )
            )
        db_session.commit()

        result = get_jobs_by_status(db_session, JobStatusEnum.PENDING, limit=3)
        assert len(result) == 3

    def test_get_recent_jobs(self, db_session, file_record):
        """Should return jobs ordered by most recent first."""
        for _ in range(5):
            db_session.add(
                ExtractionJob(
                    job_id=uuid4(),
                    file_id=file_record.file_id,
                    status=JobStatusEnum.PENDING,
                )
            )
        db_session.commit()

        result = get_recent_jobs(db_session, limit=3)
        assert len(result) == 3

    def test_get_recent_jobs_empty(self, db_session):
        """Should return empty list when no jobs exist."""
        result = get_recent_jobs(db_session)
        assert result == []


# ============================================================================
# LINEAGE QUERIES
# ============================================================================


class TestLineageQueries:
    def test_get_lineage_chain(self, db_session, job_with_lineage):
        """Should return lineage events in chronological order."""
        chain = get_lineage_chain(db_session, job_with_lineage.job_id)
        assert len(chain) == 3
        stages = [e.stage_name for e in chain]
        assert "parsing" in stages
        assert "triage" in stages
        assert "mapping" in stages

    def test_get_lineage_chain_empty(self, db_session):
        """Should return empty list for job with no lineage."""
        chain = get_lineage_chain(db_session, uuid4())
        assert chain == []

    def test_validate_lineage_completeness_complete(self, db_session, job_with_lineage):
        """Should return True when all stages present."""
        result = validate_lineage_completeness(db_session, job_with_lineage.job_id)
        assert result is True

    def test_validate_lineage_completeness_incomplete(self, db_session, file_record):
        """Should return False when stages are missing."""
        j = ExtractionJob(
            job_id=uuid4(),
            file_id=file_record.file_id,
            status=JobStatusEnum.PROCESSING,
        )
        db_session.add(j)
        db_session.flush()

        # Only add parsing event
        db_session.add(
            LineageEvent(
                event_id=uuid4(),
                job_id=j.job_id,
                stage_name="parsing",
            )
        )
        db_session.commit()

        result = validate_lineage_completeness(db_session, j.job_id)
        assert result is False

    def test_validate_lineage_completeness_custom_stages(self, db_session, job_with_lineage):
        """Should validate against custom stage list."""
        # Only require parsing and mapping (skip triage)
        result = validate_lineage_completeness(
            db_session, job_with_lineage.job_id, required_stages=["parsing", "mapping"]
        )
        assert result is True

        # Require a stage that doesn't exist
        result = validate_lineage_completeness(
            db_session, job_with_lineage.job_id, required_stages=["parsing", "validation"]
        )
        assert result is False


# ============================================================================
# PATTERN QUERIES
# ============================================================================


class TestPatternQueries:
    def test_get_patterns_by_confidence_default(self, db_session, entity, patterns):
        """Should return patterns with confidence >= 0.8."""
        result = get_patterns_by_confidence(db_session, entity.id)
        assert len(result) == 2  # 0.95 and 0.85
        assert all(p.confidence >= Decimal("0.8") for p in result)

    def test_get_patterns_by_confidence_custom_threshold(self, db_session, entity, patterns):
        """Should respect custom confidence threshold."""
        result = get_patterns_by_confidence(db_session, entity.id, min_confidence=Decimal("0.6"))
        assert len(result) == 4  # All patterns

        result = get_patterns_by_confidence(db_session, entity.id, min_confidence=Decimal("0.99"))
        assert len(result) == 0

    def test_get_patterns_ordered_by_confidence(self, db_session, entity, patterns):
        """Should return patterns ordered by confidence descending."""
        result = get_patterns_by_confidence(db_session, entity.id, min_confidence=Decimal("0.5"))
        confidences = [p.confidence for p in result]
        assert confidences == sorted(confidences, reverse=True)

    def test_find_pattern_match_found(self, db_session, entity, patterns):
        """Should find matching pattern by label."""
        result = find_pattern_match(db_session, "Net Sales")
        assert result is not None
        assert result.canonical_name == "revenue"

    def test_find_pattern_match_not_found(self, db_session):
        """Should return None when no pattern matches."""
        result = find_pattern_match(db_session, "Nonexistent Label")
        assert result is None

    def test_find_pattern_match_scoped_to_entity(self, db_session, entity, patterns):
        """Should scope search to specific entity."""
        result = find_pattern_match(db_session, "Net Sales", entity_id=entity.id)
        assert result is not None

        result = find_pattern_match(db_session, "Net Sales", entity_id=uuid4())
        assert result is None


# ============================================================================
# BATCH OPERATIONS
# ============================================================================


class TestBatchOperations:
    def test_bulk_create_lineage_events(self, db_session, job):
        """Should bulk insert multiple lineage events."""
        events = [
            {
                "event_id": uuid4(),
                "job_id": job.job_id,
                "stage_name": "parsing",
                "data": {"rows": 100},
            },
            {
                "event_id": uuid4(),
                "job_id": job.job_id,
                "stage_name": "triage",
                "data": {"sheets": 3},
            },
        ]
        bulk_create_lineage_events(db_session, events)

        chain = get_lineage_chain(db_session, job.job_id)
        assert len(chain) == 2

    def test_bulk_create_lineage_events_empty(self, db_session):
        """Should handle empty event list gracefully."""
        bulk_create_lineage_events(db_session, [])
        # No error raised

    def test_bulk_update_pattern_confidence(self, db_session, entity, patterns):
        """Should update confidence scores for multiple patterns."""
        updates = [
            {"pattern_id": patterns[0].id, "new_confidence": Decimal("0.9900")},
            {"pattern_id": patterns[1].id, "new_confidence": Decimal("0.9000")},
        ]
        count = bulk_update_pattern_confidence(db_session, updates)
        assert count == 2

        # Verify updates persisted
        db_session.expire_all()
        updated = get_patterns_by_confidence(db_session, entity.id, min_confidence=Decimal("0.9"))
        assert len(updated) >= 2

    def test_bulk_update_pattern_confidence_empty(self, db_session):
        """Should handle empty update list."""
        count = bulk_update_pattern_confidence(db_session, [])
        assert count == 0


# ============================================================================
# AUDIT QUERIES
# ============================================================================


class TestAuditQueries:
    @pytest.fixture
    def audit_entries(self, db_session):
        """Create sample audit log entries."""
        resource_id = uuid4()
        entries = [
            AuditLog(
                action="upload",
                resource_type="file",
                resource_id=resource_id,
                ip_address="192.168.1.1",
                status_code=200,
            ),
            AuditLog(
                action="view",
                resource_type="job",
                resource_id=uuid4(),
                ip_address="192.168.1.2",
                status_code=200,
            ),
            AuditLog(
                action="upload",
                resource_type="file",
                resource_id=uuid4(),
                ip_address="10.0.0.1",
                status_code=200,
            ),
            AuditLog(
                action="revoke_key",
                resource_type="api_key",
                resource_id=uuid4(),
                ip_address="10.0.0.1",
                status_code=200,
            ),
        ]
        for entry in entries:
            db_session.add(entry)
        db_session.commit()
        return entries, resource_id

    def test_get_audit_log_all(self, db_session, audit_entries):
        """Should return all audit logs."""
        entries, _ = audit_entries
        result = get_audit_log(db_session)
        assert len(result) == 4

    def test_get_audit_log_by_action(self, db_session, audit_entries):
        """Should filter by action."""
        result = get_audit_log(db_session, action="upload")
        assert len(result) == 2
        assert all(e.action == "upload" for e in result)

    def test_get_audit_log_by_resource_type(self, db_session, audit_entries):
        """Should filter by resource type."""
        result = get_audit_log(db_session, resource_type="file")
        assert len(result) == 2

    def test_get_audit_log_by_resource_id(self, db_session, audit_entries):
        """Should filter by specific resource ID."""
        _, resource_id = audit_entries
        result = get_audit_log(db_session, resource_id=resource_id)
        assert len(result) == 1
        assert result[0].resource_id == resource_id

    def test_get_audit_log_combined_filters(self, db_session, audit_entries):
        """Should combine multiple filters."""
        result = get_audit_log(db_session, action="upload", resource_type="file")
        assert len(result) == 2

    def test_get_audit_log_with_limit(self, db_session, audit_entries):
        """Should respect limit parameter."""
        result = get_audit_log(db_session, limit=2)
        assert len(result) == 2

    def test_get_audit_log_empty(self, db_session):
        """Should return empty list when no matches."""
        result = get_audit_log(db_session, action="nonexistent")
        assert result == []


# ============================================================================
# STATISTICS
# ============================================================================


class TestStatistics:
    def test_get_job_statistics_empty(self, db_session):
        """Should return zero counts when no jobs exist."""
        stats = get_job_statistics(db_session)
        assert stats["total"] == 0
        assert stats["pending"] == 0
        assert stats["completed"] == 0

    def test_get_job_statistics(self, db_session, file_record):
        """Should return correct counts by status."""
        for status in [
            JobStatusEnum.PENDING,
            JobStatusEnum.PROCESSING,
            JobStatusEnum.COMPLETED,
            JobStatusEnum.COMPLETED,
            JobStatusEnum.FAILED,
        ]:
            db_session.add(
                ExtractionJob(
                    job_id=uuid4(),
                    file_id=file_record.file_id,
                    status=status,
                )
            )
        db_session.commit()

        stats = get_job_statistics(db_session)
        assert stats["pending"] == 1
        assert stats["processing"] == 1
        assert stats["completed"] == 2
        assert stats["failed"] == 1
        assert stats["total"] == 5
