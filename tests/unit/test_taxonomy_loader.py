"""
Tests for the taxonomy JSON loader used by extraction pipeline stages.
"""
import json
import pytest
from unittest.mock import patch, mock_open
from pathlib import Path


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
        from src.extraction.taxonomy_loader import load_taxonomy_json
        import src.extraction.taxonomy_loader as mod

        data = {"version": "1.0", "categories": {"income_statement": [
            {"canonical_name": "revenue", "aliases": ["sales"]}
        ]}}
        tax_file = tmp_path / "taxonomy.json"
        tax_file.write_text(json.dumps(data))

        with patch.object(mod, "TAXONOMY_PATH", tax_file):
            result = load_taxonomy_json()

        assert result["version"] == "1.0"
        assert "income_statement" in result["categories"]

    def test_returns_cached_on_second_call(self, tmp_path):
        """Test that second call returns cached data."""
        from src.extraction.taxonomy_loader import load_taxonomy_json
        import src.extraction.taxonomy_loader as mod

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
        from src.extraction.taxonomy_loader import load_taxonomy_json
        import src.extraction.taxonomy_loader as mod

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
                            "cross_item_validation": {
                                "formula": "revenue - cogs"
                            }
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
                    {"canonical_name": "revenue", "aliases": ["sales", "net_sales", "top_line", "extra"]},
                    {"canonical_name": "cogs", "aliases": []},
                ]
            }
        }

        result = format_taxonomy_for_prompt(include_aliases=True)
        assert "Income Statement" in result
        assert "revenue (sales, net_sales, top_line)" in result
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
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt
        import time

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
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt
        import time

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
        import src.extraction.taxonomy_loader as mod
        from src.extraction.taxonomy_loader import format_taxonomy_for_prompt
        import time

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
