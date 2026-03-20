"""
Unit tests for Stage 4: Validation.

Tests the deterministic accounting checks and the stage's helper methods.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.extraction.base import PipelineContext
from src.extraction.stages.validation import DERIVATION_RULES, ValidationStage
from src.validation.accounting_validator import AccountingValidator
from src.validation.lifecycle_detector import LifecycleDetector

# ============================================================================
# DERIVATION RULES TESTS
# ============================================================================


class TestDerivationRules:
    """Test that the built-in derivation rules are correct."""

    def test_rules_exist(self):
        """Verify all expected rules are defined."""
        rule_names = {r["canonical_name"] for r in DERIVATION_RULES}
        assert "gross_profit" in rule_names
        assert "total_assets" in rule_names
        assert "revenue" in rule_names
        assert "ebit" in rule_names
        assert "net_income" in rule_names
        assert "fcf" in rule_names

    def test_balance_sheet_rule_is_critical(self):
        """The BS balance check (A=L+E) should be a critical (non-optional) error."""
        bs_rule = next(r for r in DERIVATION_RULES if r["canonical_name"] == "total_assets")
        rels = bs_rule["validation_rules"]["cross_item_validation"]["relationships"]
        critical_rel = next(r for r in rels if r.get("critical"))
        assert critical_rel.get("critical") is True
        assert critical_rel.get("warning_only") is not True

    def test_revenue_must_be_positive(self):
        """Revenue rule should enforce positive values."""
        rev_rule = next(r for r in DERIVATION_RULES if r["canonical_name"] == "revenue")
        assert rev_rule["validation_rules"]["cross_item_validation"]["must_be_positive"] is True


# ============================================================================
# ACCOUNTING VALIDATOR INTEGRATION
# ============================================================================


class TestAccountingValidatorIntegration:
    """Test the AccountingValidator with the stage's derivation rules."""

    def setup_method(self):
        self.validator = AccountingValidator(DERIVATION_RULES)

    def test_valid_income_statement(self):
        """All checks should pass for consistent income statement data."""
        data = {
            "revenue": Decimal("1000000"),
            "cogs": Decimal("600000"),
            "gross_profit": Decimal("400000"),
        }
        result = self.validator.validate(data)
        assert result.passed > 0
        assert len(result.errors) == 0

    def test_invalid_gross_profit(self):
        """Should flag when gross_profit != revenue - cogs."""
        data = {
            "revenue": Decimal("1000000"),
            "cogs": Decimal("600000"),
            "gross_profit": Decimal("500000"),  # Wrong: should be 400000
        }
        result = self.validator.validate(data)
        # Should have at least one error about gross profit
        gp_errors = [
            e
            for e in result.errors
            if "gross_profit" in e.rule.lower() or "gross" in e.message.lower()
        ]
        assert len(gp_errors) > 0

    def test_balance_sheet_balances(self):
        """Should pass when A = L + E."""
        data = {
            "total_assets": Decimal("5000000"),
            "total_liabilities": Decimal("3000000"),
            "total_equity": Decimal("2000000"),
        }
        result = self.validator.validate(data)
        bs_errors = [
            e for e in result.errors if "balance" in e.message.lower() or "total_assets" in e.rule
        ]
        assert len(bs_errors) == 0

    def test_balance_sheet_imbalance(self):
        """Should flag when A != L + E."""
        data = {
            "total_assets": Decimal("5000000"),
            "total_liabilities": Decimal("3000000"),
            "total_equity": Decimal("1500000"),  # Wrong: 3M + 1.5M != 5M
        }
        result = self.validator.validate(data)
        bs_errors = [e for e in result.errors if "total_assets" in e.item_name]
        assert len(bs_errors) > 0

    def test_negative_revenue_flagged(self):
        """Revenue should be flagged if negative."""
        data = {
            "revenue": Decimal("-100000"),
        }
        result = self.validator.validate(data)
        rev_errors = [e for e in result.errors if e.item_name == "revenue"]
        assert len(rev_errors) > 0

    def test_tolerance_within_range(self):
        """Small deviations within tolerance should pass."""
        data = {
            "revenue": Decimal("1000000"),
            "cogs": Decimal("600000"),
            "gross_profit": Decimal("401000"),  # 0.25% off — within 2% tolerance
        }
        result = self.validator.validate(data)
        gp_errors = [e for e in result.errors if "gross_profit" in e.rule]
        assert len(gp_errors) == 0

    def test_missing_data_skipped(self):
        """Validation should gracefully skip when data is missing."""
        data = {
            "revenue": Decimal("1000000"),
            # No cogs or gross_profit
        }
        result = self.validator.validate(data)
        # Should not crash, should still check revenue positive
        assert result.total_checks >= 1

    def test_percentage_normalization(self):
        """Percentage values > 1 should be auto-normalized to decimal form."""
        taxonomy_items = [
            {
                "canonical_name": "gross_margin",
                "validation_rules": {
                    "type": "percentage",
                    "cross_item_validation": {
                        "relationships": [
                            {
                                "rule": "gross_margin == gross_profit / revenue",
                                "tolerance": 0.01,
                                "error_message": "Gross margin mismatch",
                            },
                        ]
                    },
                },
            },
            {"canonical_name": "gross_profit", "validation_rules": {}},
            {"canonical_name": "revenue", "validation_rules": {}},
        ]
        validator = AccountingValidator(taxonomy_items)
        data = {
            "gross_margin": Decimal("54.5"),  # 54.5% in percentage format
            "gross_profit": Decimal("545000"),
            "revenue": Decimal("1000000"),
        }
        result = validator.validate(data)
        # After normalization: gross_margin = 0.545, gross_profit/revenue = 0.545
        gm_errors = [e for e in result.errors if e.item_name == "gross_margin"]
        assert len(gm_errors) == 0, f"Unexpected errors: {[e.message for e in gm_errors]}"

    def test_percentage_normalization_skips_small_values(self):
        """Values <= 1.0 should NOT be normalized (already in decimal form)."""
        taxonomy_items = [
            {
                "canonical_name": "gross_margin",
                "validation_rules": {
                    "type": "percentage",
                    "cross_item_validation": {
                        "relationships": [
                            {
                                "rule": "gross_margin == gross_profit / revenue",
                                "tolerance": 0.01,
                                "error_message": "Gross margin mismatch",
                            },
                        ]
                    },
                },
            },
            {"canonical_name": "gross_profit", "validation_rules": {}},
            {"canonical_name": "revenue", "validation_rules": {}},
        ]
        validator = AccountingValidator(taxonomy_items)
        data = {
            "gross_margin": Decimal("0.545"),  # Already in decimal form
            "gross_profit": Decimal("545000"),
            "revenue": Decimal("1000000"),
        }
        result = validator.validate(data)
        gm_errors = [e for e in result.errors if e.item_name == "gross_margin"]
        assert len(gm_errors) == 0

    def test_range_check_rule_in_range(self):
        """Range check rule '0 <= x <= 1' should pass for in-range values."""
        taxonomy_items = [
            {
                "canonical_name": "test_metric",
                "validation_rules": {
                    "cross_item_validation": {
                        "relationships": [
                            {
                                "rule": "0 <= test_metric <= 1",
                                "error_message": "Must be between 0 and 1",
                            }
                        ]
                    }
                },
            }
        ]
        validator = AccountingValidator(taxonomy_items)
        result = validator.validate({"test_metric": Decimal("0.5")})
        assert len(result.errors) == 0

    def test_range_check_rule_out_of_range(self):
        """Range check rule '0 <= x <= 1' should fail for out-of-range values."""
        taxonomy_items = [
            {
                "canonical_name": "test_metric",
                "validation_rules": {
                    "cross_item_validation": {
                        "relationships": [
                            {
                                "rule": "0 <= test_metric <= 1",
                                "error_message": "Must be between 0 and 1",
                            }
                        ]
                    }
                },
            }
        ]
        validator = AccountingValidator(taxonomy_items)
        result = validator.validate({"test_metric": Decimal("1.5")})
        assert len(result.errors) > 0


