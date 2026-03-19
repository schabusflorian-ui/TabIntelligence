"""
Tests for Phase 1-3 taxonomy enhancements.

Tests:
- Taxonomy JSON integrity (OCR variants, format examples, industry tags)
- Mapping stage _load_taxonomy_for_prompt() with alias inclusion
- AccountingValidator cross-item validation
- Confidence scoring metadata presence
"""

import json
from decimal import Decimal
from uuid import uuid4

import pytest

from src.db.models import Taxonomy
from src.extraction.stages.mapping import _load_taxonomy_for_prompt
from src.extraction.taxonomy_loader import TAXONOMY_PATH
from src.guidelines.taxonomy import TaxonomyManager
from src.validation.accounting_validator import AccountingValidator, ValidationSummary

# ============================================================
# Taxonomy JSON file tests
# ============================================================


class TestTaxonomyJSON:
    """Test the taxonomy.json file structure and Phase 1-3 enhancements."""

    @pytest.fixture(autouse=True)
    def load_taxonomy(self):
        """Load taxonomy data for all tests in this class."""
        with open(TAXONOMY_PATH) as f:
            self.data = json.load(f)
        self.all_items = []
        for cat_items in self.data["categories"].values():
            self.all_items.extend(cat_items)

    def test_version_is_3_0_0(self):
        assert self.data["version"] == "3.2.0"

    def test_minimum_295_items(self):
        assert len(self.all_items) >= 295

    def test_all_categories_present(self):
        expected = {
            "income_statement",
            "balance_sheet",
            "cash_flow",
            "debt_schedule",
            "metrics",
            "project_finance",
        }
        assert expected.issubset(set(self.data["categories"].keys()))

    def test_all_items_have_required_fields(self):
        required = {
            "canonical_name",
            "category",
            "display_name",
            "aliases",
            "definition",
            "typical_sign",
        }
        for item in self.all_items:
            missing = required - set(item.keys())
            assert not missing, f"{item['canonical_name']} missing: {missing}"

    def test_no_duplicate_canonical_names(self):
        names = [item["canonical_name"] for item in self.all_items]
        assert len(names) == len(set(names)), "Duplicate names found"

    def test_all_items_have_at_least_one_alias(self):
        for item in self.all_items:
            assert len(item["aliases"]) >= 1, f"{item['canonical_name']} has no aliases"

    def test_no_orphaned_parent_references(self):
        valid_names = {item["canonical_name"] for item in self.all_items}
        for item in self.all_items:
            parent = item.get("parent_canonical")
            if parent:
                assert parent in valid_names, (
                    f"{item['canonical_name']} refs missing parent: {parent}"
                )

    # Phase 1: OCR variants
    def test_ocr_variants_present_on_key_items(self):
        key_items = ["revenue", "ebitda", "net_income", "total_assets", "fcf"]
        for name in key_items:
            item = next((i for i in self.all_items if i["canonical_name"] == name), None)
            assert item is not None, f"{name} not found"
            assert "ocr_variants" in item, f"{name} missing ocr_variants"
            assert len(item["ocr_variants"]) >= 3, f"{name} needs more OCR variants"

    def test_ocr_variants_include_spacing_errors(self):
        revenue = next(i for i in self.all_items if i["canonical_name"] == "revenue")
        variants = revenue["ocr_variants"]
        has_spacing = any(" " in v for v in variants)
        assert has_spacing, "Revenue OCR variants should include spacing errors"

    # Phase 1: Format examples
    def test_format_examples_present_on_key_items(self):
        key_items = ["revenue", "ebitda", "net_income"]
        for name in key_items:
            item = next((i for i in self.all_items if i["canonical_name"] == name), None)
            assert item is not None
            assert "format_examples" in item, f"{name} missing format_examples"
            for ex in item["format_examples"]:
                assert "value" in ex, f"{name} format_example missing 'value'"
                assert "context" in ex, f"{name} format_example missing 'context'"

    # Phase 1: Industry tags
    def test_all_items_have_industry_tags(self):
        for item in self.all_items:
            assert "industry_tags" in item, f"{item['canonical_name']} missing industry_tags"
            assert len(item["industry_tags"]) >= 1

    def test_saas_metrics_tagged_correctly(self):
        saas_names = {"arr", "mrr", "cac", "ltv", "churn_rate"}
        for name in saas_names:
            item = next((i for i in self.all_items if i["canonical_name"] == name), None)
            if item:
                assert "saas" in item.get("industry_tags", []), f"{name} should be tagged 'saas'"

    # Phase 2: Confidence scoring
    def test_confidence_scoring_on_key_items(self):
        key_items = ["revenue", "ebitda", "net_income", "total_assets"]
        for name in key_items:
            item = next((i for i in self.all_items if i["canonical_name"] == name), None)
            assert item is not None
            assert "confidence_scoring" in item, f"{name} missing confidence_scoring"
            conf = item["confidence_scoring"]
            assert "high_confidence_signals" in conf, f"{name} missing high_confidence_signals"

    # Phase 3: GAAP/IFRS
    def test_gaap_ifrs_on_key_items(self):
        key_items = ["revenue", "inventory", "depreciation", "goodwill"]
        for name in key_items:
            item = next((i for i in self.all_items if i["canonical_name"] == name), None)
            assert item is not None
            assert "accounting_standards" in item, f"{name} missing accounting_standards"
            standards = item["accounting_standards"]
            assert "us_gaap" in standards, f"{name} missing us_gaap"
            assert "ifrs" in standards, f"{name} missing ifrs"

    # Phase 3: Regulatory
    def test_regulatory_context_on_key_items(self):
        key_items = ["revenue", "net_income", "ebitda", "goodwill"]
        for name in key_items:
            item = next((i for i in self.all_items if i["canonical_name"] == name), None)
            assert item is not None
            assert "regulatory_context" in item, f"{name} missing regulatory_context"

    # Phase 3: Industry-specific metrics
    def test_saas_metrics_exist(self):
        saas_items = {"arr", "mrr", "cac", "ltv", "churn_rate"}
        found = {item["canonical_name"] for item in self.all_items}
        missing = saas_items - found
        assert not missing, f"Missing SaaS metrics: {missing}"

    def test_real_estate_metrics_exist(self):
        re_items = {"noi", "cap_rate", "ffo", "occupancy_rate"}
        found = {item["canonical_name"] for item in self.all_items}
        missing = re_items - found
        assert not missing, f"Missing real estate metrics: {missing}"

    def test_manufacturing_metrics_exist(self):
        mfg_items = {"oee", "capacity_utilization", "scrap_rate"}
        found = {item["canonical_name"] for item in self.all_items}
        missing = mfg_items - found
        assert not missing, f"Missing manufacturing metrics: {missing}"

    def test_retail_metrics_exist(self):
        retail_items = {"same_store_sales", "inventory_turnover"}
        found = {item["canonical_name"] for item in self.all_items}
        missing = retail_items - found
        assert not missing, f"Missing retail metrics: {missing}"

    # Phase 4: Startup / SaaS expansion
    def test_startup_items_exist(self):
        found = {item["canonical_name"] for item in self.all_items}
        startup_items = {
            "recurring_revenue",
            "non_recurring_revenue",
            "usage_based_revenue",
            "adjusted_ebitda",
            "stock_based_compensation_expense",
            "restructuring_charges",
            "current_tax_expense",
            "deferred_tax_expense",
            "contribution_margin",
            "contract_assets",
            "contract_liabilities",
            "right_of_use_asset",
            "lease_liability_current",
            "lease_liability_non_current",
            "tax_loss_carryforward",
            "convertible_notes",
            "safe_notes",
            "change_in_contract_liabilities",
            "proceeds_from_convertible_notes",
            "change_in_deferred_revenue_cf",
            "burn_rate",
            "cash_runway_months",
            "bookings",
            "acv",
            "customer_count",
            "new_customers",
            "churned_customers",
            "headcount",
            "revenue_per_employee",
            "logo_churn_rate",
            "revenue_churn_rate",
            "monthly_burn",
            "pipeline_value",
        }
        missing = startup_items - found
        assert not missing, f"Missing startup items: {missing}"

    def test_new_saas_items_tagged(self):
        saas_names = {
            "recurring_revenue",
            "usage_based_revenue",
            "burn_rate",
            "cash_runway_months",
            "bookings",
            "acv",
        }
        for name in saas_names:
            item = next((i for i in self.all_items if i["canonical_name"] == name), None)
            assert item is not None, f"{name} not found"
            tags = item.get("industry_tags", [])
            assert "saas" in tags or "subscription" in tags, (
                f"{name} should be tagged 'saas' or 'subscription', got {tags}"
            )

    def test_no_conflicting_aliases_among_ws4_items(self):
        """WS-4 new items should not have aliases that conflict with each other."""
        ws4_items = {
            "recurring_revenue",
            "non_recurring_revenue",
            "usage_based_revenue",
            "adjusted_ebitda",
            "stock_based_compensation_expense",
            "restructuring_charges",
            "current_tax_expense",
            "deferred_tax_expense",
            "contribution_margin",
            "contract_assets",
            "contract_liabilities",
            "right_of_use_asset",
            "lease_liability_current",
            "lease_liability_non_current",
            "tax_loss_carryforward",
            "convertible_notes",
            "safe_notes",
            "change_in_contract_liabilities",
            "proceeds_from_convertible_notes",
            "change_in_deferred_revenue_cf",
            "burn_rate",
            "cash_runway_months",
            "bookings",
            "acv",
            "customer_count",
            "new_customers",
            "churned_customers",
            "headcount",
            "revenue_per_employee",
            "logo_churn_rate",
            "revenue_churn_rate",
            "monthly_burn",
            "pipeline_value",
        }
        for category, items in self.data["categories"].items():
            ws4_in_cat = [i for i in items if i["canonical_name"] in ws4_items]
            alias_to_item = {}
            for item in ws4_in_cat:
                for alias in item.get("aliases", []):
                    key = alias.lower().strip()
                    if key in alias_to_item:
                        pytest.fail(
                            f"WS-4 alias '{alias}' appears on both "
                            f"'{alias_to_item[key]}' and '{item['canonical_name']}' "
                            f"in category '{category}'"
                        )
                    alias_to_item[key] = item["canonical_name"]

    def test_arr_mrr_aliases_not_on_revenue(self):
        """ARR and MRR aliases should be on arr/mrr metrics, not on revenue."""
        revenue = next(i for i in self.all_items if i["canonical_name"] == "revenue")
        lowered = [a.lower() for a in revenue.get("aliases", [])]
        assert "arr" not in lowered, "revenue should not have 'ARR' alias"
        assert "mrr" not in lowered, "revenue should not have 'MRR' alias"

    def test_adjusted_ebitda_has_validation_rule(self):
        item = next((i for i in self.all_items if i["canonical_name"] == "adjusted_ebitda"), None)
        assert item is not None
        vr = item.get("validation_rules", {})
        civ = vr.get("cross_item_validation", {})
        assert len(civ.get("relationships", [])) >= 1

    def test_ws4_items_in_correct_categories(self):
        """Each WS-4 item must be in the expected category."""
        expected = {
            "recurring_revenue": "income_statement",
            "non_recurring_revenue": "income_statement",
            "usage_based_revenue": "income_statement",
            "adjusted_ebitda": "income_statement",
            "stock_based_compensation_expense": "income_statement",
            "restructuring_charges": "income_statement",
            "current_tax_expense": "income_statement",
            "deferred_tax_expense": "income_statement",
            "contribution_margin": "income_statement",
            "contract_assets": "balance_sheet",
            "contract_liabilities": "balance_sheet",
            "right_of_use_asset": "balance_sheet",
            "lease_liability_current": "balance_sheet",
            "lease_liability_non_current": "balance_sheet",
            "tax_loss_carryforward": "balance_sheet",
            "convertible_notes": "balance_sheet",
            "safe_notes": "balance_sheet",
            "change_in_contract_liabilities": "cash_flow",
            "proceeds_from_convertible_notes": "cash_flow",
            "change_in_deferred_revenue_cf": "cash_flow",
            "burn_rate": "metrics",
            "cash_runway_months": "metrics",
            "bookings": "metrics",
            "acv": "metrics",
            "customer_count": "metrics",
            "new_customers": "metrics",
            "churned_customers": "metrics",
            "headcount": "metrics",
            "revenue_per_employee": "metrics",
            "logo_churn_rate": "metrics",
            "revenue_churn_rate": "metrics",
            "monthly_burn": "metrics",
            "pipeline_value": "metrics",
        }
        for item in self.all_items:
            name = item["canonical_name"]
            if name in expected:
                assert item["category"] == expected[name], (
                    f"{name} should be in {expected[name]}, got {item['category']}"
                )


