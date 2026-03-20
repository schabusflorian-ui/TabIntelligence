"""
Integration tests for Phase 2: Cross-Company Normalization.

Tests CRUD functions against a real SQLite in-memory database,
verifying cross-entity comparison, unmapped label aggregation,
and anomaly detection queries work end-to-end.
"""


import pytest

from src.db import crud

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def two_entities(db_session):
    """Create two entities with different metadata."""
    alpha = crud.create_entity(
        db_session,
        name="Alpha Corp",
        industry="Technology",
        fiscal_year_end=12,
        default_currency="USD",
        reporting_standard="GAAP",
    )
    beta = crud.create_entity(
        db_session,
        name="Beta Inc",
        industry="Technology",
        fiscal_year_end=3,
        default_currency="EUR",
        reporting_standard="IFRS",
    )
    return alpha, beta


@pytest.fixture
def entities_with_facts(db_session, two_entities):
    """Two entities with extraction facts for comparison testing."""
    alpha, beta = two_entities

    # Create files and jobs for each entity
    alpha_file = crud.create_file(
        db_session, filename="alpha.xlsx", file_size=100, entity_id=alpha.id
    )
    beta_file = crud.create_file(
        db_session, filename="beta.xlsx", file_size=100, entity_id=beta.id
    )
    alpha_job = crud.create_extraction_job(db_session, file_id=alpha_file.file_id)
    beta_job = crud.create_extraction_job(db_session, file_id=beta_file.file_id)

    # Alpha facts
    alpha_items = [
        {
            "canonical_name": "revenue",
            "original_label": "Revenue",
            "values": {"FY2024": 1000000, "FY2023": 900000},
            "confidence": 0.95,
            "period_normalized": {"FY2024": "FY2024", "FY2023": "FY2023"},
            "taxonomy_category": "income_statement",
            "currency_code": "USD",
            "source_unit": "absolute",
        },
        {
            "canonical_name": "ebitda",
            "original_label": "EBITDA",
            "values": {"FY2024": 250000},
            "confidence": 0.90,
            "period_normalized": {"FY2024": "FY2024"},
            "taxonomy_category": "income_statement",
        },
    ]
    crud.persist_extraction_facts(db_session, alpha_job.job_id, alpha.id, alpha_items)

    # Beta facts
    beta_items = [
        {
            "canonical_name": "revenue",
            "original_label": "Net Sales",
            "values": {"FY2024": 1500000, "FY2023": 1300000},
            "confidence": 0.92,
            "period_normalized": {"FY2024": "FY2024", "FY2023": "FY2023"},
            "taxonomy_category": "income_statement",
            "currency_code": "EUR",
            "source_unit": "thousands",
            "source_scale": 1000.0,
        },
        {
            "canonical_name": "ebitda",
            "original_label": "EBITDA",
            "values": {"FY2024": 350000},
            "confidence": 0.88,
            "period_normalized": {"FY2024": "FY2024"},
            "taxonomy_category": "income_statement",
        },
    ]
    crud.persist_extraction_facts(db_session, beta_job.job_id, beta.id, beta_items)

    return {
        "alpha": alpha,
        "beta": beta,
        "alpha_job": alpha_job,
        "beta_job": beta_job,
    }


# ============================================================================
# Cross-Entity Comparison (CRUD)
# ============================================================================


