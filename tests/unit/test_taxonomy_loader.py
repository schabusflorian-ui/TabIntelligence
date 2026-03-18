"""
Tests for the taxonomy JSON loader used by extraction pipeline stages.

Includes tests for:
- Taxonomy loading and caching
- Alias conflict detection
- Priority-aware alias format support
- UK regional variant aliases
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


class TestAliasConflictDetection:
    """Test detect_alias_conflicts() finds cross-canonical alias conflicts."""

    def setup_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}
        mod._alias_conflicts_cache = None

    def teardown_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}
        mod._alias_conflicts_cache = None

    def test_detects_same_category_conflict(self):
        """Same alias mapping to different canonicals in same category."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import detect_alias_conflicts

        mod._taxonomy_cache = {
            "categories": {
                "balance_sheet": [
                    {"canonical_name": "inventory", "aliases": ["Stock", "Goods"]},
                    {"canonical_name": "inventories", "aliases": ["Stock", "Total Stock"]},
                ]
            }
        }

        conflicts = detect_alias_conflicts()
        assert "stock" in conflicts
        canonicals = {c for c, _ in conflicts["stock"]}
        assert "inventory" in canonicals
        assert "inventories" in canonicals

    def test_detects_cross_category_conflict(self):
        """Same alias mapping to canonicals in different categories."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import detect_alias_conflicts

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {"canonical_name": "rd_expense", "aliases": ["Development Costs"]},
                ],
                "project_finance": [
                    {"canonical_name": "development_costs", "aliases": ["Development Costs"]},
                ],
            }
        }

        conflicts = detect_alias_conflicts()
        assert "development costs" in conflicts
        entries = conflicts["development costs"]
        categories = {cat for _, cat in entries}
        assert "income_statement" in categories
        assert "project_finance" in categories

    def test_no_conflicts_returns_empty(self):
        """No conflicts when aliases are unique."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import detect_alias_conflicts

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {"canonical_name": "revenue", "aliases": ["Sales", "Top Line"]},
                    {"canonical_name": "cogs", "aliases": ["Cost of Goods"]},
                ]
            }
        }

        conflicts = detect_alias_conflicts()
        assert conflicts == {}

    def test_conflict_detection_cached(self):
        """Second call returns cached result."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import detect_alias_conflicts

        mod._taxonomy_cache = {
            "categories": {
                "balance_sheet": [
                    {"canonical_name": "cash", "aliases": ["Money"]},
                    {"canonical_name": "cash_equiv", "aliases": ["Money"]},
                ]
            }
        }

        first = detect_alias_conflicts()
        # Modify cache — should not affect result (cached)
        mod._taxonomy_cache = {"categories": {}}
        second = detect_alias_conflicts()
        assert first is second

    def test_invalidate_conflict_cache(self):
        """invalidate_alias_conflicts_cache() clears the cache."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import (
            detect_alias_conflicts,
            invalidate_alias_conflicts_cache,
        )

        mod._taxonomy_cache = {
            "categories": {
                "balance_sheet": [
                    {"canonical_name": "cash", "aliases": ["Money"]},
                    {"canonical_name": "cash_equiv", "aliases": ["Money"]},
                ]
            }
        }
        first = detect_alias_conflicts()
        assert "money" in first

        # Clear cache and re-run with no conflicts
        invalidate_alias_conflicts_cache()
        mod._taxonomy_cache = {
            "categories": {
                "balance_sheet": [
                    {"canonical_name": "cash", "aliases": ["Cash Only"]},
                ]
            }
        }
        second = detect_alias_conflicts()
        assert second == {}

    def test_real_taxonomy_has_known_conflicts(self):
        """The real taxonomy.json should have known alias conflicts like 'stock'."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import detect_alias_conflicts

        # Reset to force loading from real taxonomy file
        mod._taxonomy_cache = {}
        mod._alias_conflicts_cache = None

        conflicts = detect_alias_conflicts()
        # "stock" should conflict between inventory and inventories
        assert "stock" in conflicts
        stock_canonicals = {c for c, _ in conflicts["stock"]}
        assert len(stock_canonicals) >= 2

    def test_get_alias_conflicts_is_public_api(self):
        """get_alias_conflicts() should return same result as detect_alias_conflicts()."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import (
            detect_alias_conflicts,
            get_alias_conflicts,
        )

        mod._taxonomy_cache = {
            "categories": {
                "balance_sheet": [
                    {"canonical_name": "a", "aliases": ["Shared"]},
                    {"canonical_name": "b", "aliases": ["Shared"]},
                ]
            }
        }

        result = get_alias_conflicts()
        assert "shared" in result
        # Should be cached — same object
        assert result is detect_alias_conflicts()


