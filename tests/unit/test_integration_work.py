"""
Tests for cross-agent integration work:
- Shared taxonomy loader
- Stage 4 dynamic rule loading from taxonomy.json
- EntityPattern CRUD operations
- Stage 5 entity pattern persistence
- Taxonomy API endpoints
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.extraction.taxonomy_loader import (
    format_taxonomy_detailed,
    format_taxonomy_for_prompt,
    get_all_taxonomy_items,
    get_validation_rules,
    load_taxonomy_json,
)
from src.validation.accounting_validator import AccountingValidator

# ============================================================
# Shared Taxonomy Loader Tests
# ============================================================


class TestTaxonomyLoader:
    """Test the shared taxonomy JSON loader."""

    def test_load_taxonomy_json_returns_dict(self):
        data = load_taxonomy_json()
        assert isinstance(data, dict)
        assert "categories" in data

    def test_load_taxonomy_json_has_version(self):
        data = load_taxonomy_json()
        assert "version" in data

    def test_load_taxonomy_json_cached(self):
        """Second call should return same object (cached)."""
        data1 = load_taxonomy_json()
        data2 = load_taxonomy_json()
        assert data1 is data2

    def test_get_all_taxonomy_items(self):
        items = get_all_taxonomy_items()
        assert len(items) >= 250
        assert all("canonical_name" in item for item in items)

    def test_get_validation_rules(self):
        rules = get_validation_rules()
        assert len(rules) >= 10  # Should have more than old 7 hardcoded
        for rule in rules:
            assert "canonical_name" in rule
            assert "validation_rules" in rule
            assert "cross_item_validation" in rule["validation_rules"]

    def test_get_validation_rules_includes_key_items(self):
        rules = get_validation_rules()
        names = {r["canonical_name"] for r in rules}
        # Must include at least the critical accounting identities
        assert "gross_profit" in names
        assert "total_assets" in names
        assert "revenue" in names

    def test_format_taxonomy_for_prompt_with_aliases(self):
        result = format_taxonomy_for_prompt(include_aliases=True)
        assert "Income Statement" in result
        assert "Balance Sheet" in result
        assert "(" in result  # Aliases in parens

    def test_format_taxonomy_for_prompt_without_aliases(self):
        result = format_taxonomy_for_prompt(include_aliases=False)
        assert "Income Statement" in result
        assert "revenue" in result

    def test_format_taxonomy_for_prompt_alias_shorter(self):
        with_aliases = format_taxonomy_for_prompt(include_aliases=True)
        without = format_taxonomy_for_prompt(include_aliases=False)
        assert len(with_aliases) > len(without)

    def test_format_taxonomy_detailed(self):
        result = format_taxonomy_detailed()
        assert "Income Statement" in result
        assert "aliases:" in result
        assert "  - revenue:" in result


# ============================================================
# Stage 4: Dynamic Rule Loading Tests
# ============================================================


class TestStage4DynamicRules:
    """Test that Stage 4 loads rules from taxonomy.json instead of hardcoded."""

    def test_derivation_rules_loaded_from_json(self):
        """DERIVATION_RULES should come from taxonomy.json, not hardcoded."""
        from src.extraction.stages.validation import DERIVATION_RULES

        # Should have more rules than the old 7 hardcoded ones
        assert len(DERIVATION_RULES) >= 10

    def test_derivation_rules_have_correct_structure(self):
        from src.extraction.stages.validation import DERIVATION_RULES

        for rule in DERIVATION_RULES:
            assert "canonical_name" in rule
            assert "validation_rules" in rule
            cross_val = rule["validation_rules"].get("cross_item_validation", {})
            # Each rule should have relationships and/or must_be_positive
            has_relationships = "relationships" in cross_val
            has_positive = "must_be_positive" in cross_val
            assert has_relationships or has_positive

    def test_gross_profit_rule_present(self):
        from src.extraction.stages.validation import DERIVATION_RULES

        gp_rules = [r for r in DERIVATION_RULES if r["canonical_name"] == "gross_profit"]
        assert len(gp_rules) == 1
        relationships = gp_rules[0]["validation_rules"]["cross_item_validation"]["relationships"]
        rules_text = [r["rule"] for r in relationships]
        assert any("gross_profit" in r and "revenue" in r for r in rules_text)

    def test_balance_sheet_rule_present(self):
        from src.extraction.stages.validation import DERIVATION_RULES

        ta_rules = [r for r in DERIVATION_RULES if r["canonical_name"] == "total_assets"]
        assert len(ta_rules) == 1
        relationships = ta_rules[0]["validation_rules"]["cross_item_validation"]["relationships"]
        rules_text = [r["rule"] for r in relationships]
        assert any("total_assets" in r and "total_liabilities" in r for r in rules_text)

    def test_accounting_validator_works_with_dynamic_rules(self):
        """Validate that AccountingValidator accepts taxonomy-loaded rules."""
        rules = get_validation_rules()
        validator = AccountingValidator(rules)
        data = {
            "revenue": Decimal("1000000"),
            "cogs": Decimal("600000"),
            "gross_profit": Decimal("400000"),
        }
        results = validator.validate(data)
        assert results.total_checks > 0
        assert results.success_rate == 1.0


# ============================================================
# EntityPattern CRUD Tests
# ============================================================


class TestEntityPatternCRUD:
    """Test EntityPattern CRUD operations."""

    @pytest.fixture
    def entity(self, db_session):
        """Create a test entity."""
        from src.db.models import Entity

        entity = Entity(
            id=uuid4(),
            name="Test Company Inc.",
            industry="technology",
        )
        db_session.add(entity)
        db_session.commit()
        return entity

    def test_upsert_creates_new_pattern(self, db_session, entity):
        from src.db import crud

        pattern = crud.upsert_entity_pattern(
            db=db_session,
            entity_id=entity.id,
            original_label="Total Revenue",
            canonical_name="revenue",
            confidence=0.95,
            created_by="claude",
        )
        assert pattern.original_label == "Total Revenue"
        assert pattern.canonical_name == "revenue"
        assert float(pattern.confidence) == 0.95
        assert pattern.occurrence_count == 1

    def test_upsert_updates_existing_pattern(self, db_session, entity):
        from src.db import crud

        # Create initial
        crud.upsert_entity_pattern(
            db=db_session,
            entity_id=entity.id,
            original_label="Revenue",
            canonical_name="revenue",
            confidence=0.85,
        )
        # Upsert with higher confidence
        pattern = crud.upsert_entity_pattern(
            db=db_session,
            entity_id=entity.id,
            original_label="Revenue",
            canonical_name="revenue",
            confidence=0.95,
        )
        assert float(pattern.confidence) == 0.95
        assert pattern.occurrence_count == 2

    def test_upsert_doesnt_downgrade_confidence(self, db_session, entity):
        from src.db import crud

        crud.upsert_entity_pattern(
            db=db_session,
            entity_id=entity.id,
            original_label="Revenue",
            canonical_name="revenue",
            confidence=0.95,
        )
        pattern = crud.upsert_entity_pattern(
            db=db_session,
            entity_id=entity.id,
            original_label="Revenue",
            canonical_name="revenue",
            confidence=0.80,
        )
        # Confidence should stay at 0.95
        assert float(pattern.confidence) == 0.95
        assert pattern.occurrence_count == 2

    def test_get_entity_patterns(self, db_session, entity):
        from src.db import crud

        crud.upsert_entity_pattern(
            db=db_session,
            entity_id=entity.id,
            original_label="Revenue",
            canonical_name="revenue",
            confidence=0.95,
        )
        crud.upsert_entity_pattern(
            db=db_session,
            entity_id=entity.id,
            original_label="COGS",
            canonical_name="cogs",
            confidence=0.90,
        )
        crud.upsert_entity_pattern(
            db=db_session,
            entity_id=entity.id,
            original_label="Misc",
            canonical_name="unmapped",
            confidence=0.30,
        )

        patterns = crud.get_entity_patterns(db_session, entity.id, min_confidence=0.5)
        assert len(patterns) == 2
        # Ordered by confidence desc
        assert patterns[0].canonical_name == "revenue"
        assert patterns[1].canonical_name == "cogs"

    def test_bulk_upsert_filters_low_confidence(self, db_session, entity):
        from src.db import crud

        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "COGS", "canonical_name": "cogs", "confidence": 0.85},
            {"original_label": "Unknown", "canonical_name": "unmapped", "confidence": 0.90},
            {"original_label": "Weak", "canonical_name": "opex", "confidence": 0.50},
        ]
        count = crud.bulk_upsert_entity_patterns(
            db=db_session,
            entity_id=entity.id,
            mappings=mappings,
            min_confidence=0.8,
        )
        # Only revenue and cogs should be persisted (unmapped excluded, weak below threshold)
        assert count == 2

    def test_get_patterns_empty_entity(self, db_session, entity):
        from src.db import crud

        patterns = crud.get_entity_patterns(db_session, entity.id)
        assert patterns == []


# ============================================================
# Taxonomy API Endpoint Tests
# ============================================================


class TestTaxonomyAPI:
    """Test taxonomy REST API endpoints."""

    @pytest.fixture
    def api_client(self, test_client_with_db):
        """Authenticated test client with DB."""
        return test_client_with_db

    def test_list_taxonomy(self, api_client, db_session):
        """GET /api/v1/taxonomy/ returns taxonomy items."""
        # Seed some taxonomy data
        from src.db.models import Taxonomy

        db_session.add(
            Taxonomy(
                id=uuid4(),
                canonical_name="revenue",
                category="income_statement",
                display_name="Revenue",
                aliases=["Sales"],
                definition="Total revenue",
                typical_sign="positive",
            )
        )
        db_session.commit()

        response = api_client.get("/api/v1/taxonomy/")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "items" in data

    def test_list_taxonomy_filter_category(self, api_client, db_session):
        """GET /api/v1/taxonomy/?category=income_statement filters correctly."""
        from src.db.models import Taxonomy

        db_session.add(
            Taxonomy(
                id=uuid4(),
                canonical_name="revenue",
                category="income_statement",
                display_name="Revenue",
                aliases=["Sales"],
                definition="Total revenue",
                typical_sign="positive",
            )
        )
        db_session.add(
            Taxonomy(
                id=uuid4(),
                canonical_name="cash",
                category="balance_sheet",
                display_name="Cash",
                aliases=["Cash"],
                definition="Cash on hand",
                typical_sign="positive",
            )
        )
        db_session.commit()

        response = api_client.get("/api/v1/taxonomy/?category=income_statement")
        assert response.status_code == 200
        data = response.json()
        assert all(item["category"] == "income_statement" for item in data["items"])

    def test_get_taxonomy_item(self, api_client, db_session):
        """GET /api/v1/taxonomy/{canonical_name} returns single item."""
        from src.db.models import Taxonomy

        db_session.add(
            Taxonomy(
                id=uuid4(),
                canonical_name="revenue",
                category="income_statement",
                display_name="Revenue",
                aliases=["Sales", "Turnover"],
                definition="Total revenue",
                typical_sign="positive",
            )
        )
        db_session.commit()

        response = api_client.get("/api/v1/taxonomy/revenue")
        assert response.status_code == 200
        data = response.json()
        assert data["canonical_name"] == "revenue"
        assert "Sales" in data["aliases"]

    def test_get_taxonomy_item_not_found(self, api_client):
        """GET /api/v1/taxonomy/nonexistent returns 404."""
        response = api_client.get("/api/v1/taxonomy/nonexistent")
        assert response.status_code == 404

    def test_taxonomy_stats(self, api_client, db_session):
        """GET /api/v1/taxonomy/stats returns statistics."""
        from src.db.models import Taxonomy

        for i in range(3):
            db_session.add(
                Taxonomy(
                    id=uuid4(),
                    canonical_name=f"item_{i}",
                    category="income_statement",
                    display_name=f"Item {i}",
                    aliases=[f"Alias {i}"],
                    definition=f"Definition {i}",
                    typical_sign="positive",
                )
            )
        db_session.commit()

        response = api_client.get("/api/v1/taxonomy/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_items" in data
        assert data["total_items"] >= 3

    def test_taxonomy_hierarchy(self, api_client, db_session):
        """GET /api/v1/taxonomy/hierarchy returns parent-child structure."""
        from src.db.models import Taxonomy

        db_session.add(
            Taxonomy(
                id=uuid4(),
                canonical_name="revenue",
                category="income_statement",
                display_name="Revenue",
                aliases=["Sales"],
                definition="Total revenue",
                typical_sign="positive",
            )
        )
        db_session.add(
            Taxonomy(
                id=uuid4(),
                canonical_name="product_revenue",
                category="income_statement",
                display_name="Product Revenue",
                aliases=["Product Sales"],
                definition="Product revenue",
                typical_sign="positive",
                parent_canonical="revenue",
            )
        )
        db_session.commit()

        response = api_client.get("/api/v1/taxonomy/hierarchy")
        assert response.status_code == 200
        data = response.json()
        assert "revenue" in data
        children = data["revenue"]["children"]
        assert any(c["canonical_name"] == "product_revenue" for c in children)


# ============================================================
# Stage 3/5 Backward Compatibility Tests
# ============================================================


class TestBackwardCompatibility:
    """Test that the refactored stages maintain backward compatibility."""

    def test_mapping_load_taxonomy_for_prompt_still_works(self):
        """_load_taxonomy_for_prompt is still importable from mapping module."""
        from src.extraction.stages.mapping import _load_taxonomy_for_prompt

        result = _load_taxonomy_for_prompt()
        assert "Income Statement" in result
        assert "revenue" in result

    def test_enhanced_mapping_load_taxonomy_still_works(self):
        """_load_taxonomy is still importable from enhanced_mapping module."""
        from src.extraction.stages.enhanced_mapping import (
            _format_taxonomy_for_prompt,
            _load_taxonomy,
        )

        data = _load_taxonomy()
        assert "categories" in data
        prompt = _format_taxonomy_for_prompt(data)
        assert "revenue" in prompt

    def test_mapping_taxonomy_path_importable(self):
        """TAXONOMY_PATH is importable from taxonomy_loader module."""
        from src.extraction.taxonomy_loader import TAXONOMY_PATH

        assert TAXONOMY_PATH.name == "taxonomy.json"
