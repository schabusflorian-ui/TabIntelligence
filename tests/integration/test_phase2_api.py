"""
API/User tests for Phase 2: Cross-Company Normalization endpoints.

End-to-end tests through HTTP endpoints using test_client_with_db fixture
(auth bypassed + SQLite in-memory). Tests the full request/response cycle
including parameter validation, error handling, and response shapes.
"""


import pytest
from fastapi.testclient import TestClient

from src.db import crud

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def seeded_client(test_db, mock_api_key):
    """Client with seeded data for Phase 2 endpoint testing.

    Creates its own TestClient with DB + auth overrides, then seeds data.
    """
    from src.api.main import app
    from src.auth.dependencies import get_current_api_key
    from src.db.session import get_db

    def override_get_db():
        session = test_db()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_api_key] = lambda: mock_api_key
    client = TestClient(app)

    db = test_db()
    try:
        # Create 3 entities with varying metadata
        alpha = crud.create_entity(
            db, name="Alpha Corp", industry="Tech",
            fiscal_year_end=12, default_currency="USD", reporting_standard="GAAP",
        )
        beta = crud.create_entity(
            db, name="Beta Inc", industry="Tech",
            fiscal_year_end=3, default_currency="EUR", reporting_standard="IFRS",
        )
        gamma = crud.create_entity(
            db, name="Gamma LLC", industry="Finance",
            fiscal_year_end=12, default_currency="USD",
        )

        entities = {"alpha": alpha, "beta": beta, "gamma": gamma}

        # Create files and jobs per entity
        jobs = {}
        for key, entity in entities.items():
            file = crud.create_file(
                db, filename=f"{key}.xlsx", file_size=100, entity_id=entity.id,
            )
            job = crud.create_extraction_job(db, file_id=file.file_id)
            jobs[key] = job
        entities["alpha_job"] = jobs["alpha"]
        entities["beta_job"] = jobs["beta"]
        entities["gamma_job"] = jobs["gamma"]

        # Seed facts for alpha
        crud.persist_extraction_facts(db, entities["alpha_job"].job_id, alpha.id, [
            {
                "canonical_name": "revenue",
                "original_label": "Revenue",
                "values": {"FY2024": 1000000},
                "confidence": 0.95,
                "period_normalized": {"FY2024": "FY2024"},
                "taxonomy_category": "income_statement",
                "currency_code": "USD",
            },
            {
                "canonical_name": "ebitda",
                "original_label": "EBITDA",
                "values": {"FY2024": 250000},
                "confidence": 0.90,
                "period_normalized": {"FY2024": "FY2024"},
                "taxonomy_category": "income_statement",
            },
        ])

        # Seed facts for beta
        crud.persist_extraction_facts(db, entities["beta_job"].job_id, beta.id, [
            {
                "canonical_name": "revenue",
                "original_label": "Net Sales",
                "values": {"FY2024": 1500000},
                "confidence": 0.92,
                "period_normalized": {"FY2024": "FY2024"},
                "taxonomy_category": "income_statement",
                "currency_code": "EUR",
            },
            {
                "canonical_name": "ebitda",
                "original_label": "EBITDA",
                "values": {"FY2024": 400000},
                "confidence": 0.88,
                "period_normalized": {"FY2024": "FY2024"},
                "taxonomy_category": "income_statement",
            },
        ])

        # Seed facts for gamma
        crud.persist_extraction_facts(db, entities["gamma_job"].job_id, gamma.id, [
            {
                "canonical_name": "revenue",
                "original_label": "Revenue",
                "values": {"FY2024": 5000000},
                "confidence": 0.88,
                "period_normalized": {"FY2024": "FY2024"},
                "taxonomy_category": "income_statement",
                "currency_code": "USD",
            },
            {
                "canonical_name": "ebitda",
                "original_label": "EBITDA",
                "values": {"FY2024": 800000},
                "confidence": 0.85,
                "period_normalized": {"FY2024": "FY2024"},
                "taxonomy_category": "income_statement",
            },
        ])

        # Seed unmapped labels
        crud.persist_extraction_facts(db, entities["alpha_job"].job_id, alpha.id, [
            {"canonical_name": "unmapped", "original_label": "Custom KPI", "values": {},
             "sheet_name": "P&L"},
        ])
        crud.persist_extraction_facts(db, entities["beta_job"].job_id, beta.id, [
            {"canonical_name": "unmapped", "original_label": "custom kpi", "values": {},
             "sheet_name": "Income"},
        ])

        yield client, entities
    finally:
        db.close()
        app.dependency_overrides.clear()


