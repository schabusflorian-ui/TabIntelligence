"""Tests for Phase 7 — Comparison endpoints (structured statement + multi-period comparison)."""

import uuid
from decimal import Decimal

import pytest

from src.db import crud
from src.db.models import ExtractionFact


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def setup_comparison_data(test_db):
    """Create test entity, file, job, and extraction facts for comparison tests."""
    db = test_db()
    try:
        # Create entity
        entity = crud.create_entity(db, name="Acme Corp", industry="Technology")

        # Create file linked to entity
        file = crud.create_file(
            db,
            filename="acme_financials.xlsx",
            file_size=1024,
            entity_id=entity.id,
        )

        # Create extraction job
        job = crud.create_extraction_job(db, file_id=file.file_id)

        # Create extraction facts — income statement items
        line_items = [
            {
                "canonical_name": "revenue",
                "original_label": "Revenue",
                "values": {"FY2022": 100000, "FY2023": 120000, "FY2024": 150000},
                "confidence": 0.95,
                "taxonomy_category": "income_statement",
                "hierarchy_level": 0,
                "method": "exact",
            },
            {
                "canonical_name": "cogs",
                "original_label": "Cost of Goods Sold",
                "values": {"FY2022": 40000, "FY2023": 48000, "FY2024": 55000},
                "confidence": 0.90,
                "taxonomy_category": "income_statement",
                "hierarchy_level": 1,
                "method": "fuzzy",
            },
            {
                "canonical_name": "gross_profit",
                "original_label": "Gross Profit",
                "values": {"FY2022": 60000, "FY2023": 72000, "FY2024": 95000},
                "confidence": 0.92,
                "taxonomy_category": "income_statement",
                "hierarchy_level": 0,
                "method": "exact",
            },
            # Balance sheet item
            {
                "canonical_name": "total_assets",
                "original_label": "Total Assets",
                "values": {"FY2022": 500000, "FY2023": 600000},
                "confidence": 0.88,
                "taxonomy_category": "balance_sheet",
                "hierarchy_level": 0,
                "method": "exact",
            },
        ]

        crud.persist_extraction_facts(
            db,
            job_id=job.job_id,
            entity_id=entity.id,
            line_items=line_items,
        )

        yield {
            "entity": entity,
            "entity_id": str(entity.id),
            "file": file,
            "job": job,
            "db": db,
        }
    finally:
        db.close()


@pytest.fixture
def empty_entity(test_db):
    """Create an entity with no extraction facts."""
    db = test_db()
    try:
        entity = crud.create_entity(db, name="Empty Corp", industry="Finance")
        yield {
            "entity": entity,
            "entity_id": str(entity.id),
            "db": db,
        }
    finally:
        db.close()


# ============================================================================
# Structured Statement Endpoint Tests
# ============================================================================


class TestStructuredStatement:
    """Tests for GET /api/v1/analytics/entity/{entity_id}/statement."""

    def test_statement_with_data(self, test_client_with_db, setup_comparison_data):
        """Test structured statement returns hierarchical data."""
        entity_id = setup_comparison_data["entity_id"]
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{entity_id}/statement?category=income_statement"
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["entity_id"] == entity_id
        assert data["category"] == "income_statement"
        assert data["entity_name"] == "Acme Corp"
        assert len(data["periods"]) > 0
        assert "FY2022" in data["periods"]
        assert "FY2023" in data["periods"]
        assert len(data["items"]) > 0
        assert data["total_items"] > 0

        # Verify items have correct structure
        for item in data["items"]:
            assert "canonical_name" in item
            assert "values" in item
            assert "hierarchy_level" in item
            assert "children" in item

    def test_statement_empty_result(self, test_client_with_db, empty_entity):
        """Test structured statement with no data returns empty items."""
        entity_id = empty_entity["entity_id"]
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{entity_id}/statement?category=income_statement"
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["entity_id"] == entity_id
        assert data["category"] == "income_statement"
        assert data["items"] == []
        assert data["periods"] == []
        assert data["total_items"] == 0

    def test_statement_different_category(self, test_client_with_db, setup_comparison_data):
        """Test structured statement filters by category."""
        entity_id = setup_comparison_data["entity_id"]

        # Balance sheet should have total_assets
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{entity_id}/statement?category=balance_sheet"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["category"] == "balance_sheet"
        canonical_names = [item["canonical_name"] for item in data["items"]]
        # total_assets or a parent containing it should be present
        assert len(data["items"]) > 0

    def test_statement_invalid_category(self, test_client_with_db, setup_comparison_data):
        """Test structured statement rejects invalid category."""
        entity_id = setup_comparison_data["entity_id"]
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{entity_id}/statement?category=invalid_category"
        )
        assert resp.status_code == 400
        assert "Invalid category" in resp.json()["detail"]

    def test_statement_missing_category(self, test_client_with_db, setup_comparison_data):
        """Test structured statement requires category parameter."""
        entity_id = setup_comparison_data["entity_id"]
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{entity_id}/statement"
        )
        assert resp.status_code == 422  # Missing required query param

    def test_statement_invalid_entity_id(self, test_client_with_db):
        """Test structured statement rejects invalid entity_id format."""
        resp = test_client_with_db.get(
            "/api/v1/analytics/entity/not-a-uuid/statement?category=income_statement"
        )
        assert resp.status_code == 400
        assert "Invalid entity_id" in resp.json()["detail"]

    def test_statement_entity_not_found(self, test_client_with_db):
        """Test structured statement returns 404 for nonexistent entity."""
        fake_id = str(uuid.uuid4())
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{fake_id}/statement?category=income_statement"
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ============================================================================
# Multi-Period Comparison Endpoint Tests
# ============================================================================


