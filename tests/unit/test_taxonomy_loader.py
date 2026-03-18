"""
Tests for the taxonomy JSON loader used by extraction pipeline stages.
"""

import json
from unittest.mock import patch


class TestLoadTaxonomyJson:
    """Test load_taxonomy_json with caching behavior."""

    def setup_method(self):
        """Reset module-level cache before each test."""
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}

    def teardown_method(self):
        """Reset cache after each test."""
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}

    def test_loads_taxonomy_from_file(self, tmp_path):
        """Test loading taxonomy from a real JSON file."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import load_taxonomy_json

        data = {
            "version": "1.0",
            "categories": {
                "income_statement": [{"canonical_name": "revenue", "aliases": ["sales"]}]
            },
        }
        tax_file = tmp_path / "taxonomy.json"
        tax_file.write_text(json.dumps(data))

        with patch.object(mod, "TAXONOMY_PATH", tax_file):
            result = load_taxonomy_json()

        assert result["version"] == "1.0"
        assert "income_statement" in result["categories"]

    def test_returns_cached_on_second_call(self, tmp_path):
        """Test that second call returns cached data."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import load_taxonomy_json

        data = {"version": "2.0", "categories": {}}
        tax_file = tmp_path / "taxonomy.json"
        tax_file.write_text(json.dumps(data))

        with patch.object(mod, "TAXONOMY_PATH", tax_file):
            first = load_taxonomy_json()
            # Modify file - should not affect result (cached)
            tax_file.write_text(json.dumps({"version": "3.0", "categories": {}}))
            second = load_taxonomy_json()

        assert first is second
        assert second["version"] == "2.0"

    def test_returns_empty_when_file_missing(self, tmp_path):
        """Test graceful handling of missing taxonomy file."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import load_taxonomy_json

        with patch.object(mod, "TAXONOMY_PATH", tmp_path / "nonexistent.json"):
            result = load_taxonomy_json()

        assert result == {"categories": {}}


class TestGetAllTaxonomyItems:
    """Test get_all_taxonomy_items flattening."""

    def setup_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}

    def teardown_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}

    def test_flattens_all_categories(self):
        """Test items from all categories are returned."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import get_all_taxonomy_items

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {"canonical_name": "revenue"},
                    {"canonical_name": "cogs"},
                ],
                "balance_sheet": [
                    {"canonical_name": "cash"},
                ],
            }
        }

        items = get_all_taxonomy_items()
        assert len(items) == 3
        names = [i["canonical_name"] for i in items]
        assert "revenue" in names
        assert "cash" in names

    def test_returns_empty_for_no_categories(self):
        """Test returns empty list when no categories."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import get_all_taxonomy_items

        mod._taxonomy_cache = {"categories": {}}
        assert get_all_taxonomy_items() == []


class TestGetValidationRules:
    """Test get_validation_rules filtering."""

    def setup_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}

    def teardown_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}

    def test_returns_items_with_validation_rules(self):
        """Test that only items with cross_item_validation are returned."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import get_validation_rules

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {
                        "canonical_name": "gross_profit",
                        "validation_rules": {
                            "cross_item_validation": {"formula": "revenue - cogs"}
                        },
                    },
                    {
                        "canonical_name": "revenue",
                        "validation_rules": {},
                    },
                    {
                        "canonical_name": "cogs",
                    },
                ]
            }
        }

        rules = get_validation_rules()
        assert len(rules) == 1
        assert rules[0]["canonical_name"] == "gross_profit"
        assert "cross_item_validation" in rules[0]["validation_rules"]


