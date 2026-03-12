"""Tests for the admin review workflow (approve/reject NEEDS_REVIEW jobs)."""
import pytest
from uuid import uuid4

from src.db.models import JobStatusEnum


class TestReviewEndpoint:
    """Test POST /api/v1/jobs/{job_id}/review."""

    def _create_needs_review_job(self, test_db):
        """Helper: create a file + job in NEEDS_REVIEW status."""
        from src.db import crud

        session = test_db()
        file = crud.create_file(
            session, filename="review_test.xlsx", file_size=1024,
            s3_key="uploads/review_test.xlsx",
        )
        job = crud.create_extraction_job(session, file_id=file.file_id)
        result = {
            "quality": {
                "letter_grade": "F",
                "numeric_score": 0.25,
                "quality_gate": {"passed": False, "reason": "Grade F"},
            },
        }
        crud.complete_job(
            session, job.job_id, result=result,
            tokens_used=500, cost_usd=0.01, quality_grade="F",
        )
        session.close()
        return str(job.job_id)

    def test_approve_transitions_to_completed(self, test_client_with_db, test_db):
        """Approving a NEEDS_REVIEW job transitions it to COMPLETED."""
        job_id = self._create_needs_review_job(test_db)
        resp = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/review",
            json={"decision": "approve"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["previous_status"] == "needs_review"
        assert data["new_status"] == "completed"
        assert data["decision"] == "approve"

    def test_reject_transitions_to_failed(self, test_client_with_db, test_db):
        """Rejecting a NEEDS_REVIEW job transitions it to FAILED with reason."""
        job_id = self._create_needs_review_job(test_db)
        resp = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/review",
            json={"decision": "reject", "reason": "Bad quality"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_status"] == "failed"
        assert data["reason"] == "Bad quality"

    def test_review_non_needs_review_returns_409(self, test_client_with_db, test_db):
        """Reviewing a job not in NEEDS_REVIEW returns 409."""
        from src.db import crud

        session = test_db()
        file = crud.create_file(
            session, filename="ok.xlsx", file_size=1024,
            s3_key="uploads/ok.xlsx",
        )
        job = crud.create_extraction_job(session, file_id=file.file_id)
        result = {
            "quality": {
                "letter_grade": "A",
                "numeric_score": 0.95,
                "quality_gate": {"passed": True},
            },
        }
        crud.complete_job(
            session, job.job_id, result=result,
            tokens_used=100, cost_usd=0.005, quality_grade="A",
        )
        session.close()

        resp = test_client_with_db.post(
            f"/api/v1/jobs/{str(job.job_id)}/review",
            json={"decision": "approve"},
        )
        assert resp.status_code == 409

    def test_review_invalid_decision_returns_422(self, test_client_with_db, test_db):
        """Invalid decision value returns 422 validation error."""
        job_id = self._create_needs_review_job(test_db)
        resp = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/review",
            json={"decision": "maybe"},
        )
        assert resp.status_code == 422

    def test_review_nonexistent_job_returns_404(self, test_client_with_db):
        """Reviewing a nonexistent job returns 404."""
        fake_id = str(uuid4())
        resp = test_client_with_db.post(
            f"/api/v1/jobs/{fake_id}/review",
            json={"decision": "approve"},
        )
        assert resp.status_code == 404

    def test_needs_review_job_can_be_exported(self, test_client_with_db, test_db):
        """NEEDS_REVIEW jobs should be exportable (not blocked by status check)."""
        from src.db import crud

        session = test_db()
        file = crud.create_file(
            session, filename="export_test.xlsx", file_size=1024,
            s3_key="uploads/export_test.xlsx",
        )
        job = crud.create_extraction_job(session, file_id=file.file_id)
        result = {
            "line_items": [{"canonical_name": "revenue", "confidence": 0.9}],
            "sheets": ["Sheet1"],
            "quality": {
                "letter_grade": "F",
                "numeric_score": 0.25,
                "quality_gate": {"passed": False},
            },
        }
        crud.complete_job(
            session, job.job_id, result=result,
            tokens_used=100, cost_usd=0.005, quality_grade="F",
        )
        session.close()

        resp = test_client_with_db.get(
            f"/api/v1/jobs/{str(job.job_id)}/export?format=json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["line_items_count"] == 1


class TestExportEnhancements:
    """Test E4 (model_type) and E5 (validation_delta) in export response."""

    def test_export_includes_model_type_and_validation_delta(
        self, test_client_with_db, test_db
    ):
        """Export JSON should include model_type and validation_delta."""
        from src.db import crud

        session = test_db()
        file = crud.create_file(
            session, filename="enhanced.xlsx", file_size=1024,
            s3_key="uploads/enhanced.xlsx",
        )
        job = crud.create_extraction_job(session, file_id=file.file_id)
        result = {
            "line_items": [{"canonical_name": "revenue", "confidence": 0.9}],
            "sheets": ["Sheet1"],
            "model_type": "project_finance",
            "validation_delta": {
                "pre_stage5_rate": 0.75,
                "post_stage5_rate": 0.80,
                "delta": 0.05,
                "improved": True,
            },
            "quality": {
                "letter_grade": "B",
                "numeric_score": 0.82,
                "quality_gate": {"passed": True},
            },
        }
        crud.complete_job(
            session, job.job_id, result=result,
            tokens_used=200, cost_usd=0.01, quality_grade="B",
        )
        session.close()

        resp = test_client_with_db.get(
            f"/api/v1/jobs/{str(job.job_id)}/export?format=json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_type"] == "project_finance"
        assert data["validation_delta"]["delta"] == 0.05
        assert data["quality"]["letter_grade"] == "B"

    def test_export_model_type_null_when_absent(
        self, test_client_with_db, test_db
    ):
        """Export JSON model_type should be null when not in result."""
        from src.db import crud

        session = test_db()
        file = crud.create_file(
            session, filename="plain.xlsx", file_size=1024,
            s3_key="uploads/plain.xlsx",
        )
        job = crud.create_extraction_job(session, file_id=file.file_id)
        result = {
            "line_items": [],
            "sheets": ["Sheet1"],
            "quality": {
                "letter_grade": "C",
                "numeric_score": 0.6,
                "quality_gate": {"passed": True},
            },
        }
        crud.complete_job(
            session, job.job_id, result=result,
            tokens_used=100, cost_usd=0.005, quality_grade="C",
        )
        session.close()

        resp = test_client_with_db.get(
            f"/api/v1/jobs/{str(job.job_id)}/export?format=json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_type"] is None
        assert data["validation_delta"] is None
