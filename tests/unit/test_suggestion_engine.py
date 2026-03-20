"""
Unit tests for the taxonomy gap suggestion engine.

Tests fuzzy matching against EntityPatterns, Taxonomy aliases,
and LearnedAliases.
"""

from uuid import uuid4

import pytest

from src.db.models import EntityPattern, LearnedAlias, Taxonomy
from src.normalization.suggestion_engine import suggest_for_label

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def seeded_taxonomy(db_session):
    """Seed taxonomy items with aliases for testing."""
    items = [
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
        Taxonomy(
            id=uuid4(),
            canonical_name="total_assets",
            category="balance_sheet",
            display_name="Total Assets",
            aliases=["Assets Total", "Sum of Assets"],
            definition="Total assets",
            typical_sign="positive",
        ),
    ]
    for item in items:
        db_session.add(item)
    db_session.commit()
    return items


@pytest.fixture
def seeded_patterns(db_session):
    """Seed entity patterns for testing."""
    entity_id = uuid4()
    patterns = [
        EntityPattern(
            id=uuid4(),
            entity_id=entity_id,
            original_label="Total Net Revenue",
            canonical_name="revenue",
            confidence=0.92,
            is_active=True,
            created_by="claude",
        ),
        EntityPattern(
            id=uuid4(),
            entity_id=entity_id,
            original_label="Operating EBITDA",
            canonical_name="ebitda",
            confidence=0.88,
            is_active=True,
            created_by="claude",
        ),
    ]
    for p in patterns:
        db_session.add(p)
    db_session.commit()
    return patterns


@pytest.fixture
def seeded_learned_aliases(db_session):
    """Seed learned aliases for testing."""
    aliases = [
        LearnedAlias(
            id=uuid4(),
            canonical_name="revenue",
            alias_text="Turnover",
            occurrence_count=5,
        ),
        LearnedAlias(
            id=uuid4(),
            canonical_name="total_assets",
            alias_text="Balance Sheet Total",
            occurrence_count=3,
        ),
    ]
    for a in aliases:
        db_session.add(a)
    db_session.commit()
    return aliases


# ============================================================================
# Pattern-Based Suggestions
# ============================================================================


class TestPatternSuggestions:
    def test_exact_match_pattern(self, db_session, seeded_taxonomy, seeded_patterns):
        results = suggest_for_label(db_session, "Total Net Revenue")
        canonical_names = [r["canonical_name"] for r in results]
        assert "revenue" in canonical_names

    def test_fuzzy_match_pattern(self, db_session, seeded_taxonomy, seeded_patterns):
        results = suggest_for_label(db_session, "total net revenues")
        canonical_names = [r["canonical_name"] for r in results]
        assert "revenue" in canonical_names

    def test_pattern_source_field(self, db_session, seeded_taxonomy, seeded_patterns):
        results = suggest_for_label(db_session, "Total Net Revenue")
        revenue_match = next((r for r in results if r["canonical_name"] == "revenue"), None)
        assert revenue_match is not None
        assert revenue_match["source"] == "entity_pattern"

    def test_pattern_confidence_uses_pattern_confidence(self, db_session, seeded_taxonomy, seeded_patterns):
        results = suggest_for_label(db_session, "Total Net Revenue")
        revenue_match = next((r for r in results if r["canonical_name"] == "revenue"), None)
        assert revenue_match is not None
        # confidence = similarity * pattern.confidence * 0.95
        assert revenue_match["confidence"] > 0.5


# ============================================================================
# Taxonomy Alias Suggestions
# ============================================================================


class TestAliasSuggestions:
    def test_exact_alias_match(self, db_session, seeded_taxonomy):
        results = suggest_for_label(db_session, "Net Revenue")
        canonical_names = [r["canonical_name"] for r in results]
        assert "revenue" in canonical_names

    def test_fuzzy_alias_match(self, db_session, seeded_taxonomy):
        results = suggest_for_label(db_session, "total revenues")
        canonical_names = [r["canonical_name"] for r in results]
        assert "revenue" in canonical_names

    def test_canonical_name_match(self, db_session, seeded_taxonomy):
        results = suggest_for_label(db_session, "total assets")
        canonical_names = [r["canonical_name"] for r in results]
        assert "total_assets" in canonical_names

    def test_alias_source_field(self, db_session, seeded_taxonomy):
        results = suggest_for_label(db_session, "Net Revenue")
        revenue_match = next((r for r in results if r["canonical_name"] == "revenue"), None)
        assert revenue_match is not None
        assert revenue_match["source"] == "taxonomy_alias"


# ============================================================================
# Learned Alias Suggestions
# ============================================================================


class TestLearnedAliasSuggestions:
    def test_learned_alias_match(self, db_session, seeded_taxonomy, seeded_learned_aliases):
        results = suggest_for_label(db_session, "Turnover")
        canonical_names = [r["canonical_name"] for r in results]
        assert "revenue" in canonical_names

    def test_learned_alias_source_field(self, db_session, seeded_taxonomy, seeded_learned_aliases):
        results = suggest_for_label(db_session, "Turnover")
        match = next((r for r in results if r["source"] == "learned_alias"), None)
        assert match is not None


# ============================================================================
# Ranking and Deduplication
# ============================================================================


class TestRanking:
    def test_sorted_by_confidence_descending(self, db_session, seeded_taxonomy, seeded_patterns):
        results = suggest_for_label(db_session, "revenue")
        if len(results) >= 2:
            for i in range(len(results) - 1):
                assert results[i]["confidence"] >= results[i + 1]["confidence"]

    def test_deduplication(self, db_session, seeded_taxonomy, seeded_patterns, seeded_learned_aliases):
        """Same canonical from multiple sources should appear only once."""
        results = suggest_for_label(db_session, "Total Net Revenue")
        revenue_matches = [r for r in results if r["canonical_name"] == "revenue"]
        assert len(revenue_matches) == 1

    def test_limit_respected(self, db_session, seeded_taxonomy):
        results = suggest_for_label(db_session, "revenue", limit=2)
        assert len(results) <= 2

    def test_empty_label_returns_empty(self, db_session, seeded_taxonomy):
        results = suggest_for_label(db_session, "")
        assert results == []

    def test_completely_novel_label(self, db_session, seeded_taxonomy):
        results = suggest_for_label(db_session, "xyzzy_unknown_metric_12345")
        assert len(results) == 0

    def test_min_confidence_filter(self, db_session, seeded_taxonomy):
        results = suggest_for_label(db_session, "revenue", min_confidence=0.99)
        # Very high threshold should filter out most matches
        for r in results:
            assert r["confidence"] >= 0.99