# ============================================================
# Mapping stage prompt generation tests
# ============================================================


class TestLoadTaxonomyForPrompt:
    """Test _load_taxonomy_for_prompt with alias inclusion."""

    def test_basic_loading(self):
        result = _load_taxonomy_for_prompt(include_aliases=False)
        assert "Income Statement" in result
        assert "Balance Sheet" in result
        assert "Cash Flow" in result
        assert "revenue" in result

    def test_with_aliases(self):
        result = _load_taxonomy_for_prompt(include_aliases=True)
        assert "Income Statement" in result
        # Should contain alias hints in parentheses
        assert "(" in result
        assert ")" in result

    def test_without_aliases_is_shorter(self):
        with_aliases = _load_taxonomy_for_prompt(include_aliases=True)
        without_aliases = _load_taxonomy_for_prompt(include_aliases=False)
        assert len(with_aliases) > len(without_aliases)

    def test_all_categories_in_output(self):
        result = _load_taxonomy_for_prompt()
        for category in [
            "Income Statement",
            "Balance Sheet",
            "Cash Flow",
            "Debt Schedule",
            "Metrics",
        ]:
            assert category in result, f"Missing category: {category}"


# ============================================================
# Accounting validator tests
# ============================================================


class TestAccountingValidator:
    """Test the AccountingValidator with cross-item validation rules."""

    @pytest.fixture
    def taxonomy_with_rules(self):
        """Taxonomy items with cross-item validation rules."""
        return [
            {
                "canonical_name": "revenue",
                "validation_rules": {
                    "cross_item_validation": {
                        "must_be_positive": True,
                        "relationships": [
                            {
                                "rule": "revenue >= gross_profit",
                                "error_message": "Revenue < gross profit",
                            },
                            {"rule": "revenue >= cogs", "error_message": "Revenue < COGS"},
                        ],
                    }
                },
            },
            {
                "canonical_name": "gross_profit",
                "validation_rules": {
                    "cross_item_validation": {
                        "relationships": [
                            {
                                "rule": "gross_profit == revenue - cogs",
                                "tolerance": 0.01,
                                "error_message": "GP != revenue - COGS",
                            }
                        ]
                    }
                },
            },
            {
                "canonical_name": "total_assets",
                "validation_rules": {
                    "cross_item_validation": {
                        "must_be_positive": True,
                        "relationships": [
                            {
                                "rule": "total_assets == total_liabilities + total_equity",
                                "tolerance": 0.01,
                                "error_message": "A != L + E",
                                "critical": True,
                            }
                        ],
                    }
                },
            },
        ]

    def test_valid_data_passes(self, taxonomy_with_rules):
        validator = AccountingValidator(taxonomy_with_rules)
        data = {
            "revenue": Decimal("1000000"),
            "cogs": Decimal("600000"),
            "gross_profit": Decimal("400000"),
        }
        results = validator.validate(data)
        assert results.success_rate == 1.0
        assert not results.has_errors

    def test_invalid_gross_profit_fails(self, taxonomy_with_rules):
        validator = AccountingValidator(taxonomy_with_rules)
        data = {
            "revenue": Decimal("1000000"),
            "cogs": Decimal("600000"),
            "gross_profit": Decimal("500000"),  # Wrong: should be 400000
        }
        results = validator.validate(data)
        assert results.has_errors
        error_messages = [e.message for e in results.errors]
        assert any("GP" in m for m in error_messages)

    def test_negative_revenue_fails(self, taxonomy_with_rules):
        validator = AccountingValidator(taxonomy_with_rules)
        data = {"revenue": Decimal("-100000")}
        results = validator.validate(data)
        assert results.has_errors

    def test_accounting_equation(self, taxonomy_with_rules):
        validator = AccountingValidator(taxonomy_with_rules)
        data = {
            "total_assets": Decimal("100000"),
            "total_liabilities": Decimal("60000"),
            "total_equity": Decimal("40000"),  # Correct: 100k = 60k + 40k
        }
        results = validator.validate(data)
        errors = [r for r in results.all_results if not r.passed and r.severity == "error"]
        assert len(errors) == 0

    def test_broken_accounting_equation(self, taxonomy_with_rules):
        validator = AccountingValidator(taxonomy_with_rules)
        data = {
            "total_assets": Decimal("100000"),
            "total_liabilities": Decimal("60000"),
            "total_equity": Decimal("50000"),  # Wrong: 100k != 60k + 50k
        }
        results = validator.validate(data)
        assert results.has_errors

    def test_missing_data_doesnt_fail(self, taxonomy_with_rules):
        """Items not in extracted data should be skipped, not fail."""
        validator = AccountingValidator(taxonomy_with_rules)
        data = {"revenue": Decimal("1000000")}  # Only revenue, no cogs or GP
        results = validator.validate(data)
        # Should pass for must_be_positive; relationship checks skip missing refs
        passed = [r for r in results.all_results if r.passed]
        assert len(passed) >= 1

    def test_tolerance_for_rounding(self, taxonomy_with_rules):
        validator = AccountingValidator(taxonomy_with_rules)
        data = {
            "revenue": Decimal("1000000"),
            "cogs": Decimal("600000"),
            "gross_profit": Decimal("400001"),  # Off by 1 (within 1% tolerance)
        }
        results = validator.validate(data)
        gp_results = [
            r for r in results.all_results if "GP" in r.message or "gross_profit" in r.rule
        ]
        # Within tolerance, should pass
        for r in gp_results:
            if "==" in r.rule:
                assert r.passed, f"Should pass within tolerance: {r.message}"

    def test_empty_data_returns_empty_results(self, taxonomy_with_rules):
        validator = AccountingValidator(taxonomy_with_rules)
        results = validator.validate({})
        assert results.total_checks == 0
        assert not results.has_errors

    def test_validation_summary_properties(self, taxonomy_with_rules):
        validator = AccountingValidator(taxonomy_with_rules)
        data = {
            "revenue": Decimal("1000000"),
            "cogs": Decimal("600000"),
            "gross_profit": Decimal("400000"),
        }
        results = validator.validate(data)
        assert isinstance(results, ValidationSummary)
        assert results.total_checks > 0
        assert results.passed >= 0
        assert results.failed >= 0
        assert 0.0 <= results.success_rate <= 1.0

    def test_arr_mrr_validation(self):
        """ARR should be approximately MRR * 12."""
        taxonomy = [
            {
                "canonical_name": "arr",
                "validation_rules": {
                    "cross_item_validation": {
                        "relationships": [
                            {
                                "rule": "arr == mrr * 12",
                                "tolerance": 0.05,
                                "optional": True,
                                "error_message": "ARR should be approximately MRR x 12",
                            }
                        ]
                    }
                },
            }
        ]
        validator = AccountingValidator(taxonomy)
        # Valid: 120000 == 10000 * 12
        data = {"arr": Decimal("120000"), "mrr": Decimal("10000")}
        results = validator.validate(data)
        assert not results.has_errors

        # Invalid: 150000 != 10000 * 12 (25% off, exceeds 5% tolerance)
        data_bad = {"arr": Decimal("150000"), "mrr": Decimal("10000")}
        results_bad = validator.validate(data_bad)
        arr_results = [r for r in results_bad.all_results if "arr" in r.rule]
        assert any(not r.passed for r in arr_results)

    def test_gross_retention_range_validation(self):
        """Gross retention must be between 0 and 1."""
        taxonomy = [
            {
                "canonical_name": "gross_retention",
                "validation_rules": {
                    "type": "percentage",
                    "cross_item_validation": {
                        "relationships": [
                            {
                                "rule": "0 <= gross_retention <= 1",
                                "error_message": "Gross retention must be between 0% and 100%",
                            }
                        ]
                    },
                },
            }
        ]
        validator = AccountingValidator(taxonomy)
        # Valid
        data = {"gross_retention": Decimal("0.85")}
        results = validator.validate(data)
        assert not results.has_errors

        # Invalid: 150 (percent-scale) normalizes to 1.5 which exceeds range 0-1
        data_bad = {"gross_retention": Decimal("150")}
        results_bad = validator.validate(data_bad)
        retention_results = [r for r in results_bad.all_results if "gross_retention" in r.rule]
        assert any(not r.passed for r in retention_results)


