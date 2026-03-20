"""Tests for Phase 8 Intelligence Layer endpoints.

Tests for:
- GET /api/v1/analytics/confidence-calibration
- GET /api/v1/jobs/{job_id}/review-suggestions
- Auth requirements
- Auto-promotion CRUD
"""

import uuid
from decimal import Decimal
from unittest.mock import patch

from src.db.models import (
    CorrectionHistory,
    Entity,
    ExtractionFact,
    ExtractionJob,
    File,
    JobStatusEnum,
    LearnedAlias,
)

# ============================================================================
# Confidence Calibration Endpoint
# ============================================================================


class TestConfidenceCalibration:
    """Test GET /api/v1/analytics/confidence-calibration."""

    def test_empty_database(self, test_client_with_db):
        """Empty database returns 10 empty buckets."""
        resp = test_client_with_db.get("/api/v1/analytics/confidence-calibration")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_facts"] == 0
        assert data["total_corrections"] == 0
        assert len(data["buckets"]) == 10
        # All buckets should have 0 predictions
        for bucket in data["buckets"]:
            assert bucket["total_predictions"] == 0
            assert bucket["correct_predictions"] == 0
            assert bucket["accuracy"] is None

    def test_with_facts_no_corrections(self, test_client_with_db, test_db):
        """Facts with no corrections should show 100% accuracy."""
        db = test_db()
        try:
            # Create entity, file, job
            entity = Entity(name="Test Corp")
            db.add(entity)
            db.flush()

            f = File(filename="test.xlsx", file_size=1024, entity_id=entity.id)
            db.add(f)
            db.flush()

            job = ExtractionJob(
                file_id=f.file_id,
                status=JobStatusEnum.COMPLETED,
            )
            db.add(job)
            db.flush()

            # Create facts at different confidence levels
            for conf, cn in [
                (0.95, "revenue"),
                (0.85, "cogs"),
                (0.55, "gross_profit"),
            ]:
                fact = ExtractionFact(
                    job_id=job.job_id,
                    entity_id=entity.id,
                    canonical_name=cn,
                    period="FY2023",
                    value=Decimal("100000"),
                    confidence=conf,
                )
                db.add(fact)
            db.commit()

            resp = test_client_with_db.get("/api/v1/analytics/confidence-calibration")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_facts"] == 3
            assert data["total_corrections"] == 0

            # Bucket 9 (0.9-1.0) should have 1 fact with accuracy 1.0
            bucket_9 = data["buckets"][9]
            assert bucket_9["total_predictions"] == 1
            assert bucket_9["correct_predictions"] == 1
            assert bucket_9["accuracy"] == 1.0

            # Bucket 8 (0.8-0.9) should have 1 fact
            bucket_8 = data["buckets"][8]
            assert bucket_8["total_predictions"] == 1
            assert bucket_8["correct_predictions"] == 1

            # Bucket 5 (0.5-0.6) should have 1 fact
            bucket_5 = data["buckets"][5]
            assert bucket_5["total_predictions"] == 1
            assert bucket_5["correct_predictions"] == 1
        finally:
            db.close()

    def test_with_corrections(self, test_client_with_db, test_db):
        """Facts that were corrected should reduce accuracy."""
        db = test_db()
        try:
            entity = Entity(name="Test Corp")
            db.add(entity)
            db.flush()

            f = File(filename="test.xlsx", file_size=1024, entity_id=entity.id)
            db.add(f)
            db.flush()

            job = ExtractionJob(
                file_id=f.file_id,
                status=JobStatusEnum.COMPLETED,
            )
            db.add(job)
            db.flush()

            # Create a fact that was corrected
            fact = ExtractionFact(
                job_id=job.job_id,
                entity_id=entity.id,
                canonical_name="revenue",
                period="FY2023",
                value=Decimal("100000"),
                confidence=0.85,
            )
            db.add(fact)

            # Create a fact that was NOT corrected
            fact2 = ExtractionFact(
                job_id=job.job_id,
                entity_id=entity.id,
                canonical_name="cogs",
                period="FY2023",
                value=Decimal("50000"),
                confidence=0.85,
            )
            db.add(fact2)

            # Create correction for 'revenue'
            correction = CorrectionHistory(
                job_id=job.job_id,
                entity_id=entity.id,
                original_label="Revenue",
                old_canonical_name="revenue",
                new_canonical_name="net_revenue",
                old_confidence=0.85,
                new_confidence=1.0,
                reverted=False,
            )
            db.add(correction)
            db.commit()

            resp = test_client_with_db.get("/api/v1/analytics/confidence-calibration")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_facts"] == 2
            assert data["total_corrections"] == 1

            # Bucket 8 (0.8-0.9) should have 2 facts, 1 correct
            bucket_8 = data["buckets"][8]
            assert bucket_8["total_predictions"] == 2
            assert bucket_8["correct_predictions"] == 1
            assert bucket_8["accuracy"] == 0.5
        finally:
            db.close()

    def test_auth_required(self, test_db):
        """Endpoint should require authentication."""
        from fastapi.testclient import TestClient

        from src.api.main import app
        from src.db.session import get_db

        def override_get_db():
            db = test_db()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app, raise_server_exceptions=False)
        try:
            resp = client.get("/api/v1/analytics/confidence-calibration")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()


