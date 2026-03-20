"""
API-level tests for currency conversion in the compare endpoint.

Tests the `target_currency` parameter on GET /api/v1/analytics/compare
and verifies FX conversion logic.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.db.models import Entity, ExtractionFact, ExtractionJob, File, FxRateCache

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def comparison_data(test_db):
    """Seed two entities with facts in different currencies for comparison."""
    db = test_db()

    entity_us = Entity(
        id=uuid4(), name="US Corp", default_currency="USD", fiscal_year_end=12
    )
    entity_eu = Entity(
        id=uuid4(), name="EU Corp", default_currency="EUR", fiscal_year_end=12
    )
    db.add_all([entity_us, entity_eu])
    db.flush()

    # Create files and jobs for each entity
    file_us = File(file_id=uuid4(), filename="us_model.xlsx", s3_key="s3/us.xlsx", file_size=1024)
    file_eu = File(file_id=uuid4(), filename="eu_model.xlsx", s3_key="s3/eu.xlsx", file_size=1024)
    file_us.entity_id = entity_us.id
    file_eu.entity_id = entity_eu.id
    db.add_all([file_us, file_eu])
    db.flush()

    job_us = ExtractionJob(job_id=uuid4(), file_id=file_us.file_id)
    job_eu = ExtractionJob(job_id=uuid4(), file_id=file_eu.file_id)
    db.add_all([job_us, job_eu])
    db.flush()

    # Facts
    fact_us = ExtractionFact(
        job_id=job_us.job_id,
        entity_id=entity_us.id,
        canonical_name="revenue",
        original_label="Revenue",
        period="FY2024",
        period_normalized="FY2024",
        value=Decimal("1000000"),
        confidence=0.95,
        currency_code="USD",
        taxonomy_category="income_statement",
    )
    fact_eu = ExtractionFact(
        job_id=job_eu.job_id,
        entity_id=entity_eu.id,
        canonical_name="revenue",
        original_label="Umsatz",
        period="FY2024",
        period_normalized="FY2024",
        value=Decimal("800000"),
        confidence=0.92,
        currency_code="EUR",
        taxonomy_category="income_statement",
    )
    db.add_all([fact_us, fact_eu])

    # Cache a specific EUR/USD rate
    fx = FxRateCache(
        from_currency="EUR",
        to_currency="USD",
        rate_date="2024-01-01",
        rate=Decimal("1.10"),
        source="test",
    )
    db.add(fx)
    db.commit()

    return {
        "entity_us": entity_us,
        "entity_eu": entity_eu,
        "db": db,
    }


@pytest.fixture
def compare_client(test_db, mock_api_key, comparison_data):
    """Test client with seeded comparison data."""
    from fastapi.testclient import TestClient

    from src.api.main import app
    from src.auth.dependencies import get_current_api_key
    from src.db.session import get_db

    def override_get_db():
        db = test_db()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_api_key] = lambda: mock_api_key
    client = TestClient(app)
    yield client, comparison_data
    app.dependency_overrides.clear()


# ============================================================================
# Compare Endpoint Tests (Currency)
# ============================================================================


class TestCompareWithCurrency:
    def test_compare_without_target_currency(self, compare_client):
        """Compare without currency conversion returns raw amounts."""
        client, data = compare_client
        eids = f"{data['entity_us'].id},{data['entity_eu'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}&canonical_names=revenue&period=FY2024"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["comparisons"]) == 1
        comp = body["comparisons"][0]
        assert comp["canonical_name"] == "revenue"
        amounts = {e["entity_id"]: e["amount"] for e in comp["entities"]}
        assert amounts[str(data["entity_us"].id)] == 1000000.0
        assert amounts[str(data["entity_eu"].id)] == 800000.0

    def test_compare_with_target_currency(self, compare_client):
        """Compare with target_currency=USD converts EUR values."""
        client, data = compare_client
        eids = f"{data['entity_us'].id},{data['entity_eu'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}&canonical_names=revenue"
            f"&period=FY2024&target_currency=USD"
        )
        assert resp.status_code == 200
        body = resp.json()
        comp = body["comparisons"][0]

        for ev in comp["entities"]:
            if ev["entity_id"] == str(data["entity_eu"].id):
                # EUR -> USD conversion should have happened
                assert ev.get("original_amount") == 800000.0
                assert ev.get("fx_rate_used") is not None
                # Converted amount should be > original (EUR > 1 USD)
                assert ev["amount"] > 800000.0
            elif ev["entity_id"] == str(data["entity_us"].id):
                # USD -> USD: no conversion needed
                assert ev["amount"] == 1000000.0

    def test_compare_currency_adds_normalization_note(self, compare_client):
        """When target_currency is set, normalization_notes includes a message."""
        client, data = compare_client
        eids = f"{data['entity_us'].id},{data['entity_eu'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}&canonical_names=revenue"
            f"&period=FY2024&target_currency=USD"
        )
        assert resp.status_code == 200
        notes = resp.json()["normalization_notes"]
        assert any("converted to USD" in n for n in notes)

    def test_compare_period_normalized(self, compare_client):
        """Compare using period_normalized instead of exact period."""
        client, data = compare_client
        eids = f"{data['entity_us'].id},{data['entity_eu'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}&canonical_names=revenue"
            f"&period_normalized=FY2024"
        )
        assert resp.status_code == 200
        comp = resp.json()["comparisons"][0]
        assert len(comp["entities"]) == 2

    def test_compare_year(self, compare_client):
        """Compare using year filter."""
        client, data = compare_client
        eids = f"{data['entity_us'].id},{data['entity_eu'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}&canonical_names=revenue&year=2024"
        )
        assert resp.status_code == 200
        comp = resp.json()["comparisons"][0]
        assert len(comp["entities"]) == 2

    def test_compare_no_period_param_returns_400(self, compare_client):
        """Must provide at least one of period, period_normalized, or year."""
        client, data = compare_client
        eids = f"{data['entity_us'].id},{data['entity_eu'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}&canonical_names=revenue"
        )
        assert resp.status_code == 400

    def test_compare_include_metadata(self, compare_client):
        """include_metadata=true adds currency_code and fiscal_year_end."""
        client, data = compare_client
        eids = f"{data['entity_us'].id},{data['entity_eu'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}&canonical_names=revenue"
            f"&period=FY2024&include_metadata=true"
        )
        assert resp.status_code == 200
        comp = resp.json()["comparisons"][0]
        for ev in comp["entities"]:
            if ev["amount"] is not None:
                assert "currency_code" in ev
                assert "fiscal_year_end" in ev
