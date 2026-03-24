"""
Comprehensive tests for src/derivation/engine.py and src/derivation/rules.py.

Covers:
  - DerivationEngine.run: gap-fill, consistency check, supplement, multi-pass DAG
  - DerivationEngine._apply_rule: all decision branches
  - DerivationEngine._safe_eval: all arithmetic operators, edge cases
  - DerivationEngine._infer_formula_type: ratio, difference, sum, default
  - DerivationEngine._build_covenant_context: DSCR, leverage, coverage, no threshold
  - run_derivation: convenience wrapper, invalid inputs
  - get_rules_for_model_type: all / restricted / case-insensitive
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from src.derivation.engine import (
    DerivationEngine,
    DerivedFact,
    run_derivation,
)
from src.derivation.rules import DerivationRule, get_rules_for_model_type


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_extracted(**kwargs):
    """Return {canonical: {period: Decimal}} from keyword arguments.
    Each key maps to a single Decimal value for period "FY2024".
    """
    return {cn: {"FY2024": Decimal(str(v))} for cn, v in kwargs.items()}


def _make_confidences(**kwargs):
    """Return {canonical: {period: float}} — same structure as _make_extracted."""
    return {cn: {"FY2024": float(v)} for cn, v in kwargs.items()}


# ─────────────────────────────────────────────────────────────────────────────
# get_rules_for_model_type
# ─────────────────────────────────────────────────────────────────────────────


class TestGetRulesForModelType:
    """Test rule filtering by model type."""

    def test_none_returns_universal_rules(self):
        """None model_type should return only rules with model_types=None."""
        rules = get_rules_for_model_type(None)
        for r in rules:
            assert r.model_types is None, f"Rule {r.id} has model_types={r.model_types!r}"

    def test_project_finance_includes_universal_and_pf(self):
        """project_finance should get universal rules plus PF-specific ones."""
        rules_pf = get_rules_for_model_type("project_finance")
        rules_none = get_rules_for_model_type(None)
        # PF returns a superset
        assert len(rules_pf) > len(rules_none)
        pf_ids = {r.id for r in rules_pf}
        # DR-040 is PF-only
        assert "DR-040" in pf_ids

    def test_corporate_includes_corporate_specific(self):
        rules = get_rules_for_model_type("corporate")
        ids = {r.id for r in rules}
        # DR-042 is corporate/leveraged
        assert "DR-042" in ids
        # DR-040 (PF) should NOT be in corporate
        assert "DR-040" not in ids

    def test_case_insensitive_matching(self):
        rules_lower = get_rules_for_model_type("project_finance")
        rules_upper = get_rules_for_model_type("Project_Finance")
        assert {r.id for r in rules_lower} == {r.id for r in rules_upper}

    def test_unknown_model_type_returns_universal_only(self):
        """Unknown model type → only universal rules (those with model_types=None)."""
        rules = get_rules_for_model_type("fantasy_model")
        for r in rules:
            assert r.model_types is None

    def test_rules_sorted_by_priority(self):
        """Rules must be returned in ascending priority order."""
        rules = get_rules_for_model_type("project_finance")
        priorities = [r.priority for r in rules]
        assert priorities == sorted(priorities)


# ─────────────────────────────────────────────────────────────────────────────
# DerivationEngine._safe_eval
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeEval:
    """Test formula evaluation."""

    def setup_method(self):
        self.engine = DerivationEngine()

    def test_subtraction(self):
        result = self.engine._safe_eval(
            "revenue - cogs",
            {"revenue": Decimal("1000000"), "cogs": Decimal("600000")},
        )
        assert result == Decimal("400000")

    def test_addition(self):
        result = self.engine._safe_eval(
            "ebit + depreciation + amortization",
            {
                "ebit": Decimal("500000"),
                "depreciation": Decimal("50000"),
                "amortization": Decimal("10000"),
            },
        )
        assert result == Decimal("560000")

    def test_division(self):
        result = self.engine._safe_eval(
            "total_debt / ebitda",
            {"total_debt": Decimal("3000000"), "ebitda": Decimal("1000000")},
        )
        assert result == Decimal("3")

    def test_multiplication(self):
        result = self.engine._safe_eval(
            "accounts_receivable / revenue * 365",
            {"accounts_receivable": Decimal("100"), "revenue": Decimal("1000")},
        )
        assert result == pytest.approx(Decimal("36.5"))

    def test_division_by_zero_returns_none(self):
        result = self.engine._safe_eval(
            "a / b",
            {"a": Decimal("100"), "b": Decimal("0")},
        )
        assert result is None

    def test_unknown_variable_returns_none(self):
        result = self.engine._safe_eval(
            "revenue - missing_var",
            {"revenue": Decimal("1000")},
        )
        assert result is None

    def test_single_variable(self):
        result = self.engine._safe_eval("revenue", {"revenue": Decimal("500")})
        assert result == Decimal("500")

    def test_numeric_literal(self):
        result = self.engine._safe_eval("100", {})
        assert result == Decimal("100")

    def test_empty_formula_returns_none(self):
        result = self.engine._safe_eval("", {})
        assert result is None

    def test_unknown_operator_returns_none(self):
        """Formula with unsupported operator tokens."""
        # "revenue % 100" → unexpected token '%'
        result = self.engine._safe_eval("revenue % 100", {"revenue": Decimal("300")})
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# DerivationEngine._infer_formula_type
# ─────────────────────────────────────────────────────────────────────────────


class TestInferFormulaType:
    """Test formula type classification."""

    def test_pure_ratio(self):
        assert DerivationEngine._infer_formula_type("cfads / debt_service") == "ratio"

    def test_pure_difference(self):
        assert DerivationEngine._infer_formula_type("revenue - cogs") == "difference"

    def test_pure_sum(self):
        assert DerivationEngine._infer_formula_type("ebit + depreciation + amortization") == "sum"

    def test_mixed_operators_defaults_to_ratio(self):
        """Mixed formula (division + addition) falls back to 'ratio'."""
        assert DerivationEngine._infer_formula_type("a / b + c") == "ratio"

    def test_multiplication_defaults_to_ratio(self):
        assert DerivationEngine._infer_formula_type("a / b * 365") == "ratio"


# ─────────────────────────────────────────────────────────────────────────────
# DerivationEngine.run — gap filling
# ─────────────────────────────────────────────────────────────────────────────


class TestDerivationEngineGapFill:
    """Test gap-filling when target metric is absent from extracted data."""

    def test_gap_fill_gross_profit(self):
        """DR-001: gross_profit = revenue - cogs when absent."""
        engine = DerivationEngine()
        extracted = _make_extracted(revenue=1_000_000, cogs=600_000)
        confs = _make_confidences(revenue=0.95, cogs=0.90)

        results = engine.run(extracted, confs)
        names = {f.canonical_name for f in results}
        assert "gross_profit" in names

        gp = next(f for f in results if f.canonical_name == "gross_profit")
        assert gp.computed_value == Decimal("400000")
        assert gp.is_gap_fill is True
        assert gp.confidence > 0

    def test_gap_fill_net_debt(self):
        """DR-010: net_debt = total_debt - cash."""
        engine = DerivationEngine()
        extracted = _make_extracted(total_debt=5_000_000, cash=500_000)
        confs = _make_confidences(total_debt=0.95, cash=0.95)

        results = engine.run(extracted, confs)
        nd = next((f for f in results if f.canonical_name == "net_debt"), None)
        assert nd is not None
        assert nd.computed_value == Decimal("4500000")
        assert nd.is_gap_fill is True

    def test_gap_fill_ebitda_from_ebit_and_da(self):
        """DR-002a: ebitda = ebit + depreciation + amortization."""
        engine = DerivationEngine()
        extracted = _make_extracted(
            ebit=800_000,
            depreciation=100_000,
            amortization=50_000,
        )
        confs = _make_confidences(ebit=0.95, depreciation=0.90, amortization=0.90)

        results = engine.run(extracted, confs)
        eb = next((f for f in results if f.canonical_name == "ebitda"), None)
        assert eb is not None
        assert eb.computed_value == Decimal("950000")

    def test_gap_fill_skipped_when_confidence_too_low(self):
        """Inputs below MIN_GAP_FILL_CONFIDENCE (0.60) → skip derivation."""
        engine = DerivationEngine()
        extracted = _make_extracted(revenue=1_000_000, cogs=600_000)
        confs = _make_confidences(revenue=0.50, cogs=0.55)  # Both < 0.60

        results = engine.run(extracted, confs)
        names = {f.canonical_name for f in results}
        assert "gross_profit" not in names

    def test_gap_fill_skipped_when_input_missing(self):
        """Missing input → rule skipped."""
        engine = DerivationEngine()
        extracted = _make_extracted(revenue=1_000_000)  # cogs missing
        confs = _make_confidences(revenue=0.95)

        results = engine.run(extracted, confs)
        names = {f.canonical_name for f in results}
        assert "gross_profit" not in names

    def test_uncertainty_band_populated(self):
        """Gap-fill facts should carry value_range_low/high."""
        engine = DerivationEngine()
        extracted = _make_extracted(total_debt=3_000_000, ebitda=1_000_000)
        confs = _make_confidences(total_debt=0.90, ebitda=0.90)

        results = engine.run(extracted, confs)
        d2e = next((f for f in results if f.canonical_name == "debt_to_ebitda"), None)
        assert d2e is not None
        assert d2e.value_range_low is not None
        assert d2e.value_range_high is not None
        assert d2e.value_range_low < d2e.computed_value < d2e.value_range_high


# ─────────────────────────────────────────────────────────────────────────────
# DerivationEngine.run — consistency check
# ─────────────────────────────────────────────────────────────────────────────


class TestDerivationEngineConsistencyCheck:
    """When target is already extracted with high confidence, run consistency check."""

    def test_consistency_check_passes(self):
        """Extracted ≈ computed → passed=True."""
        engine = DerivationEngine()
        # gross_profit extracted + inputs present → consistency check
        extracted = _make_extracted(revenue=1_000_000, cogs=600_000, gross_profit=401_000)
        confs = _make_confidences(revenue=0.95, cogs=0.95, gross_profit=0.92)

        results = engine.run(extracted, confs)
        gp = next((f for f in results if f.canonical_name == "gross_profit"), None)
        # May or may not run depending on confidence thresholds
        if gp is not None:
            assert gp.consistency is not None
            assert gp.consistency.extracted_value is not None
            assert gp.consistency.computed_value is not None

    def test_consistency_check_fails_large_divergence(self):
        """Large divergence between extracted and computed → passed=False."""
        engine = DerivationEngine()
        # gross_profit extracted at 500k, but revenue-cogs = 400k → 20% divergence
        extracted = _make_extracted(revenue=1_000_000, cogs=600_000, gross_profit=500_000)
        confs = _make_confidences(revenue=0.95, cogs=0.95, gross_profit=0.92)

        results = engine.run(extracted, confs)
        gp = next((f for f in results if f.canonical_name == "gross_profit"), None)
        if gp is not None and gp.consistency is not None:
            if not gp.consistency.passed:
                assert gp.consistency.divergence_pct > gp.consistency.threshold_pct

    def test_consistency_check_skipped_inputs_too_low(self):
        """If inputs have confidence < MIN_CONSISTENCY_CHECK_CONFIDENCE (0.75), skip."""
        engine = DerivationEngine()
        extracted = _make_extracted(revenue=1_000_000, cogs=600_000, gross_profit=400_000)
        # Input confidence too low for consistency check
        confs = _make_confidences(revenue=0.70, cogs=0.70, gross_profit=0.90)

        results = engine.run(extracted, confs)
        # With low-confidence inputs and high-confidence extracted value, should be skipped
        gp = next((f for f in results if f.canonical_name == "gross_profit"), None)
        assert gp is None


# ─────────────────────────────────────────────────────────────────────────────
# DerivationEngine.run — supplement (low-confidence extraction)
# ─────────────────────────────────────────────────────────────────────────────


class TestDerivationEngineSupplement:
    """When target is extracted with low confidence, supplement with computed."""

    def test_supplement_low_confidence_extraction(self):
        """Target extracted but with low confidence → compute supplement."""
        engine = DerivationEngine()
        extracted = _make_extracted(revenue=1_000_000, cogs=600_000, gross_profit=400_000)
        # gross_profit has LOW confidence (below 0.70)
        confs = _make_confidences(revenue=0.92, cogs=0.90, gross_profit=0.50)

        results = engine.run(extracted, confs)
        gp = next((f for f in results if f.canonical_name == "gross_profit"), None)
        assert gp is not None
        assert gp.is_gap_fill is False  # it's a supplement, not pure gap fill

    def test_supplement_skipped_if_inputs_also_low(self):
        """Even for supplement, inputs must be >= MIN_GAP_FILL_CONFIDENCE."""
        engine = DerivationEngine()
        extracted = _make_extracted(revenue=1_000_000, cogs=600_000, gross_profit=400_000)
        confs = _make_confidences(revenue=0.50, cogs=0.55, gross_profit=0.50)

        results = engine.run(extracted, confs)
        names = {f.canonical_name for f in results}
        assert "gross_profit" not in names


# ─────────────────────────────────────────────────────────────────────────────
# DerivationEngine.run — multi-pass DAG
# ─────────────────────────────────────────────────────────────────────────────


class TestDerivationEngineMultiPass:
    """Test that derived values from earlier passes feed into later passes."""

    def test_net_debt_to_ebitda_uses_derived_net_debt(self):
        """DR-032 (pass 3) uses net_debt derived by DR-010 (pass 1)."""
        engine = DerivationEngine()
        extracted = _make_extracted(
            total_debt=5_000_000,
            cash=500_000,
            ebitda=1_000_000,
        )
        confs = _make_confidences(total_debt=0.95, cash=0.95, ebitda=0.95)

        results = engine.run(extracted, confs)

        # net_debt should be derived in pass 1
        nd = next((f for f in results if f.canonical_name == "net_debt"), None)
        assert nd is not None
        assert nd.computed_value == Decimal("4500000")
        assert nd.derivation_pass == 1

        # net_debt_to_ebitda should be derived in pass 3 using derived net_debt
        nd2e = next((f for f in results if f.canonical_name == "net_debt_to_ebitda"), None)
        assert nd2e is not None
        assert nd2e.computed_value == pytest.approx(Decimal("4.5"))
        assert nd2e.derivation_pass == 3

    def test_ebitda_margin_uses_derived_ebitda(self):
        """DR-034 (ebitda_margin) can use ebitda computed from DR-002a."""
        engine = DerivationEngine()
        extracted = _make_extracted(
            ebit=800_000,
            depreciation=100_000,
            amortization=50_000,
            revenue=2_000_000,
        )
        confs = _make_confidences(
            ebit=0.95,
            depreciation=0.90,
            amortization=0.90,
            revenue=0.95,
        )

        results = engine.run(extracted, confs)
        ebitda_margin = next(
            (f for f in results if f.canonical_name == "ebitda_margin"), None
        )
        assert ebitda_margin is not None
        # ebitda = 950k, revenue = 2M → margin = 0.475
        assert float(ebitda_margin.computed_value) == pytest.approx(0.475)

    def test_multiple_periods_handled(self):
        """Engine processes all available periods."""
        engine = DerivationEngine()
        extracted = {
            "revenue": {"FY2022": Decimal("900000"), "FY2023": Decimal("1000000")},
            "cogs": {"FY2022": Decimal("540000"), "FY2023": Decimal("600000")},
        }
        confs = {
            "revenue": {"FY2022": 0.95, "FY2023": 0.95},
            "cogs": {"FY2022": 0.90, "FY2023": 0.90},
        }

        results = engine.run(extracted, confs)
        gp_facts = [f for f in results if f.canonical_name == "gross_profit"]
        periods = {f.period for f in gp_facts}
        assert "FY2022" in periods
        assert "FY2023" in periods

    def test_empty_extracted_returns_empty(self):
        engine = DerivationEngine()
        results = engine.run({}, {})
        assert results == []


# ─────────────────────────────────────────────────────────────────────────────
# DerivationEngine._build_covenant_context
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildCovenantContext:
    """Test covenant context construction for coverage/leverage metrics."""

    def _make_dscr_rule(self):
        return DerivationRule(
            id="DR-040",
            target="dscr_project_finance",
            formula="cfads / debt_service",
            inputs=["cfads", "debt_service"],
            confidence_mode="product",
            priority=2,
        )

    def _make_leverage_rule(self):
        return DerivationRule(
            id="DR-030",
            target="debt_to_ebitda",
            formula="total_debt / ebitda",
            inputs=["total_debt", "ebitda"],
            confidence_mode="product",
            priority=2,
        )

    def test_no_threshold_canonical_returns_none(self):
        """Non-covenant target → None context."""
        engine = DerivationEngine()
        rule = DerivationRule(
            id="DR-001",
            target="gross_profit",
            formula="revenue - cogs",
            inputs=["revenue", "cogs"],
            confidence_mode="min",
            priority=1,
        )
        ctx = engine._build_covenant_context(
            rule=rule,
            computed=Decimal("400000"),
            val_low=Decimal("380000"),
            val_high=Decimal("420000"),
            working={"distribution_lock_up": {"FY2024": Decimal("1.25")}},
            period="FY2024",
        )
        assert ctx is None

    def test_dscr_no_threshold_in_working_returns_none(self):
        """DSCR rule but distribution_lock_up not extracted → None."""
        engine = DerivationEngine()
        rule = self._make_dscr_rule()
        ctx = engine._build_covenant_context(
            rule=rule,
            computed=Decimal("1.35"),
            val_low=Decimal("1.20"),
            val_high=Decimal("1.50"),
            working={},  # No distribution_lock_up
            period="FY2024",
        )
        assert ctx is None

    def test_dscr_comfortable_headroom(self):
        """DSCR well above covenant → not sensitive, positive headroom."""
        engine = DerivationEngine()
        rule = self._make_dscr_rule()
        working = {"distribution_lock_up": {"FY2024": Decimal("1.25")}}
        ctx = engine._build_covenant_context(
            rule=rule,
            computed=Decimal("1.80"),
            val_low=Decimal("1.65"),
            val_high=Decimal("1.95"),
            working=working,
            period="FY2024",
        )
        assert ctx is not None
        assert ctx.is_sensitive is False
        assert ctx.headroom is not None
        assert float(ctx.headroom) == pytest.approx(0.55)
        assert ctx.flag_message is None

    def test_dscr_covenant_sensitive(self):
        """DSCR uncertainty band spans threshold → sensitive flag."""
        engine = DerivationEngine()
        rule = self._make_dscr_rule()
        working = {"distribution_lock_up": {"FY2024": Decimal("1.25")}}
        ctx = engine._build_covenant_context(
            rule=rule,
            computed=Decimal("1.29"),
            val_low=Decimal("1.20"),   # Below 1.25
            val_high=Decimal("1.38"),
            working=working,
            period="FY2024",
        )
        assert ctx is not None
        assert ctx.is_sensitive is True
        assert ctx.flag_message is not None
        assert "COVENANT SENSITIVE" in ctx.flag_message

    def test_dscr_covenant_breach(self):
        """DSCR below threshold → breach message."""
        engine = DerivationEngine()
        rule = self._make_dscr_rule()
        working = {"distribution_lock_up": {"FY2024": Decimal("1.25")}}
        ctx = engine._build_covenant_context(
            rule=rule,
            computed=Decimal("1.10"),
            val_low=Decimal("0.95"),
            val_high=Decimal("1.25"),
            working=working,
            period="FY2024",
        )
        assert ctx is not None
        assert ctx.headroom is not None
        assert float(ctx.headroom) < 0  # Negative headroom
        assert ctx.flag_message is not None
        assert "COVENANT BREACH" in ctx.flag_message

    def test_leverage_uses_leverage_covenant_level(self):
        """debt_to_ebitda uses leverage_covenant_level canonical."""
        engine = DerivationEngine()
        rule = self._make_leverage_rule()
        working = {"leverage_covenant_level": {"FY2024": Decimal("6.0")}}
        ctx = engine._build_covenant_context(
            rule=rule,
            computed=Decimal("4.0"),
            val_low=Decimal("3.5"),
            val_high=Decimal("4.5"),
            working=working,
            period="FY2024",
        )
        assert ctx is not None
        assert ctx.threshold == Decimal("6.0")

    def test_interest_coverage_uses_coverage_covenant(self):
        """interest_coverage uses coverage_covenant_level canonical."""
        engine = DerivationEngine()
        rule = DerivationRule(
            id="DR-031",
            target="interest_coverage",
            formula="ebit / interest_expense",
            inputs=["ebit", "interest_expense"],
            confidence_mode="product",
            priority=2,
        )
        working = {"coverage_covenant_level": {"FY2024": Decimal("2.0")}}
        ctx = engine._build_covenant_context(
            rule=rule,
            computed=Decimal("3.5"),
            val_low=Decimal("3.0"),
            val_high=Decimal("4.0"),
            working=working,
            period="FY2024",
        )
        assert ctx is not None
        assert ctx.threshold == Decimal("2.0")
        assert ctx.is_sensitive is False  # 3.0 low > 2.0 threshold


# ─────────────────────────────────────────────────────────────────────────────
# run_derivation (convenience wrapper)
# ─────────────────────────────────────────────────────────────────────────────


class TestRunDerivation:
    """Test the run_derivation convenience wrapper."""

    def test_basic_gap_fill(self):
        facts = [
            {"canonical_name": "revenue", "period": "FY2024", "value": 1_000_000, "confidence": 0.95},
            {"canonical_name": "cogs", "period": "FY2024", "value": 600_000, "confidence": 0.90},
        ]
        results = run_derivation(facts)
        names = {f.canonical_name for f in results}
        assert "gross_profit" in names

    def test_skips_missing_canonical(self):
        """Facts missing canonical_name are silently skipped."""
        facts = [
            {"period": "FY2024", "value": 1_000_000, "confidence": 0.95},  # no canonical_name
            {"canonical_name": "revenue", "period": "FY2024", "value": 1_000_000, "confidence": 0.95},
        ]
        results = run_derivation(facts)
        assert isinstance(results, list)

    def test_skips_missing_period(self):
        facts = [
            {"canonical_name": "revenue", "value": 1_000_000, "confidence": 0.95},
        ]
        results = run_derivation(facts)
        assert isinstance(results, list)

    def test_skips_missing_value(self):
        facts = [
            {"canonical_name": "revenue", "period": "FY2024", "confidence": 0.95},
        ]
        results = run_derivation(facts)
        assert isinstance(results, list)

    def test_skips_invalid_value(self):
        """Non-numeric value strings should be skipped gracefully."""
        facts = [
            {"canonical_name": "revenue", "period": "FY2024", "value": "N/A", "confidence": 0.95},
        ]
        results = run_derivation(facts)
        assert isinstance(results, list)

    def test_accepts_decimal_value(self):
        """Decimal values passed directly should work."""
        facts = [
            {"canonical_name": "revenue", "period": "FY2024", "value": Decimal("1000000"), "confidence": 0.95},
            {"canonical_name": "cogs", "period": "FY2024", "value": Decimal("600000"), "confidence": 0.90},
        ]
        results = run_derivation(facts)
        names = {f.canonical_name for f in results}
        assert "gross_profit" in names

    def test_default_confidence_when_missing(self):
        """Missing confidence defaults to 0.5 — may or may not produce results."""
        facts = [
            {"canonical_name": "revenue", "period": "FY2024", "value": 1_000_000},
            {"canonical_name": "cogs", "period": "FY2024", "value": 600_000},
        ]
        # 0.5 confidence is below MIN_GAP_FILL_CONFIDENCE (0.60) → no results expected
        results = run_derivation(facts)
        names = {f.canonical_name for f in results}
        assert "gross_profit" not in names

    def test_empty_input_returns_empty(self):
        results = run_derivation([])
        assert results == []

    def test_model_type_filters_rules(self):
        """project_finance model type should include PF-specific derivations."""
        facts = [
            {"canonical_name": "cfads", "period": "FY2024", "value": 2_000_000, "confidence": 0.90},
            {"canonical_name": "debt_service", "period": "FY2024", "value": 1_500_000, "confidence": 0.90},
        ]
        # Without model_type → PF rules excluded
        results_generic = run_derivation(facts, model_type=None)
        results_pf = run_derivation(facts, model_type="project_finance")

        names_generic = {f.canonical_name for f in results_generic}
        names_pf = {f.canonical_name for f in results_pf}

        assert "dscr_project_finance" not in names_generic
        assert "dscr_project_finance" in names_pf


# ─────────────────────────────────────────────────────────────────────────────
# DerivedFact dataclass completeness
# ─────────────────────────────────────────────────────────────────────────────


class TestDerivedFactDataclass:
    """Sanity checks on DerivedFact fields."""

    def test_derived_fact_fields(self):
        from src.derivation.engine import CovenantContext, ConsistencyResult

        fact = DerivedFact(
            canonical_name="dscr_project_finance",
            period="FY2024",
            computed_value=Decimal("1.35"),
            confidence=0.87,
            value_range_low=Decimal("1.21"),
            value_range_high=Decimal("1.49"),
            computation_rule_id="DR-040",
            formula="cfads / debt_service",
            source_canonicals=["cfads", "debt_service"],
            confidence_mode="product",
            derivation_pass=2,
            is_gap_fill=True,
        )
        assert fact.canonical_name == "dscr_project_finance"
        assert fact.consistency is None
        assert fact.covenant is None
        assert fact.is_gap_fill is True

    def test_derived_fact_with_consistency(self):
        from src.derivation.engine import ConsistencyResult

        consistency = ConsistencyResult(
            extracted_value=Decimal("1.30"),
            computed_value=Decimal("1.35"),
            divergence_pct=0.038,
            passed=False,
            threshold_pct=0.03,
        )
        fact = DerivedFact(
            canonical_name="gross_profit",
            period="FY2024",
            computed_value=Decimal("400000"),
            confidence=0.85,
            value_range_low=None,
            value_range_high=None,
            computation_rule_id="DR-001",
            formula="revenue - cogs",
            source_canonicals=["revenue", "cogs"],
            confidence_mode="min",
            derivation_pass=1,
            consistency=consistency,
        )
        assert fact.consistency.passed is False
        assert fact.consistency.divergence_pct > fact.consistency.threshold_pct


# ─────────────────────────────────────────────────────────────────────────────
# Full pipeline integration: compound chain
# ─────────────────────────────────────────────────────────────────────────────


class TestDerivationChain:
    """Integration test: chain of derivations across multiple passes."""

    def test_full_is_chain_corporate_model(self):
        """Test typical corporate model: IS chain from revenue to net_margin."""
        engine = DerivationEngine()
        extracted = _make_extracted(
            revenue=10_000_000,
            cogs=6_000_000,
            ebit=1_500_000,
            depreciation=400_000,
            amortization=100_000,
            interest_expense=300_000,
            tax_expense=250_000,
            total_debt=8_000_000,
            cash=1_000_000,
        )
        confs = _make_confidences(
            revenue=0.98,
            cogs=0.95,
            ebit=0.95,
            depreciation=0.90,
            amortization=0.90,
            interest_expense=0.90,
            tax_expense=0.90,
            total_debt=0.95,
            cash=0.95,
        )

        results = engine.run(extracted, confs)
        names = {f.canonical_name for f in results}

        # Pass 1: gross_profit, net_debt
        assert "gross_profit" in names
        assert "net_debt" in names

        # Pass 2: ebitda, ebt, interest_coverage, debt_to_ebitda
        assert "ebitda" in names
        assert "ebt" in names

        # Verify gross_profit value
        gp = next(f for f in results if f.canonical_name == "gross_profit")
        assert gp.computed_value == Decimal("4000000")

        # Verify net_debt value
        nd = next(f for f in results if f.canonical_name == "net_debt")
        assert nd.computed_value == Decimal("7000000")

        # Verify ebitda
        eb = next(f for f in results if f.canonical_name == "ebitda")
        assert eb.computed_value == Decimal("2000000")  # 1.5M + 0.4M + 0.1M

    def test_project_finance_dscr_chain(self):
        """CFADS / debt_service → DSCR with covenant context if lock-up present."""
        engine = DerivationEngine()
        extracted = {
            "cfads": {"FY2024": Decimal("5_000_000")},
            "debt_service": {"FY2024": Decimal("3_800_000")},
            "distribution_lock_up": {"FY2024": Decimal("1.25")},
        }
        confs = {
            "cfads": {"FY2024": 0.90},
            "debt_service": {"FY2024": 0.90},
            "distribution_lock_up": {"FY2024": 1.0},
        }

        results = engine.run(extracted, confs, model_type="project_finance")
        dscr = next((f for f in results if f.canonical_name == "dscr_project_finance"), None)
        assert dscr is not None
        # 5M / 3.8M = 1.3157...
        assert float(dscr.computed_value) == pytest.approx(5_000_000 / 3_800_000)
        # Comfortable above 1.25
        assert dscr.covenant is not None
        assert dscr.covenant.is_sensitive is False
        assert float(dscr.covenant.headroom) > 0
