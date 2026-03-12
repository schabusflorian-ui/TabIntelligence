"""Section detection for multi-statement sheets.

Detects logical sections within a single Excel sheet (e.g., Income Statement
rows 1-30, Balance Sheet rows 35-65) using structural signals: bold headers
preceded by blank rows, and large row-index gaps.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.core.logging import extraction_logger as logger


@dataclass
class SheetSection:
    """A detected logical section within a sheet."""

    label: str
    start_row: int
    end_row: int
    row_count: int
    category_hint: Optional[str]
    sample_labels: List[str]
    bold_labels: List[str]
    has_subtotals: bool
    formula_count: int


# Keyword map for deterministic category hints
_SECTION_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "income_statement": [
        "income statement",
        "profit & loss",
        "profit and loss",
        "p&l",
        "p/l",
        "pl statement",
        "i/s",
    ],
    "balance_sheet": [
        "balance sheet",
        "statement of financial position",
        "financial position",
        "b/s",
    ],
    "cash_flow": [
        "cash flow",
        "cash flows",
        "statement of cash",
        "c/f",
    ],
    "debt_schedule": [
        "debt schedule",
        "debt service",
        "loan",
        "facility",
        "borrowing",
    ],
}


def _guess_category(label: str) -> Optional[str]:
    """Guess financial statement category from a section header label.

    Uses substring matching on the lowercased label.
    Returns the first matching category or None.
    """
    label_lower = label.lower()
    for category, keywords in _SECTION_CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in label_lower:
                return category
    return None


def _get_label_cell_value(
    row: Dict[str, Any],
    label_column: str,
) -> Optional[str]:
    """Get the string value of the label cell in a row."""
    for cell in row.get("cells", []):
        ref = cell.get("ref", "")
        m = re.match(r"([A-Z]+)", ref)
        if m and m.group(1) == label_column:
            val = cell.get("value")
            if isinstance(val, str) and val.strip():
                return val.strip()
            return None
    return None


def _is_bold_label(row: Dict[str, Any], label_column: str) -> bool:
    """Check if the label cell in a row is bold."""
    for cell in row.get("cells", []):
        ref = cell.get("ref", "")
        m = re.match(r"([A-Z]+)", ref)
        if m and m.group(1) == label_column:
            return bool(cell.get("is_bold"))
    return False


def _is_full_width_bold(row: Dict[str, Any]) -> bool:
    """All cells in row are bold — indicates a separator/header row."""
    cells = row.get("cells", [])
    if len(cells) < 2:
        return False
    return all(cell.get("is_bold", False) for cell in cells)


def _dominant_fill(row: Dict[str, Any]) -> Optional[str]:
    """Return the dominant fill colour of a row, or None."""
    colors = [c.get("fill_color") for c in row.get("cells", []) if c.get("fill_color")]
    if not colors:
        return None
    from collections import Counter

    most_common, count = Counter(colors).most_common(1)[0]
    return most_common if count >= len(row.get("cells", [])) // 2 else None


def _has_distinct_fill(row: Dict[str, Any], prev_row: Optional[Dict[str, Any]]) -> bool:
    """Row has a fill colour that differs from the previous row."""
    curr_fill = _dominant_fill(row)
    if not curr_fill:
        return False
    if prev_row is None:
        return True
    return curr_fill != _dominant_fill(prev_row)


def _is_full_width_merge(row: Dict[str, Any]) -> bool:
    """Row is a single merged cell spanning multiple columns."""
    cells = row.get("cells", [])
    if len(cells) < 2:
        return False
    origins = {c.get("merge_origin") for c in cells if c.get("is_merged")}
    return len(origins) == 1


def _is_content_header_row(row: Dict[str, Any], label_column: str) -> bool:
    """Check if row looks like an unformatted section header.

    True when the label matches a known section keyword AND
    the row has no numeric values (distinguishes from data rows).
    """
    label = _get_label_cell_value(row, label_column)
    if not label or not _guess_category(label):
        return False
    for cell in row.get("cells", []):
        val = cell.get("value")
        if isinstance(val, (int, float)):
            return False
    return True


class SectionDetector:
    """Detect logical sections within a sheet using structural signals."""

    def detect_sections(self, sheet: Dict[str, Any]) -> List[SheetSection]:
        """Analyze a structured sheet dict and return detected sections.

        Uses two signals:
        1. Bold text boundaries: a bold string cell in the label column
           preceded by a gap (row_index difference >= 2 from previous row).
        2. Blank row gaps: 3+ gap between consecutive row indices
           (indicating 2+ blank rows).

        Returns a list of SheetSection. If fewer than 5 rows or no
        boundaries detected, returns a single section (or empty list
        for empty sheets).
        """
        rows = sheet.get("rows", [])
        if not rows:
            return []

        rows = sorted(rows, key=lambda r: r["row_index"])

        label_column = sheet.get("label_column") or "A"

        if len(rows) < 5:
            first_label = _get_label_cell_value(rows[0], label_column)
            return [
                self._build_section(
                    rows,
                    sheet,
                    label=first_label or "(single section)",
                )
            ]

        # Find boundary row indices
        boundary_indices: List[int] = [0]  # first row is always a boundary
        for i in range(1, len(rows)):
            gap = rows[i]["row_index"] - rows[i - 1]["row_index"]

            # Gap-only boundary: 2+ blank rows between data rows
            if gap >= 3:
                boundary_indices.append(i)
                continue

            # Bold boundary: bold label cell + gap >= 2
            if gap >= 2 and _is_bold_label(rows[i], label_column):
                label_val = _get_label_cell_value(rows[i], label_column)
                if label_val:
                    boundary_indices.append(i)
                    continue

            # Full-width bold row (all cells bold, even without gap)
            if _is_full_width_bold(rows[i]):
                label_val = _get_label_cell_value(rows[i], label_column)
                if label_val:
                    boundary_indices.append(i)
                    continue

            # Fill colour change (section header has different background)
            if _has_distinct_fill(rows[i], rows[i - 1]):
                label_val = _get_label_cell_value(rows[i], label_column)
                if label_val:
                    boundary_indices.append(i)
                    continue

            # Full-width merged cell (often used as section headers)
            if _is_full_width_merge(rows[i]):
                label_val = _get_label_cell_value(rows[i], label_column)
                if label_val:
                    boundary_indices.append(i)
                    continue

        # Merge in pre-computed boundaries from parsing stage.
        # These catch border-based and gap=1+bold boundaries that the
        # stricter thresholds above miss.
        precomputed = sheet.get("section_boundaries", [])
        if precomputed:
            precomputed_indices = {b["row_index"] for b in precomputed}
            row_index_to_pos = {row["row_index"]: i for i, row in enumerate(rows)}
            existing = set(boundary_indices)
            for ri in precomputed_indices:
                pos = row_index_to_pos.get(ri)
                if pos is not None and pos not in existing:
                    boundary_indices.append(pos)
            boundary_indices.sort()

        # Content-based fallback: detect rows that match section header
        # keywords with no numeric values (catches unformatted headers).
        existing_set = set(boundary_indices)
        for i in range(1, len(rows)):
            if i in existing_set:
                continue
            if _is_content_header_row(rows[i], label_column):
                boundary_indices.append(i)
        boundary_indices.sort()

        sheet_name = sheet.get("sheet_name", "?")

        # If only the initial boundary, return single section
        if len(boundary_indices) <= 1:
            first_label = _get_label_cell_value(rows[0], label_column)
            section = self._build_section(
                rows,
                sheet,
                label=first_label or "(single section)",
            )
            logger.debug(
                f"Section detection: sheet='{sheet_name}', "
                f"sections=1, rows={len(rows)}, "
                f"labels=['{section.label}']"
            )
            return [section]

        # Build sections from boundaries
        sections: List[SheetSection] = []
        for b_idx, start_pos in enumerate(boundary_indices):
            if b_idx + 1 < len(boundary_indices):
                end_pos = boundary_indices[b_idx + 1] - 1
            else:
                end_pos = len(rows) - 1

            section_rows = rows[start_pos : end_pos + 1]
            if not section_rows:
                continue

            label = _get_label_cell_value(section_rows[0], label_column) or f"Section {b_idx + 1}"
            sections.append(
                self._build_section(
                    section_rows,
                    sheet,
                    label=label,
                )
            )

        logger.debug(
            f"Section detection: sheet='{sheet_name}', "
            f"sections={len(sections)}, rows={len(rows)}, "
            f"labels={[s.label for s in sections]}"
        )

        return sections

    def _build_section(
        self,
        rows: List[Dict[str, Any]],
        sheet: Dict[str, Any],
        label: str,
    ) -> SheetSection:
        """Build a SheetSection from a subset of rows."""
        label_column = sheet.get("label_column") or "A"

        sample_labels: List[str] = []
        bold_labels: List[str] = []
        has_subtotals = False
        formula_count = 0

        for row in rows:
            lbl = _get_label_cell_value(row, label_column)
            if lbl and len(sample_labels) < 5:
                sample_labels.append(lbl)
            if lbl and _is_bold_label(row, label_column):
                bold_labels.append(lbl)
            if row.get("is_subtotal"):
                has_subtotals = True
            for cell in row.get("cells", []):
                if cell.get("is_subtotal"):
                    has_subtotals = True
                if cell.get("formula"):
                    formula_count += 1

        return SheetSection(
            label=label,
            start_row=rows[0]["row_index"],
            end_row=rows[-1]["row_index"],
            row_count=len(rows),
            category_hint=_guess_category(label),
            sample_labels=sample_labels,
            bold_labels=bold_labels,
            has_subtotals=has_subtotals,
            formula_count=formula_count,
        )
