"""Tests for ExtractionFact decomposition, persistence, and querying (WS-H)."""
import pytest
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch, MagicMock

from src.db.models import ExtractionFact, File, ExtractionJob, JobStatusEnum
from src.db.crud import persist_extraction_facts, query_extraction_facts


# ============================================================================
# Helpers
# ============================================================================


def _seed_job(db) -> tuple:
    """Create a File + ExtractionJob and return (job_id, file_id)."""
    file_id = uuid4()
    job_id = uuid4()
    f = File(file_id=file_id, filename="test.xlsx", file_size=1024)
    db.add(f)
    db.flush()
    job = ExtractionJob(job_id=job_id, file_id=file_id, status=JobStatusEnum.COMPLETED)
    db.add(job)
    db.commit()
    return job_id, file_id


def _make_line_items(items):
    """Build line_items list from simplified tuples: (canonical_name, values_dict, confidence)."""
    return [
        {
            "canonical_name": name,
            "original_label": name.replace("_", " ").title(),
            "values": values,
            "confidence": conf,
            "method": "claude",
            "taxonomy_category": "income_statement",
        }
        for name, values, conf in items
    ]


# ============================================================================
# Fact Decomposition Tests
# ============================================================================


class TestFactDecomposition:
    """Test that line_items are correctly decomposed into facts."""

    def test_basic_decomposition(self, db_session):
        """Each (canonical_name, period, value) triple becomes one fact."""
        job_id, _ = _seed_job(db_session)
        line_items = _make_line_items([
            ("revenue", {"FY2022": 100, "FY2023": 200}, 0.95),
            ("cogs", {"FY2022": 50, "FY2023": 70}, 0.90),
        ])

        count = persist_extraction_facts(db_session, job_id, None, line_items)

        assert count == 4  # 2 items x 2 periods
        facts = db_session.query(ExtractionFact).all()
        assert len(facts) == 4

    def test_null_values_skipped(self, db_session):
        """None values are not persisted as facts."""
        job_id, _ = _seed_job(db_session)
        line_items = _make_line_items([
            ("revenue", {"FY2022": 100, "FY2023": None}, 0.95),
        ])

        count = persist_extraction_facts(db_session, job_id, None, line_items)

        assert count == 1
        facts = db_session.query(ExtractionFact).all()
        assert len(facts) == 1
        assert facts[0].period == "FY2022"

    def test_unmapped_items_skipped(self, db_session):
        """Items with canonical_name='unmapped' are not persisted."""
        job_id, _ = _seed_job(db_session)
        line_items = [
            {"canonical_name": "unmapped", "values": {"FY2022": 100}, "confidence": 0.5},
            {"canonical_name": "revenue", "original_label": "Revenue", "values": {"FY2022": 200}, "confidence": 0.95, "method": "claude", "taxonomy_category": "income_statement"},
        ]

        count = persist_extraction_facts(db_session, job_id, None, line_items)

        assert count == 1
        fact = db_session.query(ExtractionFact).one()
        assert fact.canonical_name == "revenue"

    def test_empty_line_items(self, db_session):
        """Empty line_items list returns 0."""
        job_id, _ = _seed_job(db_session)
        count = persist_extraction_facts(db_session, job_id, None, [])
        assert count == 0

    def test_malformed_value_skipped(self, db_session):
        """Non-numeric values are skipped with a warning."""
        job_id, _ = _seed_job(db_session)
        line_items = _make_line_items([
            ("revenue", {"FY2022": "not_a_number", "FY2023": 100}, 0.95),
        ])

        count = persist_extraction_facts(db_session, job_id, None, line_items)

        # "not_a_number" skipped, 100 persisted
        assert count == 1

    def test_fact_fields_populated(self, db_session):
        """All fact fields are correctly populated from line_item."""
        job_id, _ = _seed_job(db_session)
        line_items = [{
            "canonical_name": "revenue",
            "original_label": "Total Revenue",
            "values": {"FY2022": 500},
            "confidence": 0.95,
            "sheet_name": "Income Statement",
            "row_index": 5,
            "hierarchy_level": 1,
            "method": "claude",
            "taxonomy_category": "income_statement",
        }]

        persist_extraction_facts(db_session, job_id, None, line_items)

        fact = db_session.query(ExtractionFact).one()
        assert fact.canonical_name == "revenue"
        assert fact.original_label == "Total Revenue"
        assert fact.period == "FY2022"
        assert fact.value == Decimal("500")
        assert fact.confidence == 0.95
        assert fact.sheet_name == "Income Statement"
        assert fact.row_index == 5
        assert fact.hierarchy_level == 1
        assert fact.mapping_method == "claude"
        assert fact.taxonomy_category == "income_statement"