class TestMultiPeriodComparison:
    """Tests for GET /api/v1/analytics/entity/{entity_id}/compare-periods."""

    def test_compare_periods_happy_path(self, test_client_with_db, setup_comparison_data):
        """Test multi-period comparison returns values and deltas."""
        entity_id = setup_comparison_data["entity_id"]
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{entity_id}/compare-periods"
            f"?canonical_names=revenue,cogs&periods=FY2022,FY2023,FY2024"
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["entity_id"] == entity_id
        assert data["entity_name"] == "Acme Corp"
        assert data["canonical_names"] == ["revenue", "cogs"]
        assert data["periods"] == ["FY2022", "FY2023", "FY2024"]
        assert len(data["items"]) == 2

        # Check revenue item
        revenue_item = next(i for i in data["items"] if i["canonical_name"] == "revenue")
        assert len(revenue_item["values"]) == 3
        assert revenue_item["values"][0]["period"] == "FY2022"
        assert revenue_item["values"][0]["value"] == 100000.0
        assert revenue_item["values"][1]["value"] == 120000.0
        assert revenue_item["values"][2]["value"] == 150000.0

        # Check deltas
        assert len(revenue_item["deltas"]) == 2
        delta_0 = revenue_item["deltas"][0]
        assert delta_0["from_period"] == "FY2022"
        assert delta_0["to_period"] == "FY2023"
        assert delta_0["absolute_change"] == 20000.0
        assert delta_0["pct_change"] == 20.0

        delta_1 = revenue_item["deltas"][1]
        assert delta_1["from_period"] == "FY2023"
        assert delta_1["to_period"] == "FY2024"
        assert delta_1["absolute_change"] == 30000.0
        assert delta_1["pct_change"] == 25.0

    def test_compare_periods_missing_period(self, test_client_with_db, setup_comparison_data):
        """Test comparison with a period that has no data returns null values."""
        entity_id = setup_comparison_data["entity_id"]
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{entity_id}/compare-periods"
            f"?canonical_names=revenue&periods=FY2022,FY2025"
        )
        assert resp.status_code == 200
        data = resp.json()

        revenue_item = data["items"][0]
        # FY2022 should have a value, FY2025 should be None
        fy2022_val = next(v for v in revenue_item["values"] if v["period"] == "FY2022")
        fy2025_val = next(v for v in revenue_item["values"] if v["period"] == "FY2025")
        assert fy2022_val["value"] == 100000.0
        assert fy2025_val["value"] is None

        # Delta should have null changes
        delta = revenue_item["deltas"][0]
        assert delta["absolute_change"] is None
        assert delta["pct_change"] is None

    def test_compare_periods_invalid_entity(self, test_client_with_db):
        """Test comparison with nonexistent entity returns 404."""
        fake_id = str(uuid.uuid4())
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{fake_id}/compare-periods"
            f"?canonical_names=revenue&periods=FY2023"
        )
        assert resp.status_code == 404

    def test_compare_periods_invalid_entity_id_format(self, test_client_with_db):
        """Test comparison with invalid entity_id format returns 400."""
        resp = test_client_with_db.get(
            "/api/v1/analytics/entity/not-a-uuid/compare-periods"
            "?canonical_names=revenue&periods=FY2023"
        )
        assert resp.status_code == 400

    def test_compare_periods_missing_params(self, test_client_with_db, setup_comparison_data):
        """Test comparison requires canonical_names and periods params."""
        entity_id = setup_comparison_data["entity_id"]

        # Missing canonical_names
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{entity_id}/compare-periods?periods=FY2023"
        )
        assert resp.status_code == 422

        # Missing periods
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{entity_id}/compare-periods?canonical_names=revenue"
        )
        assert resp.status_code == 422

    def test_compare_periods_single_period(self, test_client_with_db, setup_comparison_data):
        """Test comparison with single period returns no deltas."""
        entity_id = setup_comparison_data["entity_id"]
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{entity_id}/compare-periods"
            f"?canonical_names=revenue&periods=FY2023"
        )
        assert resp.status_code == 200
        data = resp.json()

        revenue_item = data["items"][0]
        assert len(revenue_item["values"]) == 1
        assert revenue_item["values"][0]["value"] == 120000.0
        assert len(revenue_item["deltas"]) == 0


# ============================================================================
# Auth Tests
# ============================================================================


