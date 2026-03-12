"""Tests for user correction and entity pattern endpoints."""
import pytest
from uuid import uuid4

from src.db.models import JobStatusEnum


class TestSubmitCorrections:
    """Test POST /api/v1/jobs/{job_id}/corrections."""

    def test_submit_corrections_creates_patterns(self, test_client_with_db, test_db):
        """Submitting corrections creates entity patterns with confidence=1.0."""
        from src.db import crud

        session = test_db()
        try:
            # Create entity, file with entity_id, and job
            entity = crud.create_entity(session, name="Acme Corp", industry="Finance")
            file = crud.create_file(
                session,
                filename="test.xlsx",
                file_size=1024,
                entity_id=entity.id,
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)
            job_id = str(job.job_id)
            entity_id = str(entity.id)
        finally:
            session.close()

        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections",
            json={
                "corrections": [
                    {"original_label": "Net Sales", "canonical_name": "revenue"},
                    {"original_label": "COGS", "canonical_name": "cogs"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["patterns_created"] == 2
        assert data["patterns_updated"] == 0
        assert "Applied 2 corrections" in data["message"]

        # Verify patterns were created by querying them
        patterns_resp = test_client_with_db.get(
            f"/api/v1/entities/{entity_id}/patterns"
        )
        assert patterns_resp.status_code == 200
        patterns_data = patterns_resp.json()
        assert patterns_data["total_patterns"] == 2

        # Verify confidence is 1.0 and created_by is user_correction
        for p in patterns_data["patterns"]:
            assert p["confidence"] == 1.0
            assert p["created_by"] == "user_correction"

    def test_submit_corrections_updates_existing(self, test_client_with_db, test_db):
        """Submitting corrections for existing labels updates them."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Beta Inc")
            file = crud.create_file(
                session,
                filename="test.xlsx",
                file_size=1024,
                entity_id=entity.id,
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)
            job_id = str(job.job_id)

            # Pre-create a pattern (as if Claude created it)
            crud.upsert_entity_pattern(
                session,
                entity_id=entity.id,
                original_label="Net Sales",
                canonical_name="other_revenue",
                confidence=0.85,
                created_by="claude",
            )
        finally:
            session.close()

        # User corrects the mapping
        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections",
            json={
                "corrections": [
                    {"original_label": "Net Sales", "canonical_name": "revenue"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["patterns_created"] == 0
        assert data["patterns_updated"] == 1

    def test_submit_corrections_no_entity_id(self, test_client_with_db, test_db):
        """Corrections on a job without entity association returns 400."""
        from src.db import crud

        session = test_db()
        try:
            # Create file WITHOUT entity_id
            file = crud.create_file(
                session,
                filename="test.xlsx",
                file_size=1024,
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections",
            json={
                "corrections": [
                    {"original_label": "Revenue", "canonical_name": "revenue"},
                ]
            },
        )

        assert response.status_code == 400
        assert "entity association" in response.json()["detail"].lower()

    def test_submit_corrections_job_not_found(self, test_client_with_db):
        """Corrections on nonexistent job returns 404."""
        fake_job_id = str(uuid4())
        response = test_client_with_db.post(
            f"/api/v1/jobs/{fake_job_id}/corrections",
            json={
                "corrections": [
                    {"original_label": "Revenue", "canonical_name": "revenue"},
                ]
            },
        )
        assert response.status_code == 404

    def test_submit_corrections_invalid_job_id(self, test_client_with_db):
        """Invalid job_id format returns 400."""
        response = test_client_with_db.post(
            "/api/v1/jobs/not-a-uuid/corrections",
            json={
                "corrections": [
                    {"original_label": "Revenue", "canonical_name": "revenue"},
                ]
            },
        )
        assert response.status_code == 400


class TestListEntityPatterns:
    """Test GET /api/v1/entities/{entity_id}/patterns."""

    def test_list_patterns_empty(self, test_client_with_db, test_db):
        """Listing patterns for entity with none returns empty list."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Empty Corp")
            entity_id = str(entity.id)
        finally:
            session.close()

        response = test_client_with_db.get(
            f"/api/v1/entities/{entity_id}/patterns"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] == entity_id
        assert data["patterns"] == []
        assert data["total_patterns"] == 0

    def test_list_patterns_with_data(self, test_client_with_db, test_db):
        """Listing patterns returns all patterns for the entity."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Pattern Corp")
            crud.upsert_entity_pattern(
                session,
                entity_id=entity.id,
                original_label="Revenue",
                canonical_name="revenue",
                confidence=0.95,
                created_by="claude",
            )
            crud.upsert_entity_pattern(
                session,
                entity_id=entity.id,
                original_label="COGS",
                canonical_name="cogs",
                confidence=0.90,
                created_by="user_correction",
            )
            entity_id = str(entity.id)
        finally:
            session.close()

        response = test_client_with_db.get(
            f"/api/v1/entities/{entity_id}/patterns"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_patterns"] == 2
        assert len(data["patterns"]) == 2

        # Check pattern fields
        pattern = data["patterns"][0]
        assert "id" in pattern
        assert "original_label" in pattern
        assert "canonical_name" in pattern
        assert "confidence" in pattern
        assert "occurrence_count" in pattern
        assert "created_by" in pattern

    def test_list_patterns_invalid_entity_id(self, test_client_with_db):
        """Invalid entity_id returns 400."""
        response = test_client_with_db.get(
            "/api/v1/entities/not-a-uuid/patterns"
        )
        assert response.status_code == 400


class TestDeleteEntityPattern:
    """Test DELETE /api/v1/entities/{entity_id}/patterns/{pattern_id}."""

    def test_delete_pattern(self, test_client_with_db, test_db):
        """Deleting a pattern returns 204 and removes it."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Delete Corp")
            pattern = crud.upsert_entity_pattern(
                session,
                entity_id=entity.id,
                original_label="Revenue",
                canonical_name="revenue",
                confidence=0.95,
                created_by="claude",
            )
            entity_id = str(entity.id)
            pattern_id = str(pattern.id)
        finally:
            session.close()

        response = test_client_with_db.delete(
            f"/api/v1/entities/{entity_id}/patterns/{pattern_id}"
        )
        assert response.status_code == 204

        # Verify it's gone
        list_resp = test_client_with_db.get(
            f"/api/v1/entities/{entity_id}/patterns"
        )
        assert list_resp.json()["total_patterns"] == 0

    def test_delete_pattern_not_found(self, test_client_with_db, test_db):
        """Deleting a nonexistent pattern returns 404."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Corp")
            entity_id = str(entity.id)
        finally:
            session.close()

        fake_pattern_id = str(uuid4())
        response = test_client_with_db.delete(
            f"/api/v1/entities/{entity_id}/patterns/{fake_pattern_id}"
        )
        assert response.status_code == 404

    def test_delete_pattern_invalid_ids(self, test_client_with_db):
        """Invalid IDs return 400."""
        response = test_client_with_db.delete(
            "/api/v1/entities/bad-id/patterns/bad-id"
        )
        assert response.status_code == 400


class TestCorrectionsCRUD:
    """Test CRUD operations directly for entity pattern deletion."""

    def test_delete_entity_pattern_crud(self, db_session):
        """Test delete_entity_pattern CRUD function."""
        from src.db import crud

        entity = crud.create_entity(db_session, name="CRUD Test")
        pattern = crud.upsert_entity_pattern(
            db_session,
            entity_id=entity.id,
            original_label="Revenue",
            canonical_name="revenue",
            confidence=0.95,
            created_by="claude",
        )

        assert crud.delete_entity_pattern(db_session, pattern.id) is True
        assert crud.delete_entity_pattern(db_session, pattern.id) is False  # Already deleted

    def test_delete_entity_pattern_nonexistent(self, db_session):
        """Deleting nonexistent pattern returns False."""
        from src.db import crud

        assert crud.delete_entity_pattern(db_session, uuid4()) is False


# ============================================================================
# WS-J: Retroactive Correction Tests
# ============================================================================


def _create_job_with_result(session):
    """Helper: create entity + file + completed job with sample line_items."""
    from src.db import crud

    entity = crud.create_entity(session, name="Test Corp", industry="Finance")
    file = crud.create_file(
        session, filename="test.xlsx", file_size=1024, entity_id=entity.id
    )
    job = crud.create_extraction_job(session, file_id=file.file_id)
    job.status = JobStatusEnum.COMPLETED
    job.result = {
        "line_items": [
            {
                "sheet": "Sheet1",
                "row": 2,
                "original_label": "Revenue",
                "canonical_name": "other_revenue",
                "values": {"2022": 1000, "2023": 1200},
                "confidence": 0.85,
                "hierarchy_level": 1,
                "provenance": {
                    "mapping": {
                        "method": "claude",
                        "stage": 3,
                        "taxonomy_category": "income_statement",
                        "reasoning": "Mapped by Claude",
                    }
                },
            },
            {
                "sheet": "Sheet1",
                "row": 3,
                "original_label": "COGS",
                "canonical_name": "cogs",
                "values": {"2022": 400, "2023": 500},
                "confidence": 0.90,
                "hierarchy_level": 1,
                "provenance": {
                    "mapping": {
                        "method": "claude",
                        "stage": 3,
                        "taxonomy_category": "income_statement",
                        "reasoning": "Mapped by Claude",
                    }
                },
            },
        ],
        "sheets": ["Sheet1"],
    }
    session.commit()
    return entity, file, job


def _create_job_with_multisheet_result(session):
    """Helper: job with same original_label on two different sheets."""
    from src.db import crud

    entity = crud.create_entity(session, name="Multi Corp", industry="Finance")
    file = crud.create_file(
        session, filename="multi.xlsx", file_size=2048, entity_id=entity.id
    )
    job = crud.create_extraction_job(session, file_id=file.file_id)
    job.status = JobStatusEnum.COMPLETED
    job.result = {
        "line_items": [
            {
                "sheet": "Income Statement",
                "row": 2,
                "original_label": "Revenue",
                "canonical_name": "other_revenue",
                "values": {"2023": 5000},
                "confidence": 0.80,
                "hierarchy_level": 1,
                "provenance": {"mapping": {"method": "claude", "stage": 3}},
            },
            {
                "sheet": "Balance Sheet",
                "row": 2,
                "original_label": "Revenue",
                "canonical_name": "other_revenue",
                "values": {"2023": 3000},
                "confidence": 0.75,
                "hierarchy_level": 1,
                "provenance": {"mapping": {"method": "claude", "stage": 3}},
            },
        ],
        "sheets": ["Income Statement", "Balance Sheet"],
    }
    session.commit()
    return entity, file, job


class TestApplyCorrections:
    """Test POST /api/v1/jobs/{job_id}/corrections/apply."""

    def test_apply_updates_result(self, test_client_with_db, test_db):
        """Applying a correction updates canonical_name in job.result."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["corrections_applied"] == 1
        assert len(data["diffs"]) == 1
        assert data["diffs"][0]["old_canonical_name"] == "other_revenue"
        assert data["diffs"][0]["new_canonical_name"] == "revenue"

        # Verify job.result was actually updated
        from src.db import crud

        session2 = test_db()
        try:
            updated_job = crud.get_job(session2, job.job_id)
            li = updated_job.result["line_items"][0]
            assert li["canonical_name"] == "revenue"
            assert li["confidence"] == 1.0
            assert li["provenance"]["mapping"]["method"] == "user_correction"
        finally:
            session2.close()

    def test_apply_creates_history(self, test_client_with_db, test_db):
        """Applying a correction creates a CorrectionHistory record."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )

        # Check history endpoint
        history_resp = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/corrections/history"
        )
        assert history_resp.status_code == 200
        history = history_resp.json()
        assert history["total"] == 1
        assert history["corrections"][0]["old_canonical_name"] == "other_revenue"
        assert history["corrections"][0]["new_canonical_name"] == "revenue"
        assert history["corrections"][0]["reverted"] is False

    def test_apply_creates_entity_pattern(self, test_client_with_db, test_db):
        """Applying a correction also creates an EntityPattern."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
            entity_id = str(entity.id)
        finally:
            session.close()

        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )

        # Verify pattern was created
        patterns_resp = test_client_with_db.get(
            f"/api/v1/entities/{entity_id}/patterns"
        )
        assert patterns_resp.status_code == 200
        patterns = patterns_resp.json()["patterns"]
        assert len(patterns) >= 1
        rev_pattern = [p for p in patterns if p["original_label"] == "Revenue"]
        assert len(rev_pattern) == 1
        assert rev_pattern[0]["canonical_name"] == "revenue"
        assert rev_pattern[0]["confidence"] == 1.0

    def test_apply_invalid_canonical(self, test_client_with_db, test_db):
        """Applying with invalid canonical_name returns 422."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "not_a_real_canonical"},
                ]
            },
        )
        assert response.status_code == 422

    def test_apply_updates_fact_table(self, test_client_with_db, test_db):
        """Applying a correction updates ExtractionFact rows."""
        from src.db import crud
        from src.db.models import ExtractionFact

        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)

            # Seed ExtractionFact rows for the job's line_items
            crud.persist_extraction_facts(
                session,
                job_id=job.job_id,
                entity_id=entity.id,
                line_items=job.result["line_items"],
            )
            session.commit()

            # Verify facts were seeded (Revenue has 2 periods)
            revenue_facts = (
                session.query(ExtractionFact)
                .filter(
                    ExtractionFact.job_id == job.job_id,
                    ExtractionFact.original_label == "Revenue",
                )
                .all()
            )
            assert len(revenue_facts) == 2
            assert all(f.canonical_name == "other_revenue" for f in revenue_facts)
        finally:
            session.close()

        # Apply correction: Revenue → revenue
        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["facts_updated"] >= 2

        # Verify facts were updated
        session2 = test_db()
        try:
            updated_facts = (
                session2.query(ExtractionFact)
                .filter(
                    ExtractionFact.job_id == job.job_id,
                    ExtractionFact.original_label == "Revenue",
                )
                .all()
            )
            assert len(updated_facts) == 2
            for fact in updated_facts:
                assert fact.canonical_name == "revenue"
                assert float(fact.confidence) == 1.0
                assert fact.mapping_method == "user_correction"
        finally:
            session2.close()


class TestPreviewCorrections:
    """Test POST /api/v1/jobs/{job_id}/corrections/preview."""

    def test_preview_returns_diffs(self, test_client_with_db, test_db):
        """Preview returns accurate diffs."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/preview",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["corrections_count"] == 1
        assert data["diffs"][0]["old_canonical_name"] == "other_revenue"
        assert data["diffs"][0]["new_canonical_name"] == "revenue"

    def test_preview_no_persist(self, test_client_with_db, test_db):
        """Preview does not change job.result."""
        from src.db import crud

        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/preview",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )

        # Verify result unchanged
        session2 = test_db()
        try:
            job_after = crud.get_job(session2, job.job_id)
            assert job_after.result["line_items"][0]["canonical_name"] == "other_revenue"
        finally:
            session2.close()

    def test_preview_invalid_canonical_warns(self, test_client_with_db, test_db):
        """Invalid canonical name appears as warning, not a 422."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/preview",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "totally_fake_name"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert any("totally_fake_name" in w for w in data["warnings"])

    def test_preview_warns_missing_label(self, test_client_with_db, test_db):
        """Preview with non-existent label returns warning."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/preview",
            json={
                "corrections": [
                    {"original_label": "Nonexistent Label", "new_canonical_name": "revenue"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["corrections_count"] == 0
        assert len(data["warnings"]) == 1
        assert "not found" in data["warnings"][0].lower()


class TestUndoCorrection:
    """Test POST /api/v1/corrections/{correction_id}/undo."""

    def test_undo_restores_values(self, test_client_with_db, test_db):
        """Undoing a correction restores original canonical_name."""
        from src.db import crud

        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        # Apply correction
        apply_resp = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )
        assert apply_resp.status_code == 200

        # Get correction_id from history
        history_resp = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/corrections/history"
        )
        correction_id = history_resp.json()["corrections"][0]["id"]

        # Undo
        undo_resp = test_client_with_db.post(
            f"/api/v1/corrections/{correction_id}/undo"
        )
        assert undo_resp.status_code == 200
        assert undo_resp.json()["restored_canonical_name"] == "other_revenue"

        # Verify job.result restored
        session2 = test_db()
        try:
            updated_job = crud.get_job(session2, job.job_id)
            li = updated_job.result["line_items"][0]
            assert li["canonical_name"] == "other_revenue"
            assert li["confidence"] == 0.85
        finally:
            session2.close()

    def test_undo_marks_reverted(self, test_client_with_db, test_db):
        """Undoing a correction marks it as reverted in history."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        # Apply and undo
        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )

        history = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/corrections/history"
        ).json()
        correction_id = history["corrections"][0]["id"]

        test_client_with_db.post(f"/api/v1/corrections/{correction_id}/undo")

        # Check history shows reverted
        history2 = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/corrections/history"
        ).json()
        assert history2["corrections"][0]["reverted"] is True
        assert history2["corrections"][0]["reverted_at"] is not None

    def test_undo_already_reverted(self, test_client_with_db, test_db):
        """Double undo returns 409."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )

        history = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/corrections/history"
        ).json()
        correction_id = history["corrections"][0]["id"]

        # First undo succeeds
        resp1 = test_client_with_db.post(f"/api/v1/corrections/{correction_id}/undo")
        assert resp1.status_code == 200

        # Second undo fails
        resp2 = test_client_with_db.post(f"/api/v1/corrections/{correction_id}/undo")
        assert resp2.status_code == 409

    def test_undo_blocked_when_overlapping_correction_exists(self, test_client_with_db, test_db):
        """Undoing a correction is blocked when another active correction
        targets the same label. Prevents silent data corruption from
        overlapping snapshot restores.
        """
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        # Apply correction A: Revenue → revenue
        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )

        # Apply correction B: Revenue → gross_profit (overwrites A)
        resp_b = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "gross_profit"},
                ]
            },
        )
        assert resp_b.status_code == 200
        assert resp_b.json()["corrections_applied"] == 1

        # Get both correction IDs
        history = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/corrections/history"
        ).json()
        assert history["total"] == 2
        id_a = history["corrections"][1]["id"]
        id_b = history["corrections"][0]["id"]

        # Try to undo either — blocked because the other is still active
        resp = test_client_with_db.post(f"/api/v1/corrections/{id_a}/undo")
        assert resp.status_code == 409
        assert "another active correction" in resp.json()["detail"].lower()

        resp2 = test_client_with_db.post(f"/api/v1/corrections/{id_b}/undo")
        assert resp2.status_code == 409

    def test_undo_allowed_after_other_reverted(self, test_client_with_db, test_db):
        """After revoking one overlapping correction, the other can be undone."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        # Apply correction to Revenue, then to COGS (different labels — no conflict)
        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )
        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "COGS", "new_canonical_name": "operating_expenses"},
                ]
            },
        )

        history = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/corrections/history"
        ).json()
        assert history["total"] == 2

        # Both are for different labels, so both should be independently undoable
        for correction in history["corrections"]:
            resp = test_client_with_db.post(
                f"/api/v1/corrections/{correction['id']}/undo"
            )
            assert resp.status_code == 200

        # Verify original state restored
        from src.db import crud

        session2 = test_db()
        try:
            restored_job = crud.get_job(session2, job.job_id)
            items = restored_job.result["line_items"]
            assert items[0]["canonical_name"] == "other_revenue"
            assert items[1]["canonical_name"] == "cogs"
        finally:
            session2.close()


class TestBulkCorrections:
    """Test POST /api/v1/jobs/{job_id}/corrections/bulk."""

    def test_bulk_all_valid(self, test_client_with_db, test_db):
        """Bulk applying multiple valid corrections."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/bulk",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                    {"original_label": "COGS", "new_canonical_name": "operating_expenses"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["corrections_applied"] == 2
        assert len(data["diffs"]) == 2

    def test_bulk_invalid_rejects_all(self, test_client_with_db, test_db):
        """One invalid canonical in bulk rejects entire batch."""
        from src.db import crud

        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/bulk",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                    {"original_label": "COGS", "new_canonical_name": "completely_fake_name"},
                ]
            },
        )

        assert response.status_code == 422

        # Verify nothing was changed
        session2 = test_db()
        try:
            unchanged_job = crud.get_job(session2, job.job_id)
            assert unchanged_job.result["line_items"][0]["canonical_name"] == "other_revenue"
            assert unchanged_job.result["line_items"][1]["canonical_name"] == "cogs"
        finally:
            session2.close()