# ============================================================================
# Review Suggestions Endpoint
# ============================================================================


class TestReviewSuggestions:
    """Test GET /api/v1/jobs/{job_id}/review-suggestions."""

    def test_job_not_found(self, test_client_with_db):
        """Non-existent job returns 404."""
        fake_id = str(uuid.uuid4())
        resp = test_client_with_db.get(f"/api/v1/jobs/{fake_id}/review-suggestions")
        assert resp.status_code == 404

    def test_invalid_job_id(self, test_client_with_db):
        """Invalid job_id format returns 400."""
        resp = test_client_with_db.get("/api/v1/jobs/not-a-uuid/review-suggestions")
        assert resp.status_code == 400

    def test_job_no_results(self, test_client_with_db, test_db):
        """Job without results returns empty suggestions."""
        db = test_db()
        try:
            f = File(filename="test.xlsx", file_size=1024)
            db.add(f)
            db.flush()

            job = ExtractionJob(
                file_id=f.file_id,
                status=JobStatusEnum.COMPLETED,
                result=None,
            )
            db.add(job)
            db.commit()
            job_id = str(job.job_id)
        finally:
            db.close()

        resp = test_client_with_db.get(f"/api/v1/jobs/{job_id}/review-suggestions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["suggestions"] == []
        assert data["total_items"] == 0

    def test_mixed_confidence_items(self, test_client_with_db, test_db):
        """Items with various confidence levels should be scored correctly."""
        db = test_db()
        try:
            f = File(filename="test.xlsx", file_size=1024)
            db.add(f)
            db.flush()

            result = {
                "line_items": [
                    {
                        "original_label": "Revenue",
                        "canonical_name": "revenue",
                        "confidence": 0.95,
                        "sheet": "IS",
                        "values": {"FY2023": 100000},
                        "provenance": {"mapping": {"method": "entity_pattern"}},
                        "validation_flags": [],
                    },
                    {
                        "original_label": "Unknown Item",
                        "canonical_name": "unmapped",
                        "confidence": 0.0,
                        "sheet": "IS",
                        "values": {"FY2023": 5000},
                        "provenance": {"mapping": {"method": "none"}},
                        "validation_flags": [],
                    },
                    {
                        "original_label": "Cost of Sales",
                        "canonical_name": "cogs",
                        "confidence": 0.55,
                        "sheet": "IS",
                        "values": {"FY2023": 40000},
                        "provenance": {"mapping": {"method": "fuzzy"}},
                        "validation_flags": ["sign_mismatch"],
                    },
                    {
                        "original_label": "SGA",
                        "canonical_name": "sga",
                        "confidence": 0.75,
                        "sheet": "IS",
                        "values": {"FY2023": 20000},
                        "provenance": {"mapping": {"method": "claude"}},
                        "validation_flags": [],
                    },
                ],
                "sheets": ["IS"],
            }

            job = ExtractionJob(
                file_id=f.file_id,
                status=JobStatusEnum.COMPLETED,
                result=result,
            )
            db.add(job)
            db.commit()
            job_id = str(job.job_id)
        finally:
            db.close()

        resp = test_client_with_db.get(f"/api/v1/jobs/{job_id}/review-suggestions")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_items"] == 4
        suggestions = data["suggestions"]
        assert len(suggestions) > 0

        # The unmapped item should have highest priority
        assert suggestions[0]["canonical_name"] == "unmapped"
        assert suggestions[0]["priority_score"] >= 5
        assert "unmapped" in suggestions[0]["reasons"]

        # Cost of Sales should be second (low confidence + validation flags + non-pattern mapping)
        cos_suggestion = next(
            (s for s in suggestions if s["original_label"] == "Cost of Sales"), None
        )
        assert cos_suggestion is not None
        assert "low confidence" in cos_suggestion["reasons"]
        assert "validation flags" in cos_suggestion["reasons"]

    def test_high_confidence_items_excluded(self, test_client_with_db, test_db):
        """Items with high confidence and no issues should not appear."""
        db = test_db()
        try:
            f = File(filename="test.xlsx", file_size=1024)
            db.add(f)
            db.flush()

            result = {
                "line_items": [
                    {
                        "original_label": "Revenue",
                        "canonical_name": "revenue",
                        "confidence": 0.95,
                        "sheet": "IS",
                        "values": {"FY2023": 100000},
                        "provenance": {"mapping": {"method": "entity_pattern"}},
                        "validation_flags": [],
                    },
                ],
                "sheets": ["IS"],
            }

            job = ExtractionJob(
                file_id=f.file_id,
                status=JobStatusEnum.COMPLETED,
                result=result,
            )
            db.add(job)
            db.commit()
            job_id = str(job.job_id)
        finally:
            db.close()

        resp = test_client_with_db.get(f"/api/v1/jobs/{job_id}/review-suggestions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["suggestions"] == []
        assert data["total_items"] == 1

    def test_auth_required(self, test_db):
        """Endpoint should require authentication."""
        from fastapi.testclient import TestClient

        from src.api.main import app
        from src.db.session import get_db

        def override_get_db():
            db = test_db()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app, raise_server_exceptions=False)
        try:
            fake_id = str(uuid.uuid4())
            resp = client.get(f"/api/v1/jobs/{fake_id}/review-suggestions")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()


# ============================================================================
# Auto-Promotion CRUD
# ============================================================================


class TestAutoPromotion:
    """Test check_auto_promotions CRUD function."""

    def test_no_candidates(self, test_db):
        """No eligible aliases returns 0."""
        from src.db import crud

        db = test_db()
        try:
            result = crud.check_auto_promotions(db)
            assert result == 0
        finally:
            db.close()

    def test_promotes_eligible(self, test_db):
        """Aliases meeting criteria get promoted."""
        from src.db import crud

        db = test_db()
        try:
            # Create an alias that meets criteria
            alias = LearnedAlias(
                canonical_name="revenue",
                alias_text="Net Sales Revenue",
                occurrence_count=6,
                source_entities=["e1", "e2", "e3"],
                promoted=False,
            )
            db.add(alias)
            db.commit()

            with patch(
                "src.db.crud.invalidate_promoted_cache",
                create=True,
            ):
                result = crud.check_auto_promotions(db)

            assert result == 1
            db.refresh(alias)
            assert alias.promoted is True
        finally:
            db.close()

    def test_skips_insufficient_entities(self, test_db):
        """Aliases with too few source_entities are not promoted."""
        from src.db import crud

        db = test_db()
        try:
            alias = LearnedAlias(
                canonical_name="revenue",
                alias_text="Net Sales",
                occurrence_count=10,
                source_entities=["e1", "e2"],  # Only 2 entities, need 3
                promoted=False,
            )
            db.add(alias)
            db.commit()

            result = crud.check_auto_promotions(db)
            assert result == 0
            db.refresh(alias)
            assert alias.promoted is False
        finally:
            db.close()

    def test_skips_low_occurrence(self, test_db):
        """Aliases with occurrence_count < 5 are not promoted."""
        from src.db import crud

        db = test_db()
        try:
            alias = LearnedAlias(
                canonical_name="revenue",
                alias_text="Net Sales",
                occurrence_count=3,  # Below threshold of 5
                source_entities=["e1", "e2", "e3", "e4"],
                promoted=False,
            )
            db.add(alias)
            db.commit()

            result = crud.check_auto_promotions(db)
            assert result == 0
            db.refresh(alias)
            assert alias.promoted is False
        finally:
            db.close()

    def test_skips_already_promoted(self, test_db):
        """Already-promoted aliases are not counted."""
        from src.db import crud

        db = test_db()
        try:
            alias = LearnedAlias(
                canonical_name="revenue",
                alias_text="Net Sales",
                occurrence_count=10,
                source_entities=["e1", "e2", "e3"],
                promoted=True,  # Already promoted
            )
            db.add(alias)
            db.commit()

            result = crud.check_auto_promotions(db)
            assert result == 0
        finally:
            db.close()


# ============================================================================
# Confidence Calibration CRUD
# ============================================================================


class TestConfidenceCalibrationCRUD:
    """Test get_confidence_calibration CRUD function directly."""

    def test_empty_db(self, test_db):
        """Empty database returns zero-count buckets."""
        from src.db import crud

        db = test_db()
        try:
            result = crud.get_confidence_calibration(db)
            assert result["total_facts"] == 0
            assert result["total_corrections"] == 0
            assert len(result["buckets"]) == 10
        finally:
            db.close()

    def test_bucket_boundaries(self, test_db):
        """Facts at boundary values go to correct buckets."""
        from src.db import crud

        db = test_db()
        try:
            entity = Entity(name="Test Corp")
            db.add(entity)
            db.flush()

            f = File(filename="test.xlsx", file_size=1024, entity_id=entity.id)
            db.add(f)
            db.flush()

            job = ExtractionJob(
                file_id=f.file_id,
                status=JobStatusEnum.COMPLETED,
            )
            db.add(job)
            db.flush()

            # Confidence 0.0 -> bucket 0
            fact_0 = ExtractionFact(
                job_id=job.job_id,
                entity_id=entity.id,
                canonical_name="rev_a",
                period="FY2023",
                value=Decimal("1000"),
                confidence=0.0,
            )
            db.add(fact_0)

            # Confidence 1.0 -> bucket 9 (clamped to max index)
            fact_1 = ExtractionFact(
                job_id=job.job_id,
                entity_id=entity.id,
                canonical_name="rev_b",
                period="FY2023",
                value=Decimal("2000"),
                confidence=1.0,
            )
            db.add(fact_1)
            db.commit()

            result = crud.get_confidence_calibration(db)
            assert result["total_facts"] == 2

            # Bucket 0 (0.0-0.1) should have 1 fact
            assert result["buckets"][0]["total_predictions"] == 1

            # Bucket 9 (0.9-1.0) should have 1 fact
            assert result["buckets"][9]["total_predictions"] == 1
        finally:
            db.close()
