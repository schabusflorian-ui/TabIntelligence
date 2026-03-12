"""Tests for analytics API endpoints and CRUD functions."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_api_key():
    from src.auth.models import APIKey
    key = Mock(spec=APIKey)
    key.id = None
    key.name = "test-key"
    key.key_hash = "testhash"
    key.entity_id = None
    key.is_active = True
    key.rate_limit_per_minute = 60
    key.last_used_at = None
    return key


@pytest.fixture
def analytics_client(mock_api_key):
    from src.api.main import app
    from src.auth.dependencies import get_current_api_key

    app.dependency_overrides[get_current_api_key] = lambda: mock_api_key
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.pop(get_current_api_key, None)


def _make_fact(**kwargs):
    """Create a mock ExtractionFact."""
    fact = MagicMock()
    fact.id = kwargs.get("id", uuid.uuid4())
    fact.job_id = kwargs.get("job_id", uuid.uuid4())
    fact.entity_id = kwargs.get("entity_id", uuid.uuid4())
    fact.canonical_name = kwargs.get("canonical_name", "revenue")
    fact.original_label = kwargs.get("original_label", "Revenue")
    fact.period = kwargs.get("period", "FY2023")
    fact.period_normalized = kwargs.get("period_normalized")
    fact.value = kwargs.get("value", Decimal("100000"))
    fact.confidence = kwargs.get("confidence", 0.95)
    fact.sheet_name = kwargs.get("sheet_name", "Income Statement")
    fact.row_index = kwargs.get("row_index", 2)
    fact.mapping_method = kwargs.get("mapping_method", "exact")
    fact.taxonomy_category = kwargs.get("taxonomy_category", "income_statement")
    fact.validation_passed = kwargs.get("validation_passed", True)
    fact.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
    return fact


def _make_entity(entity_id=None, name="Acme Corp", industry="Technology"):
    entity = MagicMock()
    entity.id = entity_id or uuid.uuid4()
    entity.name = name
    entity.industry = industry
    entity.created_at = datetime.now(timezone.utc)
    return entity


# ============================================================================
# Entity Financials Endpoint
# ============================================================================


class TestEntityFinancials:

    @patch("src.api.analytics.crud")
    def test_financials_200(self, mock_crud, analytics_client):
        entity_id = str(uuid.uuid4())
        entity = _make_entity(entity_id=uuid.UUID(entity_id))
        mock_crud.get_entity.return_value = entity

        facts = [
            _make_fact(entity_id=uuid.UUID(entity_id), canonical_name="revenue", period="FY2022", value=Decimal("100000")),
            _make_fact(entity_id=uuid.UUID(entity_id), canonical_name="revenue", period="FY2023", value=Decimal("115000")),
            _make_fact(entity_id=uuid.UUID(entity_id), canonical_name="cogs", period="FY2023", value=Decimal("46000"), taxonomy_category="income_statement"),
        ]
        mock_crud.get_entity_financials.return_value = facts

        resp = analytics_client.get(f"/api/v1/analytics/entity/{entity_id}/financials")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == entity_id
        assert data["source"] == "facts"
        assert len(data["items"]) == 2
        assert len(data["periods"]) == 2
        # revenue has 2 periods
        revenue = next(i for i in data["items"] if i["canonical_name"] == "revenue")
        assert len(revenue["values"]) == 2

    @patch("src.api.analytics.crud")
    def test_financials_entity_not_found(self, mock_crud, analytics_client):
        entity_id = str(uuid.uuid4())
        mock_crud.get_entity.return_value = None

        resp = analytics_client.get(f"/api/v1/analytics/entity/{entity_id}/financials")
        assert resp.status_code == 404

    @patch("src.api.analytics.crud")
    def test_financials_invalid_uuid(self, mock_crud, analytics_client):
        resp = analytics_client.get("/api/v1/analytics/entity/not-a-uuid/financials")
        assert resp.status_code == 400

    @patch("src.api.analytics.crud")
    def test_financials_empty_returns_empty(self, mock_crud, analytics_client):
        entity_id = str(uuid.uuid4())
        entity = _make_entity(entity_id=uuid.UUID(entity_id))
        mock_crud.get_entity.return_value = entity
        mock_crud.get_entity_financials.return_value = []

        with patch("src.api.analytics._financials_from_json", return_value=None):
            resp = analytics_client.get(f"/api/v1/analytics/entity/{entity_id}/financials")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["source"] == "none"

    @patch("src.api.analytics.crud")
    def test_financials_json_fallback(self, mock_crud, analytics_client):
        entity_id = str(uuid.uuid4())
        entity = _make_entity(entity_id=uuid.UUID(entity_id))
        mock_crud.get_entity.return_value = entity
        mock_crud.get_entity_financials.return_value = []

        from src.api.schemas import EntityFinancialsResponse
        fallback = EntityFinancialsResponse(
            entity_id=entity_id,
            entity_name=None,
            items=[{"canonical_name": "revenue", "taxonomy_category": None, "values": [{"period": "FY2023", "amount": 100000}]}],
            periods=["FY2023"],
            source="json_fallback",
        )

        with patch("src.api.analytics._financials_from_json", return_value=fallback):
            resp = analytics_client.get(f"/api/v1/analytics/entity/{entity_id}/financials")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "json_fallback"
        assert len(data["items"]) == 1

    @patch("src.api.analytics.crud")
    def test_financials_with_canonical_filter(self, mock_crud, analytics_client):
        entity_id = str(uuid.uuid4())
        entity = _make_entity(entity_id=uuid.UUID(entity_id))
        mock_crud.get_entity.return_value = entity

        facts = [
            _make_fact(entity_id=uuid.UUID(entity_id), canonical_name="revenue", period="FY2023", value=Decimal("115000")),
        ]
        mock_crud.get_entity_financials.return_value = facts

        resp = analytics_client.get(
            f"/api/v1/analytics/entity/{entity_id}/financials",
            params={"canonical_names": "revenue,cogs"},
        )
        assert resp.status_code == 200
        mock_crud.get_entity_financials.assert_called_once()
        call_kwargs = mock_crud.get_entity_financials.call_args
        assert call_kwargs[1]["canonical_names"] == ["revenue", "cogs"]


# ============================================================================
# Cross-Entity Comparison
# ============================================================================


class TestCrossEntityComparison:

    @patch("src.api.analytics.crud")
    def test_compare_200(self, mock_crud, analytics_client):
        eid1 = uuid.uuid4()
        eid2 = uuid.uuid4()

        entity1 = _make_entity(entity_id=eid1, name="Acme")
        entity2 = _make_entity(entity_id=eid2, name="BetaCo")

        facts = [
            _make_fact(entity_id=eid1, canonical_name="revenue", period="FY2023", value=Decimal("100000")),
            _make_fact(entity_id=eid2, canonical_name="revenue", period="FY2023", value=Decimal("200000")),
        ]
        mock_crud.get_cross_entity_comparison.return_value = facts

        # The endpoint queries crud.Entity via db.query() — mock Entity class
        mock_entity_cls = MagicMock()
        mock_crud.Entity = mock_entity_cls
        mock_entity_cls.id = MagicMock()
        mock_entity_cls.id.in_.return_value = "mock_filter"

        # Need to inject a db session that returns entities on query()
        from src.db.session import get_db
        from src.api.main import app

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [entity1, entity2]

        def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            resp = analytics_client.get(
                "/api/v1/analytics/compare",
                params={
                    "entity_ids": f"{eid1},{eid2}",
                    "canonical_names": "revenue",
                    "period": "FY2023",
                },
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "FY2023"
        assert len(data["comparisons"]) == 1
        assert data["comparisons"][0]["canonical_name"] == "revenue"

    @patch("src.api.analytics.crud")
    def test_compare_invalid_entity_id(self, mock_crud, analytics_client):
        resp = analytics_client.get(
            "/api/v1/analytics/compare",
            params={
                "entity_ids": "not-a-uuid",
                "canonical_names": "revenue",
                "period": "FY2023",
            },
        )
        assert resp.status_code == 400

    def test_compare_missing_params(self, analytics_client):
        resp = analytics_client.get("/api/v1/analytics/compare")
        assert resp.status_code == 422  # missing required params


# ============================================================================
# Portfolio Summary
# ============================================================================


class TestPortfolioSummary:

    @patch("src.api.analytics.crud")
    def test_portfolio_summary_200(self, mock_crud, analytics_client):
        mock_crud.get_portfolio_summary.return_value = {
            "total_entities": 5,
            "total_jobs": 20,
            "total_facts": 500,
            "avg_confidence": 0.92,
            "quality_distribution": [
                {"grade": "A", "count": 10},
                {"grade": "B", "count": 8},
                {"grade": "C", "count": 2},
            ],
        }

        resp = analytics_client.get("/api/v1/analytics/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_entities"] == 5
        assert data["total_jobs"] == 20
        assert data["total_facts"] == 500
        assert data["avg_confidence"] == 0.92
        assert len(data["quality_distribution"]) == 3

    @patch("src.api.analytics.crud")
    def test_portfolio_summary_empty(self, mock_crud, analytics_client):
        mock_crud.get_portfolio_summary.return_value = {
            "total_entities": 0,
            "total_jobs": 0,
            "total_facts": 0,
            "avg_confidence": None,
            "quality_distribution": [],
        }

        resp = analytics_client.get("/api/v1/analytics/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_entities"] == 0
        assert data["avg_confidence"] is None

    @patch("src.api.analytics.crud")
    def test_portfolio_summary_with_entity_filter(self, mock_crud, analytics_client):
        eid = str(uuid.uuid4())
        mock_crud.get_portfolio_summary.return_value = {
            "total_entities": 1,
            "total_jobs": 3,
            "total_facts": 50,
            "avg_confidence": 0.88,
            "quality_distribution": [],
        }

        resp = analytics_client.get(
            "/api/v1/analytics/portfolio/summary",
            params={"entity_ids": eid},
        )
        assert resp.status_code == 200

    @patch("src.api.analytics.crud")
    def test_portfolio_summary_invalid_entity_id(self, mock_crud, analytics_client):
        resp = analytics_client.get(
            "/api/v1/analytics/portfolio/summary",
            params={"entity_ids": "bad-uuid"},
        )
        assert resp.status_code == 400


# ============================================================================
# Entity Trends
# ============================================================================


class TestEntityTrends:

    @patch("src.api.analytics.crud")
    def test_trends_200_with_yoy(self, mock_crud, analytics_client):
        entity_id = str(uuid.uuid4())
        entity = _make_entity(entity_id=uuid.UUID(entity_id))
        mock_crud.get_entity.return_value = entity

        facts = [
            _make_fact(entity_id=uuid.UUID(entity_id), canonical_name="revenue", period="FY2022", value=Decimal("100000")),
            _make_fact(entity_id=uuid.UUID(entity_id), canonical_name="revenue", period="FY2023", value=Decimal("115000")),
            _make_fact(entity_id=uuid.UUID(entity_id), canonical_name="revenue", period="FY2024", value=Decimal("138000")),
        ]
        mock_crud.get_entity_trends.return_value = facts

        resp = analytics_client.get(
            f"/api/v1/analytics/entity/{entity_id}/trends",
            params={"canonical_name": "revenue"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == entity_id
        assert data["canonical_name"] == "revenue"
        assert len(data["trend"]) == 3

        # First point has no YoY
        assert data["trend"][0]["yoy_change_pct"] is None
        # Second: (115000-100000)/100000 * 100 = 15.0
        assert data["trend"][1]["yoy_change_pct"] == 15.0
        # Third: (138000-115000)/115000 * 100 = 20.0
        assert data["trend"][2]["yoy_change_pct"] == 20.0

    @patch("src.api.analytics.crud")
    def test_trends_entity_not_found(self, mock_crud, analytics_client):
        entity_id = str(uuid.uuid4())
        mock_crud.get_entity.return_value = None

        resp = analytics_client.get(
            f"/api/v1/analytics/entity/{entity_id}/trends",
            params={"canonical_name": "revenue"},
        )
        assert resp.status_code == 404

    @patch("src.api.analytics.crud")
    def test_trends_empty(self, mock_crud, analytics_client):
        entity_id = str(uuid.uuid4())
        entity = _make_entity(entity_id=uuid.UUID(entity_id))
        mock_crud.get_entity.return_value = entity
        mock_crud.get_entity_trends.return_value = []

        resp = analytics_client.get(
            f"/api/v1/analytics/entity/{entity_id}/trends",
            params={"canonical_name": "revenue"},
        )
        assert resp.status_code == 200
        assert resp.json()["trend"] == []

    def test_trends_missing_canonical_name(self, analytics_client):
        entity_id = str(uuid.uuid4())
        resp = analytics_client.get(f"/api/v1/analytics/entity/{entity_id}/trends")
        assert resp.status_code == 422


# ============================================================================
# Taxonomy Coverage
# ============================================================================


class TestTaxonomyCoverage:

    @patch("src.api.analytics.crud")
    def test_coverage_200(self, mock_crud, analytics_client):
        mock_crud.get_taxonomy_coverage.return_value = {
            "total_taxonomy_items": 100,
            "items_ever_mapped": 45,
            "coverage_pct": 45.0,
            "most_common": [
                {
                    "canonical_name": "revenue",
                    "category": "income_statement",
                    "times_mapped": 200,
                    "avg_confidence": 0.96,
                },
            ],
            "never_mapped": ["unusual_item_1", "unusual_item_2"],
        }

        resp = analytics_client.get("/api/v1/analytics/taxonomy/coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_taxonomy_items"] == 100
        assert data["items_ever_mapped"] == 45
        assert data["coverage_pct"] == 45.0
        assert len(data["most_common"]) == 1
        assert len(data["never_mapped"]) == 2

    @patch("src.api.analytics.crud")
    def test_coverage_empty(self, mock_crud, analytics_client):
        mock_crud.get_taxonomy_coverage.return_value = {
            "total_taxonomy_items": 0,
            "items_ever_mapped": 0,
            "coverage_pct": 0.0,
            "most_common": [],
            "never_mapped": [],
        }

        resp = analytics_client.get("/api/v1/analytics/taxonomy/coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["coverage_pct"] == 0.0


# ============================================================================
# Cost Analytics
# ============================================================================


class TestCostAnalytics:

    @patch("src.api.analytics.crud")
    def test_costs_200(self, mock_crud, analytics_client):
        mock_crud.get_cost_analytics.return_value = {
            "total_cost": 12.5,
            "total_jobs": 25,
            "avg_cost_per_job": 0.5,
            "cost_by_entity": [
                {
                    "entity_id": str(uuid.uuid4()),
                    "entity_name": "Acme Corp",
                    "total_cost": 8.0,
                    "job_count": 16,
                },
            ],
            "cost_trend_daily": [
                {"date": "2024-01-15", "cost": 3.0, "job_count": 6},
                {"date": "2024-01-16", "cost": 2.5, "job_count": 5},
            ],
        }

        resp = analytics_client.get("/api/v1/analytics/costs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == 12.5
        assert data["total_jobs"] == 25
        assert data["avg_cost_per_job"] == 0.5
        assert len(data["cost_by_entity"]) == 1
        assert len(data["cost_trend_daily"]) == 2

    @patch("src.api.analytics.crud")
    def test_costs_empty(self, mock_crud, analytics_client):
        mock_crud.get_cost_analytics.return_value = {
            "total_cost": 0.0,
            "total_jobs": 0,
            "avg_cost_per_job": 0.0,
            "cost_by_entity": [],
            "cost_trend_daily": [],
        }

        resp = analytics_client.get("/api/v1/analytics/costs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == 0.0
        assert data["total_jobs"] == 0

    @patch("src.api.analytics.crud")
    def test_costs_with_entity_filter(self, mock_crud, analytics_client):
        eid = str(uuid.uuid4())
        mock_crud.get_cost_analytics.return_value = {
            "total_cost": 3.0,
            "total_jobs": 5,
            "avg_cost_per_job": 0.6,
            "cost_by_entity": [],
            "cost_trend_daily": [],
        }

        resp = analytics_client.get(
            "/api/v1/analytics/costs",
            params={"entity_id": eid},
        )
        assert resp.status_code == 200

    @patch("src.api.analytics.crud")
    def test_costs_with_date_range(self, mock_crud, analytics_client):
        mock_crud.get_cost_analytics.return_value = {
            "total_cost": 5.0,
            "total_jobs": 10,
            "avg_cost_per_job": 0.5,
            "cost_by_entity": [],
            "cost_trend_daily": [],
        }

        resp = analytics_client.get(
            "/api/v1/analytics/costs",
            params={"date_from": "2024-01-01", "date_to": "2024-01-31"},
        )
        assert resp.status_code == 200

    @patch("src.api.analytics.crud")
    def test_costs_invalid_entity_id(self, mock_crud, analytics_client):
        resp = analytics_client.get(
            "/api/v1/analytics/costs",
            params={"entity_id": "not-a-uuid"},
        )
        assert resp.status_code == 400


# ============================================================================
# CRUD Unit Tests
# ============================================================================


class TestAnalyticsCRUD:

    def test_get_entity_financials(self):
        """Test CRUD entity financials with mock DB."""
        from src.db.crud import get_entity_financials

        db = MagicMock()
        entity_id = uuid.uuid4()

        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [
            _make_fact(entity_id=entity_id, canonical_name="revenue", period="FY2023"),
        ]

        result = get_entity_financials(db, entity_id)
        assert len(result) == 1
        db.query.assert_called_once()

    def test_get_entity_financials_with_filters(self):
        from src.db.crud import get_entity_financials

        db = MagicMock()
        entity_id = uuid.uuid4()

        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        result = get_entity_financials(
            db, entity_id,
            canonical_names=["revenue", "cogs"],
            period_start="FY2022",
            period_end="FY2024",
        )
        assert result == []
        # Should have called filter multiple times (entity_id, in_, >=, <=)
        assert mock_query.filter.call_count == 4

    def test_get_cross_entity_comparison(self):
        from src.db.crud import get_cross_entity_comparison

        db = MagicMock()
        eid1 = uuid.uuid4()
        eid2 = uuid.uuid4()

        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        result = get_cross_entity_comparison(
            db,
            entity_ids=[eid1, eid2],
            canonical_names=["revenue"],
            period="FY2023",
        )
        assert result == []

    def test_get_portfolio_summary(self):
        from src.db.crud import get_portfolio_summary

        db = MagicMock()

        # entity count
        mock_entity_q = MagicMock()
        mock_entity_q.scalar.return_value = 3

        # job count
        mock_job_q = MagicMock()
        mock_job_q.count.return_value = 10

        # quality distribution
        mock_quality_q = MagicMock()
        mock_quality_q.filter.return_value = mock_quality_q
        mock_quality_q.group_by.return_value = mock_quality_q
        mock_quality_q.all.return_value = [("A", 5), ("B", 3), ("C", 2)]

        # facts count
        mock_facts_q = MagicMock()
        mock_facts_q.count.return_value = 100

        # avg confidence
        mock_avg_q = MagicMock()
        mock_avg_q.filter.return_value = mock_avg_q
        mock_avg_q.scalar.return_value = 0.91

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_entity_q
            elif call_count[0] == 2:
                return mock_job_q
            elif call_count[0] == 3:
                return mock_quality_q
            elif call_count[0] == 4:
                return mock_facts_q
            else:
                return mock_avg_q

        db.query.side_effect = side_effect

        result = get_portfolio_summary(db)
        assert result["total_entities"] == 3
        assert result["total_jobs"] == 10
        assert result["total_facts"] == 100
        assert result["avg_confidence"] == 0.91
        assert len(result["quality_distribution"]) == 3

    def test_get_entity_trends(self):
        from src.db.crud import get_entity_trends

        db = MagicMock()
        entity_id = uuid.uuid4()

        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        facts = [
            _make_fact(canonical_name="revenue", period="FY2022", value=Decimal("100000")),
            _make_fact(canonical_name="revenue", period="FY2023", value=Decimal("115000")),
        ]
        mock_query.all.return_value = facts

        result = get_entity_trends(db, entity_id, "revenue")
        assert len(result) == 2

    def test_get_cost_analytics(self):
        from src.db.crud import get_cost_analytics

        db = MagicMock()
        eid = uuid.uuid4()

        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.outerjoin.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        # Totals query returns (total_cost, total_jobs, avg_cost)
        mock_query.one.return_value = (0.5, 1, 0.5)
        # Entity query and daily query return rows
        mock_query.all.side_effect = [
            [(eid, "TestCo", 0.5, 1)],  # cost_by_entity
            [("2024-01-15", 0.5, 1)],    # cost_trend_daily
        ]

        result = get_cost_analytics(db)
        assert result["total_cost"] == 0.5
        assert result["total_jobs"] == 1
        assert result["avg_cost_per_job"] == 0.5
        assert len(result["cost_by_entity"]) == 1
        assert result["cost_by_entity"][0]["entity_name"] == "TestCo"
        assert len(result["cost_trend_daily"]) == 1
        assert result["cost_trend_daily"][0]["date"] == "2024-01-15"

    def test_get_cost_analytics_empty(self):
        from src.db.crud import get_cost_analytics

        db = MagicMock()
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        # Totals query returns (0, 0, 0)
        mock_query.join.return_value = mock_query
        mock_query.outerjoin.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.one.return_value = (0.0, 0, 0.0)
        mock_query.all.return_value = []

        result = get_cost_analytics(db)
        assert result["total_cost"] == 0.0
        assert result["total_jobs"] == 0
        assert result["avg_cost_per_job"] == 0.0
        assert result["cost_by_entity"] == []
        assert result["cost_trend_daily"] == []


# ============================================================================
# Statement Type Filter Tests
# ============================================================================


class TestStatementTypeFilter:

    @patch("src.api.analytics.crud")
    def test_financials_with_statement_type(self, mock_crud, analytics_client):
        entity_id = str(uuid.uuid4())
        entity = _make_entity(entity_id=uuid.UUID(entity_id))
        mock_crud.get_entity.return_value = entity

        facts = [
            _make_fact(
                entity_id=uuid.UUID(entity_id),
                canonical_name="revenue",
                period="FY2023",
                value=Decimal("115000"),
                taxonomy_category="income_statement",
            ),
        ]
        mock_crud.get_entity_financials.return_value = facts

        resp = analytics_client.get(
            f"/api/v1/analytics/entity/{entity_id}/financials",
            params={"statement_type": "income_statement"},
        )
        assert resp.status_code == 200
        # Verify statement_type was passed to CRUD
        call_kwargs = mock_crud.get_entity_financials.call_args
        assert call_kwargs[1]["statement_type"] == "income_statement"

    def test_crud_financials_with_statement_type(self):
        from src.db.crud import get_entity_financials

        db = MagicMock()
        entity_id = uuid.uuid4()

        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        result = get_entity_financials(
            db, entity_id, statement_type="balance_sheet"
        )
        assert result == []
        # entity_id filter + statement_type filter = 2 filter calls
        assert mock_query.filter.call_count == 2


# ============================================================================
# Pagination Tests
# ============================================================================


class TestPagination:

    @patch("src.api.analytics.crud")
    def test_financials_with_pagination(self, mock_crud, analytics_client):
        entity_id = str(uuid.uuid4())
        entity = _make_entity(entity_id=uuid.UUID(entity_id))
        mock_crud.get_entity.return_value = entity

        # Return 5 distinct canonical names
        facts = [
            _make_fact(
                entity_id=uuid.UUID(entity_id),
                canonical_name=f"item_{i}",
                period="FY2023",
                value=Decimal(str(1000 * (i + 1))),
            )
            for i in range(5)
        ]
        mock_crud.get_entity_financials.return_value = facts

        # Request page with limit=2, offset=1
        resp = analytics_client.get(
            f"/api/v1/analytics/entity/{entity_id}/financials",
            params={"limit": 2, "offset": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total_items"] == 5
        # Items are sorted, so offset=1 skips "item_0"
        assert data["items"][0]["canonical_name"] == "item_1"
        assert data["items"][1]["canonical_name"] == "item_2"

    @patch("src.api.analytics.crud")
    def test_financials_default_pagination(self, mock_crud, analytics_client):
        entity_id = str(uuid.uuid4())
        entity = _make_entity(entity_id=uuid.UUID(entity_id))
        mock_crud.get_entity.return_value = entity
        mock_crud.get_entity_financials.return_value = [
            _make_fact(entity_id=uuid.UUID(entity_id), canonical_name="revenue", period="FY2023"),
        ]

        resp = analytics_client.get(f"/api/v1/analytics/entity/{entity_id}/financials")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_items"] == 1


# ============================================================================
# JSON Fallback Integration Tests
# ============================================================================


class TestFinancialsJsonFallback:

    def test_financials_from_json_actual_data(self):
        """Test _financials_from_json with realistic ExtractionJob.result data."""
        from src.api.analytics import _financials_from_json
        from src.db.models import JobStatusEnum

        db = MagicMock()
        entity_id = uuid.uuid4()

        mock_job = MagicMock()
        mock_job.result = {
            "line_items": [
                {"canonical_name": "revenue", "values": {"FY2023": 100000, "FY2024": 115000}},
                {"canonical_name": "cogs", "values": {"FY2023": 40000}},
                {"canonical_name": "unmapped", "values": {"FY2023": 0}},  # should be skipped
                {"canonical_name": "ebitda", "values": {"FY2023": "not_a_number"}},  # should be skipped
            ]
        }

        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_job]

        result = _financials_from_json(db, entity_id, canonical_names=None)
        assert result is not None
        assert result.source == "json_fallback"
        assert len(result.items) == 2  # revenue and cogs (unmapped and bad value skipped)
        item_names = {item.canonical_name for item in result.items}
        assert "revenue" in item_names
        assert "cogs" in item_names
        assert "unmapped" not in item_names

    def test_financials_from_json_with_filter(self):
        """Test _financials_from_json filters by canonical_names."""
        from src.api.analytics import _financials_from_json

        db = MagicMock()
        entity_id = uuid.uuid4()

        mock_job = MagicMock()
        mock_job.result = {
            "line_items": [
                {"canonical_name": "revenue", "values": {"FY2023": 100000}},
                {"canonical_name": "cogs", "values": {"FY2023": 40000}},
            ]
        }

        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_job]

        result = _financials_from_json(db, entity_id, canonical_names=["revenue"])
        assert result is not None
        assert len(result.items) == 1
        assert result.items[0].canonical_name == "revenue"

    def test_financials_from_json_no_jobs(self):
        """Test _financials_from_json returns None when no jobs found."""
        from src.api.analytics import _financials_from_json

        db = MagicMock()
        entity_id = uuid.uuid4()

        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        result = _financials_from_json(db, entity_id, canonical_names=None)
        assert result is None


# ============================================================================
# DatabaseError Tests (500 response path)
# ============================================================================


class TestDatabaseErrorHandling:

    @patch("src.api.analytics.crud")
    def test_financials_database_error(self, mock_crud, analytics_client):
        from src.core.exceptions import DatabaseError

        entity_id = str(uuid.uuid4())
        entity = _make_entity(entity_id=uuid.UUID(entity_id))
        mock_crud.get_entity.return_value = entity
        mock_crud.get_entity_financials.side_effect = DatabaseError(
            "Connection failed", operation="read", table="extraction_facts"
        )

        resp = analytics_client.get(f"/api/v1/analytics/entity/{entity_id}/financials")
        assert resp.status_code == 500

    @patch("src.api.analytics.crud")
    def test_compare_database_error(self, mock_crud, analytics_client):
        from src.core.exceptions import DatabaseError
        from src.db.session import get_db
        from src.api.main import app

        eid = str(uuid.uuid4())

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        def override_db():
            yield mock_db

        mock_crud.get_cross_entity_comparison.side_effect = DatabaseError(
            "Connection failed", operation="read", table="extraction_facts"
        )
        mock_crud.Entity = MagicMock()

        app.dependency_overrides[get_db] = override_db
        try:
            resp = analytics_client.get(
                "/api/v1/analytics/compare",
                params={"entity_ids": eid, "canonical_names": "revenue", "period": "FY2023"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 500

    @patch("src.api.analytics.crud")
    def test_portfolio_summary_database_error(self, mock_crud, analytics_client):
        from src.core.exceptions import DatabaseError

        mock_crud.get_portfolio_summary.side_effect = DatabaseError(
            "Connection failed", operation="read", table="extraction_facts"
        )

        resp = analytics_client.get("/api/v1/analytics/portfolio/summary")
        assert resp.status_code == 500

    @patch("src.api.analytics.crud")
    def test_trends_database_error(self, mock_crud, analytics_client):
        from src.core.exceptions import DatabaseError

        entity_id = str(uuid.uuid4())
        entity = _make_entity(entity_id=uuid.UUID(entity_id))
        mock_crud.get_entity.return_value = entity
        mock_crud.get_entity_trends.side_effect = DatabaseError(
            "Connection failed", operation="read", table="extraction_facts"
        )

        resp = analytics_client.get(
            f"/api/v1/analytics/entity/{entity_id}/trends",
            params={"canonical_name": "revenue"},
        )
        assert resp.status_code == 500

    @patch("src.api.analytics.crud")
    def test_coverage_database_error(self, mock_crud, analytics_client):
        from src.core.exceptions import DatabaseError

        mock_crud.get_taxonomy_coverage.side_effect = DatabaseError(
            "Connection failed", operation="read", table="extraction_facts"
        )

        resp = analytics_client.get("/api/v1/analytics/taxonomy/coverage")
        assert resp.status_code == 500

    @patch("src.api.analytics.crud")
    def test_costs_database_error(self, mock_crud, analytics_client):
        from src.core.exceptions import DatabaseError

        mock_crud.get_cost_analytics.side_effect = DatabaseError(
            "Connection failed", operation="read", table="extraction_jobs"
        )

        resp = analytics_client.get("/api/v1/analytics/costs")
        assert resp.status_code == 500
