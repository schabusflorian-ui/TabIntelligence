"""Tests for sort_period_keys() — chronological period sorting via PeriodParser."""

from src.extraction.period_parser import sort_period_keys


class TestNumericPeriods:
    """Numeric string periods sort identically to the old naive sort."""

    def test_simple_floats(self):
        assert sort_period_keys(["3.0", "1.0", "2.0", "10.0"]) == [
            "1.0", "2.0", "3.0", "10.0"
        ]

    def test_integers_as_strings(self):
        assert sort_period_keys(["5", "1", "3"]) == ["1", "3", "5"]

    def test_single_period(self):
        assert sort_period_keys(["1.0"]) == ["1.0"]

    def test_empty(self):
        assert sort_period_keys([]) == []


class TestFiscalYears:
    """Fiscal year formats sort chronologically."""

    def test_fy_prefix(self):
        assert sort_period_keys(["FY2024", "FY2022", "FY2023"]) == [
            "FY2022", "FY2023", "FY2024"
        ]

    def test_fy_with_suffixes(self):
        result = sort_period_keys(["FY2024E", "FY2022A", "FY2023A"])
        assert result == ["FY2022A", "FY2023A", "FY2024E"]

    def test_actual_before_forecast_same_year(self):
        result = sort_period_keys(["FY2024E", "FY2024A"])
        assert result == ["FY2024A", "FY2024E"]

    def test_standalone_years(self):
        assert sort_period_keys(["2025", "2023", "2024"]) == [
            "2023", "2024", "2025"
        ]

    def test_fy_with_space(self):
        """Claude sometimes outputs 'FY 2024A' with a space."""
        result = sort_period_keys(["FY 2024A", "FY 2022A", "FY 2023A"])
        assert result == ["FY 2022A", "FY 2023A", "FY 2024A"]


class TestQuarterly:
    """Quarterly periods sort chronologically."""

    def test_within_year(self):
        result = sort_period_keys(["2024-Q3", "2024-Q1", "2024-Q4", "2024-Q2"])
        assert result == ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"]

    def test_across_years(self):
        result = sort_period_keys(["2024-Q3", "2024-Q1", "2025-Q1"])
        assert result == ["2024-Q1", "2024-Q3", "2025-Q1"]

    def test_q_without_dash(self):
        result = sort_period_keys(["Q3 2024", "Q1 2024", "Q2 2024"])
        assert result == ["Q1 2024", "Q2 2024", "Q3 2024"]


class TestMixedFormats:
    """Mixed period formats sort correctly — the key improvement."""

    def test_quarterly_after_fiscal_year(self):
        """Key fix: 2024-Q3 is after FY2023."""
        result = sort_period_keys(["2024-Q3", "FY2023"])
        assert result == ["FY2023", "2024-Q3"]

    def test_actual_year_after_earlier_fiscal(self):
        """Key fix: 2024A is after FY2022A."""
        result = sort_period_keys(["2024A", "FY2022A"])
        assert result == ["FY2022A", "2024A"]

    def test_numeric_before_fiscal(self):
        """Numeric periods (project model) sort before FY periods."""
        result = sort_period_keys(["2.0", "FY2021", "1.0"])
        # Numeric periods get year=0 so they sort before FY2021
        assert result[0] == "1.0"
        assert result[1] == "2.0"

    def test_mixed_quarterly_and_half_year(self):
        result = sort_period_keys(["H2 2024", "Q1 2024", "H1 2024"])
        # Half-year (granularity=1) sorts before quarterly (granularity=2)
        assert result == ["H1 2024", "H2 2024", "Q1 2024"]


class TestAnnualVsSubPeriod:
    """Annual periods sort before sub-periods of the same year (summary-first)."""

    def test_fy_before_quarters_same_year(self):
        result = sort_period_keys(["2024-Q1", "FY2024", "2024-Q3"])
        assert result == ["FY2024", "2024-Q1", "2024-Q3"]

    def test_standalone_year_before_quarters(self):
        result = sort_period_keys(["2024-Q4", "2024", "2024-Q1"])
        assert result == ["2024", "2024-Q1", "2024-Q4"]

    def test_annual_before_monthly_same_year(self):
        result = sort_period_keys(["Jan-2024", "FY2024", "Mar-2024"])
        assert result == ["FY2024", "Jan-2024", "Mar-2024"]

    def test_annual_before_half_year_same_year(self):
        result = sort_period_keys(["H1 2024", "FY2024"])
        assert result == ["FY2024", "H1 2024"]

    def test_granularity_order_full(self):
        """Annual < half-year < quarterly < monthly for same year."""
        result = sort_period_keys(["Jan-2024", "Q1 2024", "H1 2024", "FY2024"])
        assert result == ["FY2024", "H1 2024", "Q1 2024", "Jan-2024"]

    def test_different_year_annual_vs_quarter(self):
        """Cross-year: earlier year's quarter before later year's annual."""
        result = sort_period_keys(["FY2025", "Q3 2024"])
        assert result == ["Q3 2024", "FY2025"]


class TestMonthlyAndHalfYear:
    """Monthly and half-year periods."""

    def test_monthly(self):
        result = sort_period_keys(["Mar-2024", "Jan-2024", "Feb-2024"])
        assert result == ["Jan-2024", "Feb-2024", "Mar-2024"]

    def test_half_year(self):
        result = sort_period_keys(["H2 2024", "H1 2024", "H1 2025"])
        assert result == ["H1 2024", "H2 2024", "H1 2025"]


class TestUnrecognized:
    """Unrecognized strings sort last, lexicographically."""

    def test_unrecognized_after_recognized(self):
        result = sort_period_keys(["FY2023", "xyz", "FY2022"])
        assert result == ["FY2022", "FY2023", "xyz"]

    def test_multiple_unrecognized(self):
        result = sort_period_keys(["bbb", "aaa", "FY2023"])
        assert result == ["FY2023", "aaa", "bbb"]


class TestProjectFinancePeriods:
    """Project finance period sorting via sort_period_keys public API."""

    def test_relative_years_natural_order(self):
        """Year 1 < Year 2 < Year 10 < Year 30 (not lexicographic)."""
        result = sort_period_keys(["Year 10", "Year 2", "Year 30", "Year 1"])
        assert result == ["Year 1", "Year 2", "Year 10", "Year 30"]

    def test_cod_relative_order(self):
        """Pre-COD < COD-2 < COD < COD+1 < COD+5 < Post-COD."""
        result = sort_period_keys([
            "COD+5", "Pre-COD", "COD", "Post-COD", "COD-2", "COD+1"
        ])
        assert result == ["Pre-COD", "COD-2", "COD", "COD+1", "COD+5", "Post-COD"]

    def test_phase_years_construction_before_operations(self):
        """Construction years sort before operations years."""
        result = sort_period_keys([
            "Ops Yr 1", "Construction Year 2", "Construction Year 1", "Ops Yr 2"
        ])
        assert result == [
            "Construction Year 1", "Construction Year 2", "Ops Yr 1", "Ops Yr 2"
        ]

    def test_stub_sorts_after_cod(self):
        """Stub periods sort after COD-relative periods."""
        result = sort_period_keys(["Stub", "COD+1", "Year 1"])
        assert result == ["Year 1", "COD+1", "Stub"]

    def test_pf_before_unrecognized(self):
        """All PF types sort before unrecognized strings."""
        result = sort_period_keys(["unknown_label", "Year 5", "COD"])
        assert result == ["Year 5", "COD", "unknown_label"]
