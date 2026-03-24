"""Tests for cross-statement validation in AccountingValidator."""

from decimal import Decimal

from src.validation.accounting_validator import AccountingValidator

D = Decimal


def _make_taxonomy():
    """Minimal taxonomy for cross-statement tests."""
    return [
        {"canonical_name": "cash", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "ending_cash", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "beginning_cash", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "net_change_cash", "typical_sign": "varies", "validation_rules": {}},
        {"canonical_name": "retained_earnings", "typical_sign": "varies", "validation_rules": {}},
        {"canonical_name": "net_income", "typical_sign": "varies", "validation_rules": {}},
        {"canonical_name": "net_income_cf", "typical_sign": "varies", "validation_rules": {}},
        {"canonical_name": "total_debt", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "long_term_debt", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "short_term_debt", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "senior_debt", "typical_sign": "positive", "validation_rules": {}},
        {
            "canonical_name": "depreciation_and_amortization",
            "typical_sign": "negative",
            "validation_rules": {},
        },
        {"canonical_name": "depreciation_cf", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "capex", "typical_sign": "negative", "validation_rules": {}},
        {"canonical_name": "ppe", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "depreciation", "typical_sign": "negative", "validation_rules": {}},
        # Debt schedule items
        {"canonical_name": "debt_opening_balance", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "debt_closing_balance", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "debt_drawdown", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "principal_payment", "typical_sign": "negative", "validation_rules": {}},
        {"canonical_name": "interest_payment", "typical_sign": "negative", "validation_rules": {}},
        {"canonical_name": "debt_service", "typical_sign": "negative", "validation_rules": {}},
        # Project finance
        {"canonical_name": "cfads", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "dscr_project_finance", "typical_sign": "positive", "validation_rules": {}},
        # Cash flow statement
        {"canonical_name": "cfo", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "fcf", "typical_sign": "varies", "validation_rules": {}},
    ]