class TestFormatTaxonomyForPrompt:
    """Test format_taxonomy_for_prompt formatting."""

    def setup_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}

    def teardown_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}

    def test_formats_with_aliases(self):
        """Test formatting includes aliases."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {
                        "canonical_name": "revenue",
                        "aliases": ["sales", "net_sales", "top_line", "extra"],
                    },
                    {"canonical_name": "cogs", "aliases": []},
                ]
            }
        }

        result = format_taxonomy_for_prompt(include_aliases=True)
        assert "Income Statement" in result
        assert "revenue (sales, net_sales, top_line, extra)" in result
        assert "cogs" in result

    def test_formats_without_aliases(self):
        """Test formatting without aliases."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = {
            "categories": {
                "balance_sheet": [
                    {"canonical_name": "cash", "aliases": ["cash_and_equivalents"]},
                ]
            }
        }

        result = format_taxonomy_for_prompt(include_aliases=False)
        assert "Balance Sheet: cash" in result
        assert "cash_and_equivalents" not in result

    def test_fallback_when_no_categories(self):
        """Test returns fallback taxonomy when no categories."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = {"categories": {}}

        result = format_taxonomy_for_prompt()
        assert "Income Statement:" in result
        assert "revenue" in result
        assert "Balance Sheet:" in result


class TestFormatTaxonomyWithLearnedAliases:
    """Test format_taxonomy_for_prompt with include_learned=True."""

    def setup_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}
        mod._promoted_cache = {}
        mod._promoted_cache_time = 0.0

    def teardown_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}
        mod._promoted_cache = {}
        mod._promoted_cache_time = 0.0

    def test_learned_aliases_appear_in_prompt(self):
        """Promoted learned aliases should appear tagged [learned]."""
        import time

        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {"canonical_name": "revenue", "aliases": ["sales"]},
                ]
            }
        }
        # Inject promoted cache directly
        mod._promoted_cache = {"total income": [("revenue", "income_statement")]}
        mod._promoted_cache_time = time.time()

        result = format_taxonomy_for_prompt(include_aliases=True, include_learned=True)
        assert "revenue (sales, total income [learned])" in result

    def test_learned_aliases_excluded_when_false(self):
        """include_learned=False should not show learned aliases."""
        import time

        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {"canonical_name": "revenue", "aliases": ["sales"]},
                ]
            }
        }
        mod._promoted_cache = {"total income": [("revenue", "income_statement")]}
        mod._promoted_cache_time = time.time()

        result = format_taxonomy_for_prompt(include_aliases=True, include_learned=False)
        assert "[learned]" not in result
        assert "revenue (sales)" in result

    def test_learned_alias_not_duplicated_if_already_in_taxonomy(self):
        """If a promoted alias matches an existing taxonomy alias, don't duplicate."""
        import time

        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {"canonical_name": "revenue", "aliases": ["sales"]},
                ]
            }
        }
        # "sales" is already a taxonomy alias — should not appear as [learned]
        mod._promoted_cache = {"sales": [("revenue", "income_statement")]}
        mod._promoted_cache_time = time.time()

        result = format_taxonomy_for_prompt(include_aliases=True, include_learned=True)
        assert result.count("sales") == 1  # only the taxonomy alias, not duplicated
        assert "[learned]" not in result

    def test_no_promoted_aliases_still_works(self):
        """When no promoted aliases exist, output is same as before."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {"canonical_name": "revenue", "aliases": ["sales"]},
                ]
            }
        }
        mod._promoted_cache = {}
        mod._promoted_cache_time = 0.0

        result = format_taxonomy_for_prompt(include_aliases=True, include_learned=True)
        assert "revenue (sales)" in result
        assert "[learned]" not in result


class TestStartupItemsInLoader:
    """Test that new startup items are accessible via the loader."""

    def setup_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}
        mod._canonical_names_cache = frozenset()

    def teardown_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}
        mod._canonical_names_cache = frozenset()

    def test_new_startup_items_in_canonical_names(self):
        """New startup items should appear in get_all_canonical_names()."""
        from src.extraction.taxonomy_loader import get_all_canonical_names

        names = get_all_canonical_names()
        assert "adjusted_ebitda" in names
        assert "burn_rate" in names
        assert "cash_runway_months" in names
        assert "convertible_notes" in names
        assert "safe_notes" in names
        assert "headcount" in names

    def test_arr_alias_resolves_to_metrics(self):
        """'arr' alias should resolve to arr in metrics."""
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        lookup = get_alias_to_canonicals()
        arr_entries = lookup.get("arr", [])
        categories = [cat for _, cat in arr_entries]
        assert "metrics" in categories


class TestFormatTaxonomyDetailed:
    """Test format_taxonomy_detailed output."""

    def setup_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}

    def teardown_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}

    def test_detailed_format_includes_display_names(self):
        """Test detailed format includes display names and aliases."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_detailed

        mod._taxonomy_cache = {
            "categories": {
                "cash_flow": [
                    {
                        "canonical_name": "cfo",
                        "display_name": "Cash From Operations",
                        "aliases": ["operating_cash_flow", "ocf"],
                    },
                    {
                        "canonical_name": "capex",
                        "display_name": "Capital Expenditures",
                    },
                ]
            }
        }

        result = format_taxonomy_detailed()
        assert "Cash Flow:" in result
        assert "cfo: Cash From Operations" in result
        assert "aliases: operating_cash_flow, ocf" in result
        assert "capex: Capital Expenditures" in result


