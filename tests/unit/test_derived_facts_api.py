"""Tests for Stage 6 derived-facts API endpoints.

Covers:
  GET /api/v1/jobs/{job_id}/derived-facts
  GET /api/v1/jobs/{job_id}/consistency-report
  GET /api/v1/jobs/{job_id}/covenant-sensitivity
  GET /api/v1/analytics/entity/{entity_id}/standardised-financials
  GET /api/v1/analytics/portfolio/covenant-monitor
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.db import crud
from src.db.models import DerivedFact, JobStatusEnum


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_derived_fact(
    db,
    job_id,
    *,
    canonical_name="dscr_project_finance",
    period="FY2024",
    computed_value=Decimal("1.35"),
    confidence=0.87,
    value_range_low=None,
    value_range_high=None,
    computation_rule_id="DR-031",
    formula="cfads / debt_service",
    source_canonicals=None,
    confidence_mode="product",
    derivation_pass=2,
    is_gap_fill=True,
    consistency_check=None,
    covenant_context=None,
):
    """Insert a DerivedFact directly into the test DB."""
    fact = DerivedFact(
        job_id=job_id,
        canonical_name=canonical_name,
        period=period,
        computed_value=computed_value,
        confidence=confidence,
        value_range_low=value_range_low,
        value_range_high=value_range_high,
        computation_rule_id=computation_rule_id,
        formula=formula,
        source_canonicals=source_canonicals or ["cfads", "debt_service"],
        confidence_mode=confidence_mode,
        derivation_pass=derivation_pass,
        is_gap_fill=is_gap_fill,
        consistency_check=consistency_check,
        covenant_context=covenant_context,
    )
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return fact


# ---------------------------------------------------------------------------
# GET /api/v1/jobs/{job_id}/derived-facts
# ---------------------------------------------------------------------------


class TestGetDerivedFacts:
    """Tests for the derived-facts job endpoint."""

    def test_404_for_unknown_job(self, test_client_with_db):
        resp = test_client_with_db.get(f"/api/v1/jobs/{uuid4()}/derived-facts")
        assert resp.status_code == 404

    def test_422_for_invalid_uuid(self, test_client_with_db):
        resp = test_client_with_db.get("/api/v1/jobs/not-a-uuid/derived-facts")
        assert resp.status_code == 422

    def test_empty_when_no_derived_facts(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="model.xlsx", file_size=500)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        resp = test_client_with_db.get(f"/api/v1/jobs/{job.job_id}/derived-facts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == str(job.job_id)
        assert data["count"] == 0
        assert data["facts"] == []

    def test_returns_derived_facts(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="model.xlsx", file_size=500)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        _make_derived_fact(db_session, job.job_id, canonical_name="ebitda", period="FY2023")
        _make_derived_fact(db_session, job.job_id, canonical_name="net_debt", period="FY2023")

        resp = test_client_with_db.get(f"/api/v1/jobs/{job.job_id}/derived-facts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        names = {f["canonical_name"] for f in data["facts"]}
        assert names == {"ebitda", "net_debt"}

    def test_filter_by_canonical_names(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="model.xlsx", file_size=500)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        _make_derived_fact(db_session, job.job_id, canonical_name="ebitda", period="FY2023")
        _make_derived_fact(db_session, job.job_id, canonical_name="net_debt", period="FY2023")
        _make_derived_fact(db_session, job.job_id, canonical_name="dscr_project_finance", period="FY2023")

        resp = test_client_with_db.get(
            f"/api/v1/jobs/{job.job_id}/derived-facts",
            params={"canonical_names": "ebitda,dscr_project_finance"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        names = {f["canonical_name"] for f in data["facts"]}
        assert "net_debt" not in names

    def test_filter_gap_fill_only(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="model.xlsx", file_size=500)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        _make_derived_fact(db_session, job.job_id, canonical_name="ebitda", period="FY2023", is_gap_fill=True)
        _make_derived_fact(
            db_session,
            job.job_id,
            canonical_name="gross_profit",
            period="FY2023",
            is_gap_fill=False,
            consistency_check={"extracted_value": 400.0, "computed_value": 410.0, "divergence_pct": 2.4, "passed": True},
        )

        resp = test_client_with_db.get(
            f"/api/v1/jobs/{job.job_id}/derived-facts",
            params={"is_gap_fill": "true"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["facts"][0]["canonical_name"] == "ebitda"

    def test_fact_fields_populated(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="model.xlsx", file_size=500)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        _make_derived_fact(
            db_session,
            job.job_id,
            canonical_name="dscr_project_finance",
            period="FY2024",
            computed_value=Decimal("1.35"),
            confidence=0.87,
            value_range_low=Decimal("1.21"),
            value_range_high=Decimal("1.49"),
            computation_rule_id="DR-031",
            formula="cfads / debt_service",
            source_canonicals=["cfads", "debt_service"],
            confidence_mode="product",
            derivation_pass=2,
            is_gap_fill=True,
        )

        resp = test_client_with_db.get(f"/api/v1/jobs/{job.job_id}/derived-facts")
        assert resp.status_code == 200
        fact = resp.json()["facts"][0]
        assert fact["canonical_name"] == "dscr_project_finance"
        assert fact["period"] == "FY2024"
        assert abs(fact["computed_value"] - 1.35) < 0.001
        assert abs(fact["confidence"] - 0.87) < 0.001
        assert abs(fact["value_range_low"] - 1.21) < 0.001
        assert abs(fact["value_range_high"] - 1.49) < 0.001
        assert fact["computation_rule_id"] == "DR-031"
        assert fact["formula"] == "cfads / debt_service"
        assert fact["is_gap_fill"] is True
        assert fact["derivation_pass"] == 2


# ---------------------------------------------------------------------------
# GET /api/v1/jobs/{job_id}/consistency-report
# ---------------------------------------------------------------------------


class TestConsistencyReport:
    """Tests for the consistency-report endpoint."""

    def test_404_for_unknown_job(self, test_client_with_db):
        resp = test_client_with_db.get(f"/api/v1/jobs/{uuid4()}/consistency-report")
        assert resp.status_code == 404

    def test_empty_when_no_consistency_checks(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="model.xlsx", file_size=500)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)
        # Gap-fill fact — no consistency check
        _make_derived_fact(db_session, job.job_id, is_gap_fill=True, consistency_check=None)

        resp = test_client_with_db.get(f"/api/v1/jobs/{job.job_id}/consistency-report")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_checked"] == 0
        assert data["violations"] == 0
        assert data["items"] == []

    def test_reports_passing_consistency_check(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="model.xlsx", file_size=500)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        _make_derived_fact(
            db_session,
            job.job_id,
            canonical_name="ebitda",
            period="FY2023",
            is_gap_fill=False,
            consistency_check={
                "extracted_value": 500000.0,
                "computed_value": 505000.0,
                "divergence_pct": 1.0,
                "passed": True,
                "threshold_pct": 3.0,
            },
        )

        resp = test_client_with_db.get(f"/api/v1/jobs/{job.job_id}/consistency-report")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_checked"] == 1
        assert data["passed"] == 1
        assert data["violations"] == 0
        item = data["items"][0]
        assert item["canonical_name"] == "ebitda"
        assert item["passed"] is True

    def test_reports_violation(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="model.xlsx", file_size=500)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        _make_derived_fact(
            db_session,
            job.job_id,
            canonical_name="dscr_project_finance",
            period="FY2023",
            is_gap_fill=False,
            consistency_check={
                "extracted_value": 1.50,
                "computed_value": 1.28,
                "divergence_pct": 14.7,
                "passed": False,
                "threshold_pct": 5.0,
            },
        )

        resp = test_client_with_db.get(f"/api/v1/jobs/{job.job_id}/consistency-report")
        assert resp.status_code == 200
        data = resp.json()
        assert data["violations"] == 1
        item = data["items"][0]
        assert item["passed"] is False
        assert abs(item["divergence_pct"] - 14.7) < 0.01


# ---------------------------------------------------------------------------
# GET /api/v1/jobs/{job_id}/covenant-sensitivity
# ---------------------------------------------------------------------------


class TestCovenantSensitivity:
    """Tests for the covenant-sensitivity endpoint."""

    def test_404_for_unknown_job(self, test_client_with_db):
        resp = test_client_with_db.get(f"/api/v1/jobs/{uuid4()}/covenant-sensitivity")
        assert resp.status_code == 404

    def test_empty_when_no_sensitive_facts(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="model.xlsx", file_size=500)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)
        # Fact with passing covenant (not sensitive)
        _make_derived_fact(
            db_session,
            job.job_id,
            covenant_context={
                "threshold": 1.25,
                "headroom": 0.30,
                "is_sensitive": False,
            },
        )

        resp = test_client_with_db.get(f"/api/v1/jobs/{job.job_id}/covenant-sensitivity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sensitive_count"] == 0
        assert data["facts"] == []

    def test_returns_sensitive_facts(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="model.xlsx", file_size=500)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)

        # Non-sensitive
        _make_derived_fact(
            db_session,
            job.job_id,
            canonical_name="debt_to_ebitda",
            period="FY2024",
            covenant_context={"threshold": 6.0, "headroom": 2.0, "is_sensitive": False},
        )
        # Sensitive — headroom_range_low < 0
        _make_derived_fact(
            db_session,
            job.job_id,
            canonical_name="dscr_project_finance",
            period="FY2024",
            computed_value=Decimal("1.29"),
            value_range_low=Decimal("1.21"),
            value_range_high=Decimal("1.37"),
            covenant_context={
                "threshold": 1.25,
                "headroom": 0.04,
                "headroom_range_low": -0.04,
                "headroom_range_high": 0.12,
                "is_sensitive": True,
                "flag_message": "COVENANT SENSITIVE — lower bound breaches 1.25x",
            },
        )

        resp = test_client_with_db.get(f"/api/v1/jobs/{job.job_id}/covenant-sensitivity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sensitive_count"] == 1
        fact = data["facts"][0]
        assert fact["canonical_name"] == "dscr_project_finance"
        assert fact["covenant"]["is_sensitive"] is True
        assert fact["covenant"]["flag_message"] is not None
        assert abs(fact["computed_value"] - 1.29) < 0.001


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/entity/{entity_id}/standardised-financials
# ---------------------------------------------------------------------------


class TestStandardisedFinancials:
    """Tests for the entity standardised-financials endpoint."""

    def test_404_for_unknown_entity(self, test_client_with_db):
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{uuid4()}/standardised-financials"
        )
        assert resp.status_code == 404

    def test_400_for_invalid_uuid(self, test_client_with_db):
        resp = test_client_with_db.get(
            "/api/v1/analytics/entity/bad-uuid/standardised-financials"
        )
        assert resp.status_code == 400

    def test_empty_when_no_completed_job(self, test_client_with_db, db_session):
        entity = crud.create_entity(db_session, name="Acme Corp")

        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{entity.id}/standardised-financials"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == str(entity.id)
        assert data["count"] == 0
        assert data["items"] == []

    def test_returns_derived_facts_for_completed_job(self, test_client_with_db, db_session):
        entity = crud.create_entity(db_session, name="TestCo")
        file = crud.create_file(db_session, filename="model.xlsx", file_size=500, entity_id=entity.id)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)
        # Mark job completed
        job.status = JobStatusEnum.COMPLETED
        db_session.commit()

        _make_derived_fact(
            db_session,
            job.job_id,
            canonical_name="ebitda",
            period="FY2024",
            computed_value=Decimal("5000000"),
            confidence=0.91,
        )

        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{entity.id}/standardised-financials"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        names = {i["canonical_name"] for i in data["items"]}
        assert "ebitda" in names

    def test_filter_by_canonical_names(self, test_client_with_db, db_session):
        entity = crud.create_entity(db_session, name="FilterCo")
        file = crud.create_file(db_session, filename="model.xlsx", file_size=500, entity_id=entity.id)
        job = crud.create_extraction_job(db_session, file_id=file.file_id)
        job.status = JobStatusEnum.COMPLETED
        db_session.commit()

        _make_derived_fact(db_session, job.job_id, canonical_name="ebitda", period="FY2024")
        _make_derived_fact(db_session, job.job_id, canonical_name="net_debt", period="FY2024")
        _make_derived_fact(db_session, job.job_id, canonical_name="dscr_project_finance", period="FY2024")

        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{entity.id}/standardised-financials",
            params={"canonical_names": "ebitda,net_debt"},
        )
        assert resp.status_code == 200
        data = resp.json()
        names = {i["canonical_name"] for i in data["items"]}
        assert names == {"ebitda", "net_debt"}


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/portfolio/covenant-monitor
# ---------------------------------------------------------------------------


class TestPortfolioCovenantMonitor:
    """Tests for the portfolio covenant-monitor endpoint."""

    def test_empty_when_no_sensitive_facts(self, test_client_with_db, db_session):
        resp = test_client_with_db.get("/api/v1/analytics/portfolio/covenant-monitor")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sensitive_count"] == 0
        assert data["items"] == []

    def test_400_for_invalid_entity_ids(self, test_client_with_db):
        resp = test_client_with_db.get(
            "/api/v1/analytics/portfolio/covenant-monitor",
            params={"entity_ids": "not-a-uuid"},
        )
        assert resp.status_code == 400

    def test_returns_sensitive_facts_across_portfolio(self, test_client_with_db, db_session):
        # Two entities, each with a completed job and a covenant-sensitive fact
        entity_a = crud.create_entity(db_session, name="Entity A")
        entity_b = crud.create_entity(db_session, name="Entity B")

        file_a = crud.create_file(db_session, filename="a.xlsx", file_size=100, entity_id=entity_a.id)
        file_b = crud.create_file(db_session, filename="b.xlsx", file_size=100, entity_id=entity_b.id)

        job_a = crud.create_extraction_job(db_session, file_id=file_a.file_id)
        job_b = crud.create_extraction_job(db_session, file_id=file_b.file_id)

        job_a.status = JobStatusEnum.COMPLETED
        job_b.status = JobStatusEnum.COMPLETED
        db_session.commit()

        _make_derived_fact(
            db_session,
            job_a.job_id,
            canonical_name="dscr_project_finance",
            period="FY2024",
            covenant_context={"is_sensitive": True, "threshold": 1.25, "headroom": 0.03},
        )
        _make_derived_fact(
            db_session,
            job_b.job_id,
            canonical_name="dscr_project_finance",
            period="FY2024",
            covenant_context={"is_sensitive": True, "threshold": 1.20, "headroom": 0.01},
        )

        resp = test_client_with_db.get("/api/v1/analytics/portfolio/covenant-monitor")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sensitive_count"] == 2
        assert data["total_entities_monitored"] == 2
        entity_ids = {item["entity_id"] for item in data["items"]}
        assert str(entity_a.id) in entity_ids
        assert str(entity_b.id) in entity_ids

    def test_filter_by_entity_ids(self, test_client_with_db, db_session):
        entity_a = crud.create_entity(db_session, name="Monitored A")
        entity_b = crud.create_entity(db_session, name="Excluded B")

        file_a = crud.create_file(db_session, filename="a.xlsx", file_size=100, entity_id=entity_a.id)
        file_b = crud.create_file(db_session, filename="b.xlsx", file_size=100, entity_id=entity_b.id)

        job_a = crud.create_extraction_job(db_session, file_id=file_a.file_id)
        job_b = crud.create_extraction_job(db_session, file_id=file_b.file_id)

        job_a.status = JobStatusEnum.COMPLETED
        job_b.status = JobStatusEnum.COMPLETED
        db_session.commit()

        _make_derived_fact(
            db_session,
            job_a.job_id,
            canonical_name="dscr_project_finance",
            period="FY2024",
            covenant_context={"is_sensitive": True, "threshold": 1.25, "headroom": 0.02},
        )
        _make_derived_fact(
            db_session,
            job_b.job_id,
            canonical_name="dscr_project_finance",
            period="FY2024",
            covenant_context={"is_sensitive": True, "threshold": 1.25, "headroom": 0.02},
        )

        # Filter to only entity_a
        resp = test_client_with_db.get(
            "/api/v1/analytics/portfolio/covenant-monitor",
            params={"entity_ids": str(entity_a.id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sensitive_count"] == 1
        assert data["items"][0]["entity_id"] == str(entity_a.id)
