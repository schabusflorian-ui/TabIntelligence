"""
Unit tests for lineage tracking system.
Tests event emission, validation, persistence, and provenance queries.
"""
import pytest
import uuid
from sqlalchemy import select, text

from src.lineage import LineageTracker
from src.db.models import LineageEvent
from src.db.session import get_db_async
from src.core.exceptions import LineageError, LineageIncompleteError


@pytest.fixture(scope="module")
async def db_setup():
    """Initialize test database (placeholder for integration tests)."""
    # For unit tests, no database initialization needed
    # LineageTracker stores events in memory
    yield


@pytest.fixture
async def clean_lineage_events():
    """Clean lineage_events table (placeholder for integration tests)."""
    # For unit tests, events are stored in memory, no DB cleanup needed
    yield


@pytest.fixture
def job_id():
    """Generate test job ID."""
    return str(uuid.uuid4())


def test_lineage_tracker_initialization(job_id):
    """Test LineageTracker initializes correctly."""
    from src.lineage import LineageTracker
    tracker = LineageTracker(job_id=job_id)
    assert tracker.job_id == job_id
    assert len(tracker.events) == 0


def test_emit_stage_1_no_input(job_id):
    """Test Stage 1 emission with no input lineage."""
    from src.lineage import LineageTracker
    tracker = LineageTracker(job_id=job_id)

    output_id = tracker.emit(
        stage=1,
        event_type="parse",
        input_lineage_id=None,
        metadata={"sheets_count": 5, "tokens": 1000}
    )

    assert len(tracker.events) == 1
    assert output_id is not None


def test_validate_completeness_success(job_id):
    """Test validation passes when all stages present."""
    from src.lineage import LineageTracker
    tracker = LineageTracker(job_id=job_id)

    # Emit all 3 stages
    l1 = tracker.emit(1, "parse", None, {"tokens": 100})
    l2 = tracker.emit(2, "triage", l1, {"tokens": 100})
    tracker.emit(3, "map", l2, {"tokens": 100})

    # Should not raise
    tracker.validate_completeness(stages=[1, 2, 3])


def test_validate_completeness_fails_missing_stage(job_id):
    """Test validation fails when stage missing."""
    from src.lineage import LineageTracker
    from src.core.exceptions import LineageIncompleteError
    
    tracker = LineageTracker(job_id=job_id)

    # Only emit stage 1 and 2
    l1 = tracker.emit(1, "parse", None, {"tokens": 100})
    tracker.emit(2, "triage", l1, {"tokens": 100})

    # Validation should fail for missing stage 3
    with pytest.raises(LineageIncompleteError):
        tracker.validate_completeness(stages=[1, 2, 3])