# ============================================================
# TaxonomyManager database integration tests
# ============================================================


class TestTaxonomyManagerEnhancements:
    """Test TaxonomyManager with enhanced taxonomy data in DB."""

    @pytest.fixture
    def enhanced_taxonomy(self, db_session):
        """Create taxonomy items with Phase 1-3 enhanced metadata."""
        items = [
            Taxonomy(
                id=uuid4(),
                canonical_name="revenue",
                category="income_statement",
                display_name="Revenue",
                aliases=["Sales", "Net Sales", "Turnover", "revenu", "reveneu"],
                definition="Total income from primary business activities",
                typical_sign="positive",
                parent_canonical=None,
                validation_rules={
                    "type": "currency",
                    "min_value": 0,
                    "ocr_variants": ["Rev enue", "REVENUE"],
                    "industry_tags": ["all", "saas", "retail"],
                    "confidence_scoring": {"high_confidence_signals": ["First line item in P&L"]},
                },
            ),
            Taxonomy(
                id=uuid4(),
                canonical_name="arr",
                category="metrics",
                display_name="Annual Recurring Revenue",
                aliases=["ARR", "Annualized Recurring Revenue"],
                definition="Annualized value of active recurring revenue contracts",
                typical_sign="positive",
                parent_canonical=None,
                validation_rules={
                    "type": "currency",
                    "min_value": 0,
                    "industry_tags": ["saas", "subscription"],
                },
            ),
            Taxonomy(
                id=uuid4(),
                canonical_name="noi",
                category="metrics",
                display_name="Net Operating Income",
                aliases=["NOI"],
                definition="Rental income minus operating expenses",
                typical_sign="positive",
                parent_canonical=None,
                validation_rules={
                    "type": "currency",
                    "industry_tags": ["real_estate"],
                },
            ),
        ]
        for item in items:
            db_session.add(item)
        db_session.commit()
        return items

    def test_search_finds_misspelling(self, db_session, enhanced_taxonomy):
        manager = TaxonomyManager()
        results = manager.search(db_session, "revenu")
        names = [r.canonical_name for r in results]
        assert "revenue" in names

    def test_search_finds_alias(self, db_session, enhanced_taxonomy):
        manager = TaxonomyManager()
        results = manager.search(db_session, "Turnover")
        names = [r.canonical_name for r in results]
        assert "revenue" in names

    def test_get_by_category_metrics(self, db_session, enhanced_taxonomy):
        manager = TaxonomyManager()
        results = manager.get_by_category(db_session, "metrics")
        names = {r.canonical_name for r in results}
        assert "arr" in names
        assert "noi" in names

    def test_validation_rules_stored_with_enhancements(self, db_session, enhanced_taxonomy):
        manager = TaxonomyManager()
        revenue = manager.get_by_canonical_name(db_session, "revenue")
        assert revenue is not None
        rules = revenue.validation_rules
        assert rules is not None
        assert "ocr_variants" in rules
        assert "industry_tags" in rules
        assert "confidence_scoring" in rules

    def test_format_for_prompt_includes_all_categories(self, db_session, enhanced_taxonomy):
        manager = TaxonomyManager()
        prompt = manager.format_for_prompt(db_session)
        assert "income_statement" in prompt.lower() or "revenue" in prompt
        assert "metrics" in prompt.lower() or "arr" in prompt