class TestCorrectionHistory:
    """Test GET /api/v1/jobs/{job_id}/corrections/history."""

    def test_correction_history_endpoint(self, test_client_with_db, test_db):
        """History endpoint lists applied corrections."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        # Apply two corrections
        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )
        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "COGS", "new_canonical_name": "operating_expenses"},
                ]
            },
        )

        response = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/corrections/history"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["corrections"]) == 2

    def test_history_excludes_reverted(self, test_client_with_db, test_db):
        """With include_reverted=false, reverted corrections are excluded."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        # Apply and then undo one correction
        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )

        history_resp = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/corrections/history"
        )
        correction_id = history_resp.json()["corrections"][0]["id"]

        test_client_with_db.post(
            f"/api/v1/corrections/{correction_id}/undo"
        )

        # With include_reverted=false
        response = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/corrections/history?include_reverted=false"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

        # With include_reverted=true (default)
        response2 = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/corrections/history"
        )
        data2 = response2.json()
        assert data2["total"] == 1
        assert data2["corrections"][0]["reverted"] is True


# ============================================================================
# Edge-Case Tests
# ============================================================================


class TestUndoRevertsFactTable:
    """Verify undo also reverts ExtractionFact rows."""

    def test_undo_reverts_fact_table(self, test_client_with_db, test_db):
        """Undoing a correction restores ExtractionFact rows to original values."""
        from src.db import crud
        from src.db.models import ExtractionFact

        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
            job_uuid = job.job_id

            # Seed facts
            crud.persist_extraction_facts(
                session,
                job_id=job_uuid,
                entity_id=entity.id,
                line_items=job.result["line_items"],
            )
            session.commit()
        finally:
            session.close()

        # Apply correction
        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )

        # Get correction_id
        history = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/corrections/history"
        ).json()
        correction_id = history["corrections"][0]["id"]

        # Undo
        undo_resp = test_client_with_db.post(
            f"/api/v1/corrections/{correction_id}/undo"
        )
        assert undo_resp.status_code == 200

        # Verify facts restored
        session2 = test_db()
        try:
            facts = (
                session2.query(ExtractionFact)
                .filter(
                    ExtractionFact.job_id == job_uuid,
                    ExtractionFact.original_label == "Revenue",
                )
                .all()
            )
            assert len(facts) == 2
            for fact in facts:
                assert fact.canonical_name == "other_revenue"
                assert float(fact.confidence) == 0.85
        finally:
            session2.close()


