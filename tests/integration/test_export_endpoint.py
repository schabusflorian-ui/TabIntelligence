"""
Tests for the export endpoint: GET /api/v1/jobs/{job_id}/export

Tests cover:
- JSON export with full results
- CSV export with proper headers and period columns
- Confidence filtering (min_confidence)
- Canonical name filtering
- Sheet filtering
- Edge cases: job not found, job not completed, invalid format
"""
import csv
import io
import pytest
from uuid import UUID


# Realistic extraction result matching ExtractionResult.to_dict() schema
SAMPLE_RESULT = {
    "file_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "sheets": ["Income Statement", "Balance Sheet", "Cash Flow"],
    "triage": [
        {"sheet_name": "Income Statement", "tier": 1, "decision": "PROCESS"},
        {"sheet_name": "Balance Sheet", "tier": 1, "decision": "PROCESS"},
        {"sheet_name": "Cash Flow", "tier": 2, "decision": "PROCESS"},
    ],
    "line_items": [
        {
            "sheet": "Income Statement",
            "row": 5,
            "original_label": "Revenue",
            "canonical_name": "revenue",
            "values": {"FY2022": 5000000, "FY2023": 5500000, "FY2024E": 6000000},
            "confidence": 0.95,
            "hierarchy_level": 1,
        },
        {
            "sheet": "Income Statement",
            "row": 6,
            "original_label": "Cost of Goods Sold",
            "canonical_name": "cogs",
            "values": {"FY2022": 3000000, "FY2023": 3200000, "FY2024E": 3400000},
            "confidence": 0.92,
            "hierarchy_level": 1,
        },
        {
            "sheet": "Income Statement",
            "row": 8,
            "original_label": "Gross Profit",
            "canonical_name": "gross_profit",
            "values": {"FY2022": 2000000, "FY2023": 2300000, "FY2024E": 2600000},
            "confidence": 0.88,
            "hierarchy_level": 1,
        },
        {
            "sheet": "Income Statement",
            "row": 15,
            "original_label": "SGA",
            "canonical_name": "sga",
            "values": {"FY2022": 800000, "FY2023": 850000, "FY2024E": 900000},
            "confidence": 0.75,
            "hierarchy_level": 2,
        },
        {
            "sheet": "Income Statement",
            "row": 20,
            "original_label": "Misc Item",
            "canonical_name": "unmapped",
            "values": {"FY2022": 10000},
            "confidence": 0.3,
            "hierarchy_level": 3,
        },
        {
            "sheet": "Balance Sheet",
            "row": 3,
            "original_label": "Total Assets",
            "canonical_name": "total_assets",
            "values": {"FY2022": 10000000, "FY2023": 11000000},
            "confidence": 0.97,
            "hierarchy_level": 1,
        },
    ],
    "tokens_used": 4200,
    "cost_usd": 0.0126,
    "validation": {
        "period_results": {"FY2022": {"gross_profit_check": True}},
        "flags": [],
        "overall_confidence": 0.87,
    },
    "lineage_summary": {"stages_completed": 5},
    "job_id": "placeholder",
}


@pytest.fixture
def completed_job(db_session):
    """Create a completed extraction job with realistic result data."""
    from src.db import crud
    from src.db.models import JobStatusEnum

    file = crud.create_file(db_session, filename="test_model.xlsx", file_size=50000)
    job = crud.create_extraction_job(db_session, file_id=file.file_id)

    # Mark job as completed with sample result
    result = {**SAMPLE_RESULT, "job_id": str(job.job_id), "file_id": str(file.file_id)}
    crud.complete_job(
        db_session,
        job.job_id,
        result=result,
        tokens_used=4200,
        cost_usd=0.0126,
    )

    return job


@pytest.fixture
def pending_job(db_session):
    """Create a pending (not completed) job."""
    from src.db import crud

    file = crud.create_file(db_session, filename="pending.xlsx", file_size=1000)
    job = crud.create_extraction_job(db_session, file_id=file.file_id)
    return job


# ============================================================================
# JSON EXPORT TESTS
# ============================================================================


