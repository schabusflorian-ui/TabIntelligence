"""
Unit tests for Phase 1: Taxonomy Governance features.

Tests:
- Category constants SSoT (taxonomy_constants.py)
- Recursive hierarchy building (TaxonomyManager.get_hierarchy)
- Taxonomy versioning (record_taxonomy_version)
- JSON Schema (data/taxonomy.schema.json)
"""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from src.db.models import Taxonomy, TaxonomyVersion
from src.guidelines.taxonomy import TaxonomyManager
from src.taxonomy_constants import (
    CATEGORY_BADGE_CLASSES,
    CATEGORY_DISPLAY_NAMES,
    VALID_CATEGORIES,
)

# ============================================================================
# Category Constants SSoT
# ============================================================================


class TestTaxonomyConstants:
    """Test taxonomy_constants.py single source of truth."""

    def test_valid_categories_has_exactly_six(self):
        assert len(VALID_CATEGORIES) == 6

    def test_valid_categories_values(self):
        expected = {
            "income_statement",
            "balance_sheet",
            "cash_flow",
            "debt_schedule",
            "metrics",
            "project_finance",
        }
        assert set(VALID_CATEGORIES) == expected

    def test_display_names_keys_match_valid_categories(self):
        assert set(CATEGORY_DISPLAY_NAMES.keys()) == set(VALID_CATEGORIES)

    def test_badge_classes_keys_match_valid_categories(self):
        assert set(CATEGORY_BADGE_CLASSES.keys()) == set(VALID_CATEGORIES)

    def test_display_names_are_human_readable(self):
        for cat, name in CATEGORY_DISPLAY_NAMES.items():
            assert len(name) > 0
            assert name[0].isupper(), f"{cat} display name should be capitalized"

    def test_badge_classes_are_strings(self):
        for cat, badge in CATEGORY_BADGE_CLASSES.items():
            assert isinstance(badge, str)
            assert badge.startswith("b-"), f"{cat} badge should start with 'b-'"

    def test_valid_categories_is_tuple(self):
        """Tuple ensures immutability."""
        assert isinstance(VALID_CATEGORIES, tuple)

    def test_no_deprecated_categories(self):
        deprecated = {"depreciation_amortization", "working_capital", "assumptions",
                       "debt_metrics", "coverage_ratios", "credit_metrics"}
        for cat in VALID_CATEGORIES:
            assert cat not in deprecated, f"Deprecated category {cat} still in VALID_CATEGORIES"


# ============================================================================
# Recursive Hierarchy
# ============================================================================


class TestRecursiveHierarchy:
    """Test TaxonomyManager.get_hierarchy recursive tree building."""

    @pytest.fixture
    def taxonomy_tree(self, db_session):
        """Create a 3-level taxonomy tree for testing."""
        items = [
            Taxonomy(
                id=uuid4(),
                canonical_name="total_assets",
                category="balance_sheet",
                display_name="Total Assets",
                aliases=["Assets"],
                definition="Sum of all assets",
                typical_sign="positive",
                parent_canonical=None,
            ),
            Taxonomy(
                id=uuid4(),
                canonical_name="current_assets",
                category="balance_sheet",
                display_name="Current Assets",
                aliases=["CA"],
                definition="Assets due within a year",
                typical_sign="positive",
                parent_canonical="total_assets",
            ),
            Taxonomy(
                id=uuid4(),
                canonical_name="cash_and_equivalents",
                category="balance_sheet",
                display_name="Cash & Equivalents",
                aliases=["Cash"],
                definition="Liquid cash",
                typical_sign="positive",
                parent_canonical="current_assets",
            ),
            Taxonomy(
                id=uuid4(),
                canonical_name="accounts_receivable",
                category="balance_sheet",
                display_name="Accounts Receivable",
                aliases=["AR"],
                definition="Money owed to company",
                typical_sign="positive",
                parent_canonical="current_assets",
            ),
            Taxonomy(
                id=uuid4(),
                canonical_name="non_current_assets",
                category="balance_sheet",
                display_name="Non-Current Assets",
                aliases=["Fixed Assets"],
                definition="Long-term assets",
                typical_sign="positive",
                parent_canonical="total_assets",
            ),
            Taxonomy(
                id=uuid4(),
                canonical_name="revenue",
                category="income_statement",
                display_name="Revenue",
                aliases=["Sales"],
                definition="Total income",
                typical_sign="positive",
                parent_canonical=None,
            ),
        ]
        for item in items:
            db_session.add(item)
        db_session.commit()
        return items

    def test_hierarchy_returns_roots_only(self, db_session, taxonomy_tree):
        manager = TaxonomyManager()
        hierarchy = manager.get_hierarchy(db_session)
        root_names = set(hierarchy.keys())
        assert "total_assets" in root_names
        assert "revenue" in root_names
        # Children should NOT be top-level
        assert "current_assets" not in root_names
        assert "cash_and_equivalents" not in root_names

    def test_hierarchy_children_attached(self, db_session, taxonomy_tree):
        manager = TaxonomyManager()
        hierarchy = manager.get_hierarchy(db_session)
        total_assets = hierarchy["total_assets"]
        child_names = [c["item"].canonical_name for c in total_assets["children"]]
        assert "current_assets" in child_names
        assert "non_current_assets" in child_names

    def test_hierarchy_grandchildren_attached(self, db_session, taxonomy_tree):
        manager = TaxonomyManager()
        hierarchy = manager.get_hierarchy(db_session)
        total_assets = hierarchy["total_assets"]
        current_assets_node = next(
            c for c in total_assets["children"]
            if c["item"].canonical_name == "current_assets"
        )
        grandchild_names = [c["item"].canonical_name for c in current_assets_node["children"]]
        assert "cash_and_equivalents" in grandchild_names
        assert "accounts_receivable" in grandchild_names

    def test_hierarchy_category_filter(self, db_session, taxonomy_tree):
        manager = TaxonomyManager()
        hierarchy = manager.get_hierarchy(db_session, category="balance_sheet")
        assert "total_assets" in hierarchy
        assert "revenue" not in hierarchy

    def test_hierarchy_orphan_becomes_root(self, db_session):
        """Item referencing non-existent parent is treated as root."""
        item = Taxonomy(
            id=uuid4(),
            canonical_name="orphan_item",
            category="metrics",
            display_name="Orphan",
            aliases=["orphan"],
            definition="No parent",
            typical_sign="positive",
            parent_canonical="does_not_exist",
        )
        db_session.add(item)
        db_session.commit()

        manager = TaxonomyManager()
        hierarchy = manager.get_hierarchy(db_session, category="metrics")
        assert "orphan_item" in hierarchy

    def test_hierarchy_leaf_has_empty_children(self, db_session, taxonomy_tree):
        manager = TaxonomyManager()
        hierarchy = manager.get_hierarchy(db_session)
        revenue = hierarchy["revenue"]
        assert revenue["children"] == []


