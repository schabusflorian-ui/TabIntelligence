"""
Unit tests for Phase 2: Cross-Company Normalization.

Tests:
- Anomaly detection (IQR + Z-score)
- Entity metadata fields
- Fact normalization metadata
- Period normalized population
- Unmapped label collection in persist_extraction_facts
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, Mock

import pytest

from src.normalization.anomaly_detection import (
    AnomalyResult,
    detect_iqr_anomalies,
    detect_zscore_anomalies,
)


# ============================================================================
# Anomaly Detection — IQR
# ============================================================================


class TestIQRAnomalyDetection:
    """Test detect_iqr_anomalies function."""

    def test_returns_empty_for_fewer_than_3_values(self):
        values = [("e1", "A", 100.0), ("e2", "B", 200.0)]
        assert detect_iqr_anomalies(values) == []

    def test_returns_empty_for_single_value(self):
        assert detect_iqr_anomalies([("e1", "A", 100.0)]) == []

    def test_returns_empty_for_empty_input(self):
        assert detect_iqr_anomalies([]) == []

    def test_no_outliers_in_uniform_data(self):
        values = [
            ("e1", "A", 100.0),
            ("e2", "B", 102.0),
            ("e3", "C", 98.0),
            ("e4", "D", 101.0),
            ("e5", "E", 99.0),
        ]
        results = detect_iqr_anomalies(values)
        assert len(results) == 5
        assert all(not r.is_outlier for r in results)

    def test_detects_high_outlier(self):
        values = [
            ("e1", "A", 100.0),
            ("e2", "B", 102.0),
            ("e3", "C", 98.0),
            ("e4", "D", 101.0),
            ("e5", "E", 500.0),  # outlier
        ]
        results = detect_iqr_anomalies(values)
        outlier = next(r for r in results if r.entity_id == "e5")
        assert outlier.is_outlier is True
        assert outlier.direction == "high"
        assert outlier.iqr_distance is not None
        assert outlier.iqr_distance > 0

    def test_detects_low_outlier(self):
        values = [
            ("e1", "A", 100.0),
            ("e2", "B", 102.0),
            ("e3", "C", 98.0),
            ("e4", "D", 101.0),
            ("e5", "E", -200.0),  # outlier
        ]
        results = detect_iqr_anomalies(values)
        outlier = next(r for r in results if r.entity_id == "e5")
        assert outlier.is_outlier is True
        assert outlier.direction == "low"

    def test_peer_stats_correct(self):
        values = [
            ("e1", "A", 10.0),
            ("e2", "B", 20.0),
            ("e3", "C", 30.0),
        ]
        results = detect_iqr_anomalies(values)
        assert results[0].peer_count == 3
        assert results[0].peer_mean == 20.0
        assert results[0].peer_median == 20.0

    def test_result_has_no_zscore(self):
        values = [("e1", "A", 10.0), ("e2", "B", 20.0), ("e3", "C", 30.0)]
        results = detect_iqr_anomalies(values)
        assert all(r.z_score is None for r in results)

    def test_entity_name_preserved(self):
        values = [
            ("e1", "Alpha Corp", 10.0),
            ("e2", "Beta Inc", 20.0),
            ("e3", None, 30.0),
        ]
        results = detect_iqr_anomalies(values)
        assert results[0].entity_name == "Alpha Corp"
        assert results[2].entity_name is None

    def test_custom_threshold(self):
        """Lower threshold should flag more items as outliers."""
        values = [
            ("e1", "A", 100.0),
            ("e2", "B", 100.0),
            ("e3", "C", 100.0),
            ("e4", "D", 130.0),
        ]
        results_strict = detect_iqr_anomalies(values, threshold=0.5)
        results_loose = detect_iqr_anomalies(values, threshold=3.0)
        strict_outliers = sum(1 for r in results_strict if r.is_outlier)
        loose_outliers = sum(1 for r in results_loose if r.is_outlier)
        assert strict_outliers >= loose_outliers

    def test_identical_values_no_outliers(self):
        """All identical values: IQR=0, no outliers possible."""
        values = [("e1", "A", 100.0), ("e2", "B", 100.0), ("e3", "C", 100.0)]
        results = detect_iqr_anomalies(values)
        assert all(not r.is_outlier for r in results)


# ============================================================================
# Anomaly Detection — Z-score
# ============================================================================


class TestZScoreAnomalyDetection:
    """Test detect_zscore_anomalies function."""

    def test_returns_empty_for_fewer_than_3_values(self):
        values = [("e1", "A", 100.0), ("e2", "B", 200.0)]
        assert detect_zscore_anomalies(values) == []

    def test_returns_empty_for_empty_input(self):
        assert detect_zscore_anomalies([]) == []

    def test_no_outliers_in_uniform_data(self):
        values = [
            ("e1", "A", 100.0),
            ("e2", "B", 102.0),
            ("e3", "C", 98.0),
            ("e4", "D", 101.0),
        ]
        results = detect_zscore_anomalies(values)
        assert all(not r.is_outlier for r in results)

    def test_detects_high_outlier(self):
        # Need many normal values so one extreme value has z > 2.0
        values = [
            ("e1", "A", 100.0),
            ("e2", "B", 100.0),
            ("e3", "C", 100.0),
            ("e4", "D", 100.0),
            ("e5", "E", 100.0),
            ("e6", "F", 100.0),
            ("e7", "G", 100.0),
            ("e8", "H", 100.0),
            ("e9", "I", 100.0),
            ("e10", "J", 10000.0),  # extreme outlier
        ]
        results = detect_zscore_anomalies(values)
        outlier = next(r for r in results if r.entity_id == "e10")
        assert outlier.is_outlier is True
        assert outlier.direction == "high"
        assert outlier.z_score is not None
        assert outlier.z_score > 2.0

    def test_detects_low_outlier(self):
        values = [
            ("e1", "A", 100.0),
            ("e2", "B", 100.0),
            ("e3", "C", 100.0),
            ("e4", "D", 100.0),
            ("e5", "E", 100.0),
            ("e6", "F", 100.0),
            ("e7", "G", 100.0),
            ("e8", "H", 100.0),
            ("e9", "I", 100.0),
            ("e10", "J", -10000.0),  # extreme low outlier
        ]
        results = detect_zscore_anomalies(values)
        outlier = next(r for r in results if r.entity_id == "e10")
        assert outlier.is_outlier is True
        assert outlier.direction == "low"
        assert outlier.z_score < -2.0

    def test_result_has_no_iqr_distance(self):
        values = [("e1", "A", 10.0), ("e2", "B", 20.0), ("e3", "C", 30.0)]
        results = detect_zscore_anomalies(values)
        assert all(r.iqr_distance is None for r in results)

    def test_zscore_computation_correct(self):
        """Mean=20, stdev~10, z-score for 10 should be ~-1."""
        values = [("e1", "A", 10.0), ("e2", "B", 20.0), ("e3", "C", 30.0)]
        results = detect_zscore_anomalies(values)
        r_10 = next(r for r in results if r.value == 10.0)
        # z = (10 - 20) / stdev
        assert r_10.z_score is not None
        assert r_10.z_score < 0

    def test_identical_values_zscore_zero(self):
        values = [("e1", "A", 100.0), ("e2", "B", 100.0), ("e3", "C", 100.0)]
        results = detect_zscore_anomalies(values)
        assert all(r.z_score == 0.0 for r in results)
        assert all(not r.is_outlier for r in results)

    def test_custom_threshold(self):
        """Stricter threshold should flag fewer items."""
        values = [
            ("e1", "A", 10.0),
            ("e2", "B", 10.0),
            ("e3", "C", 10.0),
            ("e4", "D", 25.0),
        ]
        results_strict = detect_zscore_anomalies(values, threshold=3.0)
        results_loose = detect_zscore_anomalies(values, threshold=1.0)
        strict_outliers = sum(1 for r in results_strict if r.is_outlier)
        loose_outliers = sum(1 for r in results_loose if r.is_outlier)
        assert strict_outliers <= loose_outliers


# ============================================================================
# AnomalyResult Dataclass
# ============================================================================


class TestAnomalyResult:
    """Test AnomalyResult dataclass fields."""

    def test_all_fields_present(self):
        r = AnomalyResult(
            entity_id="e1",
            entity_name="Test Corp",
            value=100.0,
            is_outlier=False,
            z_score=0.5,
            iqr_distance=None,
            direction=None,
            peer_mean=100.0,
            peer_median=100.0,
            peer_count=5,
        )
        assert r.entity_id == "e1"
        assert r.entity_name == "Test Corp"
        assert r.peer_count == 5

    def test_optional_fields_can_be_none(self):
        r = AnomalyResult(
            entity_id="e1",
            entity_name=None,
            value=100.0,
            is_outlier=False,
            z_score=None,
            iqr_distance=None,
            direction=None,
            peer_mean=100.0,
            peer_median=100.0,
            peer_count=3,
        )
        assert r.entity_name is None
        assert r.z_score is None
        assert r.direction is None


# ============================================================================
# Entity Metadata (model-level)
# ============================================================================


class TestEntityMetadataModel:
    """Test Entity model with fiscal_year_end, default_currency, reporting_standard."""

    def test_create_entity_with_metadata(self, db_session):
        from src.db import crud

        entity = crud.create_entity(
            db_session,
            name="Test Corp",
            industry="Technology",
            fiscal_year_end=3,
            default_currency="EUR",
            reporting_standard="IFRS",
        )
        assert entity.fiscal_year_end == 3
        assert entity.default_currency == "EUR"
        assert entity.reporting_standard == "IFRS"

    def test_create_entity_without_metadata(self, db_session):
        from src.db import crud

        entity = crud.create_entity(db_session, name="Simple Corp")
        assert entity.fiscal_year_end is None
        assert entity.default_currency is None
        assert entity.reporting_standard is None

    def test_update_entity_metadata(self, db_session):
        from src.db import crud

        entity = crud.create_entity(db_session, name="Update Corp")
        updated = crud.update_entity(
            db_session,
            entity.id,
            fiscal_year_end=6,
            default_currency="USD",
            reporting_standard="GAAP",
        )
        assert updated.fiscal_year_end == 6
        assert updated.default_currency == "USD"
        assert updated.reporting_standard == "GAAP"

    def test_update_entity_partial_metadata(self, db_session):
        from src.db import crud

        entity = crud.create_entity(
            db_session,
            name="Partial Corp",
            fiscal_year_end=12,
            default_currency="GBP",
        )
        # Only update currency, fiscal_year_end should remain
        updated = crud.update_entity(db_session, entity.id, default_currency="JPY")
        assert updated.default_currency == "JPY"
        assert updated.fiscal_year_end == 12  # unchanged


# ============================================================================
# Fact Normalization Metadata
# ============================================================================


class TestFactNormalizationMetadata:
    """Test ExtractionFact with currency_code, source_unit, source_scale."""

    def test_persist_facts_with_normalization_metadata(self, db_session):
        from src.db import crud
        from src.db.models import ExtractionFact

        entity = crud.create_entity(db_session, name="Fact Corp")
        file = crud.create_file(db_session, filename="test.xlsx", file_size=100, entity_id=entity.id)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        line_items = [
            {
                "canonical_name": "revenue",
                "original_label": "Revenue",
                "values": {"FY2024": 150000000},
                "confidence": 0.95,
                "currency_code": "EUR",
                "source_unit": "millions",
                "source_scale": 1000000.0,
                "taxonomy_category": "income_statement",
            }
        ]
        count = crud.persist_extraction_facts(db_session, job.job_id, entity.id, line_items)
        assert count == 1

        fact = db_session.query(ExtractionFact).filter_by(job_id=job.job_id).first()
        assert fact.currency_code == "EUR"
        assert fact.source_unit == "millions"
        assert fact.source_scale == 1000000.0

    def test_persist_facts_without_normalization_metadata(self, db_session):
        from src.db import crud
        from src.db.models import ExtractionFact

        entity = crud.create_entity(db_session, name="Basic Corp")
        file = crud.create_file(db_session, filename="test.xlsx", file_size=100, entity_id=entity.id)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        line_items = [
            {
                "canonical_name": "revenue",
                "original_label": "Revenue",
                "values": {"FY2024": 100000},
                "confidence": 0.9,
            }
        ]
        crud.persist_extraction_facts(db_session, job.job_id, entity.id, line_items)
        fact = db_session.query(ExtractionFact).filter_by(job_id=job.job_id).first()
        assert fact.currency_code is None
        assert fact.source_unit is None
        assert fact.source_scale is None


# ============================================================================
# Period Normalized Population
# ============================================================================


class TestPeriodNormalizedPersistence:
    """Test that period_normalized dict is consumed by persist_extraction_facts."""

    def test_period_normalized_stored(self, db_session):
        from src.db import crud
        from src.db.models import ExtractionFact

        entity = crud.create_entity(db_session, name="Period Corp")
        file = crud.create_file(db_session, filename="test.xlsx", file_size=100, entity_id=entity.id)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        line_items = [
            {
                "canonical_name": "revenue",
                "original_label": "Revenue",
                "values": {"FY2024": 100000, "FY2023": 90000},
                "confidence": 0.9,
                "period_normalized": {"FY2024": "FY2024", "FY2023": "FY2023"},
            }
        ]
        crud.persist_extraction_facts(db_session, job.job_id, entity.id, line_items)
        facts = db_session.query(ExtractionFact).filter_by(job_id=job.job_id).all()
        assert len(facts) == 2
        by_period = {f.period: f for f in facts}
        assert by_period["FY2024"].period_normalized == "FY2024"
        assert by_period["FY2023"].period_normalized == "FY2023"

    def test_period_normalized_none_when_not_provided(self, db_session):
        from src.db import crud
        from src.db.models import ExtractionFact

        entity = crud.create_entity(db_session, name="NoPeriod Corp")
        file = crud.create_file(db_session, filename="test.xlsx", file_size=100, entity_id=entity.id)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        line_items = [
            {
                "canonical_name": "revenue",
                "original_label": "Revenue",
                "values": {"FY2024": 100000},
                "confidence": 0.9,
            }
        ]
        crud.persist_extraction_facts(db_session, job.job_id, entity.id, line_items)
        fact = db_session.query(ExtractionFact).filter_by(job_id=job.job_id).first()
        assert fact.period_normalized is None

    def test_period_normalized_partial_coverage(self, db_session):
        """Only some periods have normalized values."""
        from src.db import crud
        from src.db.models import ExtractionFact

        entity = crud.create_entity(db_session, name="Partial Corp")
        file = crud.create_file(db_session, filename="test.xlsx", file_size=100, entity_id=entity.id)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        line_items = [
            {
                "canonical_name": "revenue",
                "original_label": "Revenue",
                "values": {"FY2024": 100000, "Q3 2024": 25000},
                "confidence": 0.9,
                "period_normalized": {"FY2024": "FY2024"},  # Q3 2024 not mapped
            }
        ]
        crud.persist_extraction_facts(db_session, job.job_id, entity.id, line_items)
        facts = db_session.query(ExtractionFact).filter_by(job_id=job.job_id).all()
        by_period = {f.period: f for f in facts}
        assert by_period["FY2024"].period_normalized == "FY2024"
        assert by_period["Q3 2024"].period_normalized is None


# ============================================================================
# Unmapped Label Collection
# ============================================================================


class TestUnmappedLabelCollection:
    """Test that unmapped labels are collected during fact persistence."""

    def test_unmapped_labels_persisted(self, db_session):
        from src.db import crud
        from src.db.models import UnmappedLabelAggregate

        entity = crud.create_entity(db_session, name="Unmapped Corp")
        file = crud.create_file(db_session, filename="test.xlsx", file_size=100, entity_id=entity.id)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        line_items = [
            {
                "canonical_name": "revenue",
                "original_label": "Revenue",
                "values": {"FY2024": 100000},
                "confidence": 0.9,
            },
            {
                "canonical_name": "unmapped",
                "original_label": "Custom KPI Alpha",
                "values": {},
                "sheet_name": "Income Statement",
            },
            {
                "canonical_name": "unmapped",
                "original_label": "Weird Metric",
                "values": {},
                "sheet": "Balance Sheet",
            },
        ]
        crud.persist_extraction_facts(db_session, job.job_id, entity.id, line_items)

        aggregates = db_session.query(UnmappedLabelAggregate).all()
        assert len(aggregates) == 2
        labels = {a.label_normalized for a in aggregates}
        assert "custom kpi alpha" in labels
        assert "weird metric" in labels

    def test_unmapped_label_upsert_increments_count(self, db_session):
        from src.db import crud
        from src.db.models import UnmappedLabelAggregate

        entity = crud.create_entity(db_session, name="Upsert Corp")
        file = crud.create_file(db_session, filename="test.xlsx", file_size=100, entity_id=entity.id)
        job1 = crud.create_extraction_job(db_session, file_id=file.file_id)
        job2 = crud.create_extraction_job(db_session, file_id=file.file_id)

        items1 = [
            {"canonical_name": "unmapped", "original_label": "Mystery Item", "values": {}},
        ]
        items2 = [
            {"canonical_name": "unmapped", "original_label": "Mystery Item", "values": {}},
        ]
        crud.persist_extraction_facts(db_session, job1.job_id, entity.id, items1)
        crud.persist_extraction_facts(db_session, job2.job_id, entity.id, items2)

        agg = (
            db_session.query(UnmappedLabelAggregate)
            .filter_by(label_normalized="mystery item")
            .first()
        )
        assert agg is not None
        assert agg.occurrence_count == 2

    def test_unmapped_labels_dont_create_facts(self, db_session):
        from src.db import crud
        from src.db.models import ExtractionFact

        entity = crud.create_entity(db_session, name="NoFact Corp")
        file = crud.create_file(db_session, filename="test.xlsx", file_size=100, entity_id=entity.id)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        line_items = [
            {"canonical_name": "unmapped", "original_label": "Unknown Item", "values": {}},
        ]
        count = crud.persist_extraction_facts(db_session, job.job_id, entity.id, line_items)
        assert count == 0
        facts = db_session.query(ExtractionFact).filter_by(job_id=job.job_id).all()
        assert len(facts) == 0

    def test_unmapped_label_tracks_variants(self, db_session):
        from src.db import crud
        from src.db.models import UnmappedLabelAggregate

        entity = crud.create_entity(db_session, name="Variant Corp")
        file = crud.create_file(db_session, filename="test.xlsx", file_size=100, entity_id=entity.id)
        job1 = crud.create_extraction_job(db_session, file_id=file.file_id)
        job2 = crud.create_extraction_job(db_session, file_id=file.file_id)

        items1 = [
            {"canonical_name": "unmapped", "original_label": "Custom KPI", "values": {}},
        ]
        items2 = [
            {"canonical_name": "unmapped", "original_label": "custom kpi", "values": {}},
        ]
        crud.persist_extraction_facts(db_session, job1.job_id, entity.id, items1)
        crud.persist_extraction_facts(db_session, job2.job_id, entity.id, items2)

        agg = (
            db_session.query(UnmappedLabelAggregate)
            .filter_by(label_normalized="custom kpi")
            .first()
        )
        assert agg is not None
        # Both variants should be tracked
        assert "Custom KPI" in agg.original_labels
        assert "custom kpi" in agg.original_labels