class TestComparisonAuth:
    """Test that comparison endpoints require authentication."""

    def test_statement_requires_auth(self, unauthenticated_client):
        """Test structured statement endpoint returns 401 without auth."""
        fake_id = str(uuid.uuid4())
        resp = unauthenticated_client.get(
            f"/api/v1/analytics/entity/{fake_id}/statement?category=income_statement"
        )
        assert resp.status_code == 401

    def test_compare_periods_requires_auth(self, unauthenticated_client):
        """Test compare-periods endpoint returns 401 without auth."""
        fake_id = str(uuid.uuid4())
        resp = unauthenticated_client.get(
            f"/api/v1/analytics/entity/{fake_id}/compare-periods"
            f"?canonical_names=revenue&periods=FY2023"
        )
        assert resp.status_code == 401


# ============================================================================
# CRUD Function Tests
# ============================================================================


class TestStructuredStatementCRUD:
    """Tests for the get_structured_statement CRUD function."""

    def test_structured_statement_groups_by_period(self, test_db):
        """Test that facts are correctly grouped by canonical_name and period."""
        db = test_db()
        try:
            entity = crud.create_entity(db, name="Test Entity")
            file = crud.create_file(db, filename="test.xlsx", file_size=100, entity_id=entity.id)
            job = crud.create_extraction_job(db, file_id=file.file_id)

            line_items = [
                {
                    "canonical_name": "revenue",
                    "original_label": "Revenue",
                    "values": {"FY2023": 500000, "FY2024": 600000},
                    "confidence": 0.9,
                    "taxonomy_category": "income_statement",
                    "method": "exact",
                },
            ]
            crud.persist_extraction_facts(db, job.job_id, entity.id, line_items)

            result = crud.get_structured_statement(db, entity.id, "income_statement")

            assert result["category"] == "income_statement"
            assert result["entity_name"] == "Test Entity"
            assert "FY2023" in result["periods"]
            assert "FY2024" in result["periods"]
            assert len(result["items"]) > 0

            # Find revenue item
            def find_item(items, cn):
                for item in items:
                    if item["canonical_name"] == cn:
                        return item
                    found = find_item(item.get("children", []), cn)
                    if found:
                        return found
                return None

            rev = find_item(result["items"], "revenue")
            assert rev is not None
            assert rev["values"]["FY2023"] == 500000.0
            assert rev["values"]["FY2024"] == 600000.0
        finally:
            db.close()

    def test_structured_statement_empty(self, test_db):
        """Test empty result when no facts exist for category."""
        db = test_db()
        try:
            entity = crud.create_entity(db, name="Empty Entity")
            result = crud.get_structured_statement(db, entity.id, "income_statement")

            assert result["items"] == []
            assert result["periods"] == []
            assert result["total_items"] == 0
        finally:
            db.close()


class TestMultiPeriodComparisonCRUD:
    """Tests for the get_multi_period_comparison CRUD function."""

    def test_comparison_computes_deltas(self, test_db):
        """Test that absolute and percentage deltas are computed correctly."""
        db = test_db()
        try:
            entity = crud.create_entity(db, name="Delta Test")
            file = crud.create_file(db, filename="test.xlsx", file_size=100, entity_id=entity.id)
            job = crud.create_extraction_job(db, file_id=file.file_id)

            line_items = [
                {
                    "canonical_name": "revenue",
                    "original_label": "Revenue",
                    "values": {"FY2022": 100, "FY2023": 150},
                    "confidence": 0.9,
                    "taxonomy_category": "income_statement",
                    "method": "exact",
                },
            ]
            crud.persist_extraction_facts(db, job.job_id, entity.id, line_items)

            result = crud.get_multi_period_comparison(
                db, entity.id, ["revenue"], ["FY2022", "FY2023"]
            )

            assert len(result["items"]) == 1
            item = result["items"][0]
            assert item["canonical_name"] == "revenue"
            assert len(item["deltas"]) == 1
            assert item["deltas"][0]["absolute_change"] == 50.0
            assert item["deltas"][0]["pct_change"] == 50.0
        finally:
            db.close()

    def test_comparison_missing_data(self, test_db):
        """Test comparison returns null for missing periods."""
        db = test_db()
        try:
            entity = crud.create_entity(db, name="Missing Test")
            file = crud.create_file(db, filename="test.xlsx", file_size=100, entity_id=entity.id)
            job = crud.create_extraction_job(db, file_id=file.file_id)

            line_items = [
                {
                    "canonical_name": "revenue",
                    "original_label": "Revenue",
                    "values": {"FY2023": 200},
                    "confidence": 0.9,
                    "taxonomy_category": "income_statement",
                    "method": "exact",
                },
            ]
            crud.persist_extraction_facts(db, job.job_id, entity.id, line_items)

            result = crud.get_multi_period_comparison(
                db, entity.id, ["revenue"], ["FY2022", "FY2023"]
            )

            item = result["items"][0]
            # FY2022 should be None
            fy2022 = next(v for v in item["values"] if v["period"] == "FY2022")
            assert fy2022["value"] is None

            # FY2023 should have data
            fy2023 = next(v for v in item["values"] if v["period"] == "FY2023")
            assert fy2023["value"] == 200.0

            # Delta should be null since FY2022 is missing
            assert item["deltas"][0]["absolute_change"] is None
        finally:
            db.close()