class TestJsonExport:
    """Tests for JSON format export."""

    def test_export_json_returns_full_result(self, test_client_with_db, completed_job):
        """Export returns all line items in JSON format."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export?format=json"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["job_id"] == str(completed_job.job_id)
        assert len(data["line_items"]) == 6
        assert data["line_items_count"] == 6
        assert data["tokens_used"] == 4200
        assert data["cost_usd"] == 0.0126
        assert "sheets" in data
        assert "validation" in data

    def test_export_json_default_format(self, test_client_with_db, completed_job):
        """Default format is JSON when no format specified."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export"
        )

        assert response.status_code == 200
        data = response.json()
        assert "line_items" in data

    def test_export_json_includes_filter_metadata(self, test_client_with_db, completed_job):
        """Response includes which filters were applied."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export?min_confidence=0.9"
        )

        data = response.json()
        assert data["filters_applied"]["min_confidence"] == 0.9
        assert data["filters_applied"]["canonical_name"] is None
        assert data["filters_applied"]["sheet"] is None


# ============================================================================
# CSV EXPORT TESTS
# ============================================================================


class TestCsvExport:
    """Tests for CSV format export."""

    def test_export_csv_returns_valid_csv(self, test_client_with_db, completed_job):
        """CSV export returns parseable CSV with correct headers."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export?format=csv"
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]

        # Parse CSV
        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)

        # Header + 6 data rows
        assert len(rows) == 7
        header = rows[0]
        assert "sheet" in header
        assert "original_label" in header
        assert "canonical_name" in header
        assert "confidence" in header

    def test_export_csv_has_period_columns(self, test_client_with_db, completed_job):
        """CSV columns include all period values (FY2022, FY2023, etc.)."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export?format=csv"
        )

        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)
        header = rows[0]

        # Should have period columns collected from all line items
        assert "FY2022" in header
        assert "FY2023" in header
        assert "FY2024E" in header

    def test_export_csv_data_values_correct(self, test_client_with_db, completed_job):
        """CSV data rows contain correct values."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export?format=csv"
        )

        reader = csv.DictReader(io.StringIO(response.text))
        rows = list(reader)

        # Find revenue row
        revenue = next(r for r in rows if r["canonical_name"] == "revenue")
        assert revenue["original_label"] == "Revenue"
        assert revenue["sheet"] == "Income Statement"
        assert revenue["FY2022"] == "5000000"
        assert revenue["confidence"] == "0.95"

    def test_export_csv_filename_includes_job_id(self, test_client_with_db, completed_job):
        """CSV download filename includes the job ID."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export?format=csv"
        )

        disposition = response.headers["content-disposition"]
        assert str(completed_job.job_id) in disposition


# ============================================================================
# FILTERING TESTS
# ============================================================================


class TestExportFiltering:
    """Tests for filtering line items during export."""

    def test_filter_by_min_confidence(self, test_client_with_db, completed_job):
        """min_confidence filters out low-confidence items."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export?min_confidence=0.9"
        )

        data = response.json()
        # Only revenue (0.95), cogs (0.92), total_assets (0.97) pass >= 0.9
        assert data["line_items_count"] == 3
        for li in data["line_items"]:
            assert li["confidence"] >= 0.9

    def test_filter_by_high_confidence_excludes_unmapped(self, test_client_with_db, completed_job):
        """High confidence threshold excludes unmapped items."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export?min_confidence=0.5"
        )

        data = response.json()
        canonical_names = [li["canonical_name"] for li in data["line_items"]]
        assert "unmapped" not in canonical_names  # unmapped has 0.3 confidence

    def test_filter_by_canonical_name(self, test_client_with_db, completed_job):
        """canonical_name filter returns only matching items."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export?canonical_name=revenue"
        )

        data = response.json()
        assert data["line_items_count"] == 1
        assert data["line_items"][0]["canonical_name"] == "revenue"

    def test_filter_by_sheet(self, test_client_with_db, completed_job):
        """sheet filter returns only items from that sheet."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export?sheet=Balance Sheet"
        )

        data = response.json()
        assert data["line_items_count"] == 1
        assert data["line_items"][0]["sheet"] == "Balance Sheet"

    def test_combined_filters(self, test_client_with_db, completed_job):
        """Multiple filters can be combined."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export"
            f"?min_confidence=0.8&sheet=Income Statement"
        )

        data = response.json()
        for li in data["line_items"]:
            assert li["confidence"] >= 0.8
            assert li["sheet"] == "Income Statement"
        # revenue(0.95), cogs(0.92), gross_profit(0.88) — all on Income Statement with >= 0.8
        assert data["line_items_count"] == 3

    def test_filter_returns_empty_when_no_match(self, test_client_with_db, completed_job):
        """Filters that match nothing return empty list, not error."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export?canonical_name=nonexistent"
        )

        data = response.json()
        assert data["line_items_count"] == 0
        assert data["line_items"] == []

    def test_csv_export_respects_filters(self, test_client_with_db, completed_job):
        """CSV export also applies filters."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export"
            f"?format=csv&min_confidence=0.9"
        )

        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)
        # Header + 3 filtered rows (revenue, cogs, total_assets)
        assert len(rows) == 4


# ============================================================================
# ERROR CASE TESTS
# ============================================================================


class TestExportErrors:
    """Tests for error handling in export endpoint."""

    def test_export_job_not_found(self, test_client_with_db):
        """Returns 404 for non-existent job."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = test_client_with_db.get(f"/api/v1/jobs/{fake_id}/export")
        assert response.status_code == 404

    def test_export_invalid_job_id(self, test_client_with_db):
        """Returns 400 for malformed job ID."""
        response = test_client_with_db.get("/api/v1/jobs/not-a-uuid/export")
        assert response.status_code == 400

    def test_export_job_not_completed(self, test_client_with_db, pending_job):
        """Returns 409 for jobs that haven't completed yet."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{pending_job.job_id}/export"
        )
        assert response.status_code == 409
        assert "not completed" in response.json()["detail"]

    def test_export_invalid_format(self, test_client_with_db, completed_job):
        """Returns 400 for unsupported format."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export?format=xml"
        )
        assert response.status_code == 400

    def test_export_invalid_min_confidence(self, test_client_with_db, completed_job):
        """Returns 400 for out-of-range confidence."""
        response = test_client_with_db.get(
            f"/api/v1/jobs/{completed_job.job_id}/export?min_confidence=1.5"
        )
        assert response.status_code == 400
