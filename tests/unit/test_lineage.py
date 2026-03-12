"""
Unit tests for lineage tracking system.
Tests event emission, validation, chain integrity, summary, and persistence.

Tests the actual LineageTracker in src/lineage/tracker.py which uses:
- In-memory event storage (List[Dict])
- Synchronous save_to_db() via src.db CRUD
- validate_completeness() raising LineageIncompleteError
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.core.exceptions import LineageError, LineageIncompleteError
from src.lineage.tracker import LineageTracker


@pytest.fixture
def job_id():
    """Generate test job ID."""
    return str(uuid.uuid4())


# ============================================================================
# Initialization Tests
# ============================================================================


def test_tracker_initialization(job_id):
    """Test LineageTracker initializes with empty state."""
    tracker = LineageTracker(job_id=job_id)

    assert tracker.job_id == job_id
    assert tracker.events == []
    assert tracker.lineage_chain == {}


def test_tracker_stores_job_id_as_string(job_id):
    """Test job_id is stored as a string (not UUID object)."""
    tracker = LineageTracker(job_id=job_id)
    assert isinstance(tracker.job_id, str)
    assert tracker.job_id == job_id


# ============================================================================
# Emit Tests
# ============================================================================


def test_emit_stage_1_no_input(job_id):
    """Test Stage 1 emission with no input lineage."""
    tracker = LineageTracker(job_id=job_id)

    output_id = tracker.emit(
        stage=1,
        event_type="parse",
        input_lineage_id=None,
        metadata={"sheets_count": 5, "tokens": 1000},
    )

    assert len(tracker.events) == 1
    assert output_id is not None
    # Verify it's a valid UUID string
    uuid.UUID(output_id)

    event = tracker.events[0]
    assert event["stage"] == 1
    assert event["event_type"] == "parse"
    assert event["input_lineage_id"] is None
    assert event["metadata"]["sheets_count"] == 5
    assert event["metadata"]["tokens"] == 1000
    assert event["lineage_id"] == output_id
    assert "timestamp" in event


def test_emit_stage_2_with_parent(job_id):
    """Test Stage 2 links to Stage 1 output via input_lineage_id."""
    tracker = LineageTracker(job_id=job_id)

    l1 = tracker.emit(1, "parse", None, {"tokens": 800})
    l2 = tracker.emit(2, "triage", l1, {"tokens": 400})

    assert len(tracker.events) == 2

    # Verify stage 2 references stage 1
    stage2_event = tracker.events[1]
    assert stage2_event["input_lineage_id"] == l1
    assert stage2_event["lineage_id"] == l2


def test_emit_returns_unique_ids(job_id):
    """Each emit() call returns a unique lineage ID."""
    tracker = LineageTracker(job_id=job_id)

    l1 = tracker.emit(1, "parse", None, {"tokens": 100})
    l2 = tracker.emit(2, "triage", l1, {"tokens": 100})
    l3 = tracker.emit(3, "map", l2, {"tokens": 100})

    assert len({l1, l2, l3}) == 3  # All unique


def test_emit_with_default_metadata(job_id):
    """Metadata defaults to empty dict when not provided."""
    tracker = LineageTracker(job_id=job_id)
    tracker.emit(1, "parse")

    assert tracker.events[0]["metadata"] == {}


# ============================================================================
# Chain Integrity Tests
# ============================================================================


def test_full_pipeline_chain(job_id):
    """Test complete 3-stage pipeline builds correct lineage chain."""
    tracker = LineageTracker(job_id=job_id)

    l1 = tracker.emit(1, "parse", None, {"sheets_count": 3, "tokens": 800})
    l2 = tracker.emit(2, "triage", l1, {"tier_1_count": 2, "tokens": 400})
    l3 = tracker.emit(3, "map", l2, {"mappings_count": 15, "tokens": 600})

    assert len(tracker.events) == 3

    # Verify lineage_chain dict: maps each lineage_id -> parent
    assert tracker.lineage_chain[l1] is None  # Stage 1 has no parent
    assert tracker.lineage_chain[l2] == l1  # Stage 2 parent = Stage 1
    assert tracker.lineage_chain[l3] == l2  # Stage 3 parent = Stage 2


def test_chain_can_be_traced_backwards(job_id):
    """Can trace from final output back to origin via lineage_chain."""
    tracker = LineageTracker(job_id=job_id)

    l1 = tracker.emit(1, "parse", None, {"tokens": 100})
    l2 = tracker.emit(2, "triage", l1, {"tokens": 100})
    l3 = tracker.emit(3, "map", l2, {"tokens": 100})

    # Trace backwards from l3
    current = l3
    chain = [current]
    while tracker.lineage_chain.get(current) is not None:
        current = tracker.lineage_chain[current]
        chain.append(current)

    chain.reverse()
    assert chain == [l1, l2, l3]


# ============================================================================
# Validate Completeness Tests
# ============================================================================


def test_validate_completeness_success(job_id):
    """Validation passes when all required stages have events."""
    tracker = LineageTracker(job_id=job_id)

    l1 = tracker.emit(1, "parse", None, {"tokens": 100})
    l2 = tracker.emit(2, "triage", l1, {"tokens": 100})
    tracker.emit(3, "map", l2, {"tokens": 100})

    # Should not raise
    tracker.validate_completeness(stages=[1, 2, 3])


def test_validate_completeness_fails_missing_stage(job_id):
    """Validation raises LineageIncompleteError when stage is missing."""
    tracker = LineageTracker(job_id=job_id)

    l1 = tracker.emit(1, "parse", None, {"tokens": 100})
    tracker.emit(2, "triage", l1, {"tokens": 100})
    # Stage 3 NOT emitted

    with pytest.raises(LineageIncompleteError) as exc_info:
        tracker.validate_completeness(stages=[1, 2, 3])

    error = exc_info.value
    assert "stage_3" in error.missing_events


def test_validate_completeness_fails_all_missing(job_id):
    """Validation fails when no stages have been emitted."""
    tracker = LineageTracker(job_id=job_id)

    with pytest.raises(LineageIncompleteError) as exc_info:
        tracker.validate_completeness(stages=[1, 2, 3])

    error = exc_info.value
    assert len(error.missing_events) == 3


def test_validate_completeness_partial_pipeline(job_id):
    """Validation can check subsets of stages."""
    tracker = LineageTracker(job_id=job_id)

    l1 = tracker.emit(1, "parse", None, {"tokens": 100})
    tracker.emit(2, "triage", l1, {"tokens": 100})

    # Only validate stages 1-2 (not 3)
    tracker.validate_completeness(stages=[1, 2])


# ============================================================================
# get_summary() Tests
# ============================================================================


def test_get_summary_empty(job_id):
    """Summary of empty tracker."""
    tracker = LineageTracker(job_id=job_id)
    summary = tracker.get_summary()

    assert summary["total_events"] == 0
    assert summary["stages"] == []
    assert summary["event_types"] == []


def test_get_summary_full_pipeline(job_id):
    """Summary reflects all emitted events."""
    tracker = LineageTracker(job_id=job_id)

    l1 = tracker.emit(1, "parse", None, {"tokens": 100})
    l2 = tracker.emit(2, "triage", l1, {"tokens": 200})
    tracker.emit(3, "map", l2, {"tokens": 300})

    summary = tracker.get_summary()

    assert summary["total_events"] == 3
    assert sorted(summary["stages"]) == [1, 2, 3]
    assert sorted(summary["event_types"]) == ["map", "parse", "triage"]


def test_get_summary_multiple_events_per_stage(job_id):
    """Summary counts all events even if same stage emits multiple."""
    tracker = LineageTracker(job_id=job_id)

    l1 = tracker.emit(1, "parse", None, {"tokens": 100})
    tracker.emit(2, "triage", l1, {"tokens": 200})
    tracker.emit(2, "triage", l1, {"tokens": 150})  # Second triage event

    summary = tracker.get_summary()

    assert summary["total_events"] == 3
    # Stages set deduplicates
    assert sorted(summary["stages"]) == [1, 2]


# ============================================================================
# save_to_db() Tests (mocked database)
# ============================================================================


def test_save_to_db_empty_events(job_id):
    """save_to_db() is a no-op when no events exist."""
    tracker = LineageTracker(job_id=job_id)

    # Should not raise or call database
    with patch("src.lineage.tracker.get_db_context") as mock_db:
        tracker.save_to_db()
        mock_db.assert_not_called()


def test_save_to_db_calls_crud(job_id):
    """save_to_db() persists each event via CRUD."""
    tracker = LineageTracker(job_id=job_id)

    l1 = tracker.emit(1, "parse", None, {"tokens": 100})
    l2 = tracker.emit(2, "triage", l1, {"tokens": 200})
    tracker.emit(3, "map", l2, {"tokens": 300})

    mock_db_session = MagicMock()
    mock_context = MagicMock()
    mock_context.__enter__ = MagicMock(return_value=mock_db_session)
    mock_context.__exit__ = MagicMock(return_value=False)

    with patch("src.lineage.tracker.get_db_context", return_value=mock_context):
        with patch("src.lineage.tracker.crud") as mock_crud:
            tracker.save_to_db()

            # Should have called create_lineage_event 3 times
            assert mock_crud.create_lineage_event.call_count == 3

            # Verify stage names
            calls = mock_crud.create_lineage_event.call_args_list
            stage_names = [c.kwargs.get("stage_name") or c[1].get("stage_name") for c in calls]
            assert "stage_1_parse" in stage_names
            assert "stage_2_triage" in stage_names
            assert "stage_3_map" in stage_names

            # Verify commit was called
            mock_db_session.commit.assert_called_once()


def test_save_to_db_rollback_on_error(job_id):
    """save_to_db() rolls back on database error and raises LineageError."""
    tracker = LineageTracker(job_id=job_id)
    tracker.emit(1, "parse", None, {"tokens": 100})

    mock_db_session = MagicMock()
    mock_context = MagicMock()
    mock_context.__enter__ = MagicMock(return_value=mock_db_session)
    mock_context.__exit__ = MagicMock(return_value=False)

    with patch("src.lineage.tracker.get_db_context", return_value=mock_context):
        with patch("src.lineage.tracker.crud") as mock_crud:
            mock_crud.create_lineage_event.side_effect = Exception("DB connection lost")

            with pytest.raises(LineageError, match="Failed to persist lineage"):
                tracker.save_to_db()

            # Rollback should have been called
            mock_db_session.rollback.assert_called_once()
