"""
Integration tests for extraction pipeline with lineage tracking.

Tests that the orchestrator correctly:
1. Creates a LineageTracker
2. Emits lineage events at each stage
3. Validates completeness before returning
4. Includes lineage summary and item_lineage in results

These tests use the mock_anthropic fixture to avoid real API calls
and mock save_to_db to avoid needing PostgreSQL.
"""
import pytest
import uuid

from src.extraction.orchestrator import extract
from src.db.models import JobStatusEnum


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


# ============================================================================
# Item-Level Lineage Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_extraction_includes_item_lineage(mock_anthropic):
    """Full extraction produces item_lineage dict in results."""
    result = await extract(
        file_bytes=b"fake-excel-bytes",
        file_id=str(uuid.uuid4()),
    )

    assert "item_lineage" in result
    item_lineage = result["item_lineage"]

    # Should be a dict (or None if no line_items were produced)
    if result.get("line_items"):
        assert isinstance(item_lineage, dict)
        # Each item should have at least a parsing + mapping transformation
        for canonical, chain in item_lineage.items():
            assert len(chain) >= 2, f"{canonical} should have at least 2 transformations"
            stages = [t["stage"] for t in chain]
            assert "parsing" in stages
            assert "mapping" in stages


@pytest.mark.asyncio
async def test_item_lineage_has_correct_fields(mock_anthropic):
    """Each transformation record has required fields."""
    result = await extract(
        file_bytes=b"fake-excel-bytes",
        file_id=str(uuid.uuid4()),
    )

    item_lineage = result.get("item_lineage", {})
    for canonical, chain in item_lineage.items():
        for transformation in chain:
            assert "stage" in transformation
            assert "action" in transformation
            assert "original_label" in transformation
            assert "timestamp" in transformation


@pytest.mark.asyncio
async def test_item_lineage_to_dict_roundtrip(mock_anthropic):
    """item_lineage survives ExtractionResult.to_dict() serialization."""
    result = await extract(
        file_bytes=b"fake-excel-bytes",
        file_id=str(uuid.uuid4()),
    )

    # The result IS the dict (from to_dict()), so item_lineage should be present
    assert "item_lineage" in result
    # Should be JSON-serializable (no custom objects)
    import json
    if result["item_lineage"]:
        json.dumps(result["item_lineage"])  # Should not raise


# ============================================================================
# Diff Endpoint Integration Tests (with real DB)
# ============================================================================


def _create_completed_job(session, line_items, sheets=None):
    """Helper: create entity + file + completed job. Returns job_id as str."""
    from src.db import crud
    entity = crud.create_entity(session, name="Test Corp", industry="Finance")
    file = crud.create_file(
        session, filename="test.xlsx", file_size=1024, entity_id=entity.id
    )
    job = crud.create_extraction_job(session, file_id=file.file_id)
    job.status = JobStatusEnum.COMPLETED
    job.result = {
        "line_items": line_items,
        "sheets": sheets or ["Sheet1"],
    }
    session.commit()
    return str(job.job_id)