class TestCrossEntityComparison:
    """Test get_cross_entity_comparison with different period matching modes."""

    def test_compare_by_exact_period(self, db_session, entities_with_facts):
        d = entities_with_facts
        facts = crud.get_cross_entity_comparison(
            db_session,
            entity_ids=[d["alpha"].id, d["beta"].id],
            canonical_names=["revenue"],
            period="FY2024",
        )
        assert len(facts) == 2
        entity_ids = {str(f.entity_id) for f in facts}
        assert str(d["alpha"].id) in entity_ids
        assert str(d["beta"].id) in entity_ids

    def test_compare_by_period_normalized(self, db_session, entities_with_facts):
        d = entities_with_facts
        facts = crud.get_cross_entity_comparison(
            db_session,
            entity_ids=[d["alpha"].id, d["beta"].id],
            canonical_names=["revenue"],
            period_normalized="FY2024",
        )
        assert len(facts) == 2

    def test_compare_by_year(self, db_session, entities_with_facts):
        d = entities_with_facts
        facts = crud.get_cross_entity_comparison(
            db_session,
            entity_ids=[d["alpha"].id, d["beta"].id],
            canonical_names=["revenue"],
            year=2024,
        )
        # Should match all facts with "2024" in period_normalized
        assert len(facts) >= 2

    def test_compare_multiple_canonical_names(self, db_session, entities_with_facts):
        d = entities_with_facts
        facts = crud.get_cross_entity_comparison(
            db_session,
            entity_ids=[d["alpha"].id, d["beta"].id],
            canonical_names=["revenue", "ebitda"],
            period="FY2024",
        )
        canonical_names = {f.canonical_name for f in facts}
        assert "revenue" in canonical_names
        assert "ebitda" in canonical_names

    def test_compare_no_matching_period(self, db_session, entities_with_facts):
        d = entities_with_facts
        facts = crud.get_cross_entity_comparison(
            db_session,
            entity_ids=[d["alpha"].id, d["beta"].id],
            canonical_names=["revenue"],
            period="FY2030",
        )
        assert len(facts) == 0

    def test_compare_nonexistent_canonical(self, db_session, entities_with_facts):
        d = entities_with_facts
        facts = crud.get_cross_entity_comparison(
            db_session,
            entity_ids=[d["alpha"].id, d["beta"].id],
            canonical_names=["does_not_exist"],
            period="FY2024",
        )
        assert len(facts) == 0

    def test_compare_facts_have_metadata(self, db_session, entities_with_facts):
        d = entities_with_facts
        facts = crud.get_cross_entity_comparison(
            db_session,
            entity_ids=[d["alpha"].id, d["beta"].id],
            canonical_names=["revenue"],
            period="FY2024",
        )
        alpha_fact = next(f for f in facts if str(f.entity_id) == str(d["alpha"].id))
        beta_fact = next(f for f in facts if str(f.entity_id) == str(d["beta"].id))
        assert alpha_fact.currency_code == "USD"
        assert beta_fact.currency_code == "EUR"
        assert alpha_fact.period_normalized == "FY2024"


# ============================================================================
# Unmapped Label Aggregation (CRUD)
# ============================================================================


class TestUnmappedLabelAggregationCRUD:
    """Test get_unmapped_label_aggregation with real DB records."""

    @pytest.fixture
    def unmapped_data(self, db_session, two_entities):
        alpha, beta = two_entities
        alpha_file = crud.create_file(
            db_session, filename="a.xlsx", file_size=100, entity_id=alpha.id
        )
        beta_file = crud.create_file(
            db_session, filename="b.xlsx", file_size=100, entity_id=beta.id
        )
        alpha_job = crud.create_extraction_job(db_session, file_id=alpha_file.file_id)
        beta_job = crud.create_extraction_job(db_session, file_id=beta_file.file_id)

        # Both entities have "custom metric" unmapped
        alpha_items = [
            {"canonical_name": "unmapped", "original_label": "Custom Metric", "values": {},
             "sheet_name": "P&L"},
            {"canonical_name": "unmapped", "original_label": "Another Unknown", "values": {},
             "sheet_name": "BS"},
        ]
        beta_items = [
            {"canonical_name": "unmapped", "original_label": "custom metric", "values": {},
             "sheet_name": "Income Statement"},
        ]
        crud.persist_extraction_facts(db_session, alpha_job.job_id, alpha.id, alpha_items)
        crud.persist_extraction_facts(db_session, beta_job.job_id, beta.id, beta_items)
        return alpha, beta

    def test_aggregation_returns_labels(self, db_session, unmapped_data):
        result = crud.get_unmapped_label_aggregation(db_session)
        assert result["total"] > 0
        assert len(result["labels"]) > 0

    def test_aggregation_counts_correct(self, db_session, unmapped_data):
        result = crud.get_unmapped_label_aggregation(db_session)
        custom_metric = next(
            (l for l in result["labels"] if l["label_normalized"] == "custom metric"), None
        )
        assert custom_metric is not None
        assert custom_metric["total_occurrences"] == 2  # alpha + beta
        assert custom_metric["entity_count"] == 2

    def test_aggregation_min_occurrences_filter(self, db_session, unmapped_data):
        result = crud.get_unmapped_label_aggregation(db_session, min_occurrences=2)
        # Only "custom metric" has 2+ occurrences
        labels = [l["label_normalized"] for l in result["labels"]]
        assert "custom metric" in labels
        assert "another unknown" not in labels

    def test_aggregation_min_entities_filter(self, db_session, unmapped_data):
        result = crud.get_unmapped_label_aggregation(db_session, min_entities=2)
        # Only "custom metric" appears across 2 entities
        labels = [l["label_normalized"] for l in result["labels"]]
        assert "custom metric" in labels
        assert "another unknown" not in labels

    def test_aggregation_pagination(self, db_session, unmapped_data):
        result1 = crud.get_unmapped_label_aggregation(db_session, limit=1, offset=0)
        result2 = crud.get_unmapped_label_aggregation(db_session, limit=1, offset=1)
        assert len(result1["labels"]) <= 1
        assert len(result2["labels"]) <= 1
        if result1["labels"] and result2["labels"]:
            assert result1["labels"][0]["label_normalized"] != result2["labels"][0]["label_normalized"]

    def test_aggregation_includes_variants(self, db_session, unmapped_data):
        result = crud.get_unmapped_label_aggregation(db_session)
        custom_metric = next(
            (l for l in result["labels"] if l["label_normalized"] == "custom metric"), None
        )
        assert custom_metric is not None
        assert "Custom Metric" in custom_metric["original_variants"]
        assert "custom metric" in custom_metric["original_variants"]