# ============================================================================
# VALIDATION STAGE HELPER METHODS
# ============================================================================


class TestValidationStageHelpers:
    """Test the ValidationStage helper methods directly."""

    def setup_method(self):
        self.stage = ValidationStage()

    def test_build_extracted_values_basic(self):
        """Test building per-period value dicts from parsed data."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2022": 100000, "FY2023": 115000}},
                        {
                            "label": "Cost of Goods Sold",
                            "values": {"FY2022": 40000, "FY2023": 46000},
                        },
                    ],
                }
            ]
        }
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "Cost of Goods Sold", "canonical_name": "cogs", "confidence": 0.9},
        ]
        triage = [{"sheet_name": "Income Statement", "tier": 1}]

        result = self.stage._build_extracted_values(parsed, mappings, triage)

        assert "FY2022" in result
        assert "FY2023" in result
        assert result["FY2022"]["revenue"] == Decimal("100000")
        assert result["FY2022"]["cogs"] == Decimal("40000")
        assert result["FY2023"]["revenue"] == Decimal("115000")

    def test_build_extracted_values_skips_tier4(self):
        """Tier 4 sheets should be excluded from validation data."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "rows": [{"label": "Revenue", "values": {"FY2022": 100000}}],
                },
                {
                    "sheet_name": "Scratch",
                    "rows": [{"label": "Revenue", "values": {"FY2022": 999999}}],
                },
            ]
        }
        mappings = [{"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95}]
        triage = [
            {"sheet_name": "Income Statement", "tier": 1},
            {"sheet_name": "Scratch", "tier": 4},
        ]

        result = self.stage._build_extracted_values(parsed, mappings, triage)

        assert result["FY2022"]["revenue"] == Decimal("100000")  # From IS, not Scratch

    def test_build_extracted_values_skips_unmapped(self):
        """Unmapped items should be excluded."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2022": 100000}},
                        {"label": "Mystery Row", "values": {"FY2022": 50000}},
                    ],
                }
            ]
        }
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "Mystery Row", "canonical_name": "unmapped", "confidence": 0.3},
        ]
        triage = [{"sheet_name": "Income Statement", "tier": 1}]

        result = self.stage._build_extracted_values(parsed, mappings, triage)

        assert "revenue" in result["FY2022"]
        assert "unmapped" not in result["FY2022"]

    def test_build_extracted_values_handles_none(self):
        """None values should be skipped without crashing."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2022": 100000, "FY2023": None}},
                    ],
                }
            ]
        }
        mappings = [{"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95}]
        triage = [{"sheet_name": "Income Statement", "tier": 1}]

        result = self.stage._build_extracted_values(parsed, mappings, triage)

        assert "FY2022" in result
        assert result["FY2022"]["revenue"] == Decimal("100000")
        # FY2023 should either not exist or not have revenue
        assert "revenue" not in result.get("FY2023", {})

    def test_build_extracted_values_empty_sheets(self):
        """Should return empty dict for no processable data."""
        parsed = {"sheets": []}
        result = self.stage._build_extracted_values(parsed, [], [])
        assert result == {}


# ============================================================================
# LIFECYCLE-AWARE FLAG FILTERING
# ============================================================================


class TestLifecycleFiltering:
    """Test _filter_lifecycle_flags for project finance models."""

    def setup_method(self):
        self.stage = ValidationStage()
        self.detector = LifecycleDetector()

    def _detect(self, extracted):
        """Helper to compute LifecycleResult from extracted data."""
        return self.detector.detect(extracted)

    def test_filters_construction_phase_flags(self):
        """Zero revenue in construction periods (before ops) should be filtered out."""
        flags = [
            {"period": "1.0", "severity": "error", "item": "revenue", "rule": "must_be_positive"},
            {"period": "2.0", "severity": "error", "item": "revenue", "rule": "must_be_positive"},
            {"period": "3.0", "severity": "error", "item": "revenue", "rule": "must_be_positive"},
        ]
        extracted = {
            "1.0": {"revenue": Decimal("0"), "capex": Decimal("-15000000")},
            "2.0": {"revenue": Decimal("0"), "capex": Decimal("-39000000")},
            "3.0": {"revenue": Decimal("0"), "capex": Decimal("-27000000")},
            "4.0": {"revenue": Decimal("21000000")},
            "5.0": {"revenue": Decimal("22000000")},
        }
        result = self.stage._filter_lifecycle_flags(flags, self._detect(extracted))
        assert len(result) == 0, "Construction phase flags should be filtered out"

    def test_filters_post_operations_flags(self):
        """Zero revenue after operations end should be filtered out."""
        flags = [
            {"period": "24.0", "severity": "error", "item": "revenue", "rule": "must_be_positive"},
            {"period": "25.0", "severity": "error", "item": "revenue", "rule": "must_be_positive"},
        ]
        extracted = {
            "22.0": {"revenue": Decimal("30000000")},
            "23.0": {"revenue": Decimal("31000000")},
            "24.0": {"revenue": Decimal("0")},
            "25.0": {"revenue": Decimal("0")},
        }
        result = self.stage._filter_lifecycle_flags(flags, self._detect(extracted))
        assert len(result) == 0, "Post-operations flags should be filtered out"

    def test_keeps_mid_operations_flags(self):
        """Zero revenue within the operational window should NOT be filtered."""
        flags = [
            {"period": "10.0", "severity": "error", "item": "revenue", "rule": "must_be_positive"},
        ]
        extracted = {
            "4.0": {"revenue": Decimal("21000000")},
            "9.0": {"revenue": Decimal("25000000")},
            "10.0": {"revenue": Decimal("0")},
            "11.0": {"revenue": Decimal("26000000")},
            "23.0": {"revenue": Decimal("31000000")},
        }
        result = self.stage._filter_lifecycle_flags(flags, self._detect(extracted))
        assert len(result) == 1, "Mid-operations zero revenue should be kept"

    def test_construction_suppresses_all_must_be_positive(self):
        """Construction phase suppresses must_be_positive for ALL items, not just revenue."""
        flags = [
            {
                "period": "1.0",
                "severity": "error",
                "item": "gross_profit",
                "rule": "must_be_positive",
            },
            {"period": "1.0", "severity": "error", "item": "revenue", "rule": "must_be_positive"},
        ]
        extracted = {
            "1.0": {"revenue": Decimal("0"), "gross_profit": Decimal("0")},
            "4.0": {"revenue": Decimal("21000000")},
        }
        result = self.stage._filter_lifecycle_flags(flags, self._detect(extracted))
        # Both flags filtered — zero values during construction are expected
        assert len(result) == 0

    def test_keeps_non_must_be_positive_flags_in_construction(self):
        """Non-must_be_positive flags in construction should be kept."""
        flags = [
            {
                "period": "1.0",
                "severity": "error",
                "item": "gross_profit",
                "rule": "gross_profit == revenue - cogs",
            },
        ]
        extracted = {
            "1.0": {"revenue": Decimal("0"), "gross_profit": Decimal("0")},
            "4.0": {"revenue": Decimal("21000000")},
        }
        result = self.stage._filter_lifecycle_flags(flags, self._detect(extracted))
        # Non-must_be_positive rule should pass through
        assert len(result) == 1

    def test_no_revenue_data_returns_all_flags(self):
        """If no period has positive revenue, all flags are preserved."""
        flags = [
            {"period": "1.0", "severity": "error", "item": "revenue", "rule": "must_be_positive"},
        ]
        extracted = {
            "1.0": {"capex": Decimal("-15000000")},
        }
        result = self.stage._filter_lifecycle_flags(flags, self._detect(extracted))
        assert len(result) == 1

    def test_ramp_up_downgrades_errors_to_warnings(self):
        """Ramp-up phase should downgrade error severity to warning."""
        flags = [
            {
                "period": "2.0",
                "severity": "error",
                "item": "revenue",
                "rule": "must_be_positive",
                "message": "revenue must be positive",
            },
        ]
        extracted = {
            "1.0": {
                "revenue": Decimal("0"),
                "capex": Decimal("-10000000"),
                "cfads": Decimal("0"),
                "dscr": Decimal("0"),
            },
            "2.0": {
                "revenue": Decimal("3000000"),
                "cfads": Decimal("2000000"),
                "dscr": Decimal("1.1"),
            },
            "3.0": {
                "revenue": Decimal("20000000"),
                "cfads": Decimal("15000000"),
                "dscr": Decimal("1.5"),
            },
            "4.0": {
                "revenue": Decimal("20000000"),
                "cfads": Decimal("15000000"),
                "dscr": Decimal("1.5"),
            },
            "5.0": {
                "revenue": Decimal("20000000"),
                "cfads": Decimal("15000000"),
                "dscr": Decimal("1.5"),
            },
        }
        lifecycle = self._detect(extracted)
        assert lifecycle.phases["2.0"] == "ramp_up"
        result = self.stage._filter_lifecycle_flags(flags, lifecycle)
        assert len(result) == 1
        assert result[0]["severity"] == "warning"
        assert "[downgraded: ramp-up phase]" in result[0]["message"]

    def test_maintenance_shutdown_suppresses_revenue_must_be_positive(self):
        """Maintenance shutdown should suppress must_be_positive for revenue only."""
        flags = [
            {"period": "3.0", "severity": "error", "item": "revenue", "rule": "must_be_positive"},
            {
                "period": "3.0",
                "severity": "error",
                "item": "gross_profit",
                "rule": "must_be_positive",
            },
        ]
        extracted = {
            "1.0": {
                "revenue": Decimal("20000000"),
                "cfads": Decimal("15000000"),
                "dscr": Decimal("1.5"),
            },
            "2.0": {
                "revenue": Decimal("20000000"),
                "cfads": Decimal("15000000"),
                "dscr": Decimal("1.5"),
            },
            "3.0": {"revenue": Decimal("0"), "cfads": Decimal("0"), "dscr": Decimal("0")},
            "4.0": {
                "revenue": Decimal("20000000"),
                "cfads": Decimal("15000000"),
                "dscr": Decimal("1.5"),
            },
            "5.0": {
                "revenue": Decimal("20000000"),
                "cfads": Decimal("15000000"),
                "dscr": Decimal("1.5"),
            },
        }
        lifecycle = self._detect(extracted)
        assert lifecycle.phases["3.0"] == "maintenance_shutdown"
        result = self.stage._filter_lifecycle_flags(flags, lifecycle)
        # Revenue must_be_positive suppressed, gross_profit must_be_positive kept
        assert len(result) == 1
        assert result[0]["item"] == "gross_profit"


# ============================================================================
# CROSS-ITEM VALIDATION RULES (Income Statement & Project Finance)
# ============================================================================


class TestCrossItemValidation:
    """Test cross-item derivation rules for income statement and PF items."""

    def setup_method(self):
        self.validator = AccountingValidator(DERIVATION_RULES)

    def test_ebt_equals_ebit_minus_interest(self):
        """EBT should approximately equal EBIT - interest_expense."""
        data = {
            "ebit": Decimal("5000000"),
            "interest_expense": Decimal("500000"),
            "ebt": Decimal("4500000"),
        }
        result = self.validator.validate(data)
        ebt_errors = [e for e in result.errors if e.item_name == "ebt"]
        ebt_warnings = [w for w in result.warnings_list if w.item_name == "ebt"]
        assert len(ebt_errors) == 0, f"Unexpected EBT errors: {[e.message for e in ebt_errors]}"
        assert len(ebt_warnings) == 0, (
            f"Unexpected EBT warnings: {[w.message for w in ebt_warnings]}"
        )

    def test_ebt_exceeds_ebit_warns(self):
        """EBT > EBIT should generate a warning (interest expense is positive)."""
        data = {
            "ebit": Decimal("5000000"),
            "ebt": Decimal("6000000"),  # EBT shouldn't exceed EBIT
        }
        result = self.validator.validate(data)
        ebt_warnings = [w for w in result.warnings_list if w.item_name == "ebt"]
        assert len(ebt_warnings) > 0, "Should warn when EBT > EBIT"

    def test_net_income_equals_ebt_minus_taxes(self):
        """Net income should equal EBT - tax_expense."""
        data = {
            "ebt": Decimal("4500000"),
            "tax_expense": Decimal("1125000"),
            "net_income": Decimal("3375000"),
            "revenue": Decimal("10000000"),
        }
        result = self.validator.validate(data)
        ni_errors = [e for e in result.errors if e.item_name == "net_income" and "tax" in e.rule]
        assert len(ni_errors) == 0

    def test_cfads_greater_than_cfae(self):
        """CFADS should be >= CFAE (CFAE = CFADS after debt service)."""
        data = {
            "cfads": Decimal("8882610"),
            "cfae": Decimal("1315054"),
        }
        result = self.validator.validate(data)
        cfads_errors = [e for e in result.errors if e.item_name == "cfads"]
        cfads_warnings = [w for w in result.warnings_list if w.item_name == "cfads"]
        assert len(cfads_errors) == 0
        assert len(cfads_warnings) == 0

    def test_cfae_equals_cfads_plus_debt_service(self):
        """CFAE should equal CFADS + debt_service (debt_service is negative)."""
        data = {
            "cfads": Decimal("8882610"),
            "debt_service": Decimal("-7106088"),
            "cfae": Decimal("1776522"),  # cfads + debt_service
        }
        result = self.validator.validate(data)
        cfae_errors = [e for e in result.errors if e.item_name == "cfae"]
        cfae_warnings = [w for w in result.warnings_list if w.item_name == "cfae"]
        assert len(cfae_errors) == 0, f"Unexpected CFAE errors: {[e.message for e in cfae_errors]}"
        assert len(cfae_warnings) == 0, (
            f"Unexpected CFAE warnings: {[w.message for w in cfae_warnings]}"
        )

    def test_cfae_exceeds_cfads_warns(self):
        """CFAE should not exceed CFADS."""
        data = {
            "cfads": Decimal("5000000"),
            "cfae": Decimal("8000000"),  # CFAE > CFADS is suspicious
        }
        result = self.validator.validate(data)
        cfads_warnings = [
            w for w in result.warnings_list if w.item_name == "cfads" and "cfae" in w.rule
        ]
        assert len(cfads_warnings) > 0, "Should warn when CFAE > CFADS"

    def test_cfads_within_revenue(self):
        """CFADS should not exceed revenue."""
        data = {
            "cfads": Decimal("8882610"),
            "revenue": Decimal("21919251"),
        }
        result = self.validator.validate(data)
        cfads_warnings = [
            w for w in result.warnings_list if w.item_name == "cfads" and "revenue" in w.rule
        ]
        assert len(cfads_warnings) == 0

    def test_cfads_exceeds_revenue_warns(self):
        """CFADS > revenue is suspicious and should warn."""
        data = {
            "cfads": Decimal("25000000"),
            "revenue": Decimal("21000000"),
        }
        result = self.validator.validate(data)
        cfads_warnings = [
            w for w in result.warnings_list if w.item_name == "cfads" and "revenue" in w.rule
        ]
        assert len(cfads_warnings) > 0, "Should warn when CFADS > revenue"

    def test_debt_service_negative_passes(self):
        """Debt service should pass when negative (outflow)."""
        data = {
            "debt_service": Decimal("-7106088"),
        }
        result = self.validator.validate(data)
        ds_warnings = [w for w in result.warnings_list if w.item_name == "debt_service"]
        assert len(ds_warnings) == 0

    def test_debt_service_positive_warns(self):
        """Positive debt service (inflow) should warn — likely sign error."""
        data = {
            "debt_service": Decimal("7106088"),
        }
        result = self.validator.validate(data)
        ds_warnings = [w for w in result.warnings_list if w.item_name == "debt_service"]
        assert len(ds_warnings) > 0, "Should warn when debt service is positive"

    def test_dscr_in_range_passes(self):
        """DSCR within 1.0-10.0 should pass."""
        data = {
            "dscr": Decimal("1.5"),
        }
        result = self.validator.validate(data)
        dscr_warnings = [w for w in result.warnings_list if w.item_name == "dscr"]
        assert len(dscr_warnings) == 0

    def test_dscr_out_of_range_warns(self):
        """DSCR outside 1.0-10.0 should warn."""
        data = {
            "dscr": Decimal("15.0"),
        }
        result = self.validator.validate(data)
        dscr_warnings = [w for w in result.warnings_list if w.item_name == "dscr"]
        assert len(dscr_warnings) > 0, "Should warn when DSCR > 10.0"

    def test_full_project_finance_data_passes(self):
        """A complete set of consistent PF data should pass all checks."""
        data = {
            "revenue": Decimal("21919251"),
            "ebitda": Decimal("9540349"),
            "ebt": Decimal("2023813"),
            "net_income": Decimal("1366074"),
            "cfads": Decimal("8882610"),
            "debt_service": Decimal("-7106088"),
            "cfae": Decimal("1776522"),
        }
        result = self.validator.validate(data)
        # Should have no errors (warnings are acceptable for optional rules)
        assert len(result.errors) == 0, f"Unexpected errors: {[e.message for e in result.errors]}"


# ============================================================================
# STAGE PROPERTIES
# ============================================================================


class TestValidationStageProperties:
    """Test stage metadata."""

    def test_name(self):
        stage = ValidationStage()
        assert stage.name == "validation"

    def test_stage_number(self):
        stage = ValidationStage()
        assert stage.stage_number == 4


# ============================================================================
# FULL STAGE EXECUTION (with mocked Claude)
# ============================================================================


@pytest.mark.asyncio
async def test_validation_stage_execute_no_flags(mock_anthropic, sample_xlsx):
    """Validation stage should work with consistent data (no flags = no Claude call)."""
    from src.extraction.orchestrator import extract

    result = await extract(sample_xlsx, file_id="test-val-1")

    # The validation key should be present in the result
    assert "validation" in result
    validation = result["validation"]
    if validation:
        assert "flags" in validation
        assert "overall_confidence" in validation
        assert isinstance(validation["overall_confidence"], float)


@pytest.mark.asyncio
async def test_validation_stage_included_in_pipeline(mock_anthropic, sample_xlsx):
    """Validation stage should run as part of the full pipeline."""
    from src.extraction.orchestrator import extract

    result = await extract(sample_xlsx, file_id="test-val-2")

    # Result should have all expected keys
    assert "file_id" in result
    assert "sheets" in result
    assert "triage" in result
    assert "line_items" in result
    assert "tokens_used" in result
    assert "validation" in result


# ============================================================================
# UNIT MULTIPLIER TESTS
# ============================================================================


class TestUnitMultiplier:
    """Test that _build_extracted_values applies unit_multiplier from structured data."""

    def setup_method(self):
        self.stage = ValidationStage()

    def test_unit_multiplier_applied(self):
        """Sheet 'in millions' with revenue=500 → Decimal(500_000_000)."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2022": 500}},
                    ],
                }
            ]
        }
        mappings = [{"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95}]
        triage = [{"sheet_name": "Income Statement", "tier": 1}]
        structured = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "unit_multiplier": 1_000_000,
                }
            ]
        }

        result = self.stage._build_extracted_values(parsed, mappings, triage, structured)

        assert result["FY2022"]["revenue"] == Decimal("500000000")

    def test_no_multiplier_passthrough(self):
        """unit_multiplier=None → values unchanged."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2022": 500}},
                    ],
                }
            ]
        }
        mappings = [{"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95}]
        triage = [{"sheet_name": "Income Statement", "tier": 1}]
        structured = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "unit_multiplier": None,
                }
            ]
        }

        result = self.stage._build_extracted_values(parsed, mappings, triage, structured)

        assert result["FY2022"]["revenue"] == Decimal("500")

    def test_multiplier_of_1_passthrough(self):
        """unit_multiplier=1 → values unchanged (no scaling)."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2022": 500}},
                    ],
                }
            ]
        }
        mappings = [{"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95}]
        triage = [{"sheet_name": "Income Statement", "tier": 1}]
        structured = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "unit_multiplier": 1.0,
                }
            ]
        }

        result = self.stage._build_extracted_values(parsed, mappings, triage, structured)

        assert result["FY2022"]["revenue"] == Decimal("500")

    def test_cross_sheet_normalization(self):
        """Two sheets with different units → both normalised to absolute units."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "Summary",
                    "rows": [{"label": "Revenue", "values": {"FY2022": 500}}],
                },
                {
                    "sheet_name": "Detail",
                    "rows": [{"label": "COGS", "values": {"FY2022": 30}}],
                },
            ]
        }
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "COGS", "canonical_name": "cogs", "confidence": 0.9},
        ]
        triage = [
            {"sheet_name": "Summary", "tier": 1},
            {"sheet_name": "Detail", "tier": 2},
        ]
        structured = {
            "sheets": [
                {"sheet_name": "Summary", "unit_multiplier": 1_000_000},
                {"sheet_name": "Detail", "unit_multiplier": 1_000},
            ]
        }

        result = self.stage._build_extracted_values(parsed, mappings, triage, structured)

        # Summary: 500 * 1M = 500,000,000
        assert result["FY2022"]["revenue"] == Decimal("500000000")
        # Detail: 30 * 1K = 30,000
        assert result["FY2022"]["cogs"] == Decimal("30000")

    def test_backward_compat_no_structured(self):
        """structured=None → no crash, values unchanged."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "Income Statement",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2022": 500}},
                    ],
                }
            ]
        }
        mappings = [{"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95}]
        triage = [{"sheet_name": "Income Statement", "tier": 1}]

        result = self.stage._build_extracted_values(parsed, mappings, triage)

        assert result["FY2022"]["revenue"] == Decimal("500")

    def test_thousands_multiplier(self):
        """Sheet 'in thousands' with revenue=500 → Decimal(500_000)."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2022": 500}},
                    ],
                }
            ]
        }
        mappings = [{"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95}]
        triage = [{"sheet_name": "IS", "tier": 1}]
        structured = {"sheets": [{"sheet_name": "IS", "unit_multiplier": 1000}]}

        result = self.stage._build_extracted_values(parsed, mappings, triage, structured)

        assert result["FY2022"]["revenue"] == Decimal("500000")

    def test_unit_normalization_provenance(self):
        """_unit_normalization dict tracks which sheets had multipliers."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2022": 500}},
                    ],
                }
            ]
        }
        mappings = [{"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95}]
        triage = [{"sheet_name": "IS", "tier": 1}]
        structured = {"sheets": [{"sheet_name": "IS", "unit_multiplier": 1000}]}

        self.stage._build_extracted_values(parsed, mappings, triage, structured)

        assert "IS" in self.stage._unit_normalization
        assert self.stage._unit_normalization["IS"] == "1000"


# ============================================================================
# MODEL TYPE DETECTION (WS-E)
# ============================================================================


class TestModelTypeDetection:
    """Test that model_type flows from CompletenessScorer to QualityScorer."""

    def setup_method(self):
        self.stage = ValidationStage()

    def _make_context(self, stage_results=None):
        ctx = MagicMock(spec=PipelineContext)
        ctx.stage_results = stage_results or {}
        ctx.job_id = "test-job"
        return ctx

    def _make_extracted_values(self, canonical_names, periods=None):
        """Build a minimal extracted_values dict from canonical names."""
        periods = periods or ["FY2022"]
        return {period: {name: Decimal("100") for name in canonical_names} for period in periods}

    @pytest.mark.asyncio
    async def test_corporate_model_type_detected(self):
        """Corporate items → model_type='corporate' passed to QualityScorer."""
        corporate_items = {"revenue", "cogs", "gross_profit", "net_income", "total_assets"}
        extracted = self._make_extracted_values(corporate_items)

        ctx = self._make_context(
            {
                "stage_1": {"structured": None},
                "stage_2": {"triage": [{"sheet_name": "IS", "tier": 1}]},
                "stage_3": {
                    "mappings": [
                        {"original_label": n, "canonical_name": n, "confidence": 0.9}
                        for n in corporate_items
                    ]
                },
            }
        )

        with (
            patch.object(self.stage, "_build_extracted_values", return_value=extracted),
            patch.object(self.stage, "_get_claude_reasoning", return_value=({}, 0, 0, 0)),
            patch("src.extraction.stages.validation.QualityScorer") as MockQS,
        ):
            MockQS.return_value.score.return_value = MagicMock(
                numeric_score=0.85, to_dict=lambda: {"numeric_score": 0.85}
            )
            await self.stage.execute(ctx)

            MockQS.assert_called_with(model_type="corporate")

    @pytest.mark.asyncio
    async def test_pf_model_type_detected(self):
        """Project finance items → model_type='project_finance'."""
        pf_items = {"cfads", "dscr", "debt_service", "revenue", "total_assets"}
        extracted = self._make_extracted_values(pf_items)

        ctx = self._make_context(
            {
                "stage_1": {"structured": None},
                "stage_2": {"triage": [{"sheet_name": "PF", "tier": 1}]},
                "stage_3": {
                    "mappings": [
                        {"original_label": n, "canonical_name": n, "confidence": 0.9}
                        for n in pf_items
                    ]
                },
            }
        )

        with (
            patch.object(self.stage, "_build_extracted_values", return_value=extracted),
            patch.object(self.stage, "_get_claude_reasoning", return_value=({}, 0, 0, 0)),
            patch("src.extraction.stages.validation.QualityScorer") as MockQS,
        ):
            MockQS.return_value.score.return_value = MagicMock(
                numeric_score=0.85, to_dict=lambda: {"numeric_score": 0.85}
            )
            await self.stage.execute(ctx)

            MockQS.assert_called_with(model_type="project_finance")

    @pytest.mark.asyncio
    async def test_model_type_in_completeness_output(self):
        """model_type appears in the completeness section of the result."""
        items = {"revenue", "cogs", "gross_profit"}
        extracted = self._make_extracted_values(items)

        ctx = self._make_context(
            {
                "stage_1": {"structured": None},
                "stage_2": {"triage": [{"sheet_name": "IS", "tier": 1}]},
                "stage_3": {
                    "mappings": [
                        {"original_label": n, "canonical_name": n, "confidence": 0.9} for n in items
                    ]
                },
            }
        )

        with (
            patch.object(self.stage, "_build_extracted_values", return_value=extracted),
            patch.object(self.stage, "_get_claude_reasoning", return_value=({}, 0, 0, 0)),
        ):
            result = await self.stage.execute(ctx)

            completeness = result["validation"]["completeness"]
            assert "model_type" in completeness
            assert completeness["model_type"] == "corporate"

    @pytest.mark.asyncio
    async def test_model_type_none_on_completeness_failure(self):
        """When completeness scoring fails, model_type=None and QualityScorer still works."""
        extracted = self._make_extracted_values({"revenue"})

        ctx = self._make_context(
            {
                "stage_1": {"structured": None},
                "stage_2": {"triage": [{"sheet_name": "IS", "tier": 1}]},
                "stage_3": {
                    "mappings": [
                        {
                            "original_label": "revenue",
                            "canonical_name": "revenue",
                            "confidence": 0.9,
                        }
                    ]
                },
            }
        )

        with (
            patch.object(self.stage, "_build_extracted_values", return_value=extracted),
            patch.object(self.stage, "_get_claude_reasoning", return_value=({}, 0, 0, 0)),
            patch(
                "src.extraction.stages.validation.CompletenessScorer", side_effect=Exception("boom")
            ),
            patch("src.extraction.stages.validation.QualityScorer") as MockQS,
        ):
            MockQS.return_value.score.return_value = MagicMock(
                numeric_score=0.0, to_dict=lambda: {"numeric_score": 0.0}
            )
            await self.stage.execute(ctx)

            # model_type should be None since completeness failed
            MockQS.assert_called_with(model_type=None)


# ============================================================================
# EDGE CASE: First-write-wins for duplicate canonicals
# ============================================================================


class TestFirstWriteWins:
    """Test that duplicate canonical names across sheets keep the first value."""

    def setup_method(self):
        self.stage = ValidationStage()

    def test_build_extracted_values_first_write_wins(self):
        """When same canonical appears on two sheets, first sheet's value is kept."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2023": "1000"}},
                    ],
                },
                {
                    "sheet_name": "Summary",
                    "rows": [
                        {"label": "Total Revenue", "values": {"FY2023": "9999"}},
                    ],
                },
            ],
        }
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.9},
            {"original_label": "Total Revenue", "canonical_name": "revenue", "confidence": 0.8},
        ]
        triage = [
            {"sheet_name": "IS", "tier": 1},
            {"sheet_name": "Summary", "tier": 2},
        ]

        result = self.stage._build_extracted_values(parsed, mappings, triage)
        # First value (1000 from IS) should be kept, not 9999 from Summary
        from decimal import Decimal

        assert result["FY2023"]["revenue"] == Decimal("1000")

    def test_first_write_wins_records_conflict(self):
        """Duplicate with different values is recorded as a conflict."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2023": "1000"}},
                    ],
                },
                {
                    "sheet_name": "Summary",
                    "rows": [
                        {"label": "Total Revenue", "values": {"FY2023": "9999"}},
                    ],
                },
            ],
        }
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.9},
            {"original_label": "Total Revenue", "canonical_name": "revenue", "confidence": 0.8},
        ]
        triage = [
            {"sheet_name": "IS", "tier": 1},
            {"sheet_name": "Summary", "tier": 2},
        ]

        self.stage._build_extracted_values(parsed, mappings, triage)
        conflicts = self.stage._duplicate_conflicts

        assert len(conflicts) == 1
        assert conflicts[0]["canonical_name"] == "revenue"
        assert conflicts[0]["is_conflict"] is True
        assert len(conflicts[0]["values"]) == 2


class TestDuplicateConflictDetection:
    """Test conflict detection and resolution in _build_extracted_values."""

    def setup_method(self):
        self.stage = ValidationStage()

    def test_agreeing_duplicates_no_conflict(self):
        """Two sheets with same value for same canonical → not a conflict."""
        from decimal import Decimal

        parsed = {
            "sheets": [
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2023": "1000"}},
                    ],
                },
                {
                    "sheet_name": "Summary",
                    "rows": [
                        {"label": "Total Revenue", "values": {"FY2023": "1000"}},
                    ],
                },
            ],
        }
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.9},
            {"original_label": "Total Revenue", "canonical_name": "revenue", "confidence": 0.8},
        ]
        triage = [
            {"sheet_name": "IS", "tier": 1},
            {"sheet_name": "Summary", "tier": 2},
        ]

        result = self.stage._build_extracted_values(parsed, mappings, triage)

        assert result["FY2023"]["revenue"] == Decimal("1000")
        conflicts = self.stage._duplicate_conflicts
        assert len(conflicts) == 1
        assert conflicts[0]["is_conflict"] is False

    def test_conflicting_duplicates_keeps_best_tier(self):
        """When values disagree, the highest-tier sheet's value is used."""
        from decimal import Decimal

        parsed = {
            "sheets": [
                {
                    "sheet_name": "Summary",
                    "rows": [
                        {"label": "Total Revenue", "values": {"FY2023": "9999"}},
                    ],
                },
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2023": "1000"}},
                    ],
                },
            ],
        }
        mappings = [
            {"original_label": "Total Revenue", "canonical_name": "revenue", "confidence": 0.8},
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.9},
        ]
        triage = [
            {"sheet_name": "Summary", "tier": 2},
            {"sheet_name": "IS", "tier": 1},
        ]

        result = self.stage._build_extracted_values(parsed, mappings, triage)

        # Tier 1 (IS) should win even though Summary was processed first
        assert result["FY2023"]["revenue"] == Decimal("1000")
        conflicts = self.stage._duplicate_conflicts
        assert len(conflicts) == 1
        assert conflicts[0]["is_conflict"] is True
        assert conflicts[0]["chosen_sheet"] == "IS"

    def test_no_duplicates_empty_list(self):
        """No duplicates → no conflicts recorded."""
        parsed = {
            "sheets": [
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2023": "1000"}},
                        {"label": "COGS", "values": {"FY2023": "500"}},
                    ],
                },
            ],
        }
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.9},
            {"original_label": "COGS", "canonical_name": "cogs", "confidence": 0.85},
        ]
        triage = [{"sheet_name": "IS", "tier": 1}]

        self.stage._build_extracted_values(parsed, mappings, triage)

        assert len(self.stage._duplicate_conflicts) == 0

    def test_within_tolerance_not_conflict(self):
        """Values differing by less than 0.01 are not conflicts."""
        from decimal import Decimal

        parsed = {
            "sheets": [
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2023": "1000.004"}},
                    ],
                },
                {
                    "sheet_name": "Summary",
                    "rows": [
                        {"label": "Total Revenue", "values": {"FY2023": "1000.000"}},
                    ],
                },
            ],
        }
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.9},
            {"original_label": "Total Revenue", "canonical_name": "revenue", "confidence": 0.8},
        ]
        triage = [
            {"sheet_name": "IS", "tier": 1},
            {"sheet_name": "Summary", "tier": 2},
        ]

        result = self.stage._build_extracted_values(parsed, mappings, triage)

        assert result["FY2023"]["revenue"] == Decimal("1000.004")
        assert self.stage._duplicate_conflicts[0]["is_conflict"] is False

    def test_large_values_within_relative_tolerance_not_conflict(self):
        """Large values where absolute diff > 0.01 but relative diff < 0.1%
        should NOT be a conflict."""

        parsed = {
            "sheets": [
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2023": "1000000.5"}},
                    ],
                },
                {
                    "sheet_name": "Summary",
                    "rows": [
                        {"label": "Total Revenue", "values": {"FY2023": "1000000.0"}},
                    ],
                },
            ],
        }
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.9},
            {"original_label": "Total Revenue", "canonical_name": "revenue", "confidence": 0.8},
        ]
        triage = [
            {"sheet_name": "IS", "tier": 1},
            {"sheet_name": "Summary", "tier": 2},
        ]

        self.stage._build_extracted_values(parsed, mappings, triage)

        # Absolute diff = 0.5 > 0.01, but relative diff = 0.00005% < 0.1%
        assert self.stage._duplicate_conflicts[0]["is_conflict"] is False

    def test_small_values_relative_tolerance_catches_conflict(self):
        """Small values where both absolute AND relative tolerance are exceeded
        should be a conflict."""

        parsed = {
            "sheets": [
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Ratio", "values": {"FY2023": "0.10"}},
                    ],
                },
                {
                    "sheet_name": "Summary",
                    "rows": [
                        {"label": "Ratio", "values": {"FY2023": "0.20"}},
                    ],
                },
            ],
        }
        mappings = [
            {"original_label": "Ratio", "canonical_name": "ratio", "confidence": 0.9},
        ]
        triage = [
            {"sheet_name": "IS", "tier": 1},
            {"sheet_name": "Summary", "tier": 2},
        ]

        self.stage._build_extracted_values(parsed, mappings, triage)

        # Absolute diff = 0.10 > 0.01, relative diff = 100% > 0.1%
        assert self.stage._duplicate_conflicts[0]["is_conflict"] is True