class TestDiffEndpointIntegration:

    def test_diff_two_real_jobs(self, test_client_with_db, test_db):
        """Diff endpoint works with two real completed jobs in DB."""
        session = test_db()
        try:
            items_a = [
                {"original_label": "Revenue", "canonical_name": "revenue",
                 "values": {"FY2023": 1000}, "confidence": 0.9},
                {"original_label": "COGS", "canonical_name": "cogs",
                 "values": {"FY2023": 500}, "confidence": 0.85},
            ]
            items_b = [
                {"original_label": "Revenue", "canonical_name": "revenue",
                 "values": {"FY2023": 1200}, "confidence": 0.95},
                {"original_label": "EBITDA", "canonical_name": "ebitda",
                 "values": {"FY2023": 700}, "confidence": 0.88},
            ]
            job_a = _create_completed_job(session, items_a)
            job_b = _create_completed_job(session, items_b)
        finally:
            session.close()

        resp = test_client_with_db.get(
            f"/api/v1/jobs/{job_a}/diff/{job_b}"
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["summary"]["added"] == 1   # EBITDA
        assert data["summary"]["removed"] == 1  # COGS
        assert data["summary"]["changed"] >= 1  # Revenue value changed
        assert len(data["value_changes"]) >= 1

        # Verify value change detail
        rev_changes = [
            vc for vc in data["value_changes"]
            if vc["canonical_name"] == "revenue"
        ]
        assert len(rev_changes) == 1
        assert rev_changes[0]["old_value"] == 1000
        assert rev_changes[0]["new_value"] == 1200
        assert rev_changes[0]["pct_change"] == 20.0

    def test_diff_identical_jobs(self, test_client_with_db, test_db):
        """Diffing identical jobs shows no changes."""
        session = test_db()
        try:
            items = [
                {"original_label": "Revenue", "canonical_name": "revenue",
                 "values": {"FY2023": 1000}, "confidence": 0.9},
            ]
            job_a = _create_completed_job(session, items)
            job_b = _create_completed_job(session, items)
        finally:
            session.close()

        resp = test_client_with_db.get(
            f"/api/v1/jobs/{job_a}/diff/{job_b}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["unchanged"] == 1
        assert data["summary"]["added"] == 0
        assert data["summary"]["removed"] == 0
        assert data["summary"]["changed"] == 0

    def test_diff_with_canonical_filter(self, test_client_with_db, test_db):
        """canonical_name query param filters diff results."""
        session = test_db()
        try:
            items_a = [
                {"original_label": "Revenue", "canonical_name": "revenue",
                 "values": {"FY2023": 1000}, "confidence": 0.9},
                {"original_label": "COGS", "canonical_name": "cogs",
                 "values": {"FY2023": 500}, "confidence": 0.85},
            ]
            items_b = [
                {"original_label": "Revenue", "canonical_name": "revenue",
                 "values": {"FY2023": 1200}, "confidence": 0.9},
                {"original_label": "COGS", "canonical_name": "cogs",
                 "values": {"FY2023": 600}, "confidence": 0.85},
            ]
            job_a = _create_completed_job(session, items_a)
            job_b = _create_completed_job(session, items_b)
        finally:
            session.close()

        resp = test_client_with_db.get(
            f"/api/v1/jobs/{job_a}/diff/{job_b}",
            params={"canonical_name": "revenue"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Only revenue should appear
        for vc in data["value_changes"]:
            assert vc["canonical_name"] == "revenue"

    def test_diff_job_not_found(self, test_client_with_db):
        """Returns 404 for nonexistent job."""
        fake_id = str(uuid.uuid4())
        resp = test_client_with_db.get(
            f"/api/v1/jobs/{fake_id}/diff/{fake_id}"
        )
        assert resp.status_code == 404


class TestItemLineageEndpointIntegration:

    def test_item_lineage_from_real_job(self, test_client_with_db, test_db):
        """item-lineage endpoint works with real job result containing item_lineage."""
        session = test_db()
        try:
            from src.db import crud
            entity = crud.create_entity(session, name="Test Corp", industry="Finance")
            file = crud.create_file(
                session, filename="test.xlsx", file_size=1024, entity_id=entity.id
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)
            job.status = JobStatusEnum.COMPLETED
            job.result = {
                "line_items": [
                    {"original_label": "Revenue", "canonical_name": "revenue",
                     "values": {"FY2023": 1000}, "confidence": 0.9},
                ],
                "item_lineage": {
                    "revenue": [
                        {"stage": "parsing", "action": "parsed",
                         "original_label": "Revenue", "timestamp": "2026-01-01T00:00:00",
                         "sheet": "Sheet1", "row": 2},
                        {"stage": "mapping", "action": "mapped",
                         "original_label": "Revenue", "timestamp": "2026-01-01T00:00:01",
                         "method": "claude", "confidence": 0.9},
                    ],
                },
            }
            session.commit()
            job_id = str(job.job_id)
        finally:
            session.close()

        resp = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/item-lineage/revenue"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["canonical_name"] == "revenue"
        assert len(data["transformations"]) == 2
        assert data["transformations"][0]["stage"] == "parsing"
        assert data["transformations"][1]["stage"] == "mapping"

    def test_item_lineage_not_found(self, test_client_with_db, test_db):
        """Returns 404 for canonical not in item_lineage."""
        session = test_db()
        try:
            from src.db import crud
            entity = crud.create_entity(session, name="Test Corp", industry="Finance")
            file = crud.create_file(
                session, filename="test.xlsx", file_size=1024, entity_id=entity.id
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)
            job.status = JobStatusEnum.COMPLETED
            job.result = {"line_items": [], "item_lineage": {}}
            session.commit()
            job_id = str(job.job_id)
        finally:
            session.close()

        resp = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/item-lineage/nonexistent"
        )
        assert resp.status_code == 404
