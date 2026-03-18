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

            results.append(
                ValidationResult(
                    passed=not violation,
                    item_name=canonical_name,
                    rule="sign_convention",
                    message=msg if violation else f"✓ {canonical_name} sign OK",
                    severity="warning",
                    actual_value=value,
                    expected_value=typical_sign,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Cross-Statement Validation (Part C)
    # ------------------------------------------------------------------

    CROSS_STATEMENT_TOLERANCE = 0.05  # 5% tolerance for cross-statement checks

    # Debt components to sum for total_debt reconciliation
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
        passed = diff_pct <= self.CROSS_STATEMENT_TOLERANCE

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
        divisor = float(max(abs(re_change), abs(net_income), 1))  # type: ignore[arg-type]
        diff_pct = abs(float(re_change - net_income)) / divisor
        passed = diff_pct <= self.CROSS_STATEMENT_TOLERANCE

        return ValidationResult(
            passed=passed,
            item_name="retained_earnings",
            rule="cross_statement:retained_earnings_ni",
            message=(
                "✓ retained_earnings change matches net_income"
                if passed
                else f"retained_earnings change ({re_change})"
                f" differs from net_income ({net_income})"
                f" in period {period}"
            ),
            severity="warning",
            actual_value=re_change,
            expected_value=net_income,
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
        passed = diff_pct <= self.CROSS_STATEMENT_TOLERANCE

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
        passed = diff_pct <= self.CROSS_STATEMENT_TOLERANCE

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
        wider_tolerance = 0.10  # 10% for capex/PPE reconciliation
        passed = diff_pct <= wider_tolerance

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
        passed = diff_pct <= self.CROSS_STATEMENT_TOLERANCE

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
        wider_tolerance = 0.10  # 10% for IS↔DS reconciliation
        passed = diff_pct <= wider_tolerance

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

    def _check_equity_reconciliation(
        self,
        period: str,
        data: Dict[str, Decimal],
        prev_data: Dict[str, Decimal],
    ) -> Optional[ValidationResult]:
        """equity[t] ≈ equity[t-1] + net_income - dividends (5% tolerance)."""
        eq_curr = data.get("total_equity")
        eq_prev = prev_data.get("total_equity")
        net_income = data.get("net_income")

        if eq_curr is None or eq_prev is None or net_income is None:
            return None

        dividends = data.get("dividends_paid", Decimal("0"))
        expected = eq_prev + net_income - abs(dividends)
        divisor = float(max(abs(eq_curr), abs(expected), 1))
        diff_pct = abs(float(eq_curr - expected)) / divisor
        passed = diff_pct <= self.CROSS_STATEMENT_TOLERANCE

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