class TestCashBsCf:
    """Test cash (BS) ≈ ending_cash (CF) cross-statement check."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy())

    def test_matching_cash_passes(self):
        data = {
            "1.0": {"cash": D("1000000"), "ending_cash": D("1000000")},
        }
        results = self.validator.validate_cross_statement(data)
        cash_results = [r for r in results if r.rule == "cross_statement:cash_bs_cf"]
        assert len(cash_results) == 1
        assert cash_results[0].passed is True

    def test_mismatched_cash_warns(self):
        data = {
            "1.0": {"cash": D("1000000"), "ending_cash": D("800000")},
        }
        results = self.validator.validate_cross_statement(data)
        cash_results = [r for r in results if r.rule == "cross_statement:cash_bs_cf"]
        assert len(cash_results) == 1
        assert cash_results[0].passed is False
        assert cash_results[0].severity == "warning"

    def test_within_tolerance_passes(self):
        """0.5% rounding difference should pass within 1% tolerance."""
        data = {
            "1.0": {"cash": D("1000000"), "ending_cash": D("995000")},
        }
        results = self.validator.validate_cross_statement(data)
        cash_results = [r for r in results if r.rule == "cross_statement:cash_bs_cf"]
        assert len(cash_results) == 1
        assert cash_results[0].passed is True

    def test_4pct_difference_fails_tighter_tolerance(self):
        """4% difference should now fail with tighter 1% tolerance."""
        data = {
            "1.0": {"cash": D("1000000"), "ending_cash": D("960000")},
        }
        results = self.validator.validate_cross_statement(data)
        cash_results = [r for r in results if r.rule == "cross_statement:cash_bs_cf"]
        assert len(cash_results) == 1
        assert cash_results[0].passed is False

    def test_missing_ending_cash_skips(self):
        data = {
            "1.0": {"cash": D("1000000")},
        }
        results = self.validator.validate_cross_statement(data)
        cash_results = [r for r in results if r.rule == "cross_statement:cash_bs_cf"]
        assert len(cash_results) == 0


class TestRetainedEarningsNetIncome:
    """Test retained_earnings change ≈ net_income cross-statement check."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy())

    def test_matching_change_passes(self):
        data = {
            "1.0": {"retained_earnings": D("5000000"), "net_income": D("500000")},
            "2.0": {"retained_earnings": D("5500000"), "net_income": D("500000")},
        }
        results = self.validator.validate_cross_statement(data)
        re_results = [r for r in results if r.rule == "cross_statement:retained_earnings_ni"]
        assert len(re_results) == 1  # only period 2 (needs prev)
        assert re_results[0].passed is True

    def test_mismatch_warns(self):
        data = {
            "1.0": {"retained_earnings": D("5000000"), "net_income": D("500000")},
            "2.0": {"retained_earnings": D("5800000"), "net_income": D("500000")},
        }
        results = self.validator.validate_cross_statement(data)
        re_results = [r for r in results if r.rule == "cross_statement:retained_earnings_ni"]
        assert len(re_results) == 1
        assert re_results[0].passed is False

    def test_missing_prior_period_skips(self):
        """First period has no prior — should skip."""
        data = {
            "1.0": {"retained_earnings": D("5000000"), "net_income": D("500000")},
        }
        results = self.validator.validate_cross_statement(data)
        re_results = [r for r in results if r.rule == "cross_statement:retained_earnings_ni"]
        assert len(re_results) == 0

    def test_dividend_gap_within_tolerance(self):
        """Gap explained by dividends_paid should pass with tighter 2% tolerance."""
        data = {
            "1.0": {"retained_earnings": D("5000000"), "net_income": D("500000")},
            "2.0": {
                "retained_earnings": D("5450000"),
                "net_income": D("500000"),
                "dividends_paid": D("-50000"),  # 500000 - 50000 = 450000 = exact change
            },
        }
        results = self.validator.validate_cross_statement(data)
        re_results = [r for r in results if r.rule == "cross_statement:retained_earnings_ni"]
        assert len(re_results) == 1
        assert re_results[0].passed is True

    def test_4pct_unexplained_gap_fails(self):
        """4% unexplained gap (no dividends) should fail with 2% tolerance."""
        data = {
            "1.0": {"retained_earnings": D("5000000"), "net_income": D("500000")},
            "2.0": {"retained_earnings": D("5480000"), "net_income": D("500000")},
            # change = 480K vs NI 500K = 4% gap, no dividends to explain it
        }
        results = self.validator.validate_cross_statement(data)
        re_results = [r for r in results if r.rule == "cross_statement:retained_earnings_ni"]
        assert len(re_results) == 1
        assert re_results[0].passed is False


