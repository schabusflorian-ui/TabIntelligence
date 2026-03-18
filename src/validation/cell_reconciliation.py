"""Cell-level ground truth reconciliation for extracted financial data.

Compares extracted values against their source Excel cell raw values,
accounting for unit multipliers. This verifies that the extraction pipeline
faithfully preserved the numbers from the original spreadsheet.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from src.core.logging import extraction_logger as logger


@dataclass
class CellMatchResult:
    """Result of comparing a single extracted value against its source cell."""

    canonical_name: str
    period: str
    extracted_value: Decimal
    source_cell_ref: str
    source_sheet: str
    source_raw_value: float
    matched: bool
    delta: Decimal
    delta_pct: Optional[float] = None
    unit_multiplier_applied: Decimal = Decimal("1")


@dataclass
class ReconciliationSummary:
    """Aggregate result of cell-level reconciliation."""

    total_cells: int
    matched: int
    mismatched: int
    unmatched: int  # extracted values with no source cell to compare
    match_rate: float  # matched / total_cells (0.0 to 1.0)
    mismatches: List[CellMatchResult] = field(default_factory=list)
    unmatched_items: List[Dict[str, Any]] = field(default_factory=list)


class CellReconciliationValidator:
    """Validates extracted values against source Excel cell raw values."""

    ABSOLUTE_TOLERANCE = Decimal("0.01")
    RELATIVE_TOLERANCE = 0.001  # 0.1%

    def reconcile(
        self,
        parsed: Dict,
        mappings: List[Dict],
        triage: List[Dict],
        structured: Optional[Dict] = None,
    ) -> ReconciliationSummary:
        """Reconcile extracted values against source cells.

        Mirrors _build_extracted_values() iteration order to pair each
        extracted value with its corresponding source cell from openpyxl.

        Args:
            parsed: Parsed sheet data from Stage 1.
            mappings: Label-to-canonical mappings from Stage 3.
            triage: Sheet triage results from Stage 2.
            structured: Optional structured Excel data with unit multipliers.

        Returns:
            ReconciliationSummary with match statistics and mismatch details.
        """
        # Build mapping lookup (same as validation.py:426)
        mapping_lookup = {m["original_label"]: m["canonical_name"] for m in mappings}

        # Identify processable sheets — tier 1-3 (same as validation.py:429)
        processable = {t["sheet_name"] for t in triage if t.get("tier", 4) <= 3}

        # Build per-sheet unit multiplier lookup (same as validation.py:432-441)
        multiplier_lookup: Dict[str, Decimal] = {}
        if structured:
            for sheet in structured.get("sheets", []):
                name = sheet.get("sheet_name", "")
                mult = sheet.get("unit_multiplier")
                if mult is not None and mult != 1 and mult != 1.0:
                    try:
                        multiplier_lookup[name] = Decimal(str(mult))
                    except (ValueError, ArithmeticError):
                        pass

        matches: List[CellMatchResult] = []
        mismatches: List[CellMatchResult] = []
        unmatched_items: List[Dict[str, Any]] = []

        for sheet in parsed.get("sheets", []):
            sheet_name = sheet.get("sheet_name", "")
            if sheet_name not in processable:
                continue

            sheet_multiplier = multiplier_lookup.get(sheet_name, Decimal("1"))

            for row in sheet.get("rows", []):
                label = row.get("label", "")
                canonical = mapping_lookup.get(label)
                if not canonical or canonical == "unmapped":
                    continue

                source_cells = row.get("source_cells", [])
                values = row.get("values", {})

                # source_cells[0] is the label cell, source_cells[1:] are value cells
                # paired positionally with non-None entries from values.items()
                value_cells = source_cells[1:] if len(source_cells) > 1 else []
                cell_idx = 0

                for period, value in values.items():
                    if value is None:
                        continue

                    try:
                        extracted = Decimal(str(value))
                    except (ValueError, ArithmeticError, InvalidOperation):
                        continue

                    if cell_idx < len(value_cells):
                        sc = value_cells[cell_idx]
                        cell_idx += 1

                        raw_value = sc.get("raw_value")
                        if raw_value is None or not isinstance(raw_value, (int, float)):
                            unmatched_items.append({
                                "canonical_name": canonical,
                                "period": period,
                                "extracted_value": str(extracted),
                                "reason": "non_numeric_source_cell",
                            })
                            continue

                        try:
                            source_decimal = Decimal(str(raw_value))
                        except (ValueError, ArithmeticError, InvalidOperation):
                            continue

                        # Both extracted and source should be compared
                        # at the same scale (pre-multiplier)
                        delta = abs(extracted - source_decimal)

                        # Check dual tolerance
                        abs_ok = delta <= self.ABSOLUTE_TOLERANCE
                        divisor = max(abs(source_decimal), Decimal("1"))
                        rel_diff = float(delta / divisor)
                        rel_ok = rel_diff <= self.RELATIVE_TOLERANCE
                        matched = abs_ok or rel_ok

                        delta_pct = float(delta / divisor) if source_decimal != 0 else None

                        result = CellMatchResult(
                            canonical_name=canonical,
                            period=period,
                            extracted_value=extracted,
                            source_cell_ref=sc.get("cell_ref", ""),
                            source_sheet=sc.get("sheet", sheet_name),
                            source_raw_value=float(raw_value),
                            matched=matched,
                            delta=delta,
                            delta_pct=delta_pct,
                            unit_multiplier_applied=sheet_multiplier,
                        )

                        if matched:
                            matches.append(result)
                        else:
                            mismatches.append(result)
                    else:
                        unmatched_items.append({
                            "canonical_name": canonical,
                            "period": period,
                            "extracted_value": str(extracted),
                            "reason": "no_source_cell",
                        })

        total = len(matches) + len(mismatches)
        match_rate = len(matches) / total if total > 0 else 1.0

        if mismatches:
            logger.info(
                f"Cell reconciliation: {len(matches)}/{total} matched, "
                f"{len(mismatches)} mismatches, {len(unmatched_items)} unmatched"
            )

        return ReconciliationSummary(
            total_cells=total,
            matched=len(matches),
            mismatched=len(mismatches),
            unmatched=len(unmatched_items),
            match_rate=match_rate,
            mismatches=mismatches,
            unmatched_items=unmatched_items,
        )
