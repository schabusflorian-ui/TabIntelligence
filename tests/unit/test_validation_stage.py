"""
Unit tests for Stage 4: Validation.

Tests the deterministic accounting checks and the stage's helper methods.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from src.extraction.stages.validation import ValidationStage, DERIVATION_RULES
from src.extraction.base import PipelineContext
from src.validation.accounting_validator import AccountingValidator


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
        gp_errors = [e for e in result.errors if "gross_profit" in e.rule.lower() or "gross" in e.message.lower()]
        assert len(gp_errors) > 0

    def test_balance_sheet_balances(self):
        """Should pass when A = L + E."""
        data = {
            "total_assets": Decimal("5000000"),
            "total_liabilities": Decimal("3000000"),
            "total_equity": Decimal("2000000"),
        }
        result = self.validator.validate(data)
        bs_errors = [e for e in result.errors if "balance" in e.message.lower() or "total_assets" in e.rule]
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
            "sheets": [{
                "sheet_name": "Income Statement",
                "rows": [
                    {"label": "Revenue", "values": {"FY2022": 100000, "FY2023": 115000}},
                    {"label": "Cost of Goods Sold", "values": {"FY2022": 40000, "FY2023": 46000}},
                ],
            }]
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
            "sheets": [{
                "sheet_name": "Income Statement",
                "rows": [
                    {"label": "Revenue", "values": {"FY2022": 100000}},
                    {"label": "Mystery Row", "values": {"FY2022": 50000}},
                ],
            }]
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
            "sheets": [{
                "sheet_name": "Income Statement",
                "rows": [
                    {"label": "Revenue", "values": {"FY2022": 100000, "FY2023": None}},
                ],
            }]
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
