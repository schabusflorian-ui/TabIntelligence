"""
Integration tests for Phase 3: Analytics Intelligence & Currency Normalization.

End-to-end tests exercising the full cross-phase pipeline:
  Entity creation (with metadata) → File upload → Extraction → Fact persistence
  → Analytics (compare + FX conversion, anomalies, unmapped labels, suggestions,
    quality trending)

Uses SQLite in-memory DB + mocked Claude. Tests the complete data flow from
raw Excel through to the intelligence layer.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.db import crud
from src.db.models import (
    Entity,
    EntityPattern,
    ExtractionFact,
    ExtractionJob,
    File,
    FxRateCache,
    LearnedAlias,
    QualitySnapshot,
    Taxonomy,
)
from src.normalization.anomaly_detection import detect_iqr_anomalies, detect_zscore_anomalies
from src.normalization.fx_service import FxService
from src.normalization.suggestion_engine import suggest_for_label


# ============================================================================
# Fixtures — Multi-entity portfolio with full metadata
# ============================================================================


@pytest.fixture
def portfolio(db_session):
    """Create a 4-entity portfolio spanning USD/EUR, different FYEs, GAAP/IFRS.

    Entities:
      - US Tech (USD, FYE=12, GAAP): revenue=1M, ebitda=250K, total_assets=5M
      - EU Mfg  (EUR, FYE=6, IFRS):  revenue=2M, ebitda=400K, total_assets=8M
      - UK Fin  (GBP, FYE=3, IFRS):  revenue=500K, ebitda=80K, total_assets=2M
      - US Outlier (USD, FYE=12, GAAP): revenue=50M (deliberately high)

    Also seeds:
      - Taxonomy items for revenue, ebitda, total_assets
      - EntityPatterns + LearnedAliases for suggestion engine
      - Unmapped labels from extraction
      - FxRateCache entries
      - QualitySnapshots for trending
    """
    # --- Taxonomy ---
    tax_items = [
        Taxonomy(
            id=uuid4(), canonical_name="revenue", category="income_statement",
            display_name="Revenue",
            aliases=["Sales", "Net Revenue", "Total Revenue", "Turnover"],
            definition="Total income", typical_sign="positive",
        ),
        Taxonomy(
            id=uuid4(), canonical_name="ebitda", category="income_statement",
            display_name="EBITDA",
            aliases=["Earnings Before Interest Tax Depreciation Amortization"],
            definition="EBITDA", typical_sign="positive",
        ),
        Taxonomy(
            id=uuid4(), canonical_name="total_assets", category="balance_sheet",
            display_name="Total Assets",
            aliases=["Assets Total", "Sum of Assets"],
            definition="Total assets", typical_sign="positive",
        ),
    ]
    for t in tax_items:
        db_session.add(t)

    # --- Entities ---
    us_tech = crud.create_entity(
        db_session, name="US Tech Inc",
        industry="Technology", fiscal_year_end=12,
        default_currency="USD", reporting_standard="GAAP",
    )
    eu_mfg = crud.create_entity(
        db_session, name="EU Manufacturing AG",
        industry="Manufacturing", fiscal_year_end=6,
        default_currency="EUR", reporting_standard="IFRS",
    )
    uk_fin = crud.create_entity(
        db_session, name="UK Finance PLC",
        industry="Finance", fiscal_year_end=3,
        default_currency="GBP", reporting_standard="IFRS",
    )
    us_outlier = crud.create_entity(
        db_session, name="MegaCorp USA",
        industry="Technology", fiscal_year_end=12,
        default_currency="USD", reporting_standard="GAAP",
    )
    us_mid = crud.create_entity(
        db_session, name="MidCap LLC",
        industry="Technology", fiscal_year_end=12,
        default_currency="USD", reporting_standard="GAAP",
    )

    entities = {
        "us_tech": us_tech, "eu_mfg": eu_mfg,
        "uk_fin": uk_fin, "us_outlier": us_outlier,
        "us_mid": us_mid,
    }

    # --- Files + Jobs ---
    jobs = {}
    for key, entity in entities.items():
        f = crud.create_file(
            db_session, filename=f"{key}.xlsx", file_size=1024, entity_id=entity.id,
        )
        j = crud.create_extraction_job(db_session, file_id=f.file_id)
        jobs[key] = j

    # --- Extraction Facts ---
    fact_data = {
        "us_tech": [
            {"canonical_name": "revenue", "original_label": "Revenue",
             "values": {"FY2024": 1000000, "FY2023": 900000},
             "confidence": 0.95,
             "period_normalized": {"FY2024": "FY2024", "FY2023": "FY2023"},
             "taxonomy_category": "income_statement", "currency_code": "USD"},
            {"canonical_name": "ebitda", "original_label": "EBITDA",
             "values": {"FY2024": 250000},
             "confidence": 0.90,
             "period_normalized": {"FY2024": "FY2024"},
             "taxonomy_category": "income_statement", "currency_code": "USD"},
            {"canonical_name": "total_assets", "original_label": "Total Assets",
             "values": {"FY2024": 5000000},
             "confidence": 0.92,
             "period_normalized": {"FY2024": "FY2024"},
             "taxonomy_category": "balance_sheet", "currency_code": "USD"},
            # Unmapped label
            {"canonical_name": "unmapped", "original_label": "Adjusted Revenue",
             "values": {"FY2024": 1050000},
             "sheet_name": "Income Statement"},
        ],
        "eu_mfg": [
            {"canonical_name": "revenue", "original_label": "Umsatz",
             "values": {"FY2024": 2000000},
             "confidence": 0.92,
             "period_normalized": {"FY2024": "FY2024"},
             "taxonomy_category": "income_statement", "currency_code": "EUR"},
            {"canonical_name": "ebitda", "original_label": "EBITDA",
             "values": {"FY2024": 400000},
             "confidence": 0.88,
             "period_normalized": {"FY2024": "FY2024"},
             "taxonomy_category": "income_statement", "currency_code": "EUR"},
            {"canonical_name": "total_assets", "original_label": "Bilanzsumme",
             "values": {"FY2024": 8000000},
             "confidence": 0.91,
             "period_normalized": {"FY2024": "FY2024"},
             "taxonomy_category": "balance_sheet", "currency_code": "EUR"},
            # Same unmapped label across entities
            {"canonical_name": "unmapped", "original_label": "Adjusted Revenue",
             "values": {"FY2024": 2100000},
             "sheet_name": "P&L"},
        ],
        "uk_fin": [
            {"canonical_name": "revenue", "original_label": "Turnover",
             "values": {"FY2024": 500000},
             "confidence": 0.88,
             "period_normalized": {"FY2024": "FY2024"},
             "taxonomy_category": "income_statement", "currency_code": "GBP"},
            {"canonical_name": "ebitda", "original_label": "EBITDA",
             "values": {"FY2024": 80000},
             "confidence": 0.85,
             "period_normalized": {"FY2024": "FY2024"},
             "taxonomy_category": "income_statement", "currency_code": "GBP"},
            {"canonical_name": "total_assets", "original_label": "Total Assets",
             "values": {"FY2024": 2000000},
             "confidence": 0.89,
             "period_normalized": {"FY2024": "FY2024"},
             "taxonomy_category": "balance_sheet", "currency_code": "GBP"},
        ],
        "us_outlier": [
            {"canonical_name": "revenue", "original_label": "Net Revenue",
             "values": {"FY2024": 50000000},  # 50x larger — outlier
             "confidence": 0.94,
             "period_normalized": {"FY2024": "FY2024"},
             "taxonomy_category": "income_statement", "currency_code": "USD"},
        ],
        "us_mid": [
            {"canonical_name": "revenue", "original_label": "Revenue",
             "values": {"FY2024": 1200000},
             "confidence": 0.93,
             "period_normalized": {"FY2024": "FY2024"},
             "taxonomy_category": "income_statement", "currency_code": "USD"},
        ],
    }

    for key, items in fact_data.items():
        crud.persist_extraction_facts(
            db_session, jobs[key].job_id, entities[key].id, items,
        )

    # --- EntityPattern (for suggestion engine) ---
    pattern = EntityPattern(
        id=uuid4(), entity_id=us_tech.id,
        original_label="Adjusted Net Revenue",
        canonical_name="revenue", confidence=0.90,
        is_active=True, created_by="claude",
    )
    db_session.add(pattern)

    # --- LearnedAlias (for suggestion engine) ---
    alias = LearnedAlias(
        id=uuid4(), canonical_name="revenue",
        alias_text="Adjusted Revenue", occurrence_count=3,
    )
    db_session.add(alias)

    # --- FX Cache ---
    fx_entries = [
        FxRateCache(from_currency="EUR", to_currency="USD",
                    rate_date="2024-01-01", rate=Decimal("1.10"), source="test"),
        FxRateCache(from_currency="GBP", to_currency="USD",
                    rate_date="2024-01-01", rate=Decimal("1.27"), source="test"),
    ]
    for fx in fx_entries:
        db_session.add(fx)

    # --- Quality Snapshots ---
    for entity_key, data in [
        ("us_tech", [("2024-01-15", 0.82, "B", 80, 2, 4), ("2024-03-15", 0.91, "A", 150, 3, 1)]),
        ("eu_mfg", [("2024-01-15", 0.78, "C", 60, 1, 6), ("2024-03-15", 0.88, "B", 120, 2, 3)]),
    ]:
        for date, conf, grade, facts, jobs_count, unmapped in data:
            s = QualitySnapshot(
                entity_id=entities[entity_key].id,
                snapshot_date=date, avg_confidence=conf,
                quality_grade=grade, total_facts=facts,
                total_jobs=jobs_count, unmapped_label_count=unmapped,
            )
            db_session.add(s)

    db_session.commit()

    return {
        **entities,
        "jobs": jobs,
        "taxonomy": tax_items,
    }


@pytest.fixture
def api_client(test_db, mock_api_key, portfolio):
    """Test client with full portfolio seeded."""
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
    yield client, portfolio
    app.dependency_overrides.clear()


# ============================================================================
# 1. Entity Metadata Round-Trip
# ============================================================================


class TestEntityMetadata:
    """Verify entity metadata (FYE, currency, standard) persists through API."""

    def test_entity_detail_includes_metadata(self, api_client):
        client, p = api_client
        resp = client.get(f"/api/v1/entities/{p['us_tech'].id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fiscal_year_end"] == 12
        assert data["default_currency"] == "USD"
        assert data["reporting_standard"] == "GAAP"

    def test_entity_update_metadata(self, api_client):
        client, p = api_client
        resp = client.patch(
            f"/api/v1/entities/{p['eu_mfg'].id}",
            json={"fiscal_year_end": 12, "default_currency": "CHF"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["fiscal_year_end"] == 12
        assert data["default_currency"] == "CHF"
        # reporting_standard should be preserved
        assert data["reporting_standard"] == "IFRS"

    def test_entity_list_shows_currency(self, api_client):
        client, _ = api_client
        resp = client.get("/api/v1/entities/")
        assert resp.status_code == 200
        entities = resp.json()["entities"]
        currencies = {e["name"]: e.get("default_currency") for e in entities}
        assert currencies["US Tech Inc"] == "USD"
        assert currencies["EU Manufacturing AG"] == "EUR"


# ============================================================================
# 2. Cross-Entity Comparison with Currency Conversion
# ============================================================================


class TestCrossEntityComparisonWithFX:
    """Test compare endpoint with period modes, metadata, and FX conversion."""

    def test_compare_exact_period(self, api_client):
        client, p = api_client
        eids = f"{p['us_tech'].id},{p['eu_mfg'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}"
            f"&canonical_names=revenue&period=FY2024"
        )
        assert resp.status_code == 200
        comp = resp.json()["comparisons"][0]
        amounts = {e["entity_id"]: e["amount"] for e in comp["entities"]}
        assert amounts[str(p["us_tech"].id)] == 1000000.0
        assert amounts[str(p["eu_mfg"].id)] == 2000000.0

    def test_compare_normalized_period(self, api_client):
        client, p = api_client
        eids = f"{p['us_tech'].id},{p['eu_mfg'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}"
            f"&canonical_names=revenue&period_normalized=FY2024"
        )
        assert resp.status_code == 200
        comp = resp.json()["comparisons"][0]
        assert len(comp["entities"]) >= 2

    def test_compare_by_year(self, api_client):
        client, p = api_client
        eids = f"{p['us_tech'].id},{p['eu_mfg'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}"
            f"&canonical_names=revenue&year=2024"
        )
        assert resp.status_code == 200

    def test_compare_with_target_currency_usd(self, api_client):
        """EUR and GBP values should be converted to USD."""
        client, p = api_client
        eids = f"{p['us_tech'].id},{p['eu_mfg'].id},{p['uk_fin'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}"
            f"&canonical_names=revenue&period=FY2024&target_currency=USD"
        )
        assert resp.status_code == 200
        body = resp.json()
        comp = body["comparisons"][0]

        for ev in comp["entities"]:
            if ev["entity_id"] == str(p["eu_mfg"].id):
                # EUR -> USD: 2M * 1.10 = 2.2M
                assert ev.get("original_amount") == 2000000.0
                assert ev["amount"] == 2200000.0
                assert ev.get("fx_rate_used") == 1.1
            elif ev["entity_id"] == str(p["uk_fin"].id):
                # GBP -> USD: 500K * 1.27 = 635K
                assert ev.get("original_amount") == 500000.0
                assert ev["amount"] == 635000.0
                assert ev.get("fx_rate_used") == 1.27
            elif ev["entity_id"] == str(p["us_tech"].id):
                # USD -> USD: no conversion
                assert ev["amount"] == 1000000.0

        assert any("converted to USD" in n for n in body["normalization_notes"])

    def test_compare_fiscal_year_warning(self, api_client):
        """Entities with different FYEs should trigger alignment warnings."""
        client, p = api_client
        # us_tech FYE=12, eu_mfg FYE=6 — different
        eids = f"{p['us_tech'].id},{p['eu_mfg'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}"
            f"&canonical_names=revenue&period=FY2024"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert any("Fiscal year" in n for n in body["normalization_notes"])
        comp = body["comparisons"][0]
        assert len(comp["alignment_warnings"]) > 0

    def test_compare_include_metadata(self, api_client):
        client, p = api_client
        eids = f"{p['us_tech'].id},{p['eu_mfg'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}"
            f"&canonical_names=revenue&period=FY2024&include_metadata=true"
        )
        assert resp.status_code == 200
        comp = resp.json()["comparisons"][0]
        for ev in comp["entities"]:
            if ev["amount"] is not None:
                assert "currency_code" in ev
                assert "fiscal_year_end" in ev
                assert "period_normalized" in ev

    def test_compare_multiple_canonicals(self, api_client):
        client, p = api_client
        eids = f"{p['us_tech'].id},{p['eu_mfg'].id}"
        resp = client.get(
            f"/api/v1/analytics/compare?entity_ids={eids}"
            f"&canonical_names=revenue,ebitda&period=FY2024"
        )
        assert resp.status_code == 200
        canonicals = {c["canonical_name"] for c in resp.json()["comparisons"]}
        assert canonicals == {"revenue", "ebitda"}


# ============================================================================
# 3. Anomaly Detection (API)
# ============================================================================


class TestAnomalyDetectionAPI:
    """Test outlier detection across the 4-entity portfolio."""

    def test_iqr_anomaly_detection(self, api_client):
        """MegaCorp's 50M revenue should be flagged as outlier (5 entities)."""
        client, p = api_client
        resp = client.get(
            "/api/v1/analytics/anomalies?canonical_names=revenue"
            "&period_normalized=FY2024&method=iqr&threshold=1.5"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["method"] == "iqr"
        assert body["total_items"] >= 5
        assert body["total_outliers"] >= 1

        # Find the outlier
        for summary in body["summaries"]:
            outliers = [i for i in summary["items"] if i["is_outlier"]]
            for o in outliers:
                if o["entity_id"] == str(p["us_outlier"].id):
                    assert o["value"] == 50000000.0
                    assert o["direction"] == "high"

    def test_zscore_anomaly_detection(self, api_client):
        client, p = api_client
        # Threshold 1.5 needed because with 5 values the extreme outlier
        # inflates stdev, giving itself a z-score of only ~1.79
        resp = client.get(
            "/api/v1/analytics/anomalies?canonical_names=revenue"
            "&period_normalized=FY2024&method=zscore&threshold=1.5"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["method"] == "zscore"
        assert body["total_outliers"] >= 1

    def test_anomaly_detection_by_year(self, api_client):
        client, _ = api_client
        resp = client.get(
            "/api/v1/analytics/anomalies?canonical_names=revenue&year=2024"
        )
        assert resp.status_code == 200
        assert resp.json()["total_items"] >= 5

    def test_anomaly_detection_missing_period_param(self, api_client):
        client, _ = api_client
        resp = client.get("/api/v1/analytics/anomalies?canonical_names=revenue")
        assert resp.status_code == 400


# ============================================================================
# 4. Unmapped Label Aggregation (API)
# ============================================================================


class TestUnmappedLabelAPI:
    """Test unmapped label aggregation across entities."""

    def test_unmapped_labels_returned(self, api_client):
        client, _ = api_client
        resp = client.get("/api/v1/analytics/unmapped-labels")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] > 0
        # "adjusted revenue" should appear across 2 entities
        labels = {l["label_normalized"]: l for l in body["labels"]}
        assert "adjusted revenue" in labels
        assert labels["adjusted revenue"]["total_occurrences"] == 2
        assert labels["adjusted revenue"]["entity_count"] == 2

    def test_unmapped_labels_min_occurrences(self, api_client):
        client, _ = api_client
        resp = client.get("/api/v1/analytics/unmapped-labels?min_occurrences=2")
        assert resp.status_code == 200
        for label in resp.json()["labels"]:
            assert label["total_occurrences"] >= 2

    def test_unmapped_labels_pagination(self, api_client):
        client, _ = api_client
        resp = client.get("/api/v1/analytics/unmapped-labels?limit=1&offset=0")
        assert resp.status_code == 200
        assert len(resp.json()["labels"]) <= 1


# ============================================================================
# 5. Taxonomy Gap Suggestions (API)
# ============================================================================


class TestSuggestionsAPI:
    """Test suggestion engine through API for unmapped labels."""

    def test_suggestions_for_adjusted_revenue(self, api_client):
        """'Adjusted Revenue' should match 'revenue' via pattern and learned alias."""
        client, _ = api_client
        resp = client.get(
            "/api/v1/analytics/unmapped-labels/Adjusted Revenue/suggestions"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["label"] == "Adjusted Revenue"
        assert len(body["suggestions"]) > 0
        canonical_names = [s["canonical_name"] for s in body["suggestions"]]
        assert "revenue" in canonical_names

    def test_suggestions_have_source_field(self, api_client):
        """Each suggestion has a source indicating where the match came from."""
        client, _ = api_client
        resp = client.get(
            "/api/v1/analytics/unmapped-labels/Total Revenue/suggestions"
        )
        assert resp.status_code == 200
        suggestions = resp.json()["suggestions"]
        assert len(suggestions) > 0
        # Each suggestion should have a valid source
        valid_sources = {"entity_pattern", "taxonomy_alias", "learned_alias"}
        for s in suggestions:
            assert s["source"] in valid_sources

    def test_accept_suggestion_creates_mapping(self, api_client):
        """Accept creates EntityPattern + LearnedAlias."""
        client, p = api_client
        resp = client.post(
            "/api/v1/analytics/unmapped-labels/Adjusted Revenue/accept",
            json={
                "canonical_name": "revenue",
                "entity_id": str(p["us_tech"].id),
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["canonical_name"] == "revenue"
        assert body["pattern_created"] is True
        # alias_created could be False if "Adjusted Revenue" already existed
        # (we seeded it in the LearnedAlias fixture)

    def test_accept_unknown_canonical_rejected(self, api_client):
        client, _ = api_client
        resp = client.post(
            "/api/v1/analytics/unmapped-labels/SomeLabel/accept",
            json={"canonical_name": "nonexistent_canonical_xyz"},
        )
        assert resp.status_code == 400


# ============================================================================
# 6. Quality Grade Trending (API)
# ============================================================================


class TestQualityTrendingAPI:
    """Test quality grade trend retrieval through API."""

    def test_quality_trend_for_entity(self, api_client):
        client, p = api_client
        resp = client.get(
            f"/api/v1/analytics/entity/{p['us_tech'].id}/quality-trend"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == str(p["us_tech"].id)
        assert body["entity_name"] == "US Tech Inc"
        assert len(body["snapshots"]) == 2
        # Most recent first
        assert body["snapshots"][0]["quality_grade"] == "A"
        assert body["snapshots"][0]["avg_confidence"] == 0.91
        assert body["snapshots"][1]["quality_grade"] == "B"

    def test_quality_trend_eu_entity(self, api_client):
        client, p = api_client
        resp = client.get(
            f"/api/v1/analytics/entity/{p['eu_mfg'].id}/quality-trend"
        )
        assert resp.status_code == 200
        snapshots = resp.json()["snapshots"]
        assert len(snapshots) == 2
        # Improved from C to B
        assert snapshots[0]["quality_grade"] == "B"
        assert snapshots[1]["quality_grade"] == "C"

    def test_quality_trend_no_snapshots(self, api_client):
        """Entity with no snapshots returns empty list."""
        client, p = api_client
        resp = client.get(
            f"/api/v1/analytics/entity/{p['uk_fin'].id}/quality-trend"
        )
        assert resp.status_code == 200
        assert resp.json()["snapshots"] == []


# ============================================================================
# 7. FX Service Unit Integration
# ============================================================================


class TestFxServiceIntegration:
    """Test FX service with real DB cache lookups."""

    def test_cached_rate_lookup(self, db_session, portfolio):
        fx = FxService()
        rate = fx.get_rate(db_session, "EUR", "USD", "2024-01-01")
        assert rate == Decimal("1.10")

    def test_convert_eur_to_usd(self, db_session, portfolio):
        fx = FxService()
        result = fx.convert(1000.0, "EUR", "USD", db_session, "2024-01-01")
        assert result is not None
        assert result["converted_amount"] == 1100.0
        assert result["fx_rate_used"] == 1.1

    def test_convert_gbp_to_usd(self, db_session, portfolio):
        fx = FxService()
        result = fx.convert(1000.0, "GBP", "USD", db_session, "2024-01-01")
        assert result is not None
        assert result["converted_amount"] == 1270.0
        assert result["fx_rate_used"] == 1.27

    def test_same_currency_no_conversion(self, db_session, portfolio):
        fx = FxService()
        result = fx.convert(5000.0, "USD", "USD", db_session)
        assert result == {"converted_amount": 5000.0, "fx_rate_used": 1.0}


# ============================================================================
# 8. Suggestion Engine Unit Integration
# ============================================================================


class TestSuggestionEngineIntegration:
    """Test suggestion engine with seeded patterns, taxonomy, and learned aliases."""

    def test_pattern_match(self, db_session, portfolio):
        results = suggest_for_label(db_session, "Adjusted Net Revenue")
        canonical_names = [r["canonical_name"] for r in results]
        assert "revenue" in canonical_names

    def test_taxonomy_alias_match(self, db_session, portfolio):
        results = suggest_for_label(db_session, "Turnover")
        canonical_names = [r["canonical_name"] for r in results]
        assert "revenue" in canonical_names

    def test_learned_alias_match(self, db_session, portfolio):
        results = suggest_for_label(db_session, "Adjusted Revenue")
        canonical_names = [r["canonical_name"] for r in results]
        assert "revenue" in canonical_names

    def test_deduplication(self, db_session, portfolio):
        """Multiple sources matching same canonical should be deduped."""
        results = suggest_for_label(db_session, "Net Revenue")
        revenue_matches = [r for r in results if r["canonical_name"] == "revenue"]
        assert len(revenue_matches) == 1

    def test_unknown_label_returns_empty(self, db_session, portfolio):
        results = suggest_for_label(db_session, "xyzzy_unknown_metric_99999")
        assert results == []


# ============================================================================
# 9. Anomaly Detection Unit Integration
# ============================================================================


class TestAnomalyDetectionIntegration:
    """Test anomaly detection algorithms with real fact data."""

    def test_iqr_detects_outlier(self, db_session, portfolio):
        facts = crud.get_facts_for_anomaly_detection(
            db_session, canonical_names=["revenue"], period_normalized="FY2024",
        )
        values = [
            (str(f.entity_id), None, float(f.value))
            for f in facts if f.value is not None
        ]
        assert len(values) == 5  # 5 entities with revenue
        results = detect_iqr_anomalies(values)
        assert len(results) == 5
        outliers = [r for r in results if r.is_outlier]
        assert len(outliers) >= 1
        # MegaCorp's 50M should be the outlier
        outlier_values = [r.value for r in outliers]
        assert 50000000.0 in outlier_values

    def test_zscore_detects_outlier(self, db_session, portfolio):
        facts = crud.get_facts_for_anomaly_detection(
            db_session, canonical_names=["revenue"], period_normalized="FY2024",
        )
        values = [
            (str(f.entity_id), None, float(f.value))
            for f in facts if f.value is not None
        ]
        # Threshold 1.5: with 5 values the extreme outlier inflates stdev
        results = detect_zscore_anomalies(values, threshold=1.5)
        outliers = [r for r in results if r.is_outlier]
        assert len(outliers) >= 1

    def test_too_few_values_returns_empty(self, db_session, portfolio):
        """Fewer than 3 data points should return empty."""
        values = [("e1", "Name1", 100.0), ("e2", "Name2", 200.0)]
        results = detect_iqr_anomalies(values)
        assert results == []


# ============================================================================
# 10. Quality Snapshot CRUD Integration
# ============================================================================


class TestQualitySnapshotCRUD:

    def test_create_and_retrieve(self, db_session, portfolio):
        entity = portfolio["us_tech"]
        crud.create_quality_snapshot(
            db_session,
            entity_id=entity.id,
            snapshot_date="2024-06-15",
            avg_confidence=0.93,
            quality_grade="A",
            total_facts=200,
            total_jobs=7,
            unmapped_label_count=0,
        )
        trend = crud.get_quality_trend(db_session, entity.id)
        # Should have 3 now (2 seeded + 1 new)
        assert len(trend) == 3
        # Most recent should be our new one
        assert trend[0]["snapshot_date"] == "2024-06-15"
        assert trend[0]["quality_grade"] == "A"
        assert trend[0]["avg_confidence"] == 0.93


# ============================================================================
# 11. Portfolio Summary Includes All Entities
# ============================================================================


class TestPortfolioSummaryIntegration:

    def test_portfolio_summary(self, api_client):
        client, _ = api_client
        resp = client.get("/api/v1/analytics/portfolio/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_entities"] == 5
        assert body["total_facts"] > 0
        assert body["avg_confidence"] is not None


# ============================================================================
# 12. Facts Query with Phase 2/3 Fields
# ============================================================================


class TestFactsQueryIntegration:

    def test_facts_include_normalization_fields(self, api_client):
        client, p = api_client
        resp = client.get(
            f"/api/v1/analytics/facts?entity_id={p['us_tech'].id}"
            f"&canonical_name=revenue"
        )
        assert resp.status_code == 200
        facts = resp.json()["facts"]
        assert len(facts) >= 2  # FY2023 + FY2024
        # All facts should have currency_code and period_normalized
        for fact in facts:
            assert fact["currency_code"] == "USD"
            assert fact["period_normalized"] in ("FY2023", "FY2024")

    def test_facts_for_eur_entity(self, api_client):
        client, p = api_client
        resp = client.get(
            f"/api/v1/analytics/facts?entity_id={p['eu_mfg'].id}"
            f"&canonical_name=revenue"
        )
        assert resp.status_code == 200
        facts = resp.json()["facts"]
        assert len(facts) > 0
        assert facts[0]["currency_code"] == "EUR"


# ============================================================================
# 13. Entity Financials (Trends + Statement)
# ============================================================================


class TestEntityFinancialsIntegration:

    def test_entity_financials(self, api_client):
        client, p = api_client
        resp = client.get(
            f"/api/v1/analytics/entity/{p['us_tech'].id}/financials"
            f"?canonical_names=revenue"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_name"] == "US Tech Inc"
        assert len(body["items"]) > 0
        assert "FY2024" in body["periods"]

    def test_entity_trends(self, api_client):
        client, p = api_client
        resp = client.get(
            f"/api/v1/analytics/entity/{p['us_tech'].id}/trends"
            f"?canonical_name=revenue"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["trend"]) >= 2  # FY2023 + FY2024
        # Second point should have YoY change
        assert body["trend"][1]["yoy_change_pct"] is not None
