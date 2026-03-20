"""
Unit tests for quality grade trending (model, CRUD, API).

Tests create_quality_snapshot(), get_quality_trend(), and the
quality-trend API endpoint.
"""

from uuid import uuid4

import pytest

from src.db import crud
from src.db.models import Entity, QualitySnapshot

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def entity(db_session):
    """Create a test entity."""
    e = Entity(id=uuid4(), name="TestCo Quality")
    db_session.add(e)
    db_session.commit()
    return e


@pytest.fixture
def snapshots(db_session, entity):
    """Create 3 quality snapshots for the entity."""
    data = [
        ("2024-01-15", 0.82, "B", 100, 3, 5),
        ("2024-02-15", 0.85, "B", 120, 4, 3),
        ("2024-03-15", 0.91, "A", 150, 5, 1),
    ]
    created = []
    for date, conf, grade, facts, jobs, unmapped in data:
        s = QualitySnapshot(
            entity_id=entity.id,
            snapshot_date=date,
            avg_confidence=conf,
            quality_grade=grade,
            total_facts=facts,
            total_jobs=jobs,
            unmapped_label_count=unmapped,
        )
        db_session.add(s)
        created.append(s)
    db_session.commit()
    return created


# ============================================================================
# CRUD Tests
# ============================================================================


class TestCreateQualitySnapshot:
    def test_creates_snapshot(self, db_session, entity):
        snapshot = crud.create_quality_snapshot(
            db_session,
            entity_id=entity.id,
            snapshot_date="2024-04-01",
            avg_confidence=0.88,
            quality_grade="B",
            total_facts=200,
            total_jobs=6,
            unmapped_label_count=2,
        )
        assert snapshot.id is not None
        assert snapshot.entity_id == entity.id
        assert snapshot.snapshot_date == "2024-04-01"
        assert snapshot.avg_confidence == 0.88
        assert snapshot.quality_grade == "B"
        assert snapshot.total_facts == 200
        assert snapshot.total_jobs == 6
        assert snapshot.unmapped_label_count == 2

    def test_default_unmapped_count(self, db_session, entity):
        snapshot = crud.create_quality_snapshot(
            db_session,
            entity_id=entity.id,
            snapshot_date="2024-05-01",
            avg_confidence=0.90,
            quality_grade="A",
            total_facts=300,
            total_jobs=10,
        )
        assert snapshot.unmapped_label_count == 0


class TestGetQualityTrend:
    def test_returns_snapshots_desc(self, db_session, entity, snapshots):
        result = crud.get_quality_trend(db_session, entity.id)
        assert len(result) == 3
        # Ordered by date descending
        assert result[0]["snapshot_date"] == "2024-03-15"
        assert result[1]["snapshot_date"] == "2024-02-15"
        assert result[2]["snapshot_date"] == "2024-01-15"

    def test_returns_correct_fields(self, db_session, entity, snapshots):
        result = crud.get_quality_trend(db_session, entity.id)
        item = result[0]
        assert item["quality_grade"] == "A"
        assert item["avg_confidence"] == 0.91
        assert item["total_facts"] == 150
        assert item["total_jobs"] == 5
        assert item["unmapped_label_count"] == 1

    def test_limit_respected(self, db_session, entity, snapshots):
        result = crud.get_quality_trend(db_session, entity.id, limit=2)
        assert len(result) == 2

    def test_empty_for_unknown_entity(self, db_session):
        result = crud.get_quality_trend(db_session, uuid4())
        assert result == []


# ============================================================================
# API Tests
# ============================================================================


class TestQualityTrendEndpoint:
    def test_quality_trend_success(self, test_client_with_db, test_db, entity, snapshots):
        """GET /api/v1/analytics/entity/{id}/quality-trend returns snapshots."""
        from src.db.session import get_db

        def override_get_db():
            db = test_db()
            try:
                yield db
            finally:
                db.close()

        from src.api.main import app

        app.dependency_overrides[get_db] = override_get_db

        resp = test_client_with_db.get(f"/api/v1/analytics/entity/{entity.id}/quality-trend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == str(entity.id)
        assert data["entity_name"] == "TestCo Quality"
        assert len(data["snapshots"]) == 3
        # Most recent first
        assert data["snapshots"][0]["quality_grade"] == "A"

    def test_quality_trend_unknown_entity(self, test_client_with_db):
        fake_id = str(uuid4())
        resp = test_client_with_db.get(
            f"/api/v1/analytics/entity/{fake_id}/quality-trend"
        )
        assert resp.status_code == 404

    def test_quality_trend_invalid_id(self, test_client_with_db):
        resp = test_client_with_db.get("/api/v1/analytics/entity/not-a-uuid/quality-trend")
        assert resp.status_code == 400
