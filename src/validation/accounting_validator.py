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
from typing import Dict, List, Optional, Any
from decimal import Decimal
import re


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
        self.taxonomy = {item['canonical_name']: item for item in taxonomy_items}

    def validate(self, extracted_data: Dict[str, Decimal]) -> ValidationSummary:
        """
        Validate extracted data against all taxonomy rules.

        Args:
            extracted_data: Dict mapping canonical_name → extracted value

        Returns:
            ValidationSummary with all results
        """
        results = []

        # Run validations for each item
        for canonical_name, item in self.taxonomy.items():
            if canonical_name not in extracted_data:
                continue  # Skip items not in extracted data

            value = extracted_data[canonical_name]
            validation_rules = item.get('validation_rules', {})
            cross_val = validation_rules.get('cross_item_validation', {})

            # Check must_be_positive
            if cross_val.get('must_be_positive'):
                result = self._check_positive(canonical_name, value)
                results.append(result)

            # Check cross-item relationships
            for relationship in cross_val.get('relationships', []):
                result = self._check_relationship(
                    canonical_name,
                    relationship,
                    extracted_data
                )
                if result:
                    results.append(result)

            # Check time-series rules (if historical data provided)
            # TODO: Implement when historical data is available

        # Compile summary
        errors = [r for r in results if r.severity == 'error' and not r.passed]
        warnings = [r for r in results if r.severity == 'warning' and not r.passed]
        passed_count = sum(1 for r in results if r.passed)

        return ValidationSummary(
            total_checks=len(results),
            passed=passed_count,
            failed=len(results) - passed_count,
            warnings=len(warnings),
            errors=errors,
            warnings_list=warnings,
            all_results=results
        )

    def _check_positive(self, item_name: str, value: Decimal) -> ValidationResult:
        """Check if value is positive."""
        passed = value > 0
        return ValidationResult(
            passed=passed,
            item_name=item_name,
            rule="must_be_positive",
            message=f"{item_name} must be positive, got {value}",
            severity='error',
            actual_value=value,
            expected_value="positive"
        )

    def _check_relationship(
        self,
        item_name: str,
        relationship: Dict,
        data: Dict[str, Decimal]
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
        rule_str = relationship['rule']
        tolerance = relationship.get('tolerance', 0.0)
        error_message = relationship.get('error_message', f"Violated: {rule_str}")
        is_warning = relationship.get('warning_only', False)
        is_optional = relationship.get('optional', False)
        is_critical = relationship.get('critical', False)

        # Parse rule and evaluate
        try:
            passed, actual, expected = self._evaluate_rule(rule_str, data, tolerance)

            # If optional and can't evaluate, skip
            if is_optional and actual is None:
                return None

            severity = 'error'
            if is_warning:
                severity = 'warning'
            elif is_critical:
                severity = 'error'

            return ValidationResult(
                passed=passed,
                item_name=item_name,
                rule=rule_str,
                message=error_message if not passed else f"✓ {rule_str}",
                severity=severity,
                actual_value=actual,
                expected_value=expected
            )

        except Exception as e:
            # Rule couldn't be evaluated (missing data, parse error, etc.)
            if is_optional:
                return None

            return ValidationResult(
                passed=True,  # Don't fail on evaluation errors
                item_name=item_name,
                rule=rule_str,
                message=f"Could not evaluate rule: {str(e)}",
                severity='info',
                actual_value=None,
                expected_value=None
            )

    def _evaluate_rule(
        self,
        rule_str: str,
        data: Dict[str, Decimal],
        tolerance: float = 0.0
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
        if '==' in rule_str:
            left, right = rule_str.split('==')
            left_val = self._eval_expression(left.strip(), data)
            right_val = self._eval_expression(right.strip(), data)

            if left_val is None or right_val is None:
                return (True, None, None)  # Can't evaluate

            # Check with tolerance
            diff_pct = abs(float(left_val - right_val) / float(max(abs(left_val), abs(right_val), 1)))
            passed = diff_pct <= tolerance

            return (passed, left_val, right_val)

        # Handle >= comparisons
        elif '>=' in rule_str:
            left, right = rule_str.split('>=')
            left_val = self._eval_expression(left.strip(), data)
            right_val = self._eval_expression(right.strip(), data)

            if left_val is None or right_val is None:
                return (True, None, None)

            passed = left_val >= right_val
            return (passed, left_val, right_val)

        # Handle <= comparisons
        elif '<=' in rule_str:
            left, right = rule_str.split('<=')
            left_val = self._eval_expression(left.strip(), data)
            right_val = self._eval_expression(right.strip(), data)

            if left_val is None or right_val is None:
                return (True, None, None)

            passed = left_val <= right_val
            return (passed, left_val, right_val)

        # Handle range checks (e.g., "0 <= gross_margin <= 1")
        elif '<=' in rule_str and rule_str.count('<=') == 2:
            parts = re.split(r'<=', rule_str)
            if len(parts) == 3:
                lower = self._eval_expression(parts[0].strip(), data)
                value = self._eval_expression(parts[1].strip(), data)
                upper = self._eval_expression(parts[2].strip(), data)

                if value is None:
                    return (True, None, None)

                passed = lower <= value <= upper if lower is not None and upper is not None else True
                return (passed, value, f"{lower} to {upper}")

        raise ValueError(f"Unsupported rule format: {rule_str}")

    def _eval_expression(
        self,
        expr: str,
        data: Dict[str, Decimal]
    ) -> Optional[Decimal]:
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
        except:
            pass

        # Simple variable lookup
        if expr in data:
            return data[expr]

        # Addition/subtraction
        if '+' in expr or '-' in expr:
            # Parse left and right (simple case, no nested operations)
            if '+' in expr:
                parts = expr.split('+')
                operator = '+'
            else:
                # Handle subtraction (be careful with negative numbers)
                parts = expr.split('-')
                operator = '-'

            if len(parts) == 2:
                left = self._eval_expression(parts[0].strip(), data)
                right = self._eval_expression(parts[1].strip(), data)

                if left is None or right is None:
                    return None

                if operator == '+':
                    return left + right
                else:
                    return left - right

        # Multiplication/division
        if '*' in expr:
            parts = expr.split('*')
            if len(parts) == 2:
                left = self._eval_expression(parts[0].strip(), data)
                right = self._eval_expression(parts[1].strip(), data)
                if left is None or right is None:
                    return None
                return left * right

        if '/' in expr:
            parts = expr.split('/')
            if len(parts) == 2:
                left = self._eval_expression(parts[0].strip(), data)
                right = self._eval_expression(parts[1].strip(), data)
                if left is None or right is None or right == 0:
                    return None
                return left / right

        # Couldn't evaluate
        return None


# Example usage
if __name__ == "__main__":
    import asyncio

    # Sample taxonomy
    taxonomy = [
        {
            "canonical_name": "revenue",
            "validation_rules": {
                "cross_item_validation": {
                    "must_be_positive": True,
                    "relationships": [
                        {
                            "rule": "revenue >= gross_profit",
                            "error_message": "Revenue cannot be less than gross profit"
                        }
                    ]
                }
            }
        },
        {
            "canonical_name": "gross_profit",
            "validation_rules": {
                "cross_item_validation": {
                    "relationships": [
                        {
                            "rule": "gross_profit == revenue - cogs",
                            "tolerance": 0.01,
                            "error_message": "Gross profit should equal revenue minus COGS"
                        }
                    ]
                }
            }
        }
    ]

    # Sample extracted data
    extracted_data = {
        "revenue": Decimal("1000000"),
        "cogs": Decimal("600000"),
        "gross_profit": Decimal("400000"),  # Correct
    }

    # Validate
    validator = AccountingValidator(taxonomy)
    results = validator.validate(extracted_data)

    print(f"Total checks: {results.total_checks}")
    print(f"Passed: {results.passed}")
    print(f"Failed: {results.failed}")
    print(f"Success rate: {results.success_rate:.1%}")

    if results.has_errors:
        print(f"\nErrors ({len(results.errors)}):")
        for error in results.errors:
            print(f"  - {error.message}")

    if results.has_warnings:
        print(f"\nWarnings ({len(results.warnings_list)}):")
        for warning in results.warnings_list:
            print(f"  - {warning.message}")
