"""
Unit tests for taxonomy model and TaxonomyManager.

Tests taxonomy CRUD operations, search functionality, and prompt formatting.
Uses sync sessions with SQLite for fast, isolated testing.
"""

from uuid import uuid4

import pytest

from src.db.models import Taxonomy
from src.guidelines.taxonomy import TaxonomyManager, load_taxonomy_for_stage3


@pytest.fixture
def sample_taxonomy(db_session):
    """Create sample taxonomy items for testing."""
    items = [
        Taxonomy(
            id=uuid4(),
            canonical_name="revenue",
            category="income_statement",
            display_name="Revenue",
            aliases=["Sales", "Net Sales", "Turnover"],
            definition="Total income from primary business activities",
            typical_sign="positive",
            parent_canonical=None,
        ),
        Taxonomy(
            id=uuid4(),
            canonical_name="product_revenue",
            category="income_statement",
            display_name="Product Revenue",
            aliases=["Product Sales", "Goods Revenue"],
            definition="Revenue from sale of physical products",
            typical_sign="positive",
            parent_canonical="revenue",
        ),
        Taxonomy(
            id=uuid4(),
            canonical_name="cogs",
            category="income_statement",
            display_name="Cost of Goods Sold",
            aliases=["Cost of Sales", "COGS", "Direct Costs"],
            definition="Direct costs attributable to production of goods sold",
            typical_sign="negative",
            parent_canonical=None,
        ),
        Taxonomy(
            id=uuid4(),
            canonical_name="gross_profit",
            category="income_statement",
            display_name="Gross Profit",
            aliases=["Gross Margin", "GP"],
            definition="Revenue minus cost of goods sold",
            typical_sign="positive",
            parent_canonical=None,
        ),
        Taxonomy(
            id=uuid4(),
            canonical_name="cash",
            category="balance_sheet",
            display_name="Cash and Cash Equivalents",
            aliases=["Cash", "Cash & Equivalents"],
            definition="Cash on hand and demand deposits",
            typical_sign="positive",
            parent_canonical="current_assets",
        ),
        Taxonomy(
            id=uuid4(),
            canonical_name="current_assets",
            category="balance_sheet",
            display_name="Current Assets",
            aliases=["CA", "Current Assets"],
            definition="Assets expected to be converted to cash within one year",
            typical_sign="positive",
            parent_canonical="total_assets",
        ),
        Taxonomy(
            id=uuid4(),
            canonical_name="total_assets",
            category="balance_sheet",
            display_name="Total Assets",
            aliases=["Assets", "Total Assets"],
            definition="Sum of all current and non-current assets",
            typical_sign="positive",
            parent_canonical=None,
        ),
        Taxonomy(
            id=uuid4(),
            canonical_name="cfo",
            category="cash_flow",
            display_name="Cash Flow from Operations",
            aliases=["Operating Cash Flow", "CFO"],
            definition="Cash generated from core operating activities",
            typical_sign="positive",
            parent_canonical=None,
        ),
        Taxonomy(
            id=uuid4(),
            canonical_name="capex",
            category="cash_flow",
            display_name="Capital Expenditures",
            aliases=["CapEx", "Capital Spending"],
            definition="Cash spent on property, plant, and equipment",
            typical_sign="negative",
            parent_canonical=None,
        ),
        Taxonomy(
            id=uuid4(),
            canonical_name="total_debt",
            category="debt_schedule",
            display_name="Total Debt",
            aliases=["Gross Debt", "Total Borrowings"],
            definition="Total outstanding debt",
            typical_sign="positive",
            parent_canonical=None,
        ),
    ]

    for item in items:
        db_session.add(item)
    db_session.commit()

    return items


