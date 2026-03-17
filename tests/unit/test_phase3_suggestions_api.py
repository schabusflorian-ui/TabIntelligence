"""
API-level tests for taxonomy gap suggestion and accept endpoints.

Tests:
- GET /api/v1/analytics/unmapped-labels/{label}/suggestions
- POST /api/v1/analytics/unmapped-labels/{label}/accept
"""

from uuid import uuid4

import pytest

from src.db.models import Entity, EntityPattern, LearnedAlias, Taxonomy


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def seeded_data(test_db):
    """Seed taxonomy and entity data for suggestion API tests."""
    db = test_db()
    entity = Entity(id=uuid4(), name="TestCo Suggestions")
    db.add(entity)

    tax_items = [
        Taxonomy(
            id=uuid4(),
            canonical_name="revenue",
            category="income_statement",
            display_name="Revenue",
            aliases=["Sales", "Net Revenue", "Total Revenue"],
            definition="Total income",
            typical_sign="positive",
        ),
        Taxonomy(
            id=uuid4(),
            canonical_name="ebitda",
            category="income_statement",
            display_name="EBITDA",
            aliases=["Earnings Before Interest Tax Depreciation Amortization"],
            definition="EBITDA",
            typical_sign="positive",
        ),
    ]
    for t in tax_items:
        db.add(t)

    pattern = EntityPattern(
        id=uuid4(),
        entity_id=entity.id,
        original_label="Net Sales Revenue",
        canonical_name="revenue",
        confidence=0.90,
        is_active=True,
        created_by="claude",
    )
    db.add(pattern)
    db.commit()

    return {"entity": entity, "taxonomy": tax_items, "pattern": pattern, "db": db}


@pytest.fixture
def client_with_data(test_db, mock_api_key, seeded_data):
    """Test client with seeded data and DB override."""
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
    yield client, seeded_data
    app.dependency_overrides.clear()


# ============================================================================
# GET /unmapped-labels/{label}/suggestions
# ============================================================================


class TestSuggestionsEndpoint:
    def test_suggestions_returns_results(self, client_with_data):
        client, data = client_with_data
        resp = client.get("/api/v1/analytics/unmapped-labels/Net Revenue/suggestions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["label"] == "Net Revenue"
        assert len(body["suggestions"]) > 0
        # Revenue should be in suggestions (exact alias match)
        canonical_names = [s["canonical_name"] for s in body["suggestions"]]
        assert "revenue" in canonical_names

    def test_suggestions_each_has_required_fields(self, client_with_data):
        client, _ = client_with_data
        resp = client.get("/api/v1/analytics/unmapped-labels/Sales/suggestions")
        assert resp.status_code == 200
        for s in resp.json()["suggestions"]:
            assert "canonical_name" in s
            assert "confidence" in s
            assert "reason" in s
            assert "source" in s

    def test_suggestions_limit_param(self, client_with_data):
        client, _ = client_with_data
        resp = client.get("/api/v1/analytics/unmapped-labels/Revenue/suggestions?limit=1")
        assert resp.status_code == 200
        assert len(resp.json()["suggestions"]) <= 1

    def test_suggestions_unknown_label(self, client_with_data):
        client, _ = client_with_data
        resp = client.get(
            "/api/v1/analytics/unmapped-labels/xyzzy_unknown_12345/suggestions"
        )
        assert resp.status_code == 200
        assert resp.json()["suggestions"] == []


# ============================================================================
# POST /unmapped-labels/{label}/accept
# ============================================================================


class TestAcceptEndpoint:
    def test_accept_creates_alias(self, client_with_data):
        client, data = client_with_data
        resp = client.post(
            "/api/v1/analytics/unmapped-labels/Net Turnover/accept",
            json={"canonical_name": "revenue"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["label"] == "Net Turnover"
        assert body["canonical_name"] == "revenue"
        assert body["alias_created"] is True

    def test_accept_with_entity_creates_pattern(self, client_with_data):
        client, data = client_with_data
        entity_id = str(data["entity"].id)
        resp = client.post(
            "/api/v1/analytics/unmapped-labels/Gross Sales/accept",
            json={"canonical_name": "revenue", "entity_id": entity_id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["pattern_created"] is True
        assert body["alias_created"] is True

    def test_accept_unknown_canonical_returns_400(self, client_with_data):
        client, _ = client_with_data
        resp = client.post(
            "/api/v1/analytics/unmapped-labels/SomeLabel/accept",
            json={"canonical_name": "nonexistent_item_xyz"},
        )
        assert resp.status_code == 400

    def test_accept_invalid_entity_id_returns_400(self, client_with_data):
        client, _ = client_with_data
        resp = client.post(
            "/api/v1/analytics/unmapped-labels/SomeLabel/accept",
            json={"canonical_name": "revenue", "entity_id": "not-a-uuid"},
        )
        assert resp.status_code == 400

    def test_accept_duplicate_alias_increments_count(self, client_with_data):
        client, data = client_with_data
        # First accept
        client.post(
            "/api/v1/analytics/unmapped-labels/Umsatz/accept",
            json={"canonical_name": "revenue"},
        )
        # Second accept — same label + canonical should increment
        resp = client.post(
            "/api/v1/analytics/unmapped-labels/Umsatz/accept",
            json={"canonical_name": "revenue"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Second time, alias already exists, not newly created
        assert body["alias_created"] is False

    def test_accept_duplicate_pattern_not_recreated(self, client_with_data):
        client, data = client_with_data
        entity_id = str(data["entity"].id)
        # First accept with entity
        client.post(
            "/api/v1/analytics/unmapped-labels/Special Revenue/accept",
            json={"canonical_name": "revenue", "entity_id": entity_id},
        )
        # Second accept — same pattern should not be recreated
        resp = client.post(
            "/api/v1/analytics/unmapped-labels/Special Revenue/accept",
            json={"canonical_name": "revenue", "entity_id": entity_id},
        )
        assert resp.status_code == 200
        assert resp.json()["pattern_created"] is False