class TestCategoryFiltering:
    """Test category-filtered taxonomy prompts to reduce token usage."""

    # Multi-category taxonomy fixture used across all tests in this class
    MULTI_CATEGORY_CACHE = {
        "categories": {
            "income_statement": [
                {"canonical_name": "revenue", "aliases": ["sales", "net_sales"]},
                {"canonical_name": "cogs", "aliases": ["cost_of_goods_sold"]},
                {"canonical_name": "ebitda", "aliases": ["operating_profit"]},
            ],
            "balance_sheet": [
                {"canonical_name": "cash", "aliases": ["cash_and_equivalents"]},
                {"canonical_name": "total_assets", "aliases": ["assets"]},
            ],
            "cash_flow": [
                {"canonical_name": "cfo", "aliases": ["operating_cash_flow"]},
                {"canonical_name": "capex", "aliases": ["capital_expenditures"]},
            ],
            "debt_schedule": [
                {"canonical_name": "senior_debt", "aliases": ["term_loan"]},
            ],
            "metrics": [
                {"canonical_name": "ltv_ratio", "aliases": ["loan_to_value"]},
                {"canonical_name": "dscr", "aliases": ["debt_service_coverage"]},
            ],
        }
    }

    def setup_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}
        mod._promoted_cache = {}
        mod._promoted_cache_time = 0.0

    def teardown_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}
        mod._promoted_cache = {}
        mod._promoted_cache_time = 0.0

    def test_filtered_returns_fewer_items_than_unfiltered(self):
        """Filtering to one category should return fewer items than full taxonomy."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = self.MULTI_CATEGORY_CACHE

        full_result = format_taxonomy_for_prompt()
        filtered_result = format_taxonomy_for_prompt(categories={"income_statement"})

        assert len(filtered_result) < len(full_result)
        # Filtered should have income_statement items
        assert "revenue" in filtered_result
        assert "cogs" in filtered_result
        # Filtered should NOT have balance_sheet or cash_flow items
        assert "cash" not in filtered_result
        assert "total_assets" not in filtered_result
        assert "cfo" not in filtered_result
        assert "capex" not in filtered_result

    def test_metrics_always_included_when_filtering(self):
        """Metrics category should always be included even when not in the filter set."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = self.MULTI_CATEGORY_CACHE

        result = format_taxonomy_for_prompt(categories={"income_statement"})
        # Metrics should be present (ratios/KPIs apply everywhere)
        assert "ltv_ratio" in result
        assert "dscr" in result
        # Income statement should be present
        assert "revenue" in result
        # Other categories should NOT be present
        assert "cash" not in result
        assert "senior_debt" not in result

    def test_none_categories_returns_same_as_no_arg(self):
        """categories=None should return the same result as calling without categories."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = self.MULTI_CATEGORY_CACHE

        no_arg_result = format_taxonomy_for_prompt()
        none_result = format_taxonomy_for_prompt(categories=None)

        assert no_arg_result == none_result

    def test_empty_set_returns_same_as_no_arg(self):
        """categories=set() (empty) should return the same result as no filter."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = self.MULTI_CATEGORY_CACHE

        no_arg_result = format_taxonomy_for_prompt()
        empty_set_result = format_taxonomy_for_prompt(categories=set())

        assert no_arg_result == empty_set_result

    def test_multiple_categories_filter(self):
        """Filtering to multiple categories includes items from all of them."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = self.MULTI_CATEGORY_CACHE

        result = format_taxonomy_for_prompt(
            categories={"income_statement", "balance_sheet"}
        )
        # Both categories should be present
        assert "revenue" in result
        assert "cash" in result
        # Metrics always included
        assert "ltv_ratio" in result
        # Other categories should NOT be present
        assert "cfo" not in result
        assert "senior_debt" not in result

    def test_detailed_format_also_filters_categories(self):
        """format_taxonomy_detailed should also support category filtering."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_detailed

        mod._taxonomy_cache = self.MULTI_CATEGORY_CACHE

        full_result = format_taxonomy_detailed()
        filtered_result = format_taxonomy_detailed(categories={"cash_flow"})

        assert len(filtered_result) < len(full_result)
        assert "cfo" in filtered_result
        assert "capex" in filtered_result
        # Metrics always included
        assert "ltv_ratio" in filtered_result
        # Other categories should NOT be present
        assert "revenue" not in filtered_result
        assert "total_assets" not in filtered_result

    def test_filtering_with_only_metrics_requested(self):
        """Requesting only metrics should return just metrics (metrics is auto-included anyway)."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = self.MULTI_CATEGORY_CACHE

        result = format_taxonomy_for_prompt(categories={"metrics"})
        assert "ltv_ratio" in result
        assert "dscr" in result
        # No other categories
        assert "revenue" not in result
        assert "cash" not in result
        assert "cfo" not in result

    def test_filtering_with_nonexistent_category(self):
        """Requesting a category that doesn't exist returns only metrics."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = self.MULTI_CATEGORY_CACHE

        result = format_taxonomy_for_prompt(categories={"nonexistent_category"})
        # Only metrics should appear (auto-included)
        assert "ltv_ratio" in result
        assert "dscr" in result
        assert "revenue" not in result