class TestTaxonomyManager:
    """Test cases for TaxonomyManager class."""

    def test_get_all(self, db_session, sample_taxonomy):
        """Test retrieving all taxonomy items."""
        manager = TaxonomyManager()
        items = manager.get_all(db_session)

        assert len(items) == 10
        assert all(isinstance(item, Taxonomy) for item in items)

        # Verify sorting by category, then canonical_name
        categories = [item.category for item in items]
        assert categories == sorted(categories)

    def test_get_by_category(self, db_session, sample_taxonomy):
        """Test filtering taxonomy by category."""
        manager = TaxonomyManager()

        income_items = manager.get_by_category(db_session, "income_statement")
        assert len(income_items) == 4
        assert all(item.category == "income_statement" for item in income_items)
        assert any(item.canonical_name == "revenue" for item in income_items)

        bs_items = manager.get_by_category(db_session, "balance_sheet")
        assert len(bs_items) == 3

        cf_items = manager.get_by_category(db_session, "cash_flow")
        assert len(cf_items) == 2

        debt_items = manager.get_by_category(db_session, "debt_schedule")
        assert len(debt_items) == 1

        empty_items = manager.get_by_category(db_session, "nonexistent")
        assert len(empty_items) == 0

    def test_get_by_canonical_name(self, db_session, sample_taxonomy):
        """Test getting specific item by canonical name."""
        manager = TaxonomyManager()

        revenue = manager.get_by_canonical_name(db_session, "revenue")
        assert revenue is not None
        assert revenue.canonical_name == "revenue"
        assert revenue.display_name == "Revenue"
        assert "Sales" in revenue.aliases

        nonexistent = manager.get_by_canonical_name(db_session, "nonexistent")
        assert nonexistent is None

    def test_get_by_canonical_names_batch(self, db_session, sample_taxonomy):
        """Test batch lookup of multiple items."""
        manager = TaxonomyManager()

        items = manager.get_by_canonical_names(
            db_session, ["revenue", "cogs", "gross_profit", "nonexistent"]
        )

        assert len(items) == 3
        canonical_names = {item.canonical_name for item in items}
        assert canonical_names == {"revenue", "cogs", "gross_profit"}

    @pytest.mark.skip(reason="search() uses PostgreSQL any() function, not SQLite compatible")
    def test_search_by_canonical_name(self, db_session, sample_taxonomy):
        """Test searching taxonomy by canonical name (requires PostgreSQL)."""
        manager = TaxonomyManager()

        results = manager.search(db_session, "revenue")
        assert len(results) >= 1
        assert any(item.canonical_name == "revenue" for item in results)

    @pytest.mark.skip(reason="search() uses PostgreSQL any() function, not SQLite compatible")
    def test_search_partial_match(self, db_session, sample_taxonomy):
        """Test searching with partial matches (requires PostgreSQL)."""
        manager = TaxonomyManager()

        results = manager.search(db_session, "debt")
        assert len(results) >= 1
        assert any("debt" in item.canonical_name.lower() for item in results)

    def test_format_for_prompt_all_categories(self, db_session, sample_taxonomy):
        """Test formatting all taxonomy for Claude prompt."""
        manager = TaxonomyManager()

        prompt_text = manager.format_for_prompt(db_session)

        assert isinstance(prompt_text, str)
        assert len(prompt_text) > 0
        assert "revenue" in prompt_text
        assert "cogs" in prompt_text

    def test_format_for_prompt_single_category(self, db_session, sample_taxonomy):
        """Test formatting single category for prompt."""
        manager = TaxonomyManager()

        prompt_text = manager.format_for_prompt(db_session, "income_statement")

        assert isinstance(prompt_text, str)
        assert "revenue" in prompt_text
        assert "cogs" in prompt_text

    def test_get_hierarchy(self, db_session, sample_taxonomy):
        """Test getting hierarchical taxonomy structure."""
        manager = TaxonomyManager()

        hierarchy = manager.get_hierarchy(db_session)

        assert isinstance(hierarchy, dict)
        assert len(hierarchy) > 0

        # Check top-level items exist (no parent)
        assert "revenue" in hierarchy
        assert "cogs" in hierarchy
        assert "total_assets" in hierarchy

        # Check children are attached
        revenue_data = hierarchy["revenue"]
        assert "item" in revenue_data
        assert "children" in revenue_data
        assert revenue_data["item"].canonical_name == "revenue"

        children_names = [child.canonical_name for child in revenue_data["children"]]
        assert "product_revenue" in children_names

    def test_get_statistics(self, db_session, sample_taxonomy):
        """Test getting taxonomy statistics."""
        manager = TaxonomyManager()

        stats = manager.get_statistics(db_session)

        assert isinstance(stats, dict)
        assert "total_items" in stats
        assert "categories" in stats
        assert stats["total_items"] == 10

        categories = stats["categories"]
        assert categories["income_statement"] == 4
        assert categories["balance_sheet"] == 3
        assert categories["cash_flow"] == 2
        assert categories["debt_schedule"] == 1

    def test_load_taxonomy_for_stage3(self, db_session, sample_taxonomy):
        """Test convenience function for Stage 3 mapping."""
        taxonomy_text = load_taxonomy_for_stage3(db_session)

        assert isinstance(taxonomy_text, str)
        assert len(taxonomy_text) > 0
        assert "revenue" in taxonomy_text


class TestTaxonomyIntegration:
    """Integration tests for taxonomy system."""

    def test_empty_database(self, db_session):
        """Test behavior with empty database."""
        manager = TaxonomyManager()

        items = manager.get_all(db_session)
        assert items == []

        item = manager.get_by_canonical_name(db_session, "revenue")
        assert item is None

    def test_parent_child_relationship(self, db_session, sample_taxonomy):
        """Test parent-child relationships are correct."""
        manager = TaxonomyManager()

        product_revenue = manager.get_by_canonical_name(db_session, "product_revenue")
        assert product_revenue.parent_canonical == "revenue"

        revenue = manager.get_by_canonical_name(db_session, "revenue")
        assert revenue.parent_canonical is None

        cash = manager.get_by_canonical_name(db_session, "cash")
        assert cash.parent_canonical == "current_assets"

    def test_typical_sign_values(self, db_session, sample_taxonomy):
        """Test that typical_sign values are correctly set."""
        manager = TaxonomyManager()

        revenue = manager.get_by_canonical_name(db_session, "revenue")
        assert revenue.typical_sign == "positive"

        cogs = manager.get_by_canonical_name(db_session, "cogs")
        assert cogs.typical_sign == "negative"

    def test_aliases_stored_as_list(self, db_session, sample_taxonomy):
        """Test that aliases are stored and retrieved as lists."""
        manager = TaxonomyManager()

        revenue = manager.get_by_canonical_name(db_session, "revenue")
        assert isinstance(revenue.aliases, list)
        assert len(revenue.aliases) > 0
        assert "Sales" in revenue.aliases

    def test_no_duplicate_canonical_names(self, db_session, sample_taxonomy):
        """Test that canonical names are unique."""
        manager = TaxonomyManager()

        all_items = manager.get_all(db_session)
        canonical_names = [item.canonical_name for item in all_items]
        assert len(canonical_names) == len(set(canonical_names))

    def test_statistics_sum_to_total(self, db_session, sample_taxonomy):
        """Test that category counts sum to total items."""
        manager = TaxonomyManager()

        stats = manager.get_statistics(db_session)
        category_sum = sum(stats["categories"].values())
        assert category_sum == stats["total_items"]

    def test_prompt_format_consistency(self, db_session, sample_taxonomy):
        """Test that prompt formatting is consistent across calls."""
        manager = TaxonomyManager()

        prompt1 = manager.format_for_prompt(db_session)
        prompt2 = manager.format_for_prompt(db_session)
        assert prompt1 == prompt2