class TestTotalDebtSchedule:
    """Test total_debt ≈ sum of debt components."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy())

    def test_matching_debt_passes(self):
        data = {
            "1.0": {
                "total_debt": D("10000000"),
                "long_term_debt": D("7000000"),
                "short_term_debt": D("3000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        debt_results = [r for r in results if r.rule == "cross_statement:total_debt_schedule"]
        assert len(debt_results) == 1
        assert debt_results[0].passed is True

    def test_mismatch_warns(self):
        data = {
            "1.0": {
                "total_debt": D("10000000"),
                "long_term_debt": D("5000000"),
                "short_term_debt": D("3000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        debt_results = [r for r in results if r.rule == "cross_statement:total_debt_schedule"]
        assert len(debt_results) == 1
        assert debt_results[0].passed is False

    def test_single_component_skips(self):
        """Only one debt component → skip (need at least 2)."""
        data = {
            "1.0": {
                "total_debt": D("10000000"),
                "long_term_debt": D("10000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        debt_results = [r for r in results if r.rule == "cross_statement:total_debt_schedule"]
        assert len(debt_results) == 0

    def test_no_total_debt_skips(self):
        data = {
            "1.0": {
                "long_term_debt": D("7000000"),
                "short_term_debt": D("3000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        debt_results = [r for r in results if r.rule == "cross_statement:total_debt_schedule"]
        assert len(debt_results) == 0


class TestDepreciationIsCf:
    """Test depreciation_and_amortization (IS) ≈ depreciation_cf (CF)."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy())

    def test_matching_depreciation_passes(self):
        data = {
            "1.0": {
                "depreciation_and_amortization": D("-100000"),
                "depreciation_cf": D("100000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        dep_results = [r for r in results if r.rule == "cross_statement:depreciation_is_cf"]
        assert len(dep_results) == 1
        assert dep_results[0].passed is True

    def test_mismatch_warns(self):
        data = {
            "1.0": {
                "depreciation_and_amortization": D("-100000"),
                "depreciation_cf": D("200000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        dep_results = [r for r in results if r.rule == "cross_statement:depreciation_is_cf"]
        assert len(dep_results) == 1
        assert dep_results[0].passed is False

    def test_sign_difference_handled(self):
        """IS depreciation is negative, CF is positive — should compare absolute values."""
        data = {
            "1.0": {
                "depreciation_and_amortization": D("-150000"),
                "depreciation_cf": D("150000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        dep_results = [r for r in results if r.rule == "cross_statement:depreciation_is_cf"]
        assert len(dep_results) == 1
        assert dep_results[0].passed is True


class TestCapexPpeChange:
    """Test capex (CF) correlates with PPE change on BS."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy())

    def test_matching_capex_ppe_passes(self):
        data = {
            "1.0": {"ppe": D("1000000"), "capex": D("-200000"), "depreciation": D("-100000")},
            "2.0": {"ppe": D("1100000"), "capex": D("-200000"), "depreciation": D("-100000")},
            # PPE change = 100K, depreciation = 100K, implied capex = 200K, actual = 200K
        }
        results = self.validator.validate_cross_statement(data)
        capex_results = [r for r in results if r.rule == "cross_statement:capex_ppe_change"]
        assert len(capex_results) == 1  # only period 2 (needs prev)
        assert capex_results[0].passed is True

    def test_mismatch_warns(self):
        data = {
            "1.0": {"ppe": D("1000000"), "capex": D("-200000"), "depreciation": D("-100000")},
            "2.0": {"ppe": D("1500000"), "capex": D("-200000"), "depreciation": D("-100000")},
            # PPE change = 500K + dep 100K = 600K implied capex, but actual = 200K → fail
        }
        results = self.validator.validate_cross_statement(data)
        capex_results = [r for r in results if r.rule == "cross_statement:capex_ppe_change"]
        assert len(capex_results) == 1
        assert capex_results[0].passed is False

    def test_missing_ppe_skips(self):
        data = {
            "1.0": {"capex": D("-200000"), "depreciation": D("-100000")},
            "2.0": {"capex": D("-200000"), "depreciation": D("-100000")},
        }
        results = self.validator.validate_cross_statement(data)
        capex_results = [r for r in results if r.rule == "cross_statement:capex_ppe_change"]
        assert len(capex_results) == 0


class TestWorkingCapital:
    """Test working_capital = current_assets - current_liabilities."""

    def setup_method(self):
        from src.extraction.taxonomy_loader import get_all_taxonomy_items

        self.validator = AccountingValidator(get_all_taxonomy_items())

    def test_matching_working_capital_passes(self):
        data = {
            "1.0": {
                "working_capital": D("500000"),
                "current_assets": D("800000"),
                "current_liabilities": D("300000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        wc_results = [r for r in results if r.rule == "cross_statement:working_capital"]
        assert len(wc_results) == 1
        assert wc_results[0].passed is True

    def test_mismatched_working_capital_warns(self):
        data = {
            "1.0": {
                "working_capital": D("700000"),  # wrong, should be 500000
                "current_assets": D("800000"),
                "current_liabilities": D("300000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        wc_results = [r for r in results if r.rule == "cross_statement:working_capital"]
        assert len(wc_results) == 1
        assert wc_results[0].passed is False
        assert wc_results[0].severity == "warning"

    def test_missing_components_skips(self):
        data = {
            "1.0": {
                "working_capital": D("500000"),
                "current_assets": D("800000"),
                # current_liabilities missing
            },
        }
        results = self.validator.validate_cross_statement(data)
        wc_results = [r for r in results if r.rule == "cross_statement:working_capital"]
        assert len(wc_results) == 0


class TestInterestIsDsCheck:
    """Test interest_expense (IS) ≈ total_interest (DS)."""

    def setup_method(self):
        from src.extraction.taxonomy_loader import get_all_taxonomy_items

        self.validator = AccountingValidator(get_all_taxonomy_items())

    def test_matching_interest_passes(self):
        data = {
            "1.0": {
                "interest_expense": D("-50000"),
                "total_interest": D("50000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        int_results = [r for r in results if r.rule == "cross_statement:interest_is_ds"]
        assert len(int_results) == 1
        assert int_results[0].passed is True

    def test_mismatched_interest_warns(self):
        data = {
            "1.0": {
                "interest_expense": D("-50000"),
                "total_interest": D("70000"),  # >10% difference
            },
        }
        results = self.validator.validate_cross_statement(data)
        int_results = [r for r in results if r.rule == "cross_statement:interest_is_ds"]
        assert len(int_results) == 1
        assert int_results[0].passed is False
        assert int_results[0].severity == "warning"

    def test_within_5pct_passes(self):
        """3% difference — within tightened 5% tolerance."""
        data = {
            "1.0": {
                "interest_expense": D("-50000"),
                "total_interest": D("51500"),  # 3% difference, within 5%
            },
        }
        results = self.validator.validate_cross_statement(data)
        int_results = [r for r in results if r.rule == "cross_statement:interest_is_ds"]
        assert len(int_results) == 1
        assert int_results[0].passed is True

    def test_missing_total_interest_skips(self):
        data = {
            "1.0": {
                "interest_expense": D("-50000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        int_results = [r for r in results if r.rule == "cross_statement:interest_is_ds"]
        assert len(int_results) == 0


class TestEquityReconciliation:
    """Test equity[t] ≈ equity[t-1] + net_income - dividends."""

    def setup_method(self):
        from src.extraction.taxonomy_loader import get_all_taxonomy_items

        self.validator = AccountingValidator(get_all_taxonomy_items())

    def test_matching_equity_passes(self):
        data = {
            "1.0": {
                "total_equity": D("1000000"),
                "net_income": D("200000"),
            },
            "2.0": {
                "total_equity": D("1250000"),  # 1000000 + 250000 (period 2 NI)
                "net_income": D("250000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        eq_results = [r for r in results if r.rule == "cross_statement:equity_reconciliation"]
        assert len(eq_results) == 1  # only period 2.0 (needs prev)
        assert eq_results[0].passed is True

    def test_mismatch_warns(self):
        data = {
            "1.0": {
                "total_equity": D("1000000"),
                "net_income": D("200000"),
            },
            "2.0": {
                "total_equity": D("1500000"),  # too high
                "net_income": D("250000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        eq_results = [r for r in results if r.rule == "cross_statement:equity_reconciliation"]
        assert len(eq_results) == 1
        assert eq_results[0].passed is False
        assert eq_results[0].severity == "warning"

    def test_missing_prior_period_skips(self):
        data = {
            "1.0": {
                "total_equity": D("1000000"),
                "net_income": D("200000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        eq_results = [r for r in results if r.rule == "cross_statement:equity_reconciliation"]
        # Period 1.0 has no prior → skipped
        assert len(eq_results) == 0

    def test_dividends_accounted_for(self):
        data = {
            "1.0": {
                "total_equity": D("1000000"),
                "net_income": D("200000"),
                "dividends_paid": D("-50000"),
            },
            "2.0": {
                # 1000000 + 250000 (period 2 NI) - 60000 (period 2 divs) = 1190000
                "total_equity": D("1190000"),
                "net_income": D("250000"),
                "dividends_paid": D("-60000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        eq_results = [r for r in results if r.rule == "cross_statement:equity_reconciliation"]
        assert len(eq_results) == 1
        assert eq_results[0].passed is True


class TestNetIncomeCfVsIs:
    """[CF-5] net_income_cf (CF) must equal net_income (IS)."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy())

    def test_matching_passes(self):
        data = {
            "1.0": {"net_income_cf": D("500000"), "net_income": D("500000")},
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "cross_statement:net_income_cf_vs_is"]
        assert len(r) == 1
        assert r[0].passed is True

    def test_mismatch_is_error(self):
        data = {
            "1.0": {"net_income_cf": D("500000"), "net_income": D("400000")},
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "cross_statement:net_income_cf_vs_is"]
        assert len(r) == 1
        assert r[0].passed is False
        assert r[0].severity == "error"

    def test_missing_either_skips(self):
        data = {"1.0": {"net_income": D("500000")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "cross_statement:net_income_cf_vs_is"]
        assert len(r) == 0


class TestCashRollForward:
    """[BS-16] beginning_cash + net_change_cash == ending_cash."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy())

    def test_balancing_passes(self):
        data = {
            "1.0": {
                "beginning_cash": D("100000"),
                "net_change_cash": D("50000"),
                "ending_cash": D("150000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "cross_statement:cash_roll_forward"]
        assert len(r) == 1
        assert r[0].passed is True

    def test_mismatch_is_error(self):
        data = {
            "1.0": {
                "beginning_cash": D("100000"),
                "net_change_cash": D("50000"),
                "ending_cash": D("200000"),  # wrong — should be 150000
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "cross_statement:cash_roll_forward"]
        assert len(r) == 1
        assert r[0].passed is False
        assert r[0].severity == "error"

    def test_missing_component_skips(self):
        data = {"1.0": {"beginning_cash": D("100000"), "ending_cash": D("150000")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "cross_statement:cash_roll_forward"]
        assert len(r) == 0


class TestDebtRollForward:
    """[DS-1] opening + drawdown - repayment == closing."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy())

    def test_matching_passes(self):
        data = {
            "1.0": {
                "debt_opening_balance": D("10000000"),
                "debt_drawdown": D("2000000"),
                "principal_payment": D("-1000000"),
                "debt_closing_balance": D("11000000"),  # 10M + 2M - 1M
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "cross_statement:debt_roll_forward"]
        assert len(r) == 1
        assert r[0].passed is True

    def test_mismatch_is_error(self):
        data = {
            "1.0": {
                "debt_opening_balance": D("10000000"),
                "debt_drawdown": D("2000000"),
                "principal_payment": D("-1000000"),
                "debt_closing_balance": D("12000000"),  # wrong — should be 11M
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "cross_statement:debt_roll_forward"]
        assert len(r) == 1
        assert r[0].passed is False
        assert r[0].severity == "error"

    def test_missing_repayment_skips(self):
        data = {
            "1.0": {
                "debt_opening_balance": D("10000000"),
                "debt_closing_balance": D("11000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "cross_statement:debt_roll_forward"]
        assert len(r) == 0


class TestDebtServiceIdentity:
    """[DS-3] debt_service == principal + interest."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy())

    def test_matching_passes(self):
        data = {
            "1.0": {
                "debt_service": D("-3000000"),
                "principal_payment": D("-2000000"),
                "interest_payment": D("-1000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "cross_statement:debt_service_identity"]
        assert len(r) == 1
        assert r[0].passed is True

    def test_mismatch_is_error(self):
        data = {
            "1.0": {
                "debt_service": D("-3000000"),
                "principal_payment": D("-1500000"),
                "interest_payment": D("-1000000"),  # 1500 + 1000 = 2500, not 3000
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "cross_statement:debt_service_identity"]
        assert len(r) == 1
        assert r[0].passed is False
        assert r[0].severity == "error"


def _make_taxonomy_pf():
    """Extended taxonomy with project-finance-specific canonicals."""
    base = _make_taxonomy()
    pf_items = [
        {"canonical_name": "cfae", "typical_sign": "varies", "validation_rules": {}},
        {"canonical_name": "llcr", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "plcr", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "dsra_balance", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "equity_irr", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "distribution_lock_up", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "equity_contribution", "typical_sign": "positive", "validation_rules": {}},
        {"canonical_name": "total_investment", "typical_sign": "positive", "validation_rules": {}},
    ]
    return base + pf_items


class TestDscrPfConsistency:
    """[PF-2] dscr_project_finance consistency with cfads / debt_service."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy())

    def test_consistent_dscr_passes(self):
        # cfads=5M, debt_service=4M, ratio=1.25x — extracted also 1.25x
        data = {
            "1.0": {
                "dscr_project_finance": D("1.25"),
                "cfads": D("5000000"),
                "debt_service": D("4000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "cross_statement:dscr_pf_consistency"]
        assert len(r) == 1
        assert r[0].passed is True

    def test_divergent_dscr_warns(self):
        # cfads=5M, debt_service=4M, ratio=1.25x — but extracted says 1.40x
        data = {
            "1.0": {
                "dscr_project_finance": D("1.40"),
                "cfads": D("5000000"),
                "debt_service": D("4000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "cross_statement:dscr_pf_consistency"]
        assert len(r) == 1
        assert r[0].passed is False
        assert r[0].severity == "warning"


# ============================================================================
# PF-4: CFAE consistency
# ============================================================================

class TestPfCfaeConsistency:
    """[PF-4] cfae = cfads - debt_service consistency."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy_pf())

    def test_consistent_cfae_passes(self):
        # cfads=5M, debt_service=4M, cfae=1M — consistent
        data = {
            "1.0": {
                "cfae": D("1000000"),
                "cfads": D("5000000"),
                "debt_service": D("4000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:cfae_consistency"]
        assert len(r) == 1
        assert r[0].passed is True

    def test_divergent_cfae_warns(self):
        # cfads=5M, debt_service=4M, computed cfae=1M — but extracted says 0.8M (20% off)
        data = {
            "1.0": {
                "cfae": D("800000"),
                "cfads": D("5000000"),
                "debt_service": D("4000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:cfae_consistency"]
        assert len(r) == 1
        assert r[0].passed is False
        assert r[0].severity == "warning"

    def test_skips_when_cfads_missing(self):
        data = {"1.0": {"cfae": D("1000000"), "debt_service": D("4000000")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:cfae_consistency"]
        assert len(r) == 0

    def test_skips_when_cfae_missing(self):
        data = {"1.0": {"cfads": D("5000000"), "debt_service": D("4000000")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:cfae_consistency"]
        assert len(r) == 0

    def test_debt_service_sign_insensitive(self):
        # debt_service can be stored as negative; check uses abs()
        data = {
            "1.0": {
                "cfae": D("1000000"),
                "cfads": D("5000000"),
                "debt_service": D("-4000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:cfae_consistency"]
        assert len(r) == 1
        assert r[0].passed is True


# ============================================================================
# PF-8: LLCR >= DSCR
# ============================================================================

class TestPfLlcrVsDscr:
    """[PF-8] llcr >= dscr_project_finance."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy_pf())

    def test_llcr_above_dscr_passes(self):
        data = {
            "1.0": {
                "llcr": D("1.50"),
                "dscr_project_finance": D("1.25"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:llcr_vs_dscr"]
        assert len(r) == 1
        assert r[0].passed is True

    def test_llcr_equal_to_dscr_passes(self):
        data = {"1.0": {"llcr": D("1.25"), "dscr_project_finance": D("1.25")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:llcr_vs_dscr"]
        assert r[0].passed is True

    def test_llcr_below_dscr_warns(self):
        # LLCR 1.10x < DSCR 1.25x — structural inconsistency
        data = {
            "1.0": {
                "llcr": D("1.10"),
                "dscr_project_finance": D("1.25"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:llcr_vs_dscr"]
        assert len(r) == 1
        assert r[0].passed is False
        assert r[0].severity == "warning"

    def test_skips_when_llcr_missing(self):
        data = {"1.0": {"dscr_project_finance": D("1.25")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:llcr_vs_dscr"]
        assert len(r) == 0

    def test_skips_when_dscr_missing(self):
        data = {"1.0": {"llcr": D("1.50")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:llcr_vs_dscr"]
        assert len(r) == 0


# ============================================================================
# PF-9: PLCR >= LLCR
# ============================================================================

class TestPfPlcrVsLlcr:
    """[PF-9] plcr >= llcr."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy_pf())

    def test_plcr_above_llcr_passes(self):
        data = {"1.0": {"plcr": D("2.00"), "llcr": D("1.50")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:plcr_vs_llcr"]
        assert len(r) == 1
        assert r[0].passed is True

    def test_plcr_equal_to_llcr_passes(self):
        data = {"1.0": {"plcr": D("1.50"), "llcr": D("1.50")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:plcr_vs_llcr"]
        assert r[0].passed is True

    def test_plcr_below_llcr_warns(self):
        data = {"1.0": {"plcr": D("1.30"), "llcr": D("1.50")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:plcr_vs_llcr"]
        assert len(r) == 1
        assert r[0].passed is False
        assert r[0].severity == "warning"

    def test_skips_when_plcr_missing(self):
        data = {"1.0": {"llcr": D("1.50")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:plcr_vs_llcr"]
        assert len(r) == 0


# ============================================================================
# PF-10: DSRA adequacy
# ============================================================================

class TestPfDsraAdequacy:
    """[PF-10] dsra_balance >= 1× debt_service."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy_pf())

    def test_adequate_dsra_passes(self):
        # DSRA 4.2M >= 1× debt_service 4M ✓
        data = {
            "1.0": {
                "dsra_balance": D("4200000"),
                "debt_service": D("4000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:dsra_adequacy"]
        assert len(r) == 1
        assert r[0].passed is True

    def test_exactly_one_times_passes(self):
        data = {
            "1.0": {
                "dsra_balance": D("4000000"),
                "debt_service": D("4000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:dsra_adequacy"]
        assert r[0].passed is True

    def test_within_tolerance_passes(self):
        # DSRA 3.81M vs required 4M → 4.75% below 1× → within 5% tolerance
        data = {
            "1.0": {
                "dsra_balance": D("3810000"),
                "debt_service": D("4000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:dsra_adequacy"]
        assert r[0].passed is True

    def test_under_funded_dsra_warns(self):
        # DSRA 3M < required 4M (25% shortfall) → fails
        data = {
            "1.0": {
                "dsra_balance": D("3000000"),
                "debt_service": D("4000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:dsra_adequacy"]
        assert len(r) == 1
        assert r[0].passed is False
        assert r[0].severity == "warning"

    def test_debt_service_sign_insensitive(self):
        # debt_service stored as negative
        data = {
            "1.0": {
                "dsra_balance": D("4200000"),
                "debt_service": D("-4000000"),
            },
        }
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:dsra_adequacy"]
        assert r[0].passed is True

    def test_skips_when_dsra_missing(self):
        data = {"1.0": {"debt_service": D("4000000")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:dsra_adequacy"]
        assert len(r) == 0

    def test_skips_when_debt_service_zero(self):
        data = {"1.0": {"dsra_balance": D("1000000"), "debt_service": D("0")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:dsra_adequacy"]
        assert len(r) == 0


# ============================================================================
# PF-11: Equity IRR plausibility
# ============================================================================

class TestPfEquityIrrPlausibility:
    """[PF-11] equity_irr range: 3% to 40%."""

    def setup_method(self):
        self.validator = AccountingValidator(_make_taxonomy_pf())

    def test_normal_irr_passes(self):
        # 12% in decimal form
        data = {"1.0": {"equity_irr": D("0.12")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:equity_irr_plausibility"]
        assert len(r) == 1
        assert r[0].passed is True

    def test_percentage_form_normalised(self):
        # 12.0 in percentage form → normalised to 0.12
        data = {"1.0": {"equity_irr": D("12.0")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:equity_irr_plausibility"]
        assert r[0].passed is True

    def test_boundary_low_passes(self):
        # Exactly 3% (lower bound inclusive)
        data = {"1.0": {"equity_irr": D("0.03")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:equity_irr_plausibility"]
        assert r[0].passed is True

    def test_boundary_high_passes(self):
        # Exactly 40% (upper bound inclusive)
        data = {"1.0": {"equity_irr": D("0.40")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:equity_irr_plausibility"]
        assert r[0].passed is True

    def test_below_minimum_warns(self):
        # 1% — implausibly low for equity
        data = {"1.0": {"equity_irr": D("0.01")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:equity_irr_plausibility"]
        assert len(r) == 1
        assert r[0].passed is False
        assert r[0].severity == "warning"

    def test_above_maximum_warns(self):
        # 55% — unusually high, check triggers
        data = {"1.0": {"equity_irr": D("0.55")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:equity_irr_plausibility"]
        assert len(r) == 1
        assert r[0].passed is False

    def test_percentage_form_above_max_warns(self):
        # 55.0 in percentage form → 0.55 → fails
        data = {"1.0": {"equity_irr": D("55.0")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:equity_irr_plausibility"]
        assert r[0].passed is False

    def test_skips_when_irr_missing(self):
        data = {"1.0": {"cfads": D("5000000")}}
        results = self.validator.validate_cross_statement(data)
        r = [x for x in results if x.rule == "pf_check:equity_irr_plausibility"]
        assert len(r) == 0
