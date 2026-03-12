"""
Unit tests for item-level lineage tracking and cross-extraction diff.

Tests:
- LineageTracker item lineage emission and retrieval
- ExtractionDiffer comparison logic
- API endpoints for diff and item-lineage
"""
import uuid
import pytest
from unittest.mock import patch, MagicMock, Mock

from src.lineage.tracker import LineageTracker
from src.lineage.differ import ExtractionDiffer, ExtractionDiff, DiffItem


@pytest.fixture
def job_id():
    return str(uuid.uuid4())


@pytest.fixture
def tracker(job_id):
    return LineageTracker(job_id=job_id)


# ============================================================================
# Item Lineage Emission Tests
# ============================================================================


class TestItemLineageEmission:

    def test_emit_item_transformation(self, tracker):
        """Single emission creates entry with correct fields."""
        tracker.emit_item_transformation(
            "revenue", "Total Revenue", "parsing", "parsed",
            {"sheet": "IS", "row": 5},
        )
        chain = tracker.get_item_lineage("revenue")
        assert len(chain) == 1
        assert chain[0]["stage"] == "parsing"
        assert chain[0]["action"] == "parsed"
        assert chain[0]["original_label"] == "Total Revenue"
        assert chain[0]["sheet"] == "IS"
        assert chain[0]["row"] == 5
        assert "timestamp" in chain[0]

    def test_four_stage_chain(self, tracker):
        """Four stages produce a chain of 4 transformations in order."""
        tracker.emit_item_transformation("revenue", "Revenue", "parsing", "parsed")
        tracker.emit_item_transformation("revenue", "Revenue", "mapping", "mapped",
                                         {"method": "claude", "confidence": 0.95})
        tracker.emit_item_transformation("revenue", "Revenue", "validation", "validated",
                                         {"all_passed": True})
        tracker.emit_item_transformation("revenue", "Revenue", "enhanced_mapping", "remapped",
                                         {"new_confidence": 0.98})

        chain = tracker.get_item_lineage("revenue")
        assert len(chain) == 4
        assert [t["stage"] for t in chain] == [
            "parsing", "mapping", "validation", "enhanced_mapping"
        ]
        assert chain[1]["confidence"] == 0.95
        assert chain[3]["new_confidence"] == 0.98

    def test_get_item_lineage_unknown(self, tracker):
        """Unknown canonical_name returns empty list."""
        assert tracker.get_item_lineage("nonexistent") == []

    def test_get_all_item_lineage_multiple(self, tracker):
        """Multiple canonical names tracked independently."""
        tracker.emit_item_transformation("revenue", "Revenue", "parsing", "parsed")
        tracker.emit_item_transformation("cogs", "Cost of Goods Sold", "parsing", "parsed")
        tracker.emit_item_transformation("ebitda", "EBITDA", "parsing", "parsed")

        all_lineage = tracker.get_all_item_lineage()
        assert set(all_lineage.keys()) == {"revenue", "cogs", "ebitda"}
        assert len(all_lineage["revenue"]) == 1

    def test_item_lineage_does_not_affect_stage_events(self, tracker):
        """Item lineage is independent from stage-level events."""
        tracker.emit_item_transformation("revenue", "Revenue", "parsing", "parsed")
        assert tracker.events == []
        assert tracker.get_summary()["total_events"] == 0

    def test_emit_item_transformation_no_details(self, tracker):
        """Emission with no details still works."""
        tracker.emit_item_transformation("revenue", "Revenue", "parsing", "parsed")
        chain = tracker.get_item_lineage("revenue")
        assert len(chain) == 1
        assert chain[0]["stage"] == "parsing"


# ============================================================================
# ExtractionDiffer Tests
# ============================================================================


