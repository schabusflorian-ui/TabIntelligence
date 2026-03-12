"""Deterministic period detection and normalization for financial Excel models.

Parses period headers (FY2024, Q3 2024, Jan-24, 1, 2, 3...) from structured
Excel representations and produces normalized metadata for downstream consumers.

Stateless, pure Python, no external dependencies. Never raises on unparseable
input — returns None or confidence=0.0.
"""
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Compiled regex patterns (matched in priority order)
# ---------------------------------------------------------------------------

# Fiscal year: "FY2024", "FY24", "FY 2024", "FY2024E", "FY'24"
_RE_FISCAL_YEAR = re.compile(
    r"^FY\s*'?(\d{2,4})\s*([AEFP])?$", re.IGNORECASE
)

# Calendar year: "CY2024", "CY24", "CY2024E"
_RE_CALENDAR_YEAR = re.compile(
    r"^CY\s*'?(\d{2,4})\s*([AEFP])?$", re.IGNORECASE
)

# LTM / TTM / NTM (optionally followed by date/text)
_RE_LTM_TTM_NTM = re.compile(
    r"^(LTM|TTM|NTM)(?:\s+.*)?$", re.IGNORECASE
)

# Year with suffix: "2024A", "2024E", "2025F", "2026P"
# NOTE: Only 4-digit years accepted to avoid ambiguity with short codes like
# "24A". Use "FY24A" (matched by _RE_FISCAL_YEAR) for 2-digit years.
_RE_YEAR_SUFFIX = re.compile(
    r"^((?:19|20)\d{2})\s*([AEFP])$", re.IGNORECASE
)

# Quarterly (Q-first): "Q1 2024", "Q3'24", "Q4 '24"
_RE_QUARTERLY_Q_FIRST = re.compile(
    r"^Q([1-4])\s*['\s]*(\d{2,4})\s*([AEFP])?$", re.IGNORECASE
)

# Quarterly (year-first): "2024 Q1", "2024Q3"
_RE_QUARTERLY_YEAR_FIRST = re.compile(
    r"^((?:19|20)\d{2})\s*Q([1-4])\s*([AEFP])?$", re.IGNORECASE
)

# Half-year: "H1 2024", "H2'24", "1H 2024", "2H24", "1H'24"
_RE_HALF_YEAR = re.compile(
    r"^(?:([12])H|H([12]))\s*['\s]*(\d{2,4})\s*([AEFP])?$", re.IGNORECASE
)

# Monthly (name + year): "Jan-24", "Jan 2024", "March 2024", "Dec/2024"
_MONTH_ABBREVS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12,
}

_RE_MONTHLY = re.compile(
    r"^(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s*[-/\s]\s*'?(\d{2,4})$",
    re.IGNORECASE,
)

# Standalone 4-digit year: "2024", "2025"
_RE_STANDALONE_YEAR = re.compile(r"^((?:19|20)\d{2})$")

# Numeric sequential candidate: 1-3 digits, optional ".0"
_RE_NUMERIC = re.compile(r"^(\d{1,3})(?:\.0)?$")

# ---------------------------------------------------------------------------
# Project finance period patterns
# ---------------------------------------------------------------------------

# Relative year: "Year 1", "Yr 5", "Year 30", "Yr. 2", "Year 1A"
_RE_RELATIVE_YEAR = re.compile(
    r"^(?:Year|Yr)\.?\s*(\d{1,3})\s*([AEFP])?$", re.IGNORECASE
)

# COD-relative: "COD", "COD+1", "COD-3", "Pre-COD", "Post-COD"
_RE_COD_RELATIVE = re.compile(
    r"^(Pre[- ]?COD|Post[- ]?COD|COD\s*([+-]\s*\d{1,3})?)$", re.IGNORECASE
)

# Phase-prefixed year: "Construction Year 1", "Ops Yr 3", "Const. Year 2"
_RE_PHASE_YEAR = re.compile(
    r"^(Construction|Const\.?|Operations|Ops\.?)\s+(?:Year|Yr)\.?\s*(\d{1,3})$",
    re.IGNORECASE,
)

# Stub period: "Stub", "6-month stub", "3 mo stub", "Stub Period", "Short Period"
_RE_STUB = re.compile(
    r"^(?:(\d+)\s*[-]?\s*(?:month|mo)\.?\s+)?stub(?:\s+period)?$|^short\s+period$",
    re.IGNORECASE,
)

# FYE (fiscal year end): "FYE Mar 2024", "FYE Jun '24"
_RE_FISCAL_YEAR_END = re.compile(
    r"^FYE\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s*[-/\s]?\s*'?(\d{2,4})\s*([AEFP])?$",
    re.IGNORECASE,
)

# Semi-annual S-prefix: "S1 2024", "S2'24" (mapped to half_year)
_RE_SEMI_ANNUAL = re.compile(
    r"^(?:([12])S|S([12]))\s*['\s]*(\d{2,4})\s*([AEFP])?$", re.IGNORECASE
)