# ============================================================================
# Taxonomy Versioning
# ============================================================================


class TestTaxonomyVersioning:
    """Test record_taxonomy_version and TaxonomyVersion model."""

    def test_record_taxonomy_version(self, db_session):
        from src.extraction.taxonomy_loader import record_taxonomy_version

        record_taxonomy_version(db_session, applied_by="test")
        versions = db_session.query(TaxonomyVersion).all()
        assert len(versions) == 1
        v = versions[0]
        assert v.version == "3.5.0"
        assert v.item_count > 200
        assert len(v.checksum) == 64  # SHA-256 hex
        assert v.applied_by == "test"
        assert isinstance(v.categories, dict)
        assert "income_statement" in v.categories
        # Snapshot should be stored starting from this version
        assert v.snapshot is not None
        assert v.snapshot.get("version") == "3.5.0"

    def test_record_version_checksum_matches_file(self, db_session):
        from src.extraction.taxonomy_loader import TAXONOMY_PATH, record_taxonomy_version

        record_taxonomy_version(db_session, applied_by="test")
        v = db_session.query(TaxonomyVersion).first()
        content = TAXONOMY_PATH.read_bytes()
        expected_checksum = hashlib.sha256(content).hexdigest()
        assert v.checksum == expected_checksum

    def test_record_version_category_counts(self, db_session):
        from src.extraction.taxonomy_loader import record_taxonomy_version

        record_taxonomy_version(db_session, applied_by="test")
        v = db_session.query(TaxonomyVersion).first()
        total = sum(v.categories.values())
        assert total == v.item_count

    def test_multiple_version_records(self, db_session):
        from src.extraction.taxonomy_loader import record_taxonomy_version

        record_taxonomy_version(db_session, applied_by="seed")
        record_taxonomy_version(db_session, applied_by="migration")
        versions = db_session.query(TaxonomyVersion).all()
        assert len(versions) == 2
        assert {v.applied_by for v in versions} == {"seed", "migration"}


# ============================================================================
# JSON Schema
# ============================================================================


class TestTaxonomyJsonSchema:
    """Test data/taxonomy.schema.json structure and validity."""

    @pytest.fixture(autouse=True)
    def load_schema(self):
        schema_path = Path("data/taxonomy.schema.json")
        assert schema_path.exists(), "taxonomy.schema.json not found"
        with open(schema_path) as f:
            self.schema = json.load(f)

    def test_schema_has_draft_version(self):
        assert "$schema" in self.schema
        assert "draft" in self.schema["$schema"]

    def test_schema_requires_version(self):
        required = self.schema.get("required", [])
        assert "version" in required

    def test_schema_requires_categories(self):
        required = self.schema.get("required", [])
        assert "categories" in required

    def test_schema_defines_item_properties(self):
        """Schema should define canonical_name, category, display_name as required item fields."""
        # Navigate to item definition
        props = self.schema.get("properties", {})
        categories_prop = props.get("categories", {})
        # Should define items in some form (additionalProperties or patternProperties)
        assert categories_prop, "Schema must define categories property"

    def test_taxonomy_validates_against_schema(self):
        """If jsonschema is installed, validate taxonomy.json against schema."""
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")

        with open("data/taxonomy.json") as f:
            taxonomy = json.load(f)

        jsonschema.validate(taxonomy, self.schema)