class TestMultiSheetDisambiguation:
    """Verify sheet filter works when same label appears on multiple sheets."""

    def test_apply_with_sheet_filter(self, test_client_with_db, test_db):
        """Correction with sheet specified only affects matching sheet."""
        from src.db import crud

        session = test_db()
        try:
            entity, file, job = _create_job_with_multisheet_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        # Correct only the Income Statement's Revenue
        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {
                        "original_label": "Revenue",
                        "new_canonical_name": "revenue",
                        "sheet": "Income Statement",
                    },
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["corrections_applied"] == 1
        assert len(data["diffs"]) == 1
        assert data["diffs"][0]["old_canonical_name"] == "other_revenue"

        # Verify only Income Statement was changed, Balance Sheet untouched
        session2 = test_db()
        try:
            updated_job = crud.get_job(session2, job.job_id)
            items = updated_job.result["line_items"]
            is_item = [li for li in items if li["sheet"] == "Income Statement"][0]
            bs_item = [li for li in items if li["sheet"] == "Balance Sheet"][0]
            assert is_item["canonical_name"] == "revenue"
            assert is_item["confidence"] == 1.0
            assert bs_item["canonical_name"] == "other_revenue"  # unchanged
            assert bs_item["confidence"] == 0.75  # unchanged
        finally:
            session2.close()

    def test_apply_without_sheet_affects_all(self, test_client_with_db, test_db):
        """Correction without sheet filter affects all matching line_items."""
        from src.db import crud

        session = test_db()
        try:
            entity, file, job = _create_job_with_multisheet_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["diffs"]) == 2  # Both sheets updated

        session2 = test_db()
        try:
            updated_job = crud.get_job(session2, job.job_id)
            for li in updated_job.result["line_items"]:
                assert li["canonical_name"] == "revenue"
                assert li["confidence"] == 1.0
        finally:
            session2.close()


