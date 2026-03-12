"""Shared utilities for the validation package."""

from typing import List

from src.extraction.period_parser import sort_period_keys


def sort_periods(periods: List[str]) -> List[str]:
    """Sort period keys chronologically using PeriodParser's sort logic.

    Delegates to sort_period_keys() which uses NormalizedPeriod.sort_key tuples
    for correct chronological ordering of fiscal years, quarters, months, etc.

    Examples:
        ["3.0", "1.0", "2.0"]  -> ["1.0", "2.0", "3.0"]
        ["FY2023", "FY2022"]   -> ["FY2022", "FY2023"]
        ["2024-Q3", "FY2023"]  -> ["FY2023", "2024-Q3"]
    """
    return sort_period_keys(periods)