# ============================================================================
# Entity CRUD — Metadata Fields
# ============================================================================


class TestEntityMetadataAPI:
    """Test entity endpoints return and accept Phase 2 metadata fields."""

    def test_create_entity_with_metadata(self, test_client_with_db):
        resp = test_client_with_db.post("/api/v1/entities/", json={
            "name": "New Corp",
            "industry": "Retail",
            "fiscal_year_end": 6,
            "default_currency": "GBP",
            "reporting_standard": "IFRS",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["fiscal_year_end"] == 6
        assert data["default_currency"] == "GBP"
        assert data["reporting_standard"] == "IFRS"

    def test_create_entity_without_metadata(self, test_client_with_db):
        resp = test_client_with_db.post("/api/v1/entities/", json={
            "name": "Plain Corp",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["fiscal_year_end"] is None
        assert data["default_currency"] is None
        assert data["reporting_standard"] is None

    def test_create_entity_invalid_fiscal_year(self, test_client_with_db):
        resp = test_client_with_db.post("/api/v1/entities/", json={
            "name": "Bad Corp",
            "fiscal_year_end": 13,
        })
        assert resp.status_code == 422

    def test_create_entity_invalid_currency_length(self, test_client_with_db):
        resp = test_client_with_db.post("/api/v1/entities/", json={
            "name": "Bad Corp",
            "default_currency": "TOOLONG",
        })
        assert resp.status_code == 422

    def test_list_entities_includes_metadata(self, seeded_client):
        client, entities = seeded_client
        resp = client.get("/api/v1/entities/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 3
        entity_with_fye = next(
            (e for e in data["entities"] if e["name"] == "Alpha Corp"), None
        )
        assert entity_with_fye is not None
        assert entity_with_fye["fiscal_year_end"] == 12
        assert entity_with_fye["default_currency"] == "USD"

    def test_get_entity_detail_includes_metadata(self, seeded_client):
        client, entities = seeded_client
        eid = str(entities["alpha"].id)
        resp = client.get(f"/api/v1/entities/{eid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fiscal_year_end"] == 12
        assert data["default_currency"] == "USD"
        assert data["reporting_standard"] == "GAAP"

    def test_update_entity_metadata(self, seeded_client):
        client, entities = seeded_client
        eid = str(entities["alpha"].id)
        resp = client.patch(f"/api/v1/entities/{eid}", json={
            "fiscal_year_end": 6,
            "default_currency": "JPY",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["fiscal_year_end"] == 6
        assert data["default_currency"] == "JPY"
        # reporting_standard should remain unchanged
        assert data["reporting_standard"] == "GAAP"


# ============================================================================
# Cross-Entity Comparison Endpoint
# ============================================================================


class TestCompareEndpoint:
    """Test GET /api/v1/analytics/compare with Phase 2 enhancements."""

    def test_compare_requires_period_param(self, seeded_client):
        client, entities = seeded_client
        ids = f"{entities['alpha'].id},{entities['beta'].id}"
        resp = client.get(f"/api/v1/analytics/compare?entity_ids={ids}&canonical_names=revenue")
        assert resp.status_code == 400
        assert "period" in resp.json()["detail"].lower()

    def test_compare_by_period(self, seeded_client):
        client, entities = seeded_client
        ids = f"{entities['alpha'].id},{entities['beta'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={ids}"
            f"&canonical_names=revenue&period=FY2024"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "FY2024"
        assert len(data["comparisons"]) == 1
        assert data["comparisons"][0]["canonical_name"] == "revenue"
        assert len(data["comparisons"][0]["entities"]) == 2

    def test_compare_by_period_normalized(self, seeded_client):
        client, entities = seeded_client
        ids = f"{entities['alpha'].id},{entities['beta'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={ids}"
            f"&canonical_names=revenue&period_normalized=FY2024"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["period_normalized"] == "FY2024"

    def test_compare_by_year(self, seeded_client):
        client, entities = seeded_client
        ids = f"{entities['alpha'].id},{entities['beta'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={ids}"
            f"&canonical_names=revenue&year=2024"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["year"] == 2024

    def test_compare_fiscal_year_alignment_warning(self, seeded_client):
        """Alpha (Dec FYE) vs Beta (Mar FYE) should generate alignment warning."""
        client, entities = seeded_client
        ids = f"{entities['alpha'].id},{entities['beta'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={ids}"
            f"&canonical_names=revenue&period=FY2024"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["normalization_notes"]) > 0
        assert "fiscal year" in data["normalization_notes"][0].lower()

    def test_compare_no_warning_same_fye(self, seeded_client):
        """Alpha (Dec) vs Gamma (Dec) should NOT generate alignment warning."""
        client, entities = seeded_client
        ids = f"{entities['alpha'].id},{entities['gamma'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={ids}"
            f"&canonical_names=revenue&period=FY2024"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["normalization_notes"]) == 0

    def test_compare_with_metadata(self, seeded_client):
        client, entities = seeded_client
        ids = f"{entities['alpha'].id},{entities['beta'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={ids}"
            f"&canonical_names=revenue&period=FY2024&include_metadata=true"
        )
        assert resp.status_code == 200
        data = resp.json()
        entity_vals = data["comparisons"][0]["entities"]
        # At least one entity should have currency_code
        currencies = [ev.get("currency_code") for ev in entity_vals if ev.get("currency_code")]
        assert len(currencies) > 0

    def test_compare_multiple_canonical_names(self, seeded_client):
        client, entities = seeded_client
        ids = f"{entities['alpha'].id},{entities['beta'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={ids}"
            f"&canonical_names=revenue,ebitda&period=FY2024"
        )
        assert resp.status_code == 200
        data = resp.json()
        names = [c["canonical_name"] for c in data["comparisons"]]
        assert "revenue" in names
        assert "ebitda" in names

    def test_compare_invalid_entity_id(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(
            "/api/v1/analytics/compare?entity_ids=not-a-uuid"
            "&canonical_names=revenue&period=FY2024"
        )
        assert resp.status_code == 400

    def test_compare_missing_entity_shows_null(self, seeded_client):
        """Entity with no matching facts should have amount=null."""
        client, entities = seeded_client
        # Gamma has no "net_income" facts
        ids = f"{entities['alpha'].id},{entities['gamma'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={ids}"
            f"&canonical_names=net_income&period=FY2024"
        )
        assert resp.status_code == 200
        data = resp.json()
        comp = data["comparisons"][0]
        assert any(ev["amount"] is None for ev in comp["entities"])


# ============================================================================
# Unmapped Labels Endpoint
# ============================================================================


class TestUnmappedLabelsEndpoint:
    """Test GET /api/v1/analytics/unmapped-labels."""

    def test_unmapped_labels_200(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/v1/analytics/unmapped-labels")
        assert resp.status_code == 200
        data = resp.json()
        assert "labels" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    def test_unmapped_labels_returns_seeded_data(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/v1/analytics/unmapped-labels")
        data = resp.json()
        assert data["total"] > 0
        labels = [l["label_normalized"] for l in data["labels"]]
        assert "custom kpi" in labels

    def test_unmapped_labels_min_occurrences(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/v1/analytics/unmapped-labels?min_occurrences=2")
        assert resp.status_code == 200
        data = resp.json()
        for label in data["labels"]:
            assert label["total_occurrences"] >= 2

    def test_unmapped_labels_min_entities(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/v1/analytics/unmapped-labels?min_entities=2")
        assert resp.status_code == 200
        data = resp.json()
        for label in data["labels"]:
            assert label["entity_count"] >= 2

    def test_unmapped_labels_pagination(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/v1/analytics/unmapped-labels?limit=1&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 1
        assert data["offset"] == 0
        assert len(data["labels"]) <= 1

    def test_unmapped_labels_includes_variants(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/v1/analytics/unmapped-labels")
        data = resp.json()
        custom_kpi = next(
            (l for l in data["labels"] if l["label_normalized"] == "custom kpi"), None
        )
        if custom_kpi:
            assert len(custom_kpi["original_variants"]) > 0

    def test_unmapped_labels_includes_entity_ids(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/v1/analytics/unmapped-labels")
        data = resp.json()
        custom_kpi = next(
            (l for l in data["labels"] if l["label_normalized"] == "custom kpi"), None
        )
        if custom_kpi:
            assert len(custom_kpi["entity_ids"]) >= 2


# ============================================================================
# Anomaly Detection Endpoint
# ============================================================================


class TestAnomaliesEndpoint:
    """Test GET /api/v1/analytics/anomalies."""

    def test_anomalies_requires_period(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/v1/analytics/anomalies?canonical_names=revenue")
        assert resp.status_code == 400
        assert "period" in resp.json()["detail"].lower()

    def test_anomalies_requires_canonical_names(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/v1/analytics/anomalies?period_normalized=FY2024")
        assert resp.status_code == 422  # missing required param

    def test_anomalies_invalid_method(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(
            "/api/v1/analytics/anomalies?canonical_names=revenue"
            "&period_normalized=FY2024&method=invalid"
        )
        assert resp.status_code == 400
        assert "method" in resp.json()["detail"].lower()

    def test_anomalies_iqr_method(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(
            "/api/v1/analytics/anomalies?canonical_names=revenue"
            "&period_normalized=FY2024&method=iqr"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["method"] == "iqr"
        assert "summaries" in data
        assert "total_outliers" in data
        assert "total_items" in data

    def test_anomalies_zscore_method(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(
            "/api/v1/analytics/anomalies?canonical_names=revenue"
            "&period_normalized=FY2024&method=zscore"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["method"] == "zscore"

    def test_anomalies_by_year(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(
            "/api/v1/analytics/anomalies?canonical_names=revenue&year=2024"
        )
        assert resp.status_code == 200

    def test_anomalies_response_structure(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(
            "/api/v1/analytics/anomalies?canonical_names=revenue"
            "&period_normalized=FY2024"
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["summaries"]:
            summary = data["summaries"][0]
            assert "canonical_name" in summary
            assert "period" in summary
            assert "peer_count" in summary
            assert "peer_mean" in summary
            assert "peer_median" in summary
            assert "outlier_count" in summary
            assert "items" in summary
            if summary["items"]:
                item = summary["items"][0]
                assert "entity_id" in item
                assert "value" in item
                assert "is_outlier" in item

    def test_anomalies_with_entity_filter(self, seeded_client):
        client, entities = seeded_client
        eid = str(entities["alpha"].id)
        resp = client.get(
            f"/api/v1/analytics/anomalies?canonical_names=revenue"
            f"&period_normalized=FY2024&entity_ids={eid}"
        )
        assert resp.status_code == 200
        # With only 1 entity, fewer than 3 data points means empty summaries
        data = resp.json()
        assert data["total_items"] == 0  # need >= 3 for anomaly detection

    def test_anomalies_custom_threshold(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(
            "/api/v1/analytics/anomalies?canonical_names=revenue"
            "&period_normalized=FY2024&threshold=0.5"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["threshold"] == 0.5

    def test_anomalies_multiple_canonical_names(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(
            "/api/v1/analytics/anomalies?canonical_names=revenue,ebitda"
            "&period_normalized=FY2024"
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["summaries"]:
            names = {s["canonical_name"] for s in data["summaries"]}
            # At least one of them should appear
            assert names.issubset({"revenue", "ebitda"})

    def test_anomalies_invalid_entity_id(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(
            "/api/v1/analytics/anomalies?canonical_names=revenue"
            "&period_normalized=FY2024&entity_ids=not-a-uuid"
        )
        assert resp.status_code == 400


# ============================================================================
# Facts Endpoint — Normalization Metadata
# ============================================================================


class TestFactsEndpointMetadata:
    """Test that GET /api/v1/analytics/facts returns normalization metadata."""

    def test_facts_include_period_normalized(self, seeded_client):
        client, entities = seeded_client
        eid = str(entities["alpha"].id)
        resp = client.get(f"/api/v1/analytics/facts?entity_id={eid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] > 0
        fact = data["facts"][0]
        assert "period_normalized" in fact
        assert "currency_code" in fact
        assert "source_unit" in fact
        assert "source_scale" in fact

    def test_facts_metadata_values_correct(self, seeded_client):
        client, entities = seeded_client
        eid = str(entities["alpha"].id)
        resp = client.get(
            f"/api/v1/analytics/facts?entity_id={eid}&canonical_name=revenue"
        )
        assert resp.status_code == 200
        data = resp.json()
        revenue_fact = data["facts"][0]
        assert revenue_fact["period_normalized"] == "FY2024"
        assert revenue_fact["currency_code"] == "USD"
