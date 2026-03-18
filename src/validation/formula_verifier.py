"""Excel formula verification for extracted financial data.

Verifies that extracted values match the results of Excel formulas
captured during parsing. Supports simple SUM ranges and basic arithmetic
formulas. Complex formulas (VLOOKUP, IF, INDEX, etc.) are marked
as unresolvable rather than producing false negatives.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from src.core.logging import extraction_logger as logger


@dataclass
class FormulaCheckResult:
    """Result of verifying a single formula cell."""

    canonical_name: str
    period: str
    cell_ref: str
    formula: str
    extracted_value: Decimal
    computed_value: Optional[Decimal]
    matched: bool
    reason: str  # "verified", "mismatch", "unresolvable"


@dataclass
class FormulaVerificationSummary:
    """Aggregate result of formula verification."""

    total_formulas: int
    verified: int
    mismatched: int
    unresolvable: int
    results: List[FormulaCheckResult] = field(default_factory=list)


# Patterns for parseable formula types
_SUM_PATTERN = re.compile(
    r"^=SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)$", re.IGNORECASE
)
_CELL_REF = re.compile(r"[A-Z]+\d+", re.IGNORECASE)
_COMPLEX_FUNCTIONS = re.compile(
    r"(VLOOKUP|HLOOKUP|INDEX|MATCH|IF|IFERROR|INDIRECT|OFFSET|SUMIF|COUNTIF|"
    r"SUMPRODUCT|ROUND|MAX|MIN|AVERAGE|ABS|MOD|POWER|SQRT|LOG|LN|EXP|"
    r"LEFT|RIGHT|MID|LEN|CONCATENATE|TEXT|VALUE|DATE|YEAR|MONTH|DAY)",
    re.IGNORECASE,
)


class FormulaVerifier:
    """Verifies Excel formulas against extracted values."""

    ABSOLUTE_TOLERANCE = Decimal("0.01")
    RELATIVE_TOLERANCE = 0.001  # 0.1%

    def verify(
        self,
        parsed: Dict,
        mappings: List[Dict],
        triage: List[Dict],
        structured: Optional[Dict] = None,
    ) -> FormulaVerificationSummary:
        """Verify formulas in source cells against extracted values.

        Args:
            parsed: Parsed sheet data from Stage 1.
            mappings: Label-to-canonical mappings from Stage 3.
            triage: Sheet triage results from Stage 2.
            structured: Optional structured Excel data.

        Returns:
            FormulaVerificationSummary with verification statistics.
        """
        mapping_lookup = {m["original_label"]: m["canonical_name"] for m in mappings}
        processable = {t["sheet_name"] for t in triage if t.get("tier", 4) <= 3}

        # Build cell-value lookup: {(sheet, cell_ref): raw_value}
        cell_lookup: Dict[Tuple[str, str], float] = {}
        for sheet in parsed.get("sheets", []):
            sheet_name = sheet.get("sheet_name", "")
            for row in sheet.get("rows", []):
                for sc in row.get("source_cells", []):
                    raw = sc.get("raw_value")
                    if isinstance(raw, (int, float)):
                        cell_lookup[(sheet_name, sc.get("cell_ref", ""))] = raw

        results: List[FormulaCheckResult] = []

        for sheet in parsed.get("sheets", []):
            sheet_name = sheet.get("sheet_name", "")
            if sheet_name not in processable:
                continue

            for row in sheet.get("rows", []):
                label = row.get("label", "")
                canonical = mapping_lookup.get(label)
                if not canonical or canonical == "unmapped":
                    continue

                source_cells = row.get("source_cells", [])
                values = row.get("values", {})
                value_cells = source_cells[1:] if len(source_cells) > 1 else []
                cell_idx = 0

                for period, value in values.items():
                    if value is None:
                        continue

                    if cell_idx >= len(value_cells):
                        break

                    sc = value_cells[cell_idx]
                    cell_idx += 1

                    formula = sc.get("formula")
                    if not formula:
                        continue

                    try:
                        extracted = Decimal(str(value))
                    except (ValueError, ArithmeticError, InvalidOperation):
                        continue

                    result = self._verify_formula(
                        canonical, period, sc.get("cell_ref", ""),
                        formula, extracted, sheet_name, cell_lookup,
                    )
                    results.append(result)

        verified = sum(1 for r in results if r.reason == "verified")
        mismatched = sum(1 for r in results if r.reason == "mismatch")
        unresolvable = sum(1 for r in results if r.reason == "unresolvable")

        if mismatched:
            logger.info(
                f"Formula verification: {verified} verified, "
                f"{mismatched} mismatches, {unresolvable} unresolvable"
            )

        return FormulaVerificationSummary(
            total_formulas=len(results),
            verified=verified,
            mismatched=mismatched,
            unresolvable=unresolvable,
            results=results,
        )

    def _verify_formula(
        self,
        canonical: str,
        period: str,
        cell_ref: str,
        formula: str,
        extracted: Decimal,
        sheet_name: str,
        cell_lookup: Dict[Tuple[str, str], float],
    ) -> FormulaCheckResult:
        """Verify a single formula against the extracted value."""
        # Check for complex/unsupported formulas first
        if _COMPLEX_FUNCTIONS.search(formula):
            return FormulaCheckResult(
                canonical_name=canonical, period=period, cell_ref=cell_ref,
                formula=formula, extracted_value=extracted, computed_value=None,
                matched=False, reason="unresolvable",
            )

        # Try SUM pattern
        sum_match = _SUM_PATTERN.match(formula)
        if sum_match:
            computed = self._resolve_sum(
                sum_match.group(1), int(sum_match.group(2)),
                sum_match.group(3), int(sum_match.group(4)),
                sheet_name, cell_lookup,
            )
            if computed is not None:
                return self._compare(canonical, period, cell_ref, formula, extracted, computed)
            return FormulaCheckResult(
                canonical_name=canonical, period=period, cell_ref=cell_ref,
                formula=formula, extracted_value=extracted, computed_value=None,
                matched=False, reason="unresolvable",
            )

        # Try simple arithmetic: =A1+B2-C3 or =A1*B2
        computed = self._resolve_arithmetic(formula, sheet_name, cell_lookup)
        if computed is not None:
            return self._compare(canonical, period, cell_ref, formula, extracted, computed)

        return FormulaCheckResult(
            canonical_name=canonical, period=period, cell_ref=cell_ref,
            formula=formula, extracted_value=extracted, computed_value=None,
            matched=False, reason="unresolvable",
        )

    def _resolve_sum(
        self,
        start_col: str, start_row: int,
        end_col: str, end_row: int,
        sheet_name: str,
        cell_lookup: Dict[Tuple[str, str], float],
    ) -> Optional[Decimal]:
        """Resolve =SUM(A1:A10) by looking up each cell in the range."""
        if start_col.upper() != end_col.upper():
            # Row-based SUM (e.g., =SUM(A1:D1)) — resolve across columns
            col_start = _col_to_num(start_col)
            col_end = _col_to_num(end_col)
            if start_row != end_row:
                return None  # 2D range, can't resolve
            total = Decimal("0")
            found_any = False
            for col_num in range(col_start, col_end + 1):
                col_letter = _num_to_col(col_num)
                ref = f"{col_letter}{start_row}"
                val = cell_lookup.get((sheet_name, ref))
                if val is not None:
                    total += Decimal(str(val))
                    found_any = True
            return total if found_any else None

        # Column-based SUM (e.g., =SUM(B5:B10))
        total = Decimal("0")
        found_any = False
        for row_num in range(start_row, end_row + 1):
            ref = f"{start_col.upper()}{row_num}"
            val = cell_lookup.get((sheet_name, ref))
            if val is not None:
                total += Decimal(str(val))
                found_any = True
        return total if found_any else None

    def _resolve_arithmetic(
        self,
        formula: str,
        sheet_name: str,
        cell_lookup: Dict[Tuple[str, str], float],
    ) -> Optional[Decimal]:
        """Resolve simple arithmetic formulas like =A1+B2-C3."""
        if not formula.startswith("="):
            return None

        expr = formula[1:]  # strip leading =

        # Check if it only contains cell refs, numbers, and +/-/*
        refs = _CELL_REF.findall(expr)
        if not refs:
            return None

        # Replace cell refs with their values
        resolved = expr
        for ref in refs:
            val = cell_lookup.get((sheet_name, ref.upper()))
            if val is None:
                return None
            resolved = resolved.replace(ref, str(val), 1)

        # Evaluate the expression safely
        try:
            # Only allow digits, decimal points, +, -, *, /, spaces, parens
            if not re.match(r'^[\d\.\+\-\*/\s\(\)]+$', resolved):
                return None
            result = eval(resolved)  # noqa: S307 — input is sanitized
            return Decimal(str(result))
        except Exception:
            return None

    def _compare(
        self,
        canonical: str,
        period: str,
        cell_ref: str,
        formula: str,
        extracted: Decimal,
        computed: Decimal,
    ) -> FormulaCheckResult:
        """Compare extracted value against computed formula result."""
        delta = abs(extracted - computed)
        divisor = max(abs(computed), Decimal("1"))
        abs_ok = delta <= self.ABSOLUTE_TOLERANCE
        rel_ok = float(delta / divisor) <= self.RELATIVE_TOLERANCE
        matched = abs_ok or rel_ok

        return FormulaCheckResult(
            canonical_name=canonical,
            period=period,
            cell_ref=cell_ref,
            formula=formula,
            extracted_value=extracted,
            computed_value=computed,
            matched=matched,
            reason="verified" if matched else "mismatch",
        )


def _col_to_num(col: str) -> int:
    """Convert column letter(s) to 1-based number. A=1, B=2, ..., Z=26, AA=27."""
    num = 0
    for c in col.upper():
        num = num * 26 + (ord(c) - ord("A") + 1)
    return num


def _num_to_col(num: int) -> str:
    """Convert 1-based number to column letter(s). 1=A, 26=Z, 27=AA."""
    result = ""
    while num > 0:
        num, remainder = divmod(num - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result
