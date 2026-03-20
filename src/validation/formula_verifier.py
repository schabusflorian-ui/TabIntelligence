"""Excel formula verification for extracted financial data.

Verifies that extracted values match the results of Excel formulas
captured during parsing. Supports simple SUM ranges and basic arithmetic
formulas. Complex formulas (VLOOKUP, IF, INDEX, etc.) are marked
as unresolvable rather than producing false negatives.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

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
_NEGATED_SUM_PATTERN = re.compile(
    r"^=-SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)$", re.IGNORECASE
)
_SUM_LIST_PATTERN = re.compile(
    r"^=-?SUM\(([A-Z]+\d+(?:,[A-Z]+\d+)+)\)$", re.IGNORECASE
)
_AGGREGATE_PATTERN = re.compile(
    r"^=-?(MAX|MIN|AVERAGE)\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)$", re.IGNORECASE
)
_ABS_PATTERN = re.compile(r"^=ABS\((.+)\)$", re.IGNORECASE)
_ROUND_PATTERN = re.compile(r"^=ROUND\((.+),\s*(\d+)\)$", re.IGNORECASE)

_CELL_REF = re.compile(r"[A-Z]+\d+", re.IGNORECASE)
_INLINE_FUNC = re.compile(
    r"(SUM|MAX|MIN|AVERAGE)\(([A-Z]+\d+):([A-Z]+\d+)\)", re.IGNORECASE
)
_COMPLEX_FUNCTIONS = re.compile(
    r"(VLOOKUP|HLOOKUP|INDEX|MATCH|IF|IFERROR|INDIRECT|OFFSET|SUMIF|COUNTIF|"
    r"SUMPRODUCT|MOD|POWER|SQRT|LOG|LN|EXP|"
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

                # Build period-keyed lookup (matches cell_reconciliation pattern)
                value_cell_lookup: Dict[str, Dict] = {}
                for sc in source_cells:
                    sc_period = sc.get("period")
                    if sc_period is not None:
                        value_cell_lookup[sc_period] = sc

                # Fallback to positional matching for old data without period keys
                use_positional = not value_cell_lookup
                if use_positional:
                    value_cells = source_cells[1:] if len(source_cells) > 1 else []
                    cell_idx = 0

                for period, value in values.items():
                    if value is None:
                        continue

                    if use_positional:
                        if cell_idx >= len(value_cells):
                            break
                        sc = value_cells[cell_idx]
                        cell_idx += 1
                    else:
                        sc = value_cell_lookup.get(period)
                        if sc is None:
                            continue

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
        # Normalize: strip $ from absolute references ($C$10 → C10)
        formula = formula.replace("$", "")

        _unresolvable = FormulaCheckResult(
            canonical_name=canonical, period=period, cell_ref=cell_ref,
            formula=formula, extracted_value=extracted, computed_value=None,
            matched=False, reason="unresolvable",
        )

        # Check for complex/unsupported formulas first
        if _COMPLEX_FUNCTIONS.search(formula):
            return _unresolvable

        # Try ABS wrapper: =ABS(...)
        abs_match = _ABS_PATTERN.match(formula)
        if abs_match:
            inner = "=" + abs_match.group(1)
            inner_result = self._verify_formula(
                canonical, period, cell_ref, inner, extracted,
                sheet_name, cell_lookup,
            )
            if inner_result.computed_value is not None:
                computed = abs(inner_result.computed_value)
                return self._compare(canonical, period, cell_ref, formula, extracted, computed)
            return _unresolvable

        # Try ROUND wrapper: =ROUND(expr, n)
        round_match = _ROUND_PATTERN.match(formula)
        if round_match:
            inner = "=" + round_match.group(1)
            ndigits = int(round_match.group(2))
            inner_result = self._verify_formula(
                canonical, period, cell_ref, inner, extracted,
                sheet_name, cell_lookup,
            )
            if inner_result.computed_value is not None:
                rounded = round(inner_result.computed_value, ndigits)
                return self._compare(
                    canonical, period, cell_ref, formula, extracted, Decimal(str(rounded)),
                )
            return _unresolvable

        # Try negated SUM: =-SUM(range)
        neg_sum = _NEGATED_SUM_PATTERN.match(formula)
        if neg_sum:
            computed = self._resolve_sum(
                neg_sum.group(1), int(neg_sum.group(2)),
                neg_sum.group(3), int(neg_sum.group(4)),
                sheet_name, cell_lookup,
            )
            if computed is not None:
                return self._compare(canonical, period, cell_ref, formula, extracted, -computed)
            return _unresolvable

        # Try standard SUM: =SUM(range)
        sum_match = _SUM_PATTERN.match(formula)
        if sum_match:
            computed = self._resolve_sum(
                sum_match.group(1), int(sum_match.group(2)),
                sum_match.group(3), int(sum_match.group(4)),
                sheet_name, cell_lookup,
            )
            if computed is not None:
                return self._compare(canonical, period, cell_ref, formula, extracted, computed)
            return _unresolvable

        # Try non-contiguous SUM: =SUM(A1,B1,C1) or =-SUM(A1,B1,C1)
        sum_list = _SUM_LIST_PATTERN.match(formula)
        if sum_list:
            computed = self._resolve_sum_list(
                sum_list.group(1), sheet_name, cell_lookup,
            )
            if computed is not None:
                if formula.startswith("=-"):
                    computed = -computed
                return self._compare(canonical, period, cell_ref, formula, extracted, computed)
            return _unresolvable

        # Try aggregate functions: MAX, MIN, AVERAGE over a range
        agg_match = _AGGREGATE_PATTERN.match(formula)
        if agg_match:
            func_name = agg_match.group(1).upper()
            computed = self._resolve_aggregate(
                func_name,
                agg_match.group(2), int(agg_match.group(3)),
                agg_match.group(4), int(agg_match.group(5)),
                sheet_name, cell_lookup,
            )
            if computed is not None:
                if formula.startswith("=-"):
                    computed = -computed
                return self._compare(canonical, period, cell_ref, formula, extracted, computed)
            return _unresolvable

        # Try simple arithmetic: =A1+B2-C3 or =A1*B2
        computed = self._resolve_arithmetic(formula, sheet_name, cell_lookup)
        if computed is not None:
            return self._compare(canonical, period, cell_ref, formula, extracted, computed)

        return _unresolvable

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

    def _resolve_sum_list(
        self,
        cell_list_str: str,
        sheet_name: str,
        cell_lookup: Dict[Tuple[str, str], float],
    ) -> Optional[Decimal]:
        """Resolve =SUM(A1,B1,C1) by looking up each individual cell."""
        refs = [r.strip() for r in cell_list_str.split(",")]
        total = Decimal("0")
        found_any = False
        for ref in refs:
            val = cell_lookup.get((sheet_name, ref.upper()))
            if val is None:
                return None  # all cells must be resolvable
            total += Decimal(str(val))
            found_any = True
        return total if found_any else None

    def _resolve_aggregate(
        self,
        func_name: str,
        start_col: str, start_row: int,
        end_col: str, end_row: int,
        sheet_name: str,
        cell_lookup: Dict[Tuple[str, str], float],
    ) -> Optional[Decimal]:
        """Resolve MAX/MIN/AVERAGE over a cell range."""
        values: List[Decimal] = []
        if start_col.upper() == end_col.upper():
            # Column range
            for row_num in range(start_row, end_row + 1):
                ref = f"{start_col.upper()}{row_num}"
                val = cell_lookup.get((sheet_name, ref))
                if val is not None:
                    values.append(Decimal(str(val)))
        else:
            if start_row != end_row:
                return None  # 2D range unsupported
            col_start = _col_to_num(start_col)
            col_end = _col_to_num(end_col)
            for col_num in range(col_start, col_end + 1):
                col_letter = _num_to_col(col_num)
                ref = f"{col_letter}{start_row}"
                val = cell_lookup.get((sheet_name, ref))
                if val is not None:
                    values.append(Decimal(str(val)))

        if not values:
            return None

        if func_name == "MAX":
            return max(values)
        elif func_name == "MIN":
            return min(values)
        elif func_name == "AVERAGE":
            return sum(values) / len(values)
        return None

    def _resolve_arithmetic(
        self,
        formula: str,
        sheet_name: str,
        cell_lookup: Dict[Tuple[str, str], float],
    ) -> Optional[Decimal]:
        """Resolve arithmetic formulas, including those with inline functions.

        Handles patterns like =A1+B2-C3, =A1*B2^3, and =SUM(A1:A5)*B1.
        Inline SUM/MAX/MIN/AVERAGE calls are resolved first, then the
        resulting expression is evaluated as pure arithmetic.
        """
        if not formula.startswith("="):
            return None

        expr = formula[1:]  # strip leading =

        # Resolve inline function calls: SUM(A1:A5), MAX(B1:B3), etc.
        # Replace each with its computed numeric value
        while True:
            match = _INLINE_FUNC.search(expr)
            if not match:
                break
            func_name = match.group(1).upper()
            start_ref = match.group(2).upper()
            end_ref = match.group(3).upper()
            start_col = re.match(r"([A-Z]+)", start_ref).group(1)
            start_row = int(re.search(r"(\d+)", start_ref).group(1))
            end_col = re.match(r"([A-Z]+)", end_ref).group(1)
            end_row = int(re.search(r"(\d+)", end_ref).group(1))
            if func_name == "SUM":
                val = self._resolve_sum(
                    start_col, start_row, end_col, end_row,
                    sheet_name, cell_lookup,
                )
            else:
                val = self._resolve_aggregate(
                    func_name, start_col, start_row, end_col, end_row,
                    sheet_name, cell_lookup,
                )
            if val is None:
                return None
            expr = expr[:match.start()] + str(val) + expr[match.end():]

        # Check if it only contains cell refs, numbers, and +/-/*
        refs = _CELL_REF.findall(expr)
        if not refs and not re.search(r'\d', expr):
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
            # Only allow digits, decimal points, +, -, *, /, ^, spaces, parens
            if not re.match(r'^[\d\.\+\-\*/\^\s\(\)eE]+$', resolved):
                return None
            # Convert Excel ^ (power) to Python **
            resolved = resolved.replace("^", "**")
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