# ISO monthly: "2024-01", "2024/12"
_RE_ISO_MONTHLY = re.compile(
    r"^((?:19|20)\d{2})[/-](0[1-9]|1[0-2])$"
)

# Multi-row header keywords (row above period values)
_HEADER_KEYWORDS = {
    "year", "period", "date", "fy", "cy", "fiscal year", "calendar year",
    "construction", "operations", "ops", "const", "const.", "development",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NormalizedPeriod:
    """A single detected and normalized time period."""
    raw_value: str
    normalized: str
    column_letter: str
    period_type: str
    year: Optional[int]
    sub_period: Optional[int]
    is_actual: bool
    is_forecast: bool
    confidence: float
    sort_key: tuple

    def to_dict(self) -> dict:
        d = asdict(self)
        d["sort_key"] = list(d["sort_key"])
        return d


@dataclass
class PeriodDetectionResult:
    """Result of period detection for a single sheet."""
    periods: List[NormalizedPeriod]
    header_row_indices: List[int]
    dominant_type: str
    confidence: float
    layout: str

    def to_dict(self) -> dict:
        return {
            "periods": [p.to_dict() for p in self.periods],
            "header_row_indices": self.header_row_indices,
            "dominant_type": self.dominant_type,
            "confidence": self.confidence,
            "layout": self.layout,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _expand_year(y_str: str) -> int:
    """Expand 2-digit year: <50 → 2000+n, >=50 → 1900+n."""
    n = int(y_str)
    if n < 100:
        return 2000 + n if n < 50 else 1900 + n
    return n


def _suffix_flags(suffix: Optional[str]) -> Tuple[bool, bool]:
    """Return (is_actual, is_forecast) from A/E/F/P suffix."""
    if not suffix:
        return False, False
    s = suffix.upper()
    if s == "A":
        return True, False
    return False, True  # E, F, P are all forecast variants


def _compute_sort_key(
    period_type: str,
    year: Optional[int],
    sub_period: Optional[int],
    is_actual: bool,
    is_forecast: bool,
    raw_value: str,
    sequence_number: Optional[int] = None,
) -> tuple:
    """Compute deterministic sort key for chronological ordering.

    Tuple: (type_order, year_or_seq, granularity, sub_period, forecast_order, raw_value)
    - type_order: 0=numeric, 1=date-based, 2=relative_year, 3=phase_year,
                  4=cod_relative, 5=stub, 6=ltm/ttm/ntm, 7=unknown
    - granularity: 0=annual, 1=half_year, 2=quarterly, 3=monthly
    - forecast_order: 0=actual, 1=unspecified, 2=forecast
    """
    type_orders = {
        "numeric": 0,
        "fiscal_year": 1, "calendar_year": 1, "quarterly": 1,
        "half_year": 1, "monthly": 1, "date": 1, "fiscal_year_end": 1,
        "relative_year": 2,
        "phase_year": 3,
        "cod_relative": 4,
        "stub": 5,
        "ltm_ttm_ntm": 6,
        "unknown": 7,
    }
    type_order = type_orders.get(period_type, 7)

    if period_type == "numeric":
        return (type_order, 0, 0, sequence_number or 0, 0, raw_value)

    # Project finance types use specialised sort keys
    if period_type == "relative_year":
        forecast_order = 0 if is_actual else (2 if is_forecast else 1)
        return (type_order, 0, 0, sub_period or 0, forecast_order, raw_value)

    if period_type == "phase_year":
        # year stores phase_order (0=construction, 1=operations)
        forecast_order = 0 if is_actual else (2 if is_forecast else 1)
        return (type_order, year or 0, 0, sub_period or 0, forecast_order, raw_value)

    if period_type == "cod_relative":
        # sub_period stores the offset: PreCOD=-999, COD-N=-N, COD=0, COD+N=+N, PostCOD=999
        return (type_order, sub_period or 0, 0, 0, 0, raw_value)

    if period_type == "stub":
        # sub_period stores month count (0 if unspecified)
        return (type_order, sub_period or 0, 0, 0, 0, raw_value)

    # Granularity separates annual from sub-annual within the same year.
    _granularity = {
        "fiscal_year": 0, "calendar_year": 0, "standalone_year": 0,
        "year_suffix": 0, "fiscal_year_end": 0,
        "half_year": 1, "quarterly": 2, "monthly": 3,
    }
    if period_type == "date":
        granularity_order = 0 if sub_period is None else 3
    else:
        granularity_order = _granularity.get(period_type, 0)

    if is_actual:
        forecast_order = 0
    elif is_forecast:
        forecast_order = 2
    else:
        forecast_order = 1

    return (
        type_order,
        year or 0,
        granularity_order,
        sub_period or 0,
        forecast_order,
        raw_value,
    )


# ---------------------------------------------------------------------------
# PeriodParser
# ---------------------------------------------------------------------------

class PeriodParser:
    """Stateless period detection from structured Excel data."""

    MAX_HEADER_SCAN_ROWS = 8

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_single_value(
        self, raw_value: Any, column_letter: str = "",
    ) -> Optional[NormalizedPeriod]:
        """Parse a single cell value into a NormalizedPeriod.

        Handles str, int, float, datetime. Returns None if unrecognizable.
        """
        if raw_value is None:
            return None

        # datetime objects
        if isinstance(raw_value, datetime):
            return self._parse_datetime(raw_value, column_letter)

        # Convert numeric types to string
        if isinstance(raw_value, float):
            if raw_value == int(raw_value):
                text = str(int(raw_value))
            else:
                text = str(raw_value)
        elif isinstance(raw_value, int):
            text = str(raw_value)
        elif isinstance(raw_value, str):
            text = raw_value.strip()
        else:
            return None

        if not text:
            return None

        # Try patterns in priority order
        return (
            self._try_fiscal_year(text, column_letter)
            or self._try_fiscal_year_end(text, column_letter)
            or self._try_calendar_year(text, column_letter)
            or self._try_ltm_ttm_ntm(text, column_letter)
            or self._try_year_suffix(text, column_letter)
            or self._try_quarterly_q_first(text, column_letter)
            or self._try_quarterly_year_first(text, column_letter)
            or self._try_half_year(text, column_letter)
            or self._try_semi_annual(text, column_letter)
            or self._try_monthly(text, column_letter)
            or self._try_iso_monthly(text, column_letter)
            or self._try_standalone_year(text, column_letter)
            or self._try_phase_year(text, column_letter)
            or self._try_relative_year(text, column_letter)
            or self._try_cod_relative(text, column_letter)
            or self._try_stub(text, column_letter)
            # _RE_NUMERIC is NOT tried here — only via detect_numeric_sequential
        )

    def detect_periods_from_sheet(
        self, sheet: Dict[str, Any],
    ) -> PeriodDetectionResult:
        """Detect periods from a single sheet's structured data.

        Never raises — returns empty result on failure.
        """
        empty = PeriodDetectionResult(
            periods=[], header_row_indices=[], dominant_type="unknown",
            confidence=0.0, layout="time_across_columns",
        )

        try:
            return self._detect_periods_impl(sheet, empty)
        except Exception:
            # Honour "never raises" contract: malformed sheet data
            # should not crash the caller.
            return empty

    def _detect_periods_impl(
        self, sheet: Dict[str, Any], empty: PeriodDetectionResult,
    ) -> PeriodDetectionResult:
        """Internal implementation of detect_periods_from_sheet."""
        rows = sheet.get("rows", [])
        if not rows:
            return empty

        # Take first N rows for header scanning
        scan_rows = [r for r in rows if r["row_index"] <= rows[0]["row_index"] + self.MAX_HEADER_SCAN_ROWS]

        # Try multi-row header first
        multi_result = self._detect_multi_row_header(scan_rows)

        # Score each candidate row
        best_result: Optional[PeriodDetectionResult] = None
        best_score = 0.0

        if multi_result:
            best_result = multi_result
            best_score = multi_result.confidence

        for row in scan_rows:
            result = self._evaluate_header_row(row)
            if result and result.confidence > best_score:
                best_result = result
                best_score = result.confidence

        # Try numeric sequential if no good match
        if best_score < 0.3:
            for row in scan_rows:
                seq_result = self._try_numeric_sequential_row(row)
                if seq_result and seq_result.confidence > best_score:
                    best_result = seq_result
                    best_score = seq_result.confidence

        # Try time-down-rows layout if nothing found
        if best_score < 0.3:
            down_result = self._detect_time_down_rows(rows)
            if down_result and down_result.confidence > best_score:
                best_result = down_result
                best_score = down_result.confidence

        return best_result if best_result else empty

    @staticmethod
    def sort_periods(periods: List[NormalizedPeriod]) -> List[NormalizedPeriod]:
        """Sort NormalizedPeriod objects chronologically by sort_key."""
        return sorted(periods, key=lambda p: p.sort_key)

    # ------------------------------------------------------------------
    # Pattern matchers (each returns Optional[NormalizedPeriod])
    # ------------------------------------------------------------------

    def _try_fiscal_year(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        m = _RE_FISCAL_YEAR.match(text)
        if not m:
            return None
        year = _expand_year(m.group(1))
        is_actual, is_forecast = _suffix_flags(m.group(2))
        suffix = m.group(2).upper() if m.group(2) else ""
        normalized = f"FY{year}{suffix}"
        conf = 0.9 if len(m.group(1)) == 2 else 1.0
        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="fiscal_year", year=year, sub_period=None,
            is_actual=is_actual, is_forecast=is_forecast, confidence=conf,
            sort_key=_compute_sort_key("fiscal_year", year, None, is_actual, is_forecast, text),
        )

    def _try_calendar_year(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        m = _RE_CALENDAR_YEAR.match(text)
        if not m:
            return None
        year = _expand_year(m.group(1))
        is_actual, is_forecast = _suffix_flags(m.group(2))
        suffix = m.group(2).upper() if m.group(2) else ""
        normalized = f"CY{year}{suffix}"
        conf = 0.9 if len(m.group(1)) == 2 else 1.0
        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="calendar_year", year=year, sub_period=None,
            is_actual=is_actual, is_forecast=is_forecast, confidence=conf,
            sort_key=_compute_sort_key("calendar_year", year, None, is_actual, is_forecast, text),
        )

    def _try_ltm_ttm_ntm(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        m = _RE_LTM_TTM_NTM.match(text)
        if not m:
            return None
        label = m.group(1).upper()
        return NormalizedPeriod(
            raw_value=text, normalized=label, column_letter=col,
            period_type="ltm_ttm_ntm", year=None, sub_period=None,
            is_actual=False, is_forecast=False, confidence=1.0,
            sort_key=_compute_sort_key("ltm_ttm_ntm", None, None, False, False, text),
        )

    def _try_year_suffix(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        m = _RE_YEAR_SUFFIX.match(text)
        if not m:
            return None
        year = int(m.group(1))
        is_actual, is_forecast = _suffix_flags(m.group(2))
        suffix = m.group(2).upper()
        normalized = f"{year}{suffix}"
        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="calendar_year", year=year, sub_period=None,
            is_actual=is_actual, is_forecast=is_forecast, confidence=1.0,
            sort_key=_compute_sort_key("calendar_year", year, None, is_actual, is_forecast, text),
        )

    def _try_quarterly_q_first(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        m = _RE_QUARTERLY_Q_FIRST.match(text)
        if not m:
            return None
        quarter = int(m.group(1))
        year = _expand_year(m.group(2))
        is_actual, is_forecast = _suffix_flags(m.group(3))
        normalized = f"{year}-Q{quarter}"
        conf = 0.9 if len(m.group(2)) == 2 else 1.0
        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="quarterly", year=year, sub_period=quarter,
            is_actual=is_actual, is_forecast=is_forecast, confidence=conf,
            sort_key=_compute_sort_key("quarterly", year, quarter, is_actual, is_forecast, text),
        )

    def _try_quarterly_year_first(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        m = _RE_QUARTERLY_YEAR_FIRST.match(text)
        if not m:
            return None
        year = int(m.group(1))
        quarter = int(m.group(2))
        is_actual, is_forecast = _suffix_flags(m.group(3))
        normalized = f"{year}-Q{quarter}"
        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="quarterly", year=year, sub_period=quarter,
            is_actual=is_actual, is_forecast=is_forecast, confidence=1.0,
            sort_key=_compute_sort_key("quarterly", year, quarter, is_actual, is_forecast, text),
        )

    def _try_half_year(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        m = _RE_HALF_YEAR.match(text)
        if not m:
            return None
        half = int(m.group(1) or m.group(2))
        year = _expand_year(m.group(3))
        is_actual, is_forecast = _suffix_flags(m.group(4))
        normalized = f"{year}-H{half}"
        conf = 0.9 if len(m.group(3)) == 2 else 1.0
        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="half_year", year=year, sub_period=half,
            is_actual=is_actual, is_forecast=is_forecast, confidence=conf,
            sort_key=_compute_sort_key("half_year", year, half, is_actual, is_forecast, text),
        )

    def _try_monthly(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        m = _RE_MONTHLY.match(text)
        if not m:
            return None
        month_name = m.group(1).lower()
        month = _MONTH_ABBREVS.get(month_name)
        if month is None:
            return None
        year = _expand_year(m.group(2))
        normalized = f"{year}-{month:02d}"
        conf = 0.9 if len(m.group(2)) == 2 else 1.0
        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="monthly", year=year, sub_period=month,
            is_actual=False, is_forecast=False, confidence=conf,
            sort_key=_compute_sort_key("monthly", year, month, False, False, text),
        )

    def _try_standalone_year(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        m = _RE_STANDALONE_YEAR.match(text)
        if not m:
            return None
        year = int(m.group(1))
        return NormalizedPeriod(
            raw_value=text, normalized=str(year), column_letter=col,
            period_type="calendar_year", year=year, sub_period=None,
            is_actual=False, is_forecast=False, confidence=1.0,
            sort_key=_compute_sort_key("calendar_year", year, None, False, False, text),
        )

    # ------------------------------------------------------------------
    # Project finance matchers
    # ------------------------------------------------------------------

    def _try_fiscal_year_end(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        """Match 'FYE Mar 2024', 'FYE Jun '24', 'FYE December 2025E'."""
        m = _RE_FISCAL_YEAR_END.match(text)
        if not m:
            return None
        month_str = m.group(1).lower()[:3]
        month_num = _MONTH_ABBREVS.get(month_str)
        if month_num is None:
            return None
        year = _expand_year(m.group(2))
        suffix = m.group(3)
        is_actual, is_forecast = _suffix_flags(suffix)
        suffix_str = suffix.upper() if suffix else ""
        normalized = f"FYE-{year}-{month_num:02d}{suffix_str}"
        conf = 1.0 if len(m.group(2)) == 4 else 0.9
        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="fiscal_year_end", year=year, sub_period=month_num,
            is_actual=is_actual, is_forecast=is_forecast, confidence=conf,
            sort_key=_compute_sort_key(
                "fiscal_year_end", year, month_num, is_actual, is_forecast, text,
            ),
        )

    def _try_semi_annual(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        """Match 'S1 2024', 'S2'24', '1S 2024' → half_year."""
        m = _RE_SEMI_ANNUAL.match(text)
        if not m:
            return None
        half = int(m.group(1) or m.group(2))
        year = _expand_year(m.group(3))
        suffix = m.group(4)
        is_actual, is_forecast = _suffix_flags(suffix)
        normalized = f"{year}-H{half}"
        conf = 1.0 if len(m.group(3)) == 4 else 0.9
        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="half_year", year=year, sub_period=half,
            is_actual=is_actual, is_forecast=is_forecast, confidence=conf,
            sort_key=_compute_sort_key(
                "half_year", year, half, is_actual, is_forecast, text,
            ),
        )

    def _try_iso_monthly(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        """Match '2024-01', '2024/12' → monthly."""
        m = _RE_ISO_MONTHLY.match(text)
        if not m:
            return None
        year = int(m.group(1))
        month = int(m.group(2))
        normalized = f"{year}-{month:02d}"
        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="monthly", year=year, sub_period=month,
            is_actual=False, is_forecast=False, confidence=1.0,
            sort_key=_compute_sort_key(
                "monthly", year, month, False, False, text,
            ),
        )

    def _try_relative_year(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        """Match 'Year 1', 'Yr 5', 'Year 30', 'Yr. 2', 'Year 1A'."""
        m = _RE_RELATIVE_YEAR.match(text)
        if not m:
            return None
        num = int(m.group(1))
        suffix = m.group(2)
        is_actual, is_forecast = _suffix_flags(suffix)
        suffix_str = suffix.upper() if suffix else ""
        normalized = f"Year{num}{suffix_str}"
        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="relative_year", year=None, sub_period=num,
            is_actual=is_actual, is_forecast=is_forecast, confidence=0.9,
            sort_key=_compute_sort_key(
                "relative_year", None, num, is_actual, is_forecast, text,
            ),
        )

    def _try_cod_relative(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        """Match 'COD', 'COD+1', 'COD-3', 'Pre-COD', 'Post-COD'."""
        m = _RE_COD_RELATIVE.match(text)
        if not m:
            return None
        full = m.group(1).strip()
        offset_str = m.group(2)

        full_lower = full.lower().replace(" ", "").replace("-", "")
        if full_lower == "precod":
            normalized = "PreCOD"
            offset = -999
        elif full_lower == "postcod":
            normalized = "PostCOD"
            offset = 999
        elif offset_str:
            offset = int(offset_str.replace(" ", ""))
            sign = "+" if offset >= 0 else ""
            normalized = f"COD{sign}{offset}"
        else:
            normalized = "COD"
            offset = 0

        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="cod_relative", year=None, sub_period=offset,
            is_actual=False, is_forecast=False, confidence=0.95,
            sort_key=_compute_sort_key(
                "cod_relative", None, offset, False, False, text,
            ),
        )

    def _try_phase_year(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        """Match 'Construction Year 1', 'Const. Year 2', 'Ops Yr 3'."""
        m = _RE_PHASE_YEAR.match(text)
        if not m:
            return None
        phase_raw = m.group(1).lower().rstrip(".")
        num = int(m.group(2))

        if phase_raw in ("construction", "const"):
            phase_prefix = "Const"
            phase_order = 0
        else:
            phase_prefix = "Ops"
            phase_order = 1

        normalized = f"{phase_prefix}-Year{num}"
        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="phase_year", year=phase_order, sub_period=num,
            is_actual=False, is_forecast=False, confidence=0.9,
            sort_key=_compute_sort_key(
                "phase_year", phase_order, num, False, False, text,
            ),
        )

    def _try_stub(
        self, text: str, col: str,
    ) -> Optional[NormalizedPeriod]:
        """Match 'Stub', '6-month stub', '3 mo stub', 'Short Period'."""
        m = _RE_STUB.match(text)
        if not m:
            return None
        months_str = m.group(1) if m.lastindex and m.group(1) else None
        months = int(months_str) if months_str else 0
        normalized = f"Stub-{months}M" if months else "Stub"
        return NormalizedPeriod(
            raw_value=text, normalized=normalized, column_letter=col,
            period_type="stub", year=None, sub_period=months,
            is_actual=False, is_forecast=False, confidence=0.8,
            sort_key=_compute_sort_key(
                "stub", None, months, False, False, text,
            ),
        )

    def _parse_datetime(
        self, dt: datetime, col: str,
    ) -> NormalizedPeriod:
        """Convert a datetime object to a NormalizedPeriod."""
        year = dt.year
        # If it's Dec 31 or Jan 1, treat as annual; otherwise monthly
        if (dt.month == 12 and dt.day == 31) or (dt.month == 1 and dt.day == 1):
            normalized = str(year)
            sub_period = None
            period_type = "date"
        else:
            normalized = f"{year}-{dt.month:02d}"
            sub_period = dt.month
            period_type = "date"
        return NormalizedPeriod(
            raw_value=str(dt), normalized=normalized, column_letter=col,
            period_type=period_type, year=year, sub_period=sub_period,
            is_actual=False, is_forecast=False, confidence=1.0,
            sort_key=_compute_sort_key("date", year, sub_period, False, False, str(dt)),
        )

    # ------------------------------------------------------------------
    # Sheet-level detection internals
    # ------------------------------------------------------------------

    def _evaluate_header_row(
        self, row: Dict[str, Any],
    ) -> Optional[PeriodDetectionResult]:
        """Try to parse all cells in a row as periods."""
        cells = row.get("cells", [])
        if not cells:
            return None

        periods: List[NormalizedPeriod] = []
        non_empty_count = 0

        for cell in cells:
            val = cell.get("value")
            if val is None or (isinstance(val, str) and not val.strip()):
                continue
            non_empty_count += 1

            ref = cell.get("ref", "")
            col = re.match(r"([A-Z]+)", ref)
            col_letter = col.group(1) if col else ""

            parsed = self.parse_single_value(val, col_letter)
            if parsed:
                periods.append(parsed)

        if not periods or non_empty_count == 0:
            return None

        ratio = len(periods) / non_empty_count
        # Need at least 2 periods and >40% of non-empty cells to be periods
        if len(periods) < 2 or ratio < 0.4:
            return None

        dominant_type = self._get_dominant_type(periods)
        type_bonus = self._type_consistency_bonus(periods)
        confidence = ratio * type_bonus

        sorted_periods = self.sort_periods(periods)

        return PeriodDetectionResult(
            periods=sorted_periods,
            header_row_indices=[row["row_index"]],
            dominant_type=dominant_type,
            confidence=round(confidence, 4),
            layout="time_across_columns",
        )

    def _try_numeric_sequential_row(
        self, row: Dict[str, Any],
    ) -> Optional[PeriodDetectionResult]:
        """Detect numeric sequential periods (1, 2, 3...) in a row."""
        cells = row.get("cells", [])
        if not cells:
            return None

        candidates: List[Tuple[str, int]] = []  # (column_letter, value)
        non_empty_count = 0

        for cell in cells:
            val = cell.get("value")
            if val is None or (isinstance(val, str) and not val.strip()):
                continue
            non_empty_count += 1

            ref = cell.get("ref", "")
            col = re.match(r"([A-Z]+)", ref)
            col_letter = col.group(1) if col else ""

            # Try to parse as numeric
            text = ""
            if isinstance(val, (int, float)):
                if isinstance(val, float) and val == int(val):
                    text = str(int(val))
                elif isinstance(val, int):
                    text = str(val)
                else:
                    continue
            elif isinstance(val, str):
                text = val.strip()
            else:
                continue

            m = _RE_NUMERIC.match(text)
            if m:
                n = int(m.group(1))
                # Filter out large numbers that are unlikely to be period indices
                if n <= 100:
                    candidates.append((col_letter, n))

        # Need at least 3 sequential values
        if len(candidates) < 3:
            return None

        # Check if values form a consecutive sequence
        values = [c[1] for c in candidates]
        sorted_vals = sorted(values)
        is_sequential = all(
            sorted_vals[i + 1] - sorted_vals[i] == 1
            for i in range(len(sorted_vals) - 1)
        )
        if not is_sequential:
            return None

        ratio = len(candidates) / non_empty_count if non_empty_count else 0
        if ratio < 0.4:
            return None

        periods = []
        for col_letter, n in candidates:
            raw = str(n)
            periods.append(NormalizedPeriod(
                raw_value=raw, normalized=f"P{n}", column_letter=col_letter,
                period_type="numeric", year=None, sub_period=None,
                is_actual=False, is_forecast=False, confidence=0.7,
                sort_key=_compute_sort_key("numeric", None, None, False, False, raw, sequence_number=n),
            ))

        sorted_periods = self.sort_periods(periods)
        confidence = round(0.7 * ratio, 4)

        return PeriodDetectionResult(
            periods=sorted_periods,
            header_row_indices=[row["row_index"]],
            dominant_type="numeric",
            confidence=confidence,
            layout="time_across_columns",
        )

    def _detect_multi_row_header(
        self, scan_rows: List[Dict[str, Any]],
    ) -> Optional[PeriodDetectionResult]:
        """Detect compound headers where row N has a keyword and row N+1 has values.

        E.g., row 1: "Year" | "Year" | "Year"
              row 2: "2022" | "2023" | "2024"
        Or:   row 1: "FY"   | "FY"   | "FY"
              row 2: "2022A"| "2023A"| "2024E"
        """
        if len(scan_rows) < 2:
            return None

        for i in range(len(scan_rows) - 1):
            row_top = scan_rows[i]
            row_bot = scan_rows[i + 1]

            top_cells = row_top.get("cells", [])
            bot_cells = row_bot.get("cells", [])

            # Check if top row has header keywords
            has_keyword = False
            keyword_prefix = ""
            for cell in top_cells:
                val = cell.get("value")
                if isinstance(val, str) and val.strip().lower() in _HEADER_KEYWORDS:
                    has_keyword = True
                    kw = val.strip().lower()
                    if kw in ("fy", "fiscal year"):
                        keyword_prefix = "FY"
                    elif kw in ("cy", "calendar year"):
                        keyword_prefix = "CY"
                    elif kw in ("construction", "const", "const."):
                        keyword_prefix = "Construction Year "
                    elif kw in ("operations", "ops"):
                        keyword_prefix = "Operations Year "
                    break

            if not has_keyword:
                continue

            # Build column map for bottom row
            bot_by_col: Dict[str, Any] = {}
            for cell in bot_cells:
                ref = cell.get("ref", "")
                m = re.match(r"([A-Z]+)", ref)
                if m:
                    bot_by_col[m.group(1)] = cell.get("value")

            # Try parsing bottom row values, optionally prefixed
            periods: List[NormalizedPeriod] = []
            non_empty = 0

            for col_letter, val in bot_by_col.items():
                if val is None or (isinstance(val, str) and not val.strip()):
                    continue
                non_empty += 1

                # Try with prefix first, then without
                combined = None
                if keyword_prefix and isinstance(val, str):
                    combined = self.parse_single_value(
                        f"{keyword_prefix}{val.strip()}", col_letter,
                    )
                if combined:
                    # Reduce confidence slightly for combined match
                    combined = NormalizedPeriod(
                        raw_value=f"{keyword_prefix} {val}",
                        normalized=combined.normalized,
                        column_letter=col_letter,
                        period_type=combined.period_type,
                        year=combined.year,
                        sub_period=combined.sub_period,
                        is_actual=combined.is_actual,
                        is_forecast=combined.is_forecast,
                        confidence=0.8,
                        sort_key=combined.sort_key,
                    )
                    periods.append(combined)
                else:
                    parsed = self.parse_single_value(val, col_letter)
                    if parsed:
                        parsed = NormalizedPeriod(
                            raw_value=parsed.raw_value,
                            normalized=parsed.normalized,
                            column_letter=col_letter,
                            period_type=parsed.period_type,
                            year=parsed.year,
                            sub_period=parsed.sub_period,
                            is_actual=parsed.is_actual,
                            is_forecast=parsed.is_forecast,
                            confidence=0.8,
                            sort_key=parsed.sort_key,
                        )
                        periods.append(parsed)

            if len(periods) < 2 or non_empty == 0:
                continue

            ratio = len(periods) / non_empty
            if ratio < 0.4:
                continue

            dominant_type = self._get_dominant_type(periods)
            type_bonus = self._type_consistency_bonus(periods)
            confidence = round(ratio * type_bonus, 4)

            sorted_periods = self.sort_periods(periods)

            return PeriodDetectionResult(
                periods=sorted_periods,
                header_row_indices=[row_top["row_index"], row_bot["row_index"]],
                dominant_type=dominant_type,
                confidence=confidence,
                layout="time_across_columns",
            )

        return None

    def _detect_time_down_rows(
        self, rows: List[Dict[str, Any]],
    ) -> Optional[PeriodDetectionResult]:
        """Detect periods running down column A (time_down_rows layout)."""
        periods: List[NormalizedPeriod] = []
        row_indices: List[int] = []

        for row in rows:
            cells = row.get("cells", [])
            if not cells:
                continue

            # Check first cell (column A)
            first_cell = cells[0]
            ref = first_cell.get("ref", "")
            m = re.match(r"([A-Z]+)", ref)
            if not m or m.group(1) != "A":
                continue

            val = first_cell.get("value")
            parsed = self.parse_single_value(val, "A")
            if parsed:
                periods.append(parsed)
                row_indices.append(row["row_index"])

        if len(periods) < 3:
            return None

        dominant_type = self._get_dominant_type(periods)
        type_bonus = self._type_consistency_bonus(periods)
        confidence = round(min(len(periods) / max(len(rows), 1), 1.0) * type_bonus * 0.8, 4)

        sorted_periods = self.sort_periods(periods)

        return PeriodDetectionResult(
            periods=sorted_periods,
            header_row_indices=row_indices,
            dominant_type=dominant_type,
            confidence=confidence,
            layout="time_down_rows",
        )

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_dominant_type(periods: List[NormalizedPeriod]) -> str:
        """Return the most common period_type."""
        if not periods:
            return "unknown"
        counts = Counter(p.period_type for p in periods)
        return counts.most_common(1)[0][0]

    @staticmethod
    def _type_consistency_bonus(periods: List[NormalizedPeriod]) -> float:
        """Bonus multiplier based on how consistent the period types are."""
        if not periods:
            return 1.0
        types = set(p.period_type for p in periods)
        if len(types) == 1:
            return 1.0
        if len(types) == 2:
            return 0.9
        return 0.8


# ---------------------------------------------------------------------------
# Module-level singleton — PeriodParser is stateless, safe to share.
# ---------------------------------------------------------------------------

_DEFAULT_PARSER = PeriodParser()


# ---------------------------------------------------------------------------
# Smart period key sorting
# ---------------------------------------------------------------------------

def sort_period_keys(keys: List[str]) -> List[str]:
    """Sort plain string period keys using PeriodParser's deterministic sort logic.

    Parses each key via PeriodParser.parse_single_value, uses
    NormalizedPeriod.sort_key for recognized patterns, falls back to
    float-then-lexicographic for unrecognized keys.

    All three paths produce comparable 7-tuples:
    - Recognized:     (0,) + sort_key  →  (0, type, year, gran, sub, forecast, raw)
    - Float fallback: (0, 0, 0, float_val, 0, 0, raw)
    - Lexicographic:  (1, 0, 0, 0.0, 0, 0, raw)
    """
    def _sort_key_for_string(p: str) -> tuple:
        parsed = _DEFAULT_PARSER.parse_single_value(p, "")
        if parsed is not None:
            return (0,) + parsed.sort_key

        try:
            return (0, 0, 0, float(p), 0, 0, p)
        except (ValueError, TypeError):
            pass

        return (1, 0, 0, 0.0, 0, 0, p)

    return sorted(keys, key=_sort_key_for_string)


# ---------------------------------------------------------------------------
# Cross-sheet period consistency
# ---------------------------------------------------------------------------

def check_period_consistency(
    all_detected_periods: Dict[str, Dict],
) -> List[Dict[str, Any]]:
    """Check period consistency across sheets.

    Args:
        all_detected_periods: {sheet_name: PeriodDetectionResult.to_dict()}.
            Only sheets with detected periods are included.

    Returns:
        List of warning dicts with keys: type, severity, message, details.
        Returns empty list if fewer than 2 sheets have periods.
    """
    warnings: List[Dict[str, Any]] = []

    if len(all_detected_periods) < 2:
        return warnings

    # --- Check 1: Mismatched dominant_type across sheets ---
    # Project-finance types are compatible with each other (a model may have
    # relative_year on one sheet and phase_year on another).
    _PF_TYPES = {"relative_year", "phase_year", "cod_relative", "stub"}

    type_by_sheet = {
        sheet: info.get("dominant_type", "unknown")
        for sheet, info in all_detected_periods.items()
    }
    unique_types = set(type_by_sheet.values()) - {"unknown"}

    # Collapse all PF types into a single representative for comparison
    normalised = set()
    for t in unique_types:
        normalised.add("_pf" if t in _PF_TYPES else t)

    if len(normalised) > 1:
        warnings.append({
            "type": "mismatched_period_type",
            "severity": "warning",
            "message": (
                f"Sheets use different period types: "
                f"{', '.join(f'{s}={t}' for s, t in type_by_sheet.items())}"
            ),
            "details": {"types_by_sheet": type_by_sheet},
        })

    # --- Check 2: Period coverage gaps ---
    year_sets: Dict[str, set] = {}
    for sheet, info in all_detected_periods.items():
        periods = info.get("periods", [])
        years = set()
        for p in periods:
            y = p.get("year")
            if y is not None:
                years.add(y)
        if years:
            year_sets[sheet] = years

    if len(year_sets) >= 2:
        all_years: set = set()
        for ys in year_sets.values():
            all_years |= ys

        for sheet, years in year_sets.items():
            missing = all_years - years
            if missing:
                warnings.append({
                    "type": "period_coverage_gap",
                    "severity": "info",
                    "message": (
                        f"Sheet '{sheet}' is missing years present in other sheets: "
                        f"{sorted(missing)}"
                    ),
                    "details": {
                        "sheet": sheet,
                        "missing_years": sorted(missing),
                        "sheet_years": sorted(years),
                        "all_years": sorted(all_years),
                    },
                })

    # --- Check 3: Layout inconsistencies ---
    layouts = {
        sheet: info.get("layout", "unknown")
        for sheet, info in all_detected_periods.items()
    }
    unique_layouts = set(layouts.values())

    if len(unique_layouts) > 1:
        warnings.append({
            "type": "layout_inconsistency",
            "severity": "info",
            "message": (
                f"Sheets use different period layouts: "
                f"{', '.join(f'{s}={l}' for s, l in layouts.items())}"
            ),
            "details": {"layouts_by_sheet": layouts},
        })

    return warnings