# ============================================================================
# Anomaly Detection (CRUD)
# ============================================================================


class TestAnomalyDetectionCRUD:
    """Test get_facts_for_anomaly_detection with real DB."""

    @pytest.fixture
    def five_entities_with_revenue(self, db_session):
        """Create 5 entities with revenue facts for anomaly testing."""
        entities = []
        for i, (name, revenue) in enumerate([
            ("CompanyA", 100000),
            ("CompanyB", 110000),
            ("CompanyC", 95000),
            ("CompanyD", 105000),
            ("CompanyE", 500000),  # outlier
        ]):
            entity = crud.create_entity(db_session, name=name)
            file = crud.create_file(
                db_session, filename=f"{name}.xlsx", file_size=100, entity_id=entity.id
            )
            job = crud.create_extraction_job(db_session, file_id=file.file_id)
            items = [
                {
                    "canonical_name": "revenue",
                    "original_label": "Revenue",
                    "values": {"FY2024": revenue},
                    "confidence": 0.9,
                    "period_normalized": {"FY2024": "FY2024"},
                }
            ]
            crud.persist_extraction_facts(db_session, job.job_id, entity.id, items)
            entities.append(entity)
        return entities

    def test_get_facts_for_anomaly(self, db_session, five_entities_with_revenue):
        facts = crud.get_facts_for_anomaly_detection(
            db_session,
            canonical_names=["revenue"],
            period_normalized="FY2024",
        )
        assert len(facts) == 5

    def test_get_facts_for_anomaly_by_year(self, db_session, five_entities_with_revenue):
        facts = crud.get_facts_for_anomaly_detection(
            db_session,
            canonical_names=["revenue"],
            year=2024,
        )
        assert len(facts) == 5

    def test_get_facts_for_anomaly_with_entity_filter(self, db_session, five_entities_with_revenue):
        entities = five_entities_with_revenue
        facts = crud.get_facts_for_anomaly_detection(
            db_session,
            canonical_names=["revenue"],
            period_normalized="FY2024",
            entity_ids=[entities[0].id, entities[1].id],
        )
        assert len(facts) == 2

    def test_get_facts_for_anomaly_no_match(self, db_session, five_entities_with_revenue):
        facts = crud.get_facts_for_anomaly_detection(
            db_session,
            canonical_names=["does_not_exist"],
            period_normalized="FY2024",
        )
        assert len(facts) == 0

    def test_anomaly_detection_end_to_end(self, db_session, five_entities_with_revenue):
        """Full pipeline: query facts -> run IQR detection -> find outlier."""
        from src.normalization.anomaly_detection import detect_iqr_anomalies

        facts = crud.get_facts_for_anomaly_detection(
            db_session,
            canonical_names=["revenue"],
            period_normalized="FY2024",
        )
        values = [
            (str(f.entity_id), None, float(f.value))
            for f in facts
        ]
        results = detect_iqr_anomalies(values)
        assert len(results) == 5
        outliers = [r for r in results if r.is_outlier]
        assert len(outliers) >= 1
        # The 500000 value should be the outlier
        outlier_values = [r.value for r in outliers]
        assert 500000.0 in outlier_values


# ============================================================================
# Entity Metadata — Cross-Entity Alignment
# ============================================================================


class TestFiscalYearAlignment:
    """Test that entities with different fiscal year ends are tracked correctly."""

    def test_entities_retain_fiscal_year_end(self, db_session, two_entities):
        alpha, beta = two_entities
        assert alpha.fiscal_year_end == 12
        assert beta.fiscal_year_end == 3

    def test_entity_currency_retained(self, db_session, two_entities):
        alpha, beta = two_entities
        assert alpha.default_currency == "USD"
        assert beta.default_currency == "EUR"

    def test_entity_reporting_standard_retained(self, db_session, two_entities):
        alpha, beta = two_entities
        assert alpha.reporting_standard == "GAAP"
        assert beta.reporting_standard == "IFRS"

    def test_entity_metadata_survives_update(self, db_session, two_entities):
        alpha, _ = two_entities
        updated = crud.update_entity(db_session, alpha.id, name="Alpha Corp v2")
        # Metadata fields should be preserved
        assert updated.fiscal_year_end == 12
        assert updated.default_currency == "USD"
        assert updated.reporting_standard == "GAAP"