class TestExtractionDiffer:

    def _make_items(self, items_spec):
        """Helper: build line_items list from spec dicts."""
        result = []
        for spec in items_spec:
            result.append({
                "original_label": spec["label"],
                "canonical_name": spec.get("canonical", "unmapped"),
                "confidence": spec.get("confidence", 0.9),
                "values": spec.get("values", {}),
            })
        return result

    def _make_job(self, line_items):
        """Helper: create a mock job with result containing line_items."""
        job = MagicMock()
        job.result = {"line_items": line_items}
        return job

    def _ids(self):
        """Return two valid UUID strings."""
        return str(uuid.uuid4()), str(uuid.uuid4())

    def test_diff_identical_no_changes(self):
        """Two identical results produce no changes."""
        items = self._make_items([
            {"label": "Revenue", "canonical": "revenue", "values": {"FY2023": 1000}},
            {"label": "COGS", "canonical": "cogs", "values": {"FY2023": 500}},
        ])
        job_a = self._make_job(items)
        job_b = self._make_job(items)

        db = MagicMock()
        with patch.object(ExtractionDiffer, "_load_all_facts", return_value=[]), \
             patch("src.lineage.differ.crud") as mock_crud:
            mock_crud.get_job.side_effect = [job_a, job_b]

            differ = ExtractionDiffer()
            a_id, b_id = self._ids()
            result = differ.diff(db, a_id, b_id)

        assert result.unchanged_count == 2
        assert result.added_items == []
        assert result.removed_items == []
        assert result.changed_items == []
        assert result.value_changes == []

    def test_diff_added_removed(self):
        """Items in A not in B are removed; items in B not in A are added."""
        items_a = self._make_items([
            {"label": "Revenue", "canonical": "revenue"},
            {"label": "COGS", "canonical": "cogs"},
        ])
        items_b = self._make_items([
            {"label": "Revenue", "canonical": "revenue"},
            {"label": "EBITDA", "canonical": "ebitda"},
        ])
        job_a = self._make_job(items_a)
        job_b = self._make_job(items_b)

        db = MagicMock()
        with patch.object(ExtractionDiffer, "_load_all_facts", return_value=[]), \
             patch("src.lineage.differ.crud") as mock_crud:
            mock_crud.get_job.side_effect = [job_a, job_b]

            a_id, b_id = self._ids()
            result = ExtractionDiffer().diff(db, a_id, b_id)

        assert len(result.removed_items) == 1
        assert result.removed_items[0].canonical_name == "cogs"
        assert result.removed_items[0].change_type == "removed"

        assert len(result.added_items) == 1
        assert result.added_items[0].canonical_name == "ebitda"
        assert result.added_items[0].change_type == "added"

    def test_diff_value_changed(self):
        """Same label with different values produces value_changed + value_changes."""
        items_a = self._make_items([
            {"label": "Revenue", "canonical": "revenue",
             "values": {"FY2023": 1000}},
        ])
        items_b = self._make_items([
            {"label": "Revenue", "canonical": "revenue",
             "values": {"FY2023": 1200}},
        ])
        job_a = self._make_job(items_a)
        job_b = self._make_job(items_b)

        db = MagicMock()
        with patch.object(ExtractionDiffer, "_load_all_facts", return_value=[]), \
             patch("src.lineage.differ.crud") as mock_crud:
            mock_crud.get_job.side_effect = [job_a, job_b]

            a_id, b_id = self._ids()
            result = ExtractionDiffer().diff(db, a_id, b_id)

        assert len(result.changed_items) == 1
        assert result.changed_items[0].change_type == "value_changed"
        assert len(result.value_changes) == 1
        vc = result.value_changes[0]
        assert vc["period"] == "FY2023"
        assert vc["old_value"] == 1000
        assert vc["new_value"] == 1200
        assert vc["pct_change"] == 20.0

    def test_diff_mapping_changed(self):
        """Same label with different canonical_name is mapping_changed."""
        items_a = self._make_items([
            {"label": "Total Revenue", "canonical": "revenue"},
        ])
        items_b = self._make_items([
            {"label": "Total Revenue", "canonical": "net_revenue"},
        ])
        job_a = self._make_job(items_a)
        job_b = self._make_job(items_b)

        db = MagicMock()
        with patch.object(ExtractionDiffer, "_load_all_facts", return_value=[]), \
             patch("src.lineage.differ.crud") as mock_crud:
            mock_crud.get_job.side_effect = [job_a, job_b]

            a_id, b_id = self._ids()
            result = ExtractionDiffer().diff(db, a_id, b_id)

        assert len(result.changed_items) == 1
        assert result.changed_items[0].change_type == "mapping_changed"
        assert result.changed_items[0].details["old_canonical"] == "revenue"
        assert result.changed_items[0].details["new_canonical"] == "net_revenue"

    def test_diff_confidence_changed(self):
        """Same label/canonical with different confidence is confidence_changed."""
        items_a = self._make_items([
            {"label": "Revenue", "canonical": "revenue", "confidence": 0.7},
        ])
        items_b = self._make_items([
            {"label": "Revenue", "canonical": "revenue", "confidence": 0.95},
        ])
        job_a = self._make_job(items_a)
        job_b = self._make_job(items_b)

        db = MagicMock()
        with patch.object(ExtractionDiffer, "_load_all_facts", return_value=[]), \
             patch("src.lineage.differ.crud") as mock_crud:
            mock_crud.get_job.side_effect = [job_a, job_b]

            a_id, b_id = self._ids()
            result = ExtractionDiffer().diff(db, a_id, b_id)

        change_types = [c.change_type for c in result.changed_items]
        assert "confidence_changed" in change_types

    def test_diff_canonical_filter(self):
        """canonical_name filter limits diff to matching items only."""
        items_a = self._make_items([
            {"label": "Revenue", "canonical": "revenue", "values": {"FY2023": 1000}},
            {"label": "COGS", "canonical": "cogs", "values": {"FY2023": 500}},
        ])
        items_b = self._make_items([
            {"label": "Revenue", "canonical": "revenue", "values": {"FY2023": 1200}},
            {"label": "COGS", "canonical": "cogs", "values": {"FY2023": 600}},
        ])
        job_a = self._make_job(items_a)
        job_b = self._make_job(items_b)

        db = MagicMock()
        with patch.object(ExtractionDiffer, "_load_all_facts", return_value=[]), \
             patch("src.lineage.differ.crud") as mock_crud:
            mock_crud.get_job.side_effect = [job_a, job_b]

            result = ExtractionDiffer().diff(
                db, *self._ids(), canonical_name="revenue",
            )

        # Only revenue should appear — cogs filtered out
        assert len(result.value_changes) == 1
        assert result.value_changes[0]["canonical_name"] == "revenue"
        assert result.unchanged_count == 0

    def test_diff_min_change_pct_filter(self):
        """min_change_pct suppresses small value changes."""
        items_a = self._make_items([
            {"label": "Revenue", "canonical": "revenue",
             "values": {"FY2023": 1000}},
        ])
        items_b = self._make_items([
            {"label": "Revenue", "canonical": "revenue",
             "values": {"FY2023": 1005}},  # 0.5% change
        ])
        job_a = self._make_job(items_a)
        job_b = self._make_job(items_b)

        db = MagicMock()
        with patch.object(ExtractionDiffer, "_load_all_facts", return_value=[]), \
             patch("src.lineage.differ.crud") as mock_crud:
            mock_crud.get_job.side_effect = [job_a, job_b]

            result = ExtractionDiffer().diff(
                db, *self._ids(), min_change_pct=1.0,
            )

        # 0.5% change should be suppressed by 1.0% threshold
        assert result.value_changes == []
        assert result.unchanged_count == 1

    def test_diff_from_facts_identical(self):
        """Fact-based diff with identical facts shows no changes."""
        fact_a = MagicMock()
        fact_a.canonical_name = "revenue"
        fact_a.original_label = "Revenue"
        fact_a.confidence = 0.9
        fact_a.period = "FY2023"
        fact_a.value = 1000.0

        fact_b = MagicMock()
        fact_b.canonical_name = "revenue"
        fact_b.original_label = "Revenue"
        fact_b.confidence = 0.9
        fact_b.period = "FY2023"
        fact_b.value = 1000.0

        db = MagicMock()
        with patch.object(ExtractionDiffer, "_load_all_facts",
                          side_effect=[[fact_a], [fact_b]]):
            a_id, b_id = self._ids()
            result = ExtractionDiffer().diff(db, a_id, b_id)

        assert result.unchanged_count == 1
        assert result.added_items == []
        assert result.removed_items == []
        assert result.value_changes == []

    def test_diff_from_facts_value_changed(self):
        """Fact-based diff detects value changes across periods."""
        fact_a = MagicMock()
        fact_a.canonical_name = "revenue"
        fact_a.original_label = "Revenue"
        fact_a.confidence = 0.9
        fact_a.period = "FY2023"
        fact_a.value = 1000.0

        fact_b = MagicMock()
        fact_b.canonical_name = "revenue"
        fact_b.original_label = "Revenue"
        fact_b.confidence = 0.9
        fact_b.period = "FY2023"
        fact_b.value = 1500.0

        db = MagicMock()
        with patch.object(ExtractionDiffer, "_load_all_facts",
                          side_effect=[[fact_a], [fact_b]]):
            a_id, b_id = self._ids()
            result = ExtractionDiffer().diff(db, a_id, b_id)

        assert len(result.value_changes) == 1
        assert result.value_changes[0]["old_value"] == 1000.0
        assert result.value_changes[0]["new_value"] == 1500.0
        assert result.value_changes[0]["pct_change"] == 50.0

    def test_diff_from_facts_added_removed(self):
        """Fact-based diff detects added and removed items."""
        fact_a = MagicMock()
        fact_a.canonical_name = "revenue"
        fact_a.original_label = "Revenue"
        fact_a.confidence = 0.9
        fact_a.period = "FY2023"
        fact_a.value = 1000.0

        fact_b = MagicMock()
        fact_b.canonical_name = "ebitda"
        fact_b.original_label = "EBITDA"
        fact_b.confidence = 0.85
        fact_b.period = "FY2023"
        fact_b.value = 500.0

        db = MagicMock()
        with patch.object(ExtractionDiffer, "_load_all_facts",
                          side_effect=[[fact_a], [fact_b]]):
            a_id, b_id = self._ids()
            result = ExtractionDiffer().diff(db, a_id, b_id)

        assert len(result.removed_items) == 1
        assert result.removed_items[0].canonical_name == "revenue"
        assert len(result.added_items) == 1
        assert result.added_items[0].canonical_name == "ebitda"

    def test_diff_from_facts_canonical_filter(self):
        """Fact-based diff respects canonical_name filter."""
        fact_a1 = MagicMock()
        fact_a1.canonical_name = "revenue"
        fact_a1.original_label = "Revenue"
        fact_a1.confidence = 0.9
        fact_a1.period = "FY2023"
        fact_a1.value = 1000.0

        fact_a2 = MagicMock()
        fact_a2.canonical_name = "cogs"
        fact_a2.original_label = "COGS"
        fact_a2.confidence = 0.85
        fact_a2.period = "FY2023"
        fact_a2.value = 500.0

        fact_b1 = MagicMock()
        fact_b1.canonical_name = "revenue"
        fact_b1.original_label = "Revenue"
        fact_b1.confidence = 0.9
        fact_b1.period = "FY2023"
        fact_b1.value = 1200.0

        fact_b2 = MagicMock()
        fact_b2.canonical_name = "cogs"
        fact_b2.original_label = "COGS"
        fact_b2.confidence = 0.85
        fact_b2.period = "FY2023"
        fact_b2.value = 600.0

        db = MagicMock()
        with patch.object(ExtractionDiffer, "_load_all_facts",
                          side_effect=[[fact_a1, fact_a2], [fact_b1, fact_b2]]):
            a_id, b_id = self._ids()
            result = ExtractionDiffer().diff(
                db, a_id, b_id, canonical_name="revenue"
            )

        assert len(result.value_changes) == 1
        assert result.value_changes[0]["canonical_name"] == "revenue"

    def test_to_dict_format(self):
        """ExtractionDiff.to_dict() includes summary counts."""
        diff = ExtractionDiff(
            job_a_id="a", job_b_id="b",
            added_items=[DiffItem("x", "added")],
            removed_items=[DiffItem("y", "removed")],
            changed_items=[DiffItem("z", "value_changed")],
            unchanged_count=5,
            value_changes=[{"canonical_name": "z", "period": "FY2023",
                           "old_value": 1, "new_value": 2, "pct_change": 100.0}],
        )
        d = diff.to_dict()
        assert d["summary"] == {"added": 1, "removed": 1, "changed": 1, "unchanged": 5}
        assert len(d["added_items"]) == 1
        assert len(d["value_changes"]) == 1


