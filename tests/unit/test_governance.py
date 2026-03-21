"""Tests for taxonomy governance features: impact preview, bulk ops, health."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.models import Base


@pytest.fixture
def governance_db():
    """Create an in-memory SQLite database for governance tests."""
    import src.auth.models  # noqa: F401
    import src.db.models  # noqa: F401

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


class TestImpactPreview:
    """Test taxonomy impact preview."""

    def test_empty_database(self, governance_db):
        from src.db.crud import get_taxonomy_impact_preview

        result = get_taxonomy_impact_preview(governance_db, "revenue")

        assert result["canonical_name"] == "revenue"
        assert result["affected_facts"] == 0
        assert result["affected_patterns"] == 0
        assert result["affected_entities"] == 0
        assert result["pending_suggestions"] == 0
        assert result["total_impact"] == 0

    def test_with_facts_and_patterns(self, governance_db):
        from src.db.crud import get_taxonomy_impact_preview
        from src.db.models import Entity, EntityPattern, ExtractionFact

        # Create an entity
        entity = Entity(name="Test Corp", industry="tech")
        governance_db.add(entity)
        governance_db.flush()

        # Create extraction facts
        for _ in range(3):
            governance_db.add(ExtractionFact(
                job_id=uuid4(),
                canonical_name="revenue",
                original_label="Revenue",
                value=100.0,
                period="2024",
            ))

        # Create entity pattern
        governance_db.add(EntityPattern(
            entity_id=entity.id,
            original_label="Revenue",
            canonical_name="revenue",
            confidence=0.95,
            occurrence_count=5,
            created_by="claude",
        ))
        governance_db.commit()

        result = get_taxonomy_impact_preview(governance_db, "revenue")

        assert result["affected_facts"] == 3
        assert result["affected_patterns"] == 1
        assert result["affected_entities"] == 1
        assert result["total_impact"] == 4


class TestBulkAcceptSuggestions:
    """Test bulk suggestion acceptance."""

    def test_accept_multiple(self, governance_db):
        from src.db.crud import bulk_accept_suggestions
        from src.db.models import Taxonomy, TaxonomySuggestion

        # Create a taxonomy item to accept aliases for
        tax = Taxonomy(
            canonical_name="revenue",
            category="income_statement",
            display_name="Revenue",
            aliases=["Sales"],
            definition="Revenue",
            typical_sign="positive",
        )
        governance_db.add(tax)

        # Create pending suggestions
        s1 = TaxonomySuggestion(
            suggestion_type="new_alias",
            canonical_name="revenue",
            suggested_text="Net Sales",
            evidence_count=5,
            status="pending",
        )
        s2 = TaxonomySuggestion(
            suggestion_type="new_alias",
            canonical_name="revenue",
            suggested_text="Gross Sales",
            evidence_count=3,
            status="pending",
        )
        governance_db.add_all([s1, s2])
        governance_db.commit()

        result = bulk_accept_suggestions(
            governance_db, [str(s1.id), str(s2.id)]
        )

        assert result["accepted"] == 2
        assert result["already_resolved"] == 0
        assert result["total_requested"] == 2

    def test_already_resolved_skipped(self, governance_db):
        from src.db.crud import bulk_accept_suggestions
        from src.db.models import TaxonomySuggestion

        s1 = TaxonomySuggestion(
            suggestion_type="new_alias",
            canonical_name="revenue",
            suggested_text="Net Sales",
            evidence_count=5,
            status="accepted",
        )
        governance_db.add(s1)
        governance_db.commit()

        result = bulk_accept_suggestions(governance_db, [str(s1.id)])

        assert result["accepted"] == 0
        assert result["already_resolved"] == 1

    def test_not_found_reported(self, governance_db):
        from src.db.crud import bulk_accept_suggestions

        result = bulk_accept_suggestions(governance_db, [str(uuid4())])

        assert result["accepted"] == 0
        assert len(result["failed"]) == 1
        assert result["failed"][0]["reason"] == "not found"


class TestBulkAddAliases:
    """Test bulk alias addition."""

    def test_add_new_aliases(self, governance_db):
        from src.db.crud import bulk_add_aliases
        from src.db.models import Taxonomy

        tax = Taxonomy(
            canonical_name="revenue",
            category="income_statement",
            display_name="Revenue",
            aliases=["Sales"],
            definition="Revenue",
            typical_sign="positive",
        )
        governance_db.add(tax)
        governance_db.commit()

        result = bulk_add_aliases(governance_db, [
            {"canonical_name": "revenue", "alias": "Net Sales"},
            {"canonical_name": "revenue", "alias": "Gross Revenue"},
        ])

        assert result["added"] == 2
        assert result["duplicate"] == 0

        # Verify aliases were added
        governance_db.refresh(tax)
        assert "Net Sales" in tax.aliases
        assert "Gross Revenue" in tax.aliases

    def test_duplicate_skipped(self, governance_db):
        from src.db.crud import bulk_add_aliases
        from src.db.models import Taxonomy

        tax = Taxonomy(
            canonical_name="revenue",
            category="income_statement",
            display_name="Revenue",
            aliases=["Sales"],
            definition="Revenue",
            typical_sign="positive",
        )
        governance_db.add(tax)
        governance_db.commit()

        result = bulk_add_aliases(governance_db, [
            {"canonical_name": "revenue", "alias": "Sales"},  # duplicate
        ])

        assert result["added"] == 0
        assert result["duplicate"] == 1

    def test_not_found_reported(self, governance_db):
        from src.db.crud import bulk_add_aliases

        result = bulk_add_aliases(governance_db, [
            {"canonical_name": "nonexistent", "alias": "test"},
        ])

        assert result["added"] == 0
        assert len(result["failed"]) == 1


class TestTaxonomyHealth:
    """Test taxonomy health metrics."""

    def test_empty_database(self, governance_db):
        from src.db.crud import get_taxonomy_health

        result = get_taxonomy_health(governance_db)

        assert result["mapping_success_rate"] == 0.0
        assert result["alias_hit_rate"] == 0.0
        assert result["total_facts"] == 0
        assert result["coverage_utilization"] == 0.0
        assert result["suggestions"]["pending"] == 0

    def test_with_data(self, governance_db):
        from src.db.crud import get_taxonomy_health
        from src.db.models import ExtractionFact, Taxonomy

        # Create taxonomy items
        for name in ["revenue", "cogs", "ebitda"]:
            governance_db.add(Taxonomy(
                canonical_name=name,
                category="income_statement",
                display_name=name.title(),
                aliases=[],
                definition=name,
                typical_sign="positive",
            ))

        # Create facts: 8 mapped, 2 unmapped
        for i in range(8):
            governance_db.add(ExtractionFact(
                job_id=uuid4(),
                canonical_name="revenue",
                original_label="Revenue",
                value=100.0,
                period="2024",
            ))
        for i in range(2):
            governance_db.add(ExtractionFact(
                job_id=uuid4(),
                canonical_name="unmapped",
                original_label="Custom KPI",
                value=50.0,
                period="2024",
            ))
        governance_db.commit()

        result = get_taxonomy_health(governance_db)

        assert result["total_facts"] == 10
        assert result["mapped_facts"] == 8
        assert result["mapping_success_rate"] == 0.8
        assert result["total_taxonomy_items"] == 3
        assert result["used_taxonomy_items"] == 1  # only "revenue" used
