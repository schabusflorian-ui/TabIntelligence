"""Tests for sign convention enforcement in AccountingValidator."""

from decimal import Decimal

from src.validation.accounting_validator import AccountingValidator


D = Decimal


def _make_taxonomy_with_signs():
    """Taxonomy items with typical_sign for sign convention tests."""
    return [
        {"canonical_name": "revenue", "typical_sign": "positive",
         "validation_rules": {}},
        {"canonical_name": "cogs", "typical_sign": "negative",
         "validation_rules": {}},
        {"canonical_name": "net_income", "typical_sign": "varies",
         "validation_rules": {}},
        {"canonical_name": "total_assets", "typical_sign": "positive",
         "validation_rules": {}},
        {"canonical_name": "capex", "typical_sign": "negative",
         "validation_rules": {}},
        {"canonical_name": "depreciation", "typical_sign": "negative",
         "validation_rules": {}},
    ]


class TestSignConvention:
    """Test validate_sign_conventions method."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy_with_signs())

    def test_positive_revenue_passes(self):
        data = {"revenue": D("1000000")}
        results = self.validator.validate_sign_conventions(data)
        rev_results = [r for r in results if r.item_name == "revenue"]
        assert len(rev_results) == 1
        assert rev_results[0].passed is True

    def test_negative_revenue_warns(self):
        data = {"revenue": D("-1000000")}
        results = self.validator.validate_sign_conventions(data)
        rev_results = [r for r in results if r.item_name == "revenue"]
        assert len(rev_results) == 1
        assert rev_results[0].passed is False
        assert rev_results[0].severity == "warning"
        assert "negative" in rev_results[0].message

    def test_negative_cogs_passes(self):
        """Negative value for a 'negative' typical_sign item is correct."""
        data = {"cogs": D("-600000")}
        results = self.validator.validate_sign_conventions(data)
        cogs_results = [r for r in results if r.item_name == "cogs"]
        assert len(cogs_results) == 1
        assert cogs_results[0].passed is True

    def test_positive_cogs_warns(self):
        """Positive value for a 'negative' typical_sign item triggers warning."""
        data = {"cogs": D("600000")}
        results = self.validator.validate_sign_conventions(data)
        cogs_results = [r for r in results if r.item_name == "cogs"]
        assert len(cogs_results) == 1
        assert cogs_results[0].passed is False
        assert cogs_results[0].severity == "warning"
        assert "positive" in cogs_results[0].message

    def test_varies_item_skipped(self):
        """Items with typical_sign='varies' should not generate results."""
        data = {"net_income": D("-500000")}
        results = self.validator.validate_sign_conventions(data)
        ni_results = [r for r in results if r.item_name == "net_income"]
        assert len(ni_results) == 0

    def test_zero_value_skipped(self):
        """Zero values should not generate sign convention results."""
        data = {"revenue": D("0")}
        results = self.validator.validate_sign_conventions(data)
        rev_results = [r for r in results if r.item_name == "revenue"]
        assert len(rev_results) == 0

    def test_missing_taxonomy_entry_skipped(self):
        """Items not in taxonomy should not generate results."""
        data = {"unknown_item": D("-100")}
        results = self.validator.validate_sign_conventions(data)
        assert len(results) == 0

    def test_all_items_correct_sign_passes(self):
        """All items with correct signs should all pass."""
        data = {
            "revenue": D("1000000"),
            "cogs": D("-600000"),
            "total_assets": D("5000000"),
            "capex": D("-200000"),
            "depreciation": D("-100000"),
        }
        results = self.validator.validate_sign_conventions(data)
        assert all(r.passed for r in results)
        assert len(results) == 5  # one per non-varies item

    def test_multiple_violations(self):
        """Multiple sign violations should each generate a warning."""
        data = {
            "revenue": D("-1000000"),  # wrong
            "cogs": D("600000"),       # wrong
            "capex": D("200000"),      # wrong
        }
        results = self.validator.validate_sign_conventions(data)
        violations = [r for r in results if not r.passed]
        assert len(violations) == 3
        assert all(v.severity == "warning" for v in violations)


class TestSignConventionSeverity:
    """Verify sign convention checks are always warnings, never errors."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy_with_signs())

    def test_sign_violations_are_warnings_not_errors(self):
        data = {"revenue": D("-1000000"), "total_assets": D("-5000000")}
        results = self.validator.validate_sign_conventions(data)
        for r in results:
            if not r.passed:
                assert r.severity == "warning"
                assert r.rule == "sign_convention"