class TestPriorityAwareAliases:
    """Test priority-aware alias format support."""

    def setup_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}
        mod._alias_conflicts_cache = None

    def teardown_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}
        mod._alias_conflicts_cache = None

    def test_normalize_alias_string(self):
        """String aliases get implicit priority=1."""
        from src.extraction.taxonomy_loader import _normalize_alias

        text, priority = _normalize_alias("Revenue")
        assert text == "Revenue"
        assert priority == 1

    def test_normalize_alias_dict(self):
        """Dict aliases use explicit text and priority."""
        from src.extraction.taxonomy_loader import _normalize_alias

        text, priority = _normalize_alias({"text": "Sls", "priority": 3})
        assert text == "Sls"
        assert priority == 3

    def test_normalize_alias_dict_default_priority(self):
        """Dict aliases without priority default to 1."""
        from src.extraction.taxonomy_loader import _normalize_alias

        text, priority = _normalize_alias({"text": "Sales"})
        assert text == "Sales"
        assert priority == 1

    def test_get_alias_text_string(self):
        """_get_alias_text extracts text from string alias."""
        from src.extraction.taxonomy_loader import _get_alias_text

        assert _get_alias_text("Revenue") == "Revenue"

    def test_get_alias_text_dict(self):
        """_get_alias_text extracts text from dict alias."""
        from src.extraction.taxonomy_loader import _get_alias_text

        assert _get_alias_text({"text": "Sls", "priority": 3}) == "Sls"

    def test_get_alias_priority_string(self):
        """String aliases have priority 1."""
        from src.extraction.taxonomy_loader import _get_alias_priority

        assert _get_alias_priority("Revenue") == 1

    def test_get_alias_priority_dict(self):
        """Dict aliases return their explicit priority."""
        from src.extraction.taxonomy_loader import _get_alias_priority

        assert _get_alias_priority({"text": "Sls", "priority": 3}) == 3

    def test_alias_lookup_handles_mixed_formats(self):
        """get_alias_to_canonicals works with both string and dict aliases."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {
                        "canonical_name": "revenue",
                        "display_name": "Revenue",
                        "aliases": [
                            "Sales",
                            {"text": "Sls", "priority": 3},
                            {"text": "Turnover", "priority": 2},
                        ],
                    }
                ]
            }
        }

        lookup = get_alias_to_canonicals()
        # String alias
        assert ("revenue", "income_statement") in lookup.get("sales", [])
        # Dict alias
        assert ("revenue", "income_statement") in lookup.get("sls", [])
        assert ("revenue", "income_statement") in lookup.get("turnover", [])
        # Display name
        assert ("revenue", "income_statement") in lookup.get("revenue", [])

    def test_priority_lookup_includes_priority_values(self):
        """get_alias_to_canonicals_with_priority includes priority in tuples."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import get_alias_to_canonicals_with_priority

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {
                        "canonical_name": "revenue",
                        "display_name": "Revenue",
                        "aliases": [
                            "Sales",
                            {"text": "Sls", "priority": 3},
                        ],
                    }
                ]
            }
        }

        lookup = get_alias_to_canonicals_with_priority()
        # String alias: priority=1
        sales_entries = lookup.get("sales", [])
        assert ("revenue", "income_statement", 1) in sales_entries
        # Dict alias: priority=3
        sls_entries = lookup.get("sls", [])
        assert ("revenue", "income_statement", 3) in sls_entries
        # Display name: priority=1
        rev_entries = lookup.get("revenue", [])
        assert ("revenue", "income_statement", 1) in rev_entries

    def test_format_prompt_with_mixed_aliases(self):
        """format_taxonomy_for_prompt extracts text from both alias formats."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {
                        "canonical_name": "revenue",
                        "aliases": [
                            "Sales",
                            {"text": "Turnover", "priority": 2},
                            {"text": "Sls", "priority": 3},
                        ],
                    }
                ]
            }
        }

        result = format_taxonomy_for_prompt(include_aliases=True)
        assert "revenue (Sales, Turnover, Sls)" in result

    def test_format_detailed_with_mixed_aliases(self):
        """format_taxonomy_detailed extracts text from both alias formats."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_detailed

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {
                        "canonical_name": "revenue",
                        "display_name": "Revenue",
                        "aliases": [
                            "Sales",
                            {"text": "Turnover", "priority": 2},
                        ],
                    }
                ]
            }
        }

        result = format_taxonomy_detailed()
        assert "aliases: Sales, Turnover" in result

    def test_backward_compat_string_only_aliases(self):
        """String-only aliases still work identically to before."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import (
            format_taxonomy_for_prompt,
            get_alias_to_canonicals,
        )

        mod._taxonomy_cache = {
            "categories": {
                "income_statement": [
                    {
                        "canonical_name": "revenue",
                        "display_name": "Revenue",
                        "aliases": ["Sales", "Net Sales", "Top Line"],
                    },
                    {
                        "canonical_name": "cogs",
                        "display_name": "COGS",
                        "aliases": [],
                    },
                ]
            }
        }

        # Lookup should work exactly as before
        lookup = get_alias_to_canonicals()
        assert ("revenue", "income_statement") in lookup.get("sales", [])
        assert ("revenue", "income_statement") in lookup.get("net sales", [])

        # Prompt formatting should work exactly as before
        result = format_taxonomy_for_prompt(include_aliases=True)
        assert "revenue (Sales, Net Sales, Top Line)" in result

    def test_conflict_detection_with_mixed_aliases(self):
        """detect_alias_conflicts handles mixed string/dict alias formats."""
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import detect_alias_conflicts

        mod._taxonomy_cache = {
            "categories": {
                "balance_sheet": [
                    {
                        "canonical_name": "inventory",
                        "aliases": [
                            {"text": "Stock", "priority": 1},
                        ],
                    },
                    {
                        "canonical_name": "inventories",
                        "aliases": ["Stock"],
                    },
                ]
            }
        }

        conflicts = detect_alias_conflicts()
        assert "stock" in conflicts
        canonicals = {c for c, _ in conflicts["stock"]}
        assert "inventory" in canonicals
        assert "inventories" in canonicals


class TestUKRegionalVariants:
    """Test that UK regional variants are present in the taxonomy."""

    def setup_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}

    def teardown_method(self):
        import src.extraction.taxonomy_loader as mod

        mod._taxonomy_cache = {}

    def test_turnover_maps_to_revenue(self):
        """UK 'Turnover' should resolve to revenue."""
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        lookup = get_alias_to_canonicals()
        entries = lookup.get("turnover", [])
        canonicals = [c for c, _ in entries]
        assert "revenue" in canonicals

    def test_debtors_maps_to_accounts_receivable(self):
        """UK 'Debtors' should resolve to accounts_receivable."""
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        lookup = get_alias_to_canonicals()
        entries = lookup.get("debtors", [])
        canonicals = [c for c, _ in entries]
        assert "accounts_receivable" in canonicals

    def test_creditors_maps_to_accounts_payable(self):
        """UK 'Creditors' should resolve to accounts_payable."""
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        lookup = get_alias_to_canonicals()
        entries = lookup.get("creditors", [])
        canonicals = [c for c, _ in entries]
        assert "accounts_payable" in canonicals

    def test_stock_maps_to_inventory(self):
        """UK 'Stock' should resolve to inventory."""
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        lookup = get_alias_to_canonicals()
        entries = lookup.get("stock", [])
        canonicals = [c for c, _ in entries]
        assert "inventory" in canonicals

    def test_sundry_debtors_maps_to_accounts_receivable(self):
        """UK 'Sundry Debtors' should resolve to accounts_receivable."""
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        lookup = get_alias_to_canonicals()
        entries = lookup.get("sundry debtors", [])
        canonicals = [c for c, _ in entries]
        assert "accounts_receivable" in canonicals

    def test_sundry_creditors_maps_to_accounts_payable(self):
        """UK 'Sundry Creditors' should resolve to accounts_payable."""
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        lookup = get_alias_to_canonicals()
        entries = lookup.get("sundry creditors", [])
        canonicals = [c for c, _ in entries]
        assert "accounts_payable" in canonicals

    def test_profit_and_loss_account_maps_to_retained_earnings(self):
        """UK 'Profit and Loss Account' should resolve to retained_earnings."""
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        lookup = get_alias_to_canonicals()
        entries = lookup.get("profit and loss account", [])
        canonicals = [c for c, _ in entries]
        assert "retained_earnings" in canonicals

    def test_share_capital_maps_to_common_stock(self):
        """UK 'Share Capital' should resolve to common_stock."""
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        lookup = get_alias_to_canonicals()
        entries = lookup.get("share capital", [])
        canonicals = [c for c, _ in entries]
        assert "common_stock" in canonicals

    def test_cash_at_bank_maps_to_cash(self):
        """UK 'Cash at Bank and in Hand' should resolve to cash or cash_and_equivalents."""
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        lookup = get_alias_to_canonicals()
        entries = lookup.get("cash at bank and in hand", [])
        canonicals = [c for c, _ in entries]
        assert any(c in canonicals for c in ["cash", "cash_and_equivalents"])

    def test_uk_creditors_due_within_one_year(self):
        """UK Companies Act format for current liabilities."""
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        lookup = get_alias_to_canonicals()
        entries = lookup.get("creditors: amounts falling due within one year", [])
        canonicals = [c for c, _ in entries]
        assert "current_liabilities" in canonicals

    def test_common_misspelling_recievables(self):
        """Common misspelling 'recievables' should resolve to accounts_receivable."""
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        lookup = get_alias_to_canonicals()
        entries = lookup.get("recievables", [])
        canonicals = [c for c, _ in entries]
        assert "accounts_receivable" in canonicals