class TestApplyJobStatus:
    """Verify apply rejects non-completed jobs."""

    def test_apply_processing_job_returns_409(self, test_client_with_db, test_db):
        """Correcting a PROCESSING job returns 409."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Status Corp", industry="Finance")
            file = crud.create_file(
                session, filename="test.xlsx", file_size=1024, entity_id=entity.id
            )
            job = crud.create_extraction_job(session, file_id=file.file_id)
            # Job starts as PENDING — not COMPLETED or NEEDS_REVIEW
            assert job.status == JobStatusEnum.PENDING
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "revenue"},
                ]
            },
        )
        assert response.status_code == 409


class TestApplyAlreadyMapped:
    """Verify that applying the same canonical name is a no-op."""

    def test_apply_same_canonical_is_noop(self, test_client_with_db, test_db):
        """Correcting to the same canonical_name produces 0 diffs."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        # Revenue is already "other_revenue"; apply "other_revenue" again
        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Revenue", "new_canonical_name": "other_revenue"},
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["corrections_applied"] == 0
        assert len(data["diffs"]) == 0


class TestApplyNoMatch:
    """Verify apply is a no-op when label doesn't match."""

    def test_apply_unmatched_label_is_noop(self, test_client_with_db, test_db):
        """Correcting a nonexistent label applies 0 changes (not an error)."""
        from src.db import crud

        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={
                "corrections": [
                    {"original_label": "Nonexistent Label", "new_canonical_name": "revenue"},
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["corrections_applied"] == 0
        assert len(data["diffs"]) == 0

        # Verify nothing changed
        session2 = test_db()
        try:
            unchanged_job = crud.get_job(session2, job.job_id)
            assert unchanged_job.result["line_items"][0]["canonical_name"] == "other_revenue"
            assert unchanged_job.result["line_items"][1]["canonical_name"] == "cogs"
        finally:
            session2.close()


class TestHistoryFiltering:
    """Test history include_reverted query parameter."""

    def test_history_exclude_reverted(self, test_client_with_db, test_db):
        """History with include_reverted=false excludes reverted corrections."""
        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        # Apply two corrections
        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={"corrections": [{"original_label": "Revenue", "new_canonical_name": "revenue"}]},
        )
        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={"corrections": [{"original_label": "COGS", "new_canonical_name": "operating_expenses"}]},
        )

        # Undo the first one
        history = test_client_with_db.get(f"/api/v1/jobs/{job_id}/corrections/history").json()
        # History is ordered desc; find the Revenue correction
        rev_correction = [c for c in history["corrections"] if c["original_label"] == "Revenue"][0]
        test_client_with_db.post(f"/api/v1/corrections/{rev_correction['id']}/undo")

        # include_reverted=true (default) shows both
        all_history = test_client_with_db.get(f"/api/v1/jobs/{job_id}/corrections/history").json()
        assert all_history["total"] == 2

        # include_reverted=false shows only active
        active_history = test_client_with_db.get(
            f"/api/v1/jobs/{job_id}/corrections/history?include_reverted=false"
        ).json()
        assert active_history["total"] == 1
        assert active_history["corrections"][0]["reverted"] is False

    def test_history_empty(self, test_client_with_db, test_db):
        """History endpoint for job with no corrections returns empty list."""
        from src.db import crud

        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        response = test_client_with_db.get(f"/api/v1/jobs/{job_id}/corrections/history")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["corrections"] == []