# ============================================================================
# Endpoint Tests
# ============================================================================


class TestDiffEndpoint:

    def test_diff_endpoint_200(self, test_client_with_db):
        """Diff endpoint returns structured response for two jobs."""
        from src.db.models import JobStatusEnum

        with patch("src.api.jobs.crud") as mock_crud, \
             patch("src.api.jobs.ExtractionDiffer") as MockDiffer:
            job_a = MagicMock()
            job_a.result = {"line_items": []}
            job_a.status = JobStatusEnum.COMPLETED
            job_b = MagicMock()
            job_b.result = {"line_items": []}
            job_b.status = JobStatusEnum.COMPLETED
            mock_crud.get_job.side_effect = [job_a, job_b]

            mock_diff = ExtractionDiff(job_a_id="a", job_b_id="b", unchanged_count=0)
            MockDiffer.return_value.diff.return_value = mock_diff

            a_id = str(uuid.uuid4())
            b_id = str(uuid.uuid4())
            resp = test_client_with_db.get(f"/api/v1/jobs/{a_id}/diff/{b_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "added_items" in data
        assert "removed_items" in data
        assert "changed_items" in data
        assert "value_changes" in data

    def test_diff_endpoint_409_not_completed(self, test_client_with_db):
        """Diff endpoint returns 409 when job is not completed."""
        from src.db.models import JobStatusEnum

        with patch("src.api.jobs.crud") as mock_crud:
            job_a = MagicMock()
            job_a.status = JobStatusEnum.PROCESSING
            mock_crud.get_job.return_value = job_a

            a_id = str(uuid.uuid4())
            b_id = str(uuid.uuid4())
            resp = test_client_with_db.get(f"/api/v1/jobs/{a_id}/diff/{b_id}")

        assert resp.status_code == 409

    def test_diff_endpoint_404(self, test_client_with_db):
        """Diff endpoint returns 404 when job not found."""
        with patch("src.api.jobs.crud") as mock_crud:
            mock_crud.get_job.return_value = None

            a_id = str(uuid.uuid4())
            b_id = str(uuid.uuid4())
            resp = test_client_with_db.get(f"/api/v1/jobs/{a_id}/diff/{b_id}")

        assert resp.status_code == 404

    def test_diff_endpoint_invalid_uuid(self, test_client_with_db):
        """Diff endpoint returns 400 for invalid UUID."""
        resp = test_client_with_db.get("/api/v1/jobs/not-a-uuid/diff/also-bad")
        assert resp.status_code == 400


class TestItemLineageEndpoint:

    def test_item_lineage_200(self, test_client_with_db):
        """Item lineage endpoint returns transformation chain."""
        with patch("src.api.jobs.crud") as mock_crud:
            job = MagicMock()
            job.result = {
                "item_lineage": {
                    "revenue": [
                        {"stage": "parsing", "action": "parsed",
                         "original_label": "Revenue", "timestamp": "2026-01-01T00:00:00"},
                    ]
                }
            }
            mock_crud.get_job.return_value = job

            job_id = str(uuid.uuid4())
            resp = test_client_with_db.get(
                f"/api/v1/jobs/{job_id}/item-lineage/revenue"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["canonical_name"] == "revenue"
        assert len(data["transformations"]) == 1

    def test_item_lineage_404_no_match(self, test_client_with_db):
        """Item lineage endpoint returns 404 for unknown canonical."""
        with patch("src.api.jobs.crud") as mock_crud:
            job = MagicMock()
            job.result = {"item_lineage": {}}
            mock_crud.get_job.return_value = job

            job_id = str(uuid.uuid4())
            resp = test_client_with_db.get(
                f"/api/v1/jobs/{job_id}/item-lineage/nonexistent"
            )

        assert resp.status_code == 404


# ============================================================================
# Cross-Entity Warning & Correction Metadata Tests
# ============================================================================


class TestDiffCrossEntityWarning:

    def _make_mock_job(self, status, entity_id):
        """Helper: create a mock job with file.entity_id."""
        job = MagicMock()
        job.status = status
        job.file = MagicMock()
        job.file.entity_id = entity_id
        return job

    def test_diff_cross_entity_warning(self, test_client_with_db):
        """Diff response includes warning when jobs belong to different entities."""
        from src.db.models import JobStatusEnum

        with patch("src.api.jobs.crud") as mock_crud, \
             patch("src.api.jobs.ExtractionDiffer") as MockDiffer:
            job_a = self._make_mock_job(JobStatusEnum.COMPLETED, uuid.uuid4())
            job_b = self._make_mock_job(JobStatusEnum.COMPLETED, uuid.uuid4())
            mock_crud.get_job.side_effect = [job_a, job_b]

            mock_diff = ExtractionDiff(job_a_id="a", job_b_id="b", unchanged_count=0)
            MockDiffer.return_value.diff.return_value = mock_diff

            a_id = str(uuid.uuid4())
            b_id = str(uuid.uuid4())
            resp = test_client_with_db.get(f"/api/v1/jobs/{a_id}/diff/{b_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert "warnings" in data
        assert any("different entities" in w for w in data["warnings"])

    def test_diff_no_warning_same_entity(self, test_client_with_db):
        """No warning when both jobs belong to the same entity."""
        from src.db.models import JobStatusEnum

        entity_id = uuid.uuid4()

        with patch("src.api.jobs.crud") as mock_crud, \
             patch("src.api.jobs.ExtractionDiffer") as MockDiffer:
            job_a = self._make_mock_job(JobStatusEnum.COMPLETED, entity_id)
            job_b = self._make_mock_job(JobStatusEnum.COMPLETED, entity_id)
            mock_crud.get_job.side_effect = [job_a, job_b]

            mock_diff = ExtractionDiff(job_a_id="a", job_b_id="b", unchanged_count=0)
            MockDiffer.return_value.diff.return_value = mock_diff

            a_id = str(uuid.uuid4())
            b_id = str(uuid.uuid4())
            resp = test_client_with_db.get(f"/api/v1/jobs/{a_id}/diff/{b_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("warnings", []) == []

    def test_diff_no_warning_null_entity(self, test_client_with_db):
        """No warning when either entity_id is None."""
        from src.db.models import JobStatusEnum

        with patch("src.api.jobs.crud") as mock_crud, \
             patch("src.api.jobs.ExtractionDiffer") as MockDiffer:
            job_a = self._make_mock_job(JobStatusEnum.COMPLETED, None)
            job_b = self._make_mock_job(JobStatusEnum.COMPLETED, uuid.uuid4())
            mock_crud.get_job.side_effect = [job_a, job_b]

            mock_diff = ExtractionDiff(job_a_id="a", job_b_id="b", unchanged_count=0)
            MockDiffer.return_value.diff.return_value = mock_diff

            a_id = str(uuid.uuid4())
            b_id = str(uuid.uuid4())
            resp = test_client_with_db.get(f"/api/v1/jobs/{a_id}/diff/{b_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("warnings", []) == []


class TestDiffCorrectionMetadata:

    def test_to_dict_includes_warnings_and_metadata(self):
        """ExtractionDiff.to_dict() includes warnings and metadata when present."""
        diff = ExtractionDiff(
            job_a_id="a", job_b_id="b", unchanged_count=3,
            warnings=["Jobs belong to different entities"],
            metadata={"job_a_corrections": 2, "job_b_corrections": 0},
        )
        d = diff.to_dict()
        assert d["warnings"] == ["Jobs belong to different entities"]
        assert d["metadata"]["job_a_corrections"] == 2
        assert d["metadata"]["job_b_corrections"] == 0

    def test_to_dict_omits_empty_warnings_and_metadata(self):
        """ExtractionDiff.to_dict() omits warnings/metadata when empty."""
        diff = ExtractionDiff(job_a_id="a", job_b_id="b", unchanged_count=1)
        d = diff.to_dict()
        assert "warnings" not in d
        assert "metadata" not in d

    def test_diff_no_metadata_zero_corrections(self, test_client_with_db):
        """Metadata absent when no corrections exist for either job."""
        from src.db.models import JobStatusEnum

        with patch("src.api.jobs.crud") as mock_crud, \
             patch("src.api.jobs.ExtractionDiffer") as MockDiffer:
            job_a = MagicMock()
            job_a.status = JobStatusEnum.COMPLETED
            job_a.file = MagicMock()
            job_a.file.entity_id = None
            job_b = MagicMock()
            job_b.status = JobStatusEnum.COMPLETED
            job_b.file = MagicMock()
            job_b.file.entity_id = None
            mock_crud.get_job.side_effect = [job_a, job_b]

            mock_diff = ExtractionDiff(job_a_id="a", job_b_id="b", unchanged_count=0)
            MockDiffer.return_value.diff.return_value = mock_diff

            a_id = str(uuid.uuid4())
            b_id = str(uuid.uuid4())
            resp = test_client_with_db.get(f"/api/v1/jobs/{a_id}/diff/{b_id}")

        assert resp.status_code == 200
        data = resp.json()
        # With zero corrections in test DB, metadata should not be in response
        assert "metadata" not in data or data.get("metadata", {}) == {}
