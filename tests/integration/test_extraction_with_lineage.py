"""
Integration tests for extraction pipeline with lineage tracking.

Tests that the orchestrator correctly:
1. Creates a LineageTracker
2. Emits lineage events at each stage
3. Validates completeness before returning
4. Includes lineage summary in results

These tests use the mock_anthropic fixture to avoid real API calls
and mock save_to_db to avoid needing PostgreSQL.
"""
import pytest
import uuid

from src.extraction.orchestrator import extract


@pytest.mark.asyncio
async def test_extraction_emits_complete_lineage(mock_anthropic):
    """Full extraction produces lineage for all registered stages."""
    from src.extraction.registry import registry

    result = await extract(
        file_bytes=b"fake-excel-bytes",
        file_id=str(uuid.uuid4()),
    )

    # Result should include lineage fields
    assert "lineage_summary" in result
    assert "final_lineage_id" in result
    assert "job_id" in result

    # Lineage should cover all registered stages
    expected_stage_count = len(registry.get_pipeline())
    summary = result["lineage_summary"]
    assert summary["total_events"] == expected_stage_count
    assert len(summary["stages"]) == expected_stage_count


@pytest.mark.asyncio
async def test_extraction_lineage_event_types(mock_anthropic):
    """Lineage events match the stage names from the registry."""
    result = await extract(
        file_bytes=b"fake-excel-bytes",
        file_id=str(uuid.uuid4()),
    )

    summary = result["lineage_summary"]
    assert "parsing" in summary["event_types"]
    assert "triage" in summary["event_types"]
    assert "mapping" in summary["event_types"]


@pytest.mark.asyncio
async def test_extraction_generates_job_id_if_missing(mock_anthropic):
    """Extraction generates a job_id when none is provided."""
    result = await extract(
        file_bytes=b"fake-excel-bytes",
        file_id=str(uuid.uuid4()),
    )

    assert result["job_id"] is not None
    # Should be a valid UUID
    uuid.UUID(result["job_id"])


@pytest.mark.asyncio
async def test_extraction_uses_provided_job_id(mock_anthropic):
    """Extraction uses the job_id when explicitly provided."""
    expected_job_id = str(uuid.uuid4())
    result = await extract(
        file_bytes=b"fake-excel-bytes",
        file_id=str(uuid.uuid4()),
        job_id=expected_job_id,
    )

    assert result["job_id"] == expected_job_id


@pytest.mark.asyncio
async def test_extraction_final_lineage_id_is_valid(mock_anthropic):
    """The final_lineage_id is a valid UUID from the last stage."""
    result = await extract(
        file_bytes=b"fake-excel-bytes",
        file_id=str(uuid.uuid4()),
    )

    assert result["final_lineage_id"] is not None
    uuid.UUID(result["final_lineage_id"])