class TestUndoSnapshotFidelity:
    """Verify undo restores full line_item snapshot, not just canonical_name."""

    def test_undo_restores_provenance(self, test_client_with_db, test_db):
        """Undoing a correction restores original provenance fields."""
        from src.db import crud

        session = test_db()
        try:
            entity, file, job = _create_job_with_result(session)
            job_id = str(job.job_id)
        finally:
            session.close()

        # Apply correction (changes provenance.mapping.method to "user_correction")
        test_client_with_db.post(
            f"/api/v1/jobs/{job_id}/corrections/apply",
            json={"corrections": [{"original_label": "Revenue", "new_canonical_name": "revenue"}]},
        )

        # Verify provenance was changed
        session2 = test_db()
        try:
            corrected_job = crud.get_job(session2, job.job_id)
            li = corrected_job.result["line_items"][0]
            assert li["provenance"]["mapping"]["method"] == "user_correction"
        finally:
            session2.close()

        # Get correction_id and undo
        history = test_client_with_db.get(f"/api/v1/jobs/{job_id}/corrections/history").json()
        correction_id = history["corrections"][0]["id"]
        undo_resp = test_client_with_db.post(f"/api/v1/corrections/{correction_id}/undo")
        assert undo_resp.status_code == 200

        # Verify provenance is FULLY restored (snapshot restores entire line_item)
        session3 = test_db()
        try:
            restored_job = crud.get_job(session3, job.job_id)
            li = restored_job.result["line_items"][0]
            assert li["canonical_name"] == "other_revenue"
            assert li["confidence"] == 0.85
            assert li["provenance"]["mapping"]["method"] == "claude"
            assert li["provenance"]["mapping"]["stage"] == 3
            assert li["provenance"]["mapping"]["taxonomy_category"] == "income_statement"
            assert li["values"] == {"2022": 1000, "2023": 1200}
            assert li["hierarchy_level"] == 1
        finally:
            session3.close()
