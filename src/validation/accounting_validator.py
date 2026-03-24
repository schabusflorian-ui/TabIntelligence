"""
Accounting Identity Validator

Validates extracted financial data against cross-item validation rules
defined in the taxonomy. Catches data extraction errors by checking
fundamental accounting relationships.

Usage:
    from src.validation.accounting_validator import AccountingValidator

    validator = AccountingValidator(taxonomy_manager)
    results = await validator.validate(extracted_data)

    if results.has_errors:
        print(f"Found {len(results.errors)} errors")
    if results.has_warnings:
        print(f"Found {len(results.warnings)} warnings")
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from src.validation.utils import sort_periods


@dataclass
class ValidationResult:
    """Result of validation check."""

    passed: bool
    item_name: str
    rule: str
    message: str
    severity: str  # 'error', 'warning', 'info'
    actual_value: Optional[Any] = None
    expected_value: Optional[Any] = None


@dataclass
class ValidationSummary:
    """Summary of all validation results."""

    total_checks: int
    passed: int
    failed: int
    warnings: int
    errors: List[ValidationResult]
    warnings_list: List[ValidationResult]
    all_results: List[ValidationResult]

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings_list) > 0

    @property
    def success_rate(self) -> float:
        if self.total_checks == 0:
            return 1.0
        return self.passed / self.total_checks


class AccountingValidator:
    """
    Validates extracted financial data against taxonomy rules.

    Checks:
    1. Cross-item relationships (A = L + E, gross_profit = revenue - cogs, etc.)
    2. Range constraints (must_be_positive, bounds checking)
    3. Time-series validation (YoY change limits)
    4. Accounting identities
    """

    def __init__(self, taxonomy_items: List[Dict]):
        """
        Initialize validator with taxonomy items.

        Args:
            taxonomy_items: List of taxonomy item dicts with validation rules
        """
        self.taxonomy = {item["canonical_name"]: item for item in taxonomy_items}

    def _normalize_percentages(self, data: Dict[str, Decimal]) -> Dict[str, Decimal]:
        """Normalize percentage fields from 0-100 scale to 0-1 decimal scale.

        If a taxonomy item has type 'percentage' and the extracted value > 1.0,
        divide by 100 to convert from percentage format (e.g., 54.5% -> 0.545).
        """
        normalized = dict(data)
        for canonical_name, value in data.items():
            item = self.taxonomy.get(canonical_name)
            if not item:
                continue
            vr = item.get("validation_rules", {})
            if vr.get("type") == "percentage" and abs(value) > Decimal("1.0"):
                normalized[canonical_name] = value / Decimal("100")
        return normalized

    def validate(self, extracted_data: Dict[str, Decimal]) -> ValidationSummary:
        """
        Validate extracted data against all taxonomy rules.

        Args:
            extracted_data: Dict mapping canonical_name → extracted value

        Returns:
            ValidationSummary with all results
        """
        # Normalize percentage values (e.g., 54.5 -> 0.545) before validation
        data = self._normalize_percentages(extracted_data)
        results = []

        # Run validations for each item
        for canonical_name, item in self.taxonomy.items():
            if canonical_name not in data:
                continue  # Skip items not in extracted data

            value = data[canonical_name]
            validation_rules = item.get("validation_rules", {})
            cross_val = validation_rules.get("cross_item_validation", {})

            # Check must_be_positive
            if cross_val.get("must_be_positive"):
                result = self._check_positive(canonical_name, value)
                results.append(result)

            # Check cross-item relationships
            for relationship in cross_val.get("relationships", []):
                rel_result = self._check_relationship(canonical_name, relationship, data)
                if rel_result:
                    results.append(rel_result)

            # Check time-series rules (if historical data provided)
            # TODO: Implement when historical data is available

        # Compile summary
        errors = [r for r in results if r.severity == "error" and not r.passed]
        warnings = [r for r in results if r.severity == "warning" and not r.passed]
        passed_count = sum(1 for r in results if r.passed)

        return ValidationSummary(
            total_checks=len(results),
            passed=passed_count,
            failed=len(results) - passed_count,
            warnings=len(warnings),
            errors=errors,
            warnings_list=warnings,
            all_results=results,
        )

    def _check_positive(self, item_name: str, value: Decimal) -> ValidationResult:
        """Check if value is positive."""
        passed = value > 0
        return ValidationResult(
            passed=passed,
            item_name=item_name,
            rule="must_be_positive",
            message=f"{item_name} must be positive, got {value}",
            severity="error",
            actual_value=value,
            expected_value="positive",
        )

    def _check_relationship(
        self, item_name: str, relationship: Dict, data: Dict[str, Decimal]
    ) -> Optional[ValidationResult]:
        """
        Check cross-item relationship.

        Args:
            item_name: Canonical name of item being validated
            relationship: Relationship rule dict
            data: All extracted data

        Returns:
            ValidationResult or None if check can't be performed
        """
        rule_str = relationship["rule"]
        tolerance = relationship.get("tolerance", 0.0)
        error_message = relationship.get("error_message", f"Violated: {rule_str}")
        is_warning = relationship.get("warning_only", False)
        is_optional = relationship.get("optional", False)
        is_critical = relationship.get("critical", False)

        # Parse rule and evaluate
        try:
            passed, actual, expected = self._evaluate_rule(rule_str, data, tolerance)

            # If optional and can't evaluate, skip
            if is_optional and actual is None:
                return None

            severity = "error"
            if is_warning:
                severity = "warning"
            elif is_critical:
                severity = "error"

            return ValidationResult(
                passed=passed,
                item_name=item_name,
                rule=rule_str,
                message=error_message if not passed else f"✓ {rule_str}",
                severity=severity,
                actual_value=actual,
                expected_value=expected,
            )

        except Exception as e:
            # Rule couldn't be evaluated (missing data, parse error, etc.)
            if is_optional:
                return None

            return ValidationResult(
                passed=False,
                item_name=item_name,
                rule=rule_str,
                message=f"Could not evaluate rule: {str(e)}",
                severity="warning",
                actual_value=None,
                expected_value=None,
            )

    def _evaluate_rule(
        self, rule_str: str, data: Dict[str, Decimal], tolerance: float = 0.0
    ) -> tuple[bool, Optional[Decimal], Optional[Decimal]]:
        """
        Evaluate a validation rule.

        Args:
            rule_str: Rule string (e.g., "revenue >= gross_profit")
            data: Extracted data
            tolerance: Tolerance for equality checks (decimal %)

        Returns:
            (passed, actual_value, expected_value)
        """
        # Handle equality checks with derivations
        if "==" in rule_str:
            left, right = rule_str.split("==")
            left_name = left.strip()
            left_val = self._eval_expression(left_name, data)
            right_val = self._eval_expression(right.strip(), data)

            if left_val is None or right_val is None:
                return (True, None, None)  # Can't evaluate

            # Percentage items use absolute difference; others use relative
            item_meta = self.taxonomy.get(left_name, {})
            is_percentage = item_meta.get("validation_rules", {}).get("type") == "percentage"

            if is_percentage:
                diff = abs(float(left_val - right_val))
                passed = diff <= tolerance
            else:
                divisor = float(max(abs(left_val), abs(right_val), 1))  # type: ignore[arg-type]
                diff_pct = abs(float(left_val - right_val)) / divisor
                passed = diff_pct <= tolerance

            return (passed, left_val, right_val)

        # Handle >= comparisons
        elif ">=" in rule_str:
            left, right = rule_str.split(">=")
            left_val = self._eval_expression(left.strip(), data)
            right_val = self._eval_expression(right.strip(), data)

            if left_val is None or right_val is None:
                return (True, None, None)

            passed = left_val >= right_val
            return (passed, left_val, right_val)

        # Handle range checks FIRST (e.g., "0 <= gross_margin <= 1")
        # Must come before simple <= to avoid misparse on 3-part split
        elif rule_str.count("<=") == 2:
            parts = rule_str.split("<=")
            if len(parts) == 3:
                lower = self._eval_expression(parts[0].strip(), data)
                value = self._eval_expression(parts[1].strip(), data)
                upper = self._eval_expression(parts[2].strip(), data)

                if value is None:
                    return (True, None, None)

                passed = (
                    lower <= value <= upper if lower is not None and upper is not None else True
                )
                return (passed, value, f"{lower} to {upper}")  # type: ignore[return-value]

        # Handle simple <= comparisons (single operator)
        elif "<=" in rule_str:
            left, right = rule_str.split("<=")
            left_val = self._eval_expression(left.strip(), data)
            right_val = self._eval_expression(right.strip(), data)

            if left_val is None or right_val is None:
                return (True, None, None)

            passed = left_val <= right_val
            return (passed, left_val, right_val)

        raise ValueError(f"Unsupported rule format: {rule_str}")

    def _eval_expression(self, expr: str, data: Dict[str, Decimal]) -> Optional[Decimal]:
        """
        Evaluate a simple mathematical expression.

        Supports:
        - Variable lookup (e.g., "revenue")
        - Literals (e.g., "0", "1", "0.5")
        - Addition/subtraction (e.g., "revenue - cogs")
        - Multiplication/division (e.g., "gross_profit / revenue")

        Args:
            expr: Expression string
            data: Data dictionary

        Returns:
            Evaluated Decimal value or None if can't evaluate
        """
        expr = expr.strip()

        # Literal number
        try:
            return Decimal(expr)
        except (ValueError, ArithmeticError):
            pass

        # Simple variable lookup
        if expr in data:
            return data[expr]

        # Addition/subtraction
        if "+" in expr or "-" in expr:
            # Parse left and right (simple case, no nested operations)
            if "+" in expr:
                parts = expr.split("+")
                operator = "+"
            else:
                # Handle subtraction (be careful with negative numbers)
                parts = expr.split("-")
                operator = "-"

            if len(parts) == 2:
                left = self._eval_expression(parts[0].strip(), data)
                right = self._eval_expression(parts[1].strip(), data)

                if left is None or right is None:
                    return None

                if operator == "+":
                    return left + right
                else:
                    return left - right

        # Multiplication/division
        if "*" in expr:
            parts = expr.split("*")
            if len(parts) == 2:
                left = self._eval_expression(parts[0].strip(), data)
                right = self._eval_expression(parts[1].strip(), data)
                if left is None or right is None:
                    return None
                return left * right

        if "/" in expr:
            parts = expr.split("/")
            if len(parts) == 2:
                left = self._eval_expression(parts[0].strip(), data)
                right = self._eval_expression(parts[1].strip(), data)
                if left is None or right is None or right == 0:
                    return None
                return left / right

        # Couldn't evaluate
        return None

    # ------------------------------------------------------------------
    # Sign Convention Enforcement (Part D)
    # ------------------------------------------------------------------

    def validate_sign_conventions(
        self,
        data: Dict[str, Decimal],
    ) -> List[ValidationResult]:
        """Check extracted values against typical_sign from taxonomy.

        Returns warning-severity results for sign violations.
        Skips items with typical_sign == "varies" or None, and zero values.
        """
        results: List[ValidationResult] = []
        for canonical_name, value in data.items():
            item = self.taxonomy.get(canonical_name)
            if not item:
                continue

            typical_sign = item.get("typical_sign")
            if typical_sign is None or typical_sign == "varies":
                continue

            if value == 0:
                continue

            violation = False
            msg = ""
            if typical_sign == "positive" and value < 0:
                violation = True
                msg = f"{canonical_name} is negative ({value}) but typically positive"
            elif typical_sign == "negative" and value > 0:
                violation = True
                msg = f"{canonical_name} is positive ({value}) but typically negative"

            # Hard sign errors corrupt downstream ratio calculations
            severity = (
                "error"
                if violation and canonical_name in self._HARD_SIGN_ERROR_ITEMS
                else "warning"
            )
            results.append(
                ValidationResult(
                    passed=not violation,
                    item_name=canonical_name,
                    rule="sign_convention",
                    message=msg if violation else f"✓ {canonical_name} sign OK",
                    severity=severity,
                    actual_value=value,
                    expected_value=typical_sign,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Cross-Statement Validation (Part C)
    # ------------------------------------------------------------------

    # Granular tolerances — context matters for cross-statement checks.
    # Primary accounting identities (A=L+E) are enforced at 0.01% in the
    # taxonomy itself.  These tolerances cover reconciliations that legitimately
    # carry timing differences, rounding, or secondary treatments.
    TOLERANCE_CASH_BS_CF = 0.01          # 1%  — cash position should close tightly
    TOLERANCE_RETAINED_EARNINGS = 0.02   # 2%  — dividends explain residual gap
    TOLERANCE_DEBT_SCHEDULE = 0.02       # 2%  — tranche sum vs. BS total
    TOLERANCE_DEPRECIATION = 0.03        # 3%  — IS vs. CF add-back (timing)
    TOLERANCE_CAPEX_PPE = 0.10           # 10% — disposals / impairments justify wider
    TOLERANCE_WORKING_CAPITAL = 0.01     # 1%  — pure identity
    TOLERANCE_INTEREST_IS_DS = 0.05      # 5%  — capitalised interest / timing
    TOLERANCE_EQUITY_RECON = 0.02        # 2%  — equity issuance / buybacks
    TOLERANCE_DEBT_ROLL_FORWARD = 0.01   # 1%  — roll-forward must be tight
    TOLERANCE_NET_INCOME_CF = 0.02       # 2%  — minor restatement differences
    TOLERANCE_CASH_ROLL_FORWARD = 0.01   # 1%  — cash position identity
    TOLERANCE_DEBT_SERVICE = 0.01        # 1%  — P+I = debt service (pure identity)
    TOLERANCE_ADDITIVITY = 0.03          # 3%  — sub-item sum vs. parent (rounding)
    TOLERANCE_PF_DSCR_COVENANT = 0.0    # 0%  — covenant breach is binary (< threshold = breach)
    TOLERANCE_SOURCES_USES = 0.03        # 3%  — equity + debt ≈ total investment
    TOLERANCE_CFAE_CONSISTENCY = 0.02    # 2%  — cfae = cfads - debt_service
    TOLERANCE_DSRA_RESERVE = 0.05        # 5%  — DSRA coverage adequacy

    # Items whose sign violations are elevated to ERROR (not just warning).
    # These items, when wrong-signed, directly corrupt FCF, net-debt, and
    # coverage ratio calculations.
    _HARD_SIGN_ERROR_ITEMS: Set[str] = {
        "capex",
        "capital_expenditures",
        "debt_repayment",
        "debt_mandatory_repayment",
        "debt_optional_repayment",
        "interest_expense",
        "dividends_paid",
        "share_repurchase",
        "share_buyback",
    }

    # All debt tranche canonicals — used for total_debt additivity check
    _DEBT_COMPONENTS: Set[str] = {
        "senior_debt",
        "subordinated_debt",
        "term_loan_a",
        "term_loan_b",
        "bonds_payable",
        "notes_payable",
        "revolver_balance",
        "revolving_credit",
        "long_term_debt",
        "short_term_debt",
        "unitranche",
        "delayed_draw_term_loan",
        "mezzanine_debt",
        "convertible_notes",
        "safe_notes",
    }

    def validate_cross_statement(
        self,
        multi_period_data: Dict[str, Dict[str, Decimal]],
    ) -> List[ValidationResult]:
        """Validate relationships across financial statements.

        Best-effort: skips checks where required items are missing.
        All checks use 5% tolerance and warning severity.
        """
        results: List[ValidationResult] = []
        sorted_periods = sort_periods(list(multi_period_data.keys()))

        for idx, period in enumerate(sorted_periods):
            data = multi_period_data.get(period, {})
            prev_data = multi_period_data.get(sorted_periods[idx - 1], {}) if idx > 0 else {}

            # 1. cash (BS) ≈ ending_cash (CF)
            r = self._check_cash_bs_cf(period, data)
            if r is not None:
                results.append(r)

            # 2. retained_earnings change ≈ net_income
            r = self._check_retained_earnings_net_income(period, data, prev_data)
            if r is not None:
                results.append(r)

            # 3. total_debt (BS) ≈ sum of debt components
            r = self._check_total_debt_schedule(period, data)
            if r is not None:
                results.append(r)

            # 4. depreciation_and_amortization (IS) ≈ depreciation_cf (CF)
            r = self._check_depreciation_is_cf(period, data)
            if r is not None:
                results.append(r)

            # 5. capex (CF) correlates with PPE change on BS
            r = self._check_capex_ppe_change(period, data, prev_data)
            if r is not None:
                results.append(r)

            # 6. working_capital = current_assets - current_liabilities
            r = self._check_working_capital(period, data)
            if r is not None:
                results.append(r)

            # 7. interest_expense (IS) ≈ total_interest (DS)
            r = self._check_interest_is_ds(period, data)
            if r is not None:
                results.append(r)

            # 8. equity reconciliation: equity[t] ≈ equity[t-1] + net_income - dividends
            r = self._check_equity_reconciliation(period, data, prev_data)
            if r is not None:
                results.append(r)

            # 9. [CF-5] net_income_cf (CF starting line) == net_income (IS)
            r = self._check_net_income_cf_vs_is(period, data)
            if r is not None:
                results.append(r)

            # 10. [BS-16] beginning_cash + net_change_cash == ending_cash
            r = self._check_cash_roll_forward(period, data)
            if r is not None:
                results.append(r)

            # 11. [DS-1] debt roll-forward: opening + drawdown - repayment == closing
            r = self._check_debt_roll_forward(period, data)
            if r is not None:
                results.append(r)

            # 12. [DS-3] debt_service == principal + interest
            r = self._check_debt_service_identity(period, data)
            if r is not None:
                results.append(r)

            # 13. [PF-2] dscr_project_finance == cfads / debt_service (consistency)
            r = self._check_dscr_pf_consistency(period, data)
            if r is not None:
                results.append(r)

            # 14. [CF-3] fcf == cfo - capex (consistency)
            r = self._check_fcf_consistency(period, data)
            if r is not None:
                results.append(r)

            # ── P1-7: Additivity tree checks ──────────────────────────────
            # 15. [IS-7] sum of revenue sub-items ≈ revenue
            for r in self._check_revenue_additivity(period, data):
                results.append(r)

            # 16. [BS-2] total_assets ≈ current_assets + non_current_assets
            r = self._check_total_assets_additivity(period, data)
            if r is not None:
                results.append(r)

            # 17. [BS-3] total_liabilities ≈ current + non-current liabilities
            r = self._check_total_liabilities_additivity(period, data)
            if r is not None:
                results.append(r)

            # ── P1-8: Enhanced tranche additivity (DS-4) ──────────────────
            # (already covered by _check_total_debt_schedule; extended below)

            # ── P1-9: Project finance covenant checks ──────────────────────
            # 18. [PF-3] dscr_project_finance >= minimum_dscr_covenant
            r = self._check_pf_dscr_covenant(period, data)
            if r is not None:
                results.append(r)

            # 19. [PF-5] cfae >= 0 OR flag distribution lock-up breach
            r = self._check_pf_cfae_positive(period, data)
            if r is not None:
                results.append(r)

            # 20. [PF-6] equity_contribution + total_debt ≈ total_investment
            r = self._check_pf_sources_uses(period, data)
            if r is not None:
                results.append(r)

            # 21. [PF-7] loan_to_cost ≤ 90%
            r = self._check_pf_loan_to_cost(period, data)
            if r is not None:
                results.append(r)

            # 22. [PF-4] cfae consistency: extracted vs. computed cfads - debt_service
            r = self._check_pf_cfae_consistency(period, data)
            if r is not None:
                results.append(r)

            # 23. [PF-8] llcr >= dscr_project_finance
            r = self._check_pf_llcr_vs_dscr(period, data)
            if r is not None:
                results.append(r)

            # 24. [PF-9] plcr >= llcr
            r = self._check_pf_plcr_vs_llcr(period, data)
            if r is not None:
                results.append(r)

            # 25. [PF-10] dsra_balance >= 1× debt_service
            r = self._check_pf_dsra_adequacy(period, data)
            if r is not None:
                results.append(r)

            # 26. [PF-11] equity_irr plausibility: 3% to 40%
            r = self._check_pf_equity_irr_plausibility(period, data)
            if r is not None:
                results.append(r)

        return results

    def _check_cash_bs_cf(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """cash (BS) ≈ ending_cash (CF)."""
        cash = data.get("cash")
        ending_cash = data.get("ending_cash")
        if cash is None or ending_cash is None:
            return None

        divisor = float(max(abs(cash), abs(ending_cash), 1))  # type: ignore[arg-type]
        diff_pct = abs(float(cash - ending_cash)) / divisor
        passed = diff_pct <= self.TOLERANCE_CASH_BS_CF

        return ValidationResult(
            passed=passed,
            item_name="cash",
            rule="cross_statement:cash_bs_cf",
            message=(
                "✓ cash (BS) matches ending_cash (CF)"
                if passed
                else f"cash (BS) = {cash} differs from"
                f" ending_cash (CF) = {ending_cash}"
                f" in period {period}"
            ),
            severity="warning",
            actual_value=cash,
            expected_value=ending_cash,
        )

    def _check_retained_earnings_net_income(
        self,
        period: str,
        data: Dict[str, Decimal],
        prev_data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """Change in retained_earnings ≈ net_income."""
        re_curr = data.get("retained_earnings")
        re_prev = prev_data.get("retained_earnings")
        net_income = data.get("net_income")

        if re_curr is None or re_prev is None or net_income is None:
            return None

        re_change = re_curr - re_prev
        # Account for dividends declared (gap between RE change and NI)
        dividends = data.get("dividends_paid", Decimal("0"))
        expected_re_change = net_income - abs(dividends)
        divisor = float(max(abs(re_change), abs(expected_re_change), 1))  # type: ignore[arg-type]
        diff_pct = abs(float(re_change - expected_re_change)) / divisor
        passed = diff_pct <= self.TOLERANCE_RETAINED_EARNINGS

        return ValidationResult(
            passed=passed,
            item_name="retained_earnings",
            rule="cross_statement:retained_earnings_ni",
            message=(
                "✓ retained_earnings change matches net_income (net of dividends)"
                if passed
                else f"retained_earnings change ({re_change})"
                f" differs from net_income - dividends ({expected_re_change})"
                f" in period {period}"
            ),
            severity="warning",
            actual_value=re_change,
            expected_value=expected_re_change,
        )

    def _check_total_debt_schedule(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """total_debt (BS) ≈ sum of debt schedule components."""
        total_debt = data.get("total_debt")
        if total_debt is None:
            return None

        # Sum whichever debt components are present
        components_found = []
        debt_sum = Decimal("0")
        for comp in self._DEBT_COMPONENTS:
            val = data.get(comp)
            if val is not None:
                debt_sum += val
                components_found.append(comp)

        # Need at least 2 components to make this check meaningful
        if len(components_found) < 2:
            return None

        divisor = float(max(abs(total_debt), abs(debt_sum), 1))  # type: ignore[arg-type]
        diff_pct = abs(float(total_debt - debt_sum)) / divisor
        passed = diff_pct <= self.TOLERANCE_DEBT_SCHEDULE

        return ValidationResult(
            passed=passed,
            item_name="total_debt",
            rule="cross_statement:total_debt_schedule",
            message=(
                "✓ total_debt matches sum of debt components"
                if passed
                else f"total_debt ({total_debt}) differs from"
                f" sum of components ({debt_sum})"
                f" in period {period}"
            ),
            severity="warning",
            actual_value=total_debt,
            expected_value=debt_sum,
        )

    def _check_depreciation_is_cf(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """depreciation_and_amortization (IS) ≈ depreciation_cf (CF)."""
        da_is = data.get("depreciation_and_amortization")
        da_cf = data.get("depreciation_cf")

        if da_is is None or da_cf is None:
            return None

        # Compare absolute values (signs may differ between IS and CF)
        abs_is = abs(da_is)
        abs_cf = abs(da_cf)
        divisor = float(max(abs_is, abs_cf, 1))  # type: ignore[arg-type]
        diff_pct = abs(float(abs_is - abs_cf)) / divisor
        passed = diff_pct <= self.TOLERANCE_DEPRECIATION

        return ValidationResult(
            passed=passed,
            item_name="depreciation_and_amortization",
            rule="cross_statement:depreciation_is_cf",
            message=(
                "✓ D&A (IS) matches depreciation_cf (CF)"
                if passed
                else f"D&A (IS) = {da_is} differs from"
                f" depreciation_cf (CF) = {da_cf}"
                f" in period {period}"
            ),
            severity="warning",
            actual_value=da_is,
            expected_value=da_cf,
        )

    def _check_capex_ppe_change(
        self,
        period: str,
        data: Dict[str, Decimal],
        prev_data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """capex (CF) correlates with PPE change on BS.

        PPE[t] - PPE[t-1] + depreciation[t] ≈ abs(capex[t])
        Uses 10% tolerance (wider than standard 5%) because disposals
        and impairments can cause legitimate gaps.
        """
        capex = data.get("capex")
        ppe_curr = data.get("ppe")
        ppe_prev = prev_data.get("ppe")
        depreciation = data.get("depreciation") or data.get("depreciation_and_amortization")

        if capex is None or ppe_curr is None or ppe_prev is None or depreciation is None:
            return None

        ppe_change = ppe_curr - ppe_prev
        # PPE change + depreciation ≈ capex (all in absolute terms)
        implied_capex = ppe_change + abs(depreciation)
        actual_capex = abs(capex)

        divisor = float(max(actual_capex, abs(implied_capex), 1))  # type: ignore[arg-type]
        diff_pct = abs(float(actual_capex - implied_capex)) / divisor
        passed = diff_pct <= self.TOLERANCE_CAPEX_PPE

        return ValidationResult(
            passed=passed,
            item_name="capex",
            rule="cross_statement:capex_ppe_change",
            message=(
                "✓ capex correlates with PPE change"
                if passed
                else f"capex ({capex}) inconsistent with"
                f" PPE change + depreciation"
                f" ({implied_capex}) in period {period}"
            ),
            severity="warning",
            actual_value=capex,
            expected_value=implied_capex,
        )

    def _check_working_capital(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """working_capital == current_assets - current_liabilities."""
        wc = data.get("working_capital")
        ca = data.get("current_assets")
        cl = data.get("current_liabilities")

        if wc is None or ca is None or cl is None:
            return None

        expected = ca - cl
        divisor = float(max(abs(wc), abs(expected), 1))
        diff_pct = abs(float(wc - expected)) / divisor
        passed = diff_pct <= self.TOLERANCE_WORKING_CAPITAL

        return ValidationResult(
            passed=passed,
            item_name="working_capital",
            rule="cross_statement:working_capital",
            message=(
                "working_capital matches current_assets - current_liabilities"
                if passed
                else f"working_capital ({wc}) differs from"
                f" current_assets - current_liabilities ({expected})"
                f" in period {period}"
            ),
            severity="warning",
            actual_value=wc,
            expected_value=expected,
        )

    def _check_interest_is_ds(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """interest_expense (IS) ≈ total_interest (DS), 10% tolerance."""
        ie = data.get("interest_expense")
        ti = data.get("total_interest")

        if ie is None or ti is None:
            return None

        abs_ie = abs(ie)
        abs_ti = abs(ti)
        divisor = float(max(abs_ie, abs_ti, 1))
        diff_pct = abs(float(abs_ie - abs_ti)) / divisor
        passed = diff_pct <= self.TOLERANCE_INTEREST_IS_DS

        return ValidationResult(
            passed=passed,
            item_name="interest_expense",
            rule="cross_statement:interest_is_ds",
            message=(
                "interest_expense (IS) matches total_interest (DS)"
                if passed
                else f"interest_expense (IS) = {ie} differs from"
                f" total_interest (DS) = {ti}"
                f" in period {period}"
            ),
            severity="warning",
            actual_value=ie,
            expected_value=ti,
        )

    # ------------------------------------------------------------------
    # NEW checks added as part of financial audit hardening
    # ------------------------------------------------------------------

    def _check_net_income_cf_vs_is(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[CF-5] net_income_cf (CF starting line) must equal net_income (IS).

        The starting line of the indirect method cash flow statement must match
        the net income on the income statement.  Any divergence (beyond rounding)
        signals either a different reporting period or an extraction error.
        Severity: ERROR — this is a fundamental statement linkage.
        """
        ni_cf = data.get("net_income_cf")
        ni_is = data.get("net_income")

        if ni_cf is None or ni_is is None:
            return None

        divisor = float(max(abs(ni_cf), abs(ni_is), 1))  # type: ignore[arg-type]
        diff_pct = abs(float(ni_cf - ni_is)) / divisor
        passed = diff_pct <= self.TOLERANCE_NET_INCOME_CF

        return ValidationResult(
            passed=passed,
            item_name="net_income_cf",
            rule="cross_statement:net_income_cf_vs_is",
            message=(
                "✓ net_income_cf (CF) matches net_income (IS)"
                if passed
                else f"net_income_cf ({ni_cf}) differs from net_income ({ni_is})"
                f" in period {period} — possible period mismatch or extraction error"
            ),
            severity="error" if not passed else "warning",
            actual_value=ni_cf,
            expected_value=ni_is,
        )

    def _check_cash_roll_forward(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[BS-16] beginning_cash + net_change_cash == ending_cash.

        Cash identity across periods — if all three are extracted from the same
        period they must close to within rounding.  Any divergence > 1% signals
        a scale mismatch, wrong period, or extraction error.
        Severity: ERROR — cash position is a fundamental anchor.
        """
        beg = data.get("beginning_cash")
        net_chg = data.get("net_change_cash")
        ending = data.get("ending_cash")

        if beg is None or net_chg is None or ending is None:
            return None

        expected = beg + net_chg
        divisor = float(max(abs(ending), abs(expected), 1))  # type: ignore[arg-type]
        diff_pct = abs(float(ending - expected)) / divisor
        passed = diff_pct <= self.TOLERANCE_CASH_ROLL_FORWARD

        return ValidationResult(
            passed=passed,
            item_name="ending_cash",
            rule="cross_statement:cash_roll_forward",
            message=(
                "✓ cash roll-forward: beginning + net_change == ending"
                if passed
                else f"ending_cash ({ending}) ≠ beginning_cash ({beg})"
                f" + net_change_cash ({net_chg}) = {expected}"
                f" in period {period}"
            ),
            severity="error" if not passed else "warning",
            actual_value=ending,
            expected_value=expected,
        )

    def _check_debt_roll_forward(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[DS-1] debt roll-forward: opening + drawdown - repayment == closing.

        The fundamental debt schedule identity.  A model with arithmetic errors in its
        debt schedule will have a roll-forward gap.  Severity: ERROR — this is
        the most important integrity check for any leveraged or project finance model.
        """
        opening = data.get("debt_opening_balance")
        drawdown = data.get("debt_drawdown", Decimal("0"))
        repayment = data.get("principal_payment") or data.get("debt_mandatory_repayment")
        closing = data.get("debt_closing_balance")

        if opening is None or closing is None or repayment is None:
            return None

        # Drawdown is positive (cash in); repayment is typically negative (cash out)
        expected = opening + abs(drawdown) - abs(repayment)
        divisor = float(max(abs(closing), abs(expected), 1))  # type: ignore[arg-type]
        diff_pct = abs(float(closing - expected)) / divisor
        passed = diff_pct <= self.TOLERANCE_DEBT_ROLL_FORWARD

        return ValidationResult(
            passed=passed,
            item_name="debt_closing_balance",
            rule="cross_statement:debt_roll_forward",
            message=(
                "✓ debt roll-forward: opening + drawdown - repayment == closing"
                if passed
                else f"debt_closing_balance ({closing}) ≠ expected ({expected})"
                f" [opening={opening} + drawdown={abs(drawdown)} - repayment={abs(repayment)}]"
                f" in period {period}"
            ),
            severity="error" if not passed else "warning",
            actual_value=closing,
            expected_value=expected,
        )

    def _check_debt_service_identity(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[DS-3] debt_service == principal_payment + interest_payment.

        Debt service is a pure additive identity.  Any divergence is an error
        in the debt schedule structure.
        """
        ds = data.get("debt_service")
        principal = data.get("principal_payment")
        interest = data.get("interest_payment")

        if ds is None or principal is None or interest is None:
            return None

        expected = abs(principal) + abs(interest)
        actual = abs(ds)
        divisor = float(max(actual, expected, 1))  # type: ignore[arg-type]
        diff_pct = abs(float(actual - expected)) / divisor
        passed = diff_pct <= self.TOLERANCE_DEBT_SERVICE

        return ValidationResult(
            passed=passed,
            item_name="debt_service",
            rule="cross_statement:debt_service_identity",
            message=(
                "✓ debt_service == principal + interest"
                if passed
                else f"debt_service ({abs(ds)}) ≠ principal ({abs(principal)})"
                f" + interest ({abs(interest)}) = {expected}"
                f" in period {period}"
            ),
            severity="error" if not passed else "warning",
            actual_value=actual,
            expected_value=expected,
        )

    def _check_dscr_pf_consistency(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[PF-2] dscr_project_finance consistency: extracted vs. computed CFADS/debt_service.

        If dscr_project_finance is extracted AND both cfads and debt_service are available,
        compare the extracted value to the computed ratio.  Divergence > 3% suggests
        a model arithmetic error or a different CFADS definition in the source model.
        """
        dscr_extracted = data.get("dscr_project_finance")
        cfads = data.get("cfads")
        ds = data.get("debt_service")

        if dscr_extracted is None or cfads is None or ds is None or ds == 0:
            return None

        dscr_computed = abs(cfads) / abs(ds)
        divisor = float(max(abs(dscr_extracted), float(dscr_computed), Decimal("0.001")))  # type: ignore[arg-type]
        diff_pct = abs(float(dscr_extracted) - float(dscr_computed)) / divisor
        # 3% consistency threshold — tighter than cross-statement because this is
        # a ratio of two extracted items from the same model
        passed = diff_pct <= 0.03

        return ValidationResult(
            passed=passed,
            item_name="dscr_project_finance",
            rule="cross_statement:dscr_pf_consistency",
            message=(
                f"✓ dscr_project_finance consistent with cfads/debt_service ({dscr_computed:.3f})"
                if passed
                else f"dscr_project_finance extracted ({dscr_extracted:.3f})"
                f" diverges from computed ({dscr_computed:.3f})"
                f" by {diff_pct*100:.1f}% in period {period}"
                f" — possible model arithmetic error or CFADS definition mismatch"
            ),
            severity="warning",
            actual_value=dscr_extracted,
            expected_value=Decimal(str(round(float(dscr_computed), 4))),
        )

    def _check_fcf_consistency(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[CF-3] fcf consistency: extracted vs. computed cfo - capex."""
        fcf_extracted = data.get("fcf")
        cfo = data.get("cfo")
        capex = data.get("capex")

        if fcf_extracted is None or cfo is None or capex is None:
            return None

        fcf_computed = cfo - abs(capex)
        divisor = float(max(abs(fcf_extracted), abs(fcf_computed), 1))  # type: ignore[arg-type]
        diff_pct = abs(float(fcf_extracted - fcf_computed)) / divisor
        passed = diff_pct <= 0.02  # 2% — should be very close

        return ValidationResult(
            passed=passed,
            item_name="fcf",
            rule="cross_statement:fcf_consistency",
            message=(
                "✓ fcf consistent with cfo - capex"
                if passed
                else f"fcf ({fcf_extracted}) diverges from computed cfo - capex ({fcf_computed})"
                f" by {diff_pct*100:.1f}% in period {period}"
            ),
            severity="warning",
            actual_value=fcf_extracted,
            expected_value=fcf_computed,
        )

    def _check_equity_reconciliation(
        self,
        period: str,
        data: Dict[str, Decimal],
        prev_data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """equity[t] ≈ equity[t-1] + net_income - dividends."""
        eq_curr = data.get("total_equity")
        eq_prev = prev_data.get("total_equity")
        net_income = data.get("net_income")

        if eq_curr is None or eq_prev is None or net_income is None:
            return None

        dividends = data.get("dividends_paid", Decimal("0"))
        # Also absorb equity issuances / buybacks (wider tolerance covers these)
        expected = eq_prev + net_income - abs(dividends)
        divisor = float(max(abs(eq_curr), abs(expected), 1))
        diff_pct = abs(float(eq_curr - expected)) / divisor
        passed = diff_pct <= self.TOLERANCE_EQUITY_RECON

        return ValidationResult(
            passed=passed,
            item_name="total_equity",
            rule="cross_statement:equity_reconciliation",
            message=(
                "equity reconciliation matches"
                if passed
                else f"total_equity ({eq_curr}) differs from"
                f" expected ({expected} = prev_equity + net_income - dividends)"
                f" in period {period}"
            ),
            severity="warning",
            actual_value=eq_curr,
            expected_value=expected,
        )

    # ── P1-7: Additivity tree checks ──────────────────────────────────────

    #: Revenue sub-item canonicals used for IS-7 additivity check
    _REVENUE_COMPONENTS: Set[str] = {
        "product_revenue",
        "service_revenue",
        "subscription_revenue",
        "license_revenue",
        "transaction_revenue",
        "recurring_revenue",
        "non_recurring_revenue",
        "rental_income",
        "interest_income",
        "other_revenue",
    }

    def _check_revenue_additivity(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> List[ValidationResult]:
        """[IS-7] sum of revenue sub-items ≈ revenue when sub-items present."""
        revenue = data.get("revenue")
        if revenue is None:
            return []

        sub_items = {
            k: v for k, v in data.items()
            if k in self._REVENUE_COMPONENTS and v is not None
        }
        if len(sub_items) < 2:
            return []  # not enough sub-items to check additivity

        sub_total = sum(sub_items.values(), Decimal("0"))
        divisor = float(max(abs(revenue), abs(sub_total), 1))
        diff_pct = abs(float(revenue - sub_total)) / divisor
        passed = diff_pct <= self.TOLERANCE_ADDITIVITY

        return [
            ValidationResult(
                passed=passed,
                item_name="revenue",
                rule="additivity:revenue_components",
                message=(
                    f"revenue sub-items sum to {sub_total} ≈ revenue {revenue}"
                    if passed
                    else f"revenue ({revenue}) ≠ sum of sub-items ({sub_total})"
                    f" divergence={diff_pct:.1%} in period {period}"
                ),
                severity="warning",
                actual_value=sub_total,
                expected_value=revenue,
            )
        ]

    def _check_total_assets_additivity(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[BS-2] total_assets ≈ total_current_assets + total_non_current_assets."""
        total = data.get("total_assets")
        current = data.get("total_current_assets")
        non_current = data.get("total_non_current_assets")

        if total is None or current is None or non_current is None:
            return None

        expected = current + non_current
        divisor = float(max(abs(total), abs(expected), 1))
        diff_pct = abs(float(total - expected)) / divisor
        passed = diff_pct <= self.TOLERANCE_ADDITIVITY

        return ValidationResult(
            passed=passed,
            item_name="total_assets",
            rule="additivity:total_assets",
            message=(
                "total_assets = current + non_current assets ✓"
                if passed
                else f"total_assets ({total}) ≠ current ({current}) + non_current ({non_current})"
                f" in period {period}"
            ),
            severity="warning",
            actual_value=total,
            expected_value=expected,
        )

    def _check_total_liabilities_additivity(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[BS-3] total_liabilities ≈ total_current_liabilities + total_non_current_liabilities."""
        total = data.get("total_liabilities")
        current = data.get("total_current_liabilities")
        non_current = data.get("total_non_current_liabilities")

        if total is None or current is None or non_current is None:
            return None

        expected = current + non_current
        divisor = float(max(abs(total), abs(expected), 1))
        diff_pct = abs(float(total - expected)) / divisor
        passed = diff_pct <= self.TOLERANCE_ADDITIVITY

        return ValidationResult(
            passed=passed,
            item_name="total_liabilities",
            rule="additivity:total_liabilities",
            message=(
                "total_liabilities = current + non_current ✓"
                if passed
                else f"total_liabilities ({total}) ≠ current ({current})"
                f" + non_current ({non_current}) in period {period}"
            ),
            severity="warning",
            actual_value=total,
            expected_value=expected,
        )

    # ── P1-9: Project Finance Covenant Checks ──────────────────────────────

    def _check_pf_dscr_covenant(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[PF-3] dscr_project_finance >= minimum_dscr_covenant (distribution_lock_up).

        If the DSCR is below the lock-up trigger, flag as ERROR (covenant breach).
        """
        dscr = data.get("dscr_project_finance") or data.get("dscr")
        lock_up = data.get("distribution_lock_up")

        if dscr is None or lock_up is None:
            return None

        breached = dscr < lock_up
        headroom = dscr - lock_up

        return ValidationResult(
            passed=not breached,
            item_name="dscr_project_finance",
            rule="pf_covenant:dscr_distribution_lock_up",
            message=(
                f"DSCR {float(dscr):.3f}x headroom {float(headroom):+.3f}x vs lock-up {float(lock_up):.3f}x ✓"
                if not breached
                else f"COVENANT BREACH: DSCR {float(dscr):.3f}x < distribution lock-up "
                f"{float(lock_up):.3f}x (headroom {float(headroom):.3f}x)"
                f" in period {period}"
            ),
            severity="error" if breached else "warning",
            actual_value=dscr,
            expected_value=lock_up,
        )

    def _check_pf_cfae_positive(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[PF-5] cfae >= 0 (CFADS after debt service).

        Negative CFAE means CFADS is insufficient to cover debt service.
        This triggers distribution lock-up.
        """
        cfae = data.get("cfae")
        if cfae is None:
            return None

        passed = cfae >= Decimal("0")
        return ValidationResult(
            passed=passed,
            item_name="cfae",
            rule="pf_covenant:cfae_positive",
            message=(
                f"cfae {float(cfae):.0f} >= 0 ✓"
                if passed
                else f"CFAE ({float(cfae):.0f}) is negative in period {period} "
                f"— debt service exceeds CFADS, distribution lock-up triggered"
            ),
            severity="warning",
            actual_value=cfae,
            expected_value=Decimal("0"),
        )

    def _check_pf_sources_uses(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[PF-6] equity_contribution + total_debt ≈ total_investment (sources = uses)."""
        equity_contrib = data.get("equity_contribution")
        total_debt = data.get("total_debt")
        total_investment = data.get("total_investment")

        if equity_contrib is None or total_debt is None or total_investment is None:
            return None

        sources = equity_contrib + total_debt
        divisor = float(max(abs(total_investment), abs(sources), 1))
        diff_pct = abs(float(total_investment - sources)) / divisor
        passed = diff_pct <= self.TOLERANCE_SOURCES_USES

        return ValidationResult(
            passed=passed,
            item_name="total_investment",
            rule="pf_check:sources_uses",
            message=(
                f"sources ({float(sources):.0f}) ≈ total_investment ({float(total_investment):.0f}) ✓"
                if passed
                else f"PF sources ≠ uses: equity ({float(equity_contrib):.0f})"
                f" + debt ({float(total_debt):.0f}) = {float(sources):.0f}"
                f" vs total_investment {float(total_investment):.0f}"
                f" ({diff_pct:.1%} divergence) in period {period}"
            ),
            severity="warning",
            actual_value=sources,
            expected_value=total_investment,
        )

    def _check_pf_loan_to_cost(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[PF-7] loan_to_cost = total_debt / total_investment ≤ 90%."""
        total_debt = data.get("total_debt")
        total_investment = data.get("total_investment")

        if total_debt is None or total_investment is None:
            return None
        if total_investment == 0:
            return None

        ltc = total_debt / total_investment
        MAX_LTC = Decimal("0.90")
        passed = ltc <= MAX_LTC

        return ValidationResult(
            passed=passed,
            item_name="loan_to_cost",
            rule="pf_check:loan_to_cost_plausibility",
            message=(
                f"loan_to_cost {float(ltc):.1%} ≤ 90% ✓"
                if passed
                else f"PF loan_to_cost {float(ltc):.1%} > 90% in period {period}"
                f" — verify debt quantum or total investment figure"
            ),
            severity="warning",
            actual_value=ltc,
            expected_value=MAX_LTC,
        )

    def _check_pf_cfae_consistency(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[PF-4] cfae consistency: extracted cfae vs. computed cfads - debt_service.

        CFAE (Cash Flow Available for Equity) = CFADS - Debt Service.
        If both the extracted cfae and the inputs (cfads, debt_service) are
        present, any divergence > 2% signals a model arithmetic error or a
        different CFAE definition in the source model.
        """
        cfae_extracted = data.get("cfae")
        cfads = data.get("cfads")
        ds = data.get("debt_service")

        if cfae_extracted is None or cfads is None or ds is None:
            return None

        cfae_computed = cfads - abs(ds)
        divisor = float(max(abs(cfae_extracted), abs(cfae_computed), Decimal("1")))
        diff_pct = abs(float(cfae_extracted - cfae_computed)) / divisor
        passed = diff_pct <= self.TOLERANCE_CFAE_CONSISTENCY

        return ValidationResult(
            passed=passed,
            item_name="cfae",
            rule="pf_check:cfae_consistency",
            message=(
                f"✓ cfae consistent with cfads - debt_service (computed={float(cfae_computed):.0f})"
                if passed
                else f"cfae ({float(cfae_extracted):.0f}) diverges from"
                f" cfads ({float(cfads):.0f}) - debt_service ({float(ds):.0f})"
                f" = {float(cfae_computed):.0f}"
                f" ({diff_pct:.1%} divergence) in period {period}"
            ),
            severity="warning",
            actual_value=cfae_extracted,
            expected_value=Decimal(str(round(float(cfae_computed), 0))),
        )

    def _check_pf_llcr_vs_dscr(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[PF-8] llcr >= dscr_project_finance.

        For amortising project finance debt, the Loan Life Coverage Ratio (LLCR)
        represents the NPV of all future CFADS divided by the outstanding debt —
        it should always be >= the point-in-time DSCR.  An LLCR below the current
        DSCR signals that the project cannot fully service debt over its remaining
        loan life.
        """
        llcr = data.get("llcr")
        dscr = data.get("dscr_project_finance") or data.get("dscr")

        if llcr is None or dscr is None:
            return None

        passed = llcr >= dscr

        return ValidationResult(
            passed=passed,
            item_name="llcr",
            rule="pf_check:llcr_vs_dscr",
            message=(
                f"✓ llcr ({float(llcr):.3f}x) >= dscr ({float(dscr):.3f}x)"
                if passed
                else f"llcr ({float(llcr):.3f}x) < dscr ({float(dscr):.3f}x)"
                f" in period {period}"
                f" — loan life coverage insufficient relative to point-in-time coverage"
            ),
            severity="warning",
            actual_value=llcr,
            expected_value=dscr,
        )

    def _check_pf_plcr_vs_llcr(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[PF-9] plcr >= llcr.

        The Project Life Coverage Ratio (PLCR) — NPV of CFADS over the full
        project life — should be >= the Loan Life Coverage Ratio (LLCR) because
        the project life extends beyond the loan maturity.  PLCR < LLCR is a
        structural inconsistency in the financial model.
        """
        plcr = data.get("plcr")
        llcr = data.get("llcr")

        if plcr is None or llcr is None:
            return None

        passed = plcr >= llcr

        return ValidationResult(
            passed=passed,
            item_name="plcr",
            rule="pf_check:plcr_vs_llcr",
            message=(
                f"✓ plcr ({float(plcr):.3f}x) >= llcr ({float(llcr):.3f}x)"
                if passed
                else f"plcr ({float(plcr):.3f}x) < llcr ({float(llcr):.3f}x)"
                f" in period {period}"
                f" — project life coverage should exceed loan life coverage"
            ),
            severity="warning",
            actual_value=plcr,
            expected_value=llcr,
        )

    def _check_pf_dsra_adequacy(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[PF-10] dsra_balance >= 1× debt_service (minimum reserve adequacy).

        The Debt Service Reserve Account (DSRA) must hold at least one period's
        worth of debt service.  Accounts holding less than that are under-funded
        relative to the minimum required reserve (typically 6 months to 12 months
        in practice; this check uses 1× as a conservative floor).
        Uses 5% tolerance to absorb minor investment return accruals.
        """
        dsra = data.get("dsra_balance")
        ds = data.get("debt_service")

        if dsra is None or ds is None or ds == 0:
            return None

        required = abs(ds)
        # Passed if dsra >= required within tolerance
        passed = dsra >= required * Decimal(str(1 - self.TOLERANCE_DSRA_RESERVE))

        return ValidationResult(
            passed=passed,
            item_name="dsra_balance",
            rule="pf_check:dsra_adequacy",
            message=(
                f"✓ dsra_balance ({float(dsra):.0f}) >= 1× debt_service ({float(required):.0f})"
                if passed
                else f"dsra_balance ({float(dsra):.0f}) < required 1×"
                f" debt_service ({float(required):.0f})"
                f" — DSRA under-funded in period {period}"
            ),
            severity="warning",
            actual_value=dsra,
            expected_value=required,
        )

    def _check_pf_equity_irr_plausibility(
        self,
        period: str,
        data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """[PF-11] equity_irr plausibility: expected range 3% to 40%.

        Project equity IRRs below 3% are implausibly low (below risk-free rate)
        and typically indicate a data error (wrong scale, wrong sign, or a model
        that has not been run to completion).  IRRs above 40% are unusually high
        for infrastructure / project finance and warrant verification.
        The check is applied at any period where equity_irr is extracted.
        """
        irr = data.get("equity_irr")
        if irr is None:
            return None

        # Normalise: values > 1.0 are assumed to be in percentage form (e.g., 15.0 = 15%)
        irr_decimal = irr / Decimal("100") if abs(irr) > Decimal("1") else irr

        MIN_IRR = Decimal("0.03")
        MAX_IRR = Decimal("0.40")
        passed = MIN_IRR <= irr_decimal <= MAX_IRR

        return ValidationResult(
            passed=passed,
            item_name="equity_irr",
            rule="pf_check:equity_irr_plausibility",
            message=(
                f"✓ equity_irr {float(irr_decimal):.1%} within plausible range (3%–40%)"
                if passed
                else f"equity_irr {float(irr_decimal):.1%} outside plausible range (3%–40%)"
                f" in period {period}"
                f" — verify scale, sign, or model completion"
            ),
            severity="warning",
            actual_value=irr_decimal,
            expected_value=f"{float(MIN_IRR):.0%} to {float(MAX_IRR):.0%}",  # type: ignore[arg-type]
        )