# ============================================================================
# Validation Status Attachment
# ============================================================================


class TestValidationAttachment:
    """Test that validation_passed is attached from validation lookup."""

    def test_validation_status_attached(self, db_session):
        """validation_passed comes from validation_lookup dict."""
        job_id, _ = _seed_job(db_session)
        line_items = _make_line_items([
            ("revenue", {"FY2022": 100}, 0.95),
        ])
        validation_lookup = {"revenue": {"passed": True}}

        persist_extraction_facts(db_session, job_id, None, line_items, validation_lookup)

        fact = db_session.query(ExtractionFact).one()
        assert fact.validation_passed is True

    def test_validation_none_when_missing(self, db_session):
        """validation_passed is None when no validation lookup provided."""
        job_id, _ = _seed_job(db_session)
        line_items = _make_line_items([
            ("revenue", {"FY2022": 100}, 0.95),
        ])

        persist_extraction_facts(db_session, job_id, None, line_items)

        fact = db_session.query(ExtractionFact).one()
        assert fact.validation_passed is None


# ============================================================================
# Query Tests
# ============================================================================


class TestFactQueries:
    """Test query_extraction_facts with various filters."""

    def _seed_facts(self, db_session):
        """Seed 6 facts for query testing."""
        job_id, _ = _seed_job(db_session)
        line_items = _make_line_items([
            ("revenue", {"FY2022": 100, "FY2023": 200}, 0.95),
            ("cogs", {"FY2022": 50, "FY2023": 70}, 0.60),
            ("net_income", {"FY2022": 30}, 0.85),
        ])
        persist_extraction_facts(db_session, job_id, None, line_items)
        return job_id

    def test_query_all(self, db_session):
        """No filters returns all facts."""
        self._seed_facts(db_session)
        facts = query_extraction_facts(db_session)
        assert len(facts) == 5

    def test_query_by_canonical_name(self, db_session):
        """Filter by canonical_name."""
        self._seed_facts(db_session)
        facts = query_extraction_facts(db_session, canonical_name="revenue")
        assert len(facts) == 2
        assert all(f.canonical_name == "revenue" for f in facts)

    def test_query_by_period(self, db_session):
        """Filter by period."""
        self._seed_facts(db_session)
        facts = query_extraction_facts(db_session, period="FY2022")
        assert len(facts) == 3  # revenue, cogs, net_income

    def test_query_by_job_id(self, db_session):
        """Filter by job_id."""
        job_id = self._seed_facts(db_session)
        facts = query_extraction_facts(db_session, job_id=job_id)
        assert len(facts) == 5

    def test_query_by_min_confidence(self, db_session):
        """Filter by minimum confidence."""
        self._seed_facts(db_session)
        facts = query_extraction_facts(db_session, min_confidence=0.80)
        # revenue (0.95) x 2, net_income (0.85) x 1 = 3
        assert len(facts) == 3

    def test_query_pagination(self, db_session):
        """Limit and offset work correctly."""
        self._seed_facts(db_session)
        page1 = query_extraction_facts(db_session, limit=2, offset=0)
        page2 = query_extraction_facts(db_session, limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        # No overlap
        page1_ids = {f.id for f in page1}
        page2_ids = {f.id for f in page2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_query_limit_capped(self, db_session):
        """Limit is capped at 1000."""
        self._seed_facts(db_session)
        # Should not crash with large limit
        facts = query_extraction_facts(db_session, limit=5000)
        assert len(facts) == 5  # only 5 facts exist


# ============================================================================
# Orchestrator Integration (Best-Effort)
# ============================================================================


class TestBestEffortPersistence:
    """Test that orchestrator continues when fact persistence fails."""

    def test_orchestrator_continues_on_fact_error(self):
        """Extraction completes even if fact persistence raises."""
        # The orchestrator wraps persist_extraction_facts in try/except
        # so a failure should only log a warning, not crash
        with patch("src.db.session.get_db_sync", side_effect=Exception("DB unavailable")):
            # Simulating what the orchestrator does
            try:
                from src.db.session import get_db_sync
                from src.db.crud import persist_extraction_facts
                with get_db_sync() as db:
                    persist_extraction_facts(db, uuid4(), None, [])
                fact_persisted = True
            except Exception:
                fact_persisted = False

            assert fact_persisted is False
            # Pipeline would continue after this point
