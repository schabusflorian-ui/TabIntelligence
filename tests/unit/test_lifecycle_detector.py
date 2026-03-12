"""Tests for LifecycleDetector — project finance lifecycle phase detection."""

from decimal import Decimal

from src.validation.lifecycle_detector import LifecycleDetector

D = Decimal


def _pf_data_25_periods():
    """25-period project finance model with full lifecycle."""
    data = {}
    # Periods 1-3: construction (capex, no revenue)
    for p in range(1, 4):
        data[str(float(p))] = {
            "revenue": D("0"),
            "capex": D("-15000000"),
            "debt_drawdown": D("10000000"),
            "cfads": D("0"),
            "dscr": D("0"),
        }
    # Period 4: ramp-up (low revenue)
    data["4.0"] = {
        "revenue": D("2000000"),
        "capex": D("-1000000"),
        "cfads": D("1000000"),
        "dscr": D("1.1"),
    }
    # Periods 5-22: operations (steady revenue ~20M)
    for p in range(5, 23):
        data[str(float(p))] = {
            "revenue": D("20000000"),
            "capex": D("-500000"),
            "cfads": D("15000000"),
            "dscr": D("1.5"),
        }
    # Period 23-24: tail (declining revenue)
    data["23.0"] = {
        "revenue": D("8000000"),
        "capex": D("0"),
        "cfads": D("5000000"),
        "dscr": D("1.1"),
    }
    data["24.0"] = {
        "revenue": D("3000000"),
        "capex": D("0"),
        "cfads": D("2000000"),
        "dscr": D("0.9"),
    }
    # Period 25: post-operations
    data["25.0"] = {
        "revenue": D("0"),
        "capex": D("0"),
        "cfads": D("0"),
        "dscr": D("0"),
    }
    return data


class TestPFDetection:
    """Test is_project_finance detection."""

    def setup_method(self):
        self.detector = LifecycleDetector()

    def test_pf_model_detected(self):
        """Data with cfads + dscr + debt_service -> is_project_finance=True."""
        data = {
            "1.0": {"revenue": D("0"), "cfads": D("0"), "dscr": D("0"), "debt_service": D("-100")},
            "2.0": {"revenue": D("1000"), "cfads": D("800"), "dscr": D("1.5")},
        }
        result = self.detector.detect(data)
        assert result.is_project_finance is True

    def test_corporate_model_not_pf(self):
        """Data with only revenue + cogs + net_income -> is_project_finance=False."""
        data = {
            "1.0": {"revenue": D("1000"), "cogs": D("600"), "net_income": D("200")},
            "2.0": {"revenue": D("1100"), "cogs": D("660"), "net_income": D("220")},
        }
        result = self.detector.detect(data)
        assert result.is_project_finance is False

    def test_single_pf_indicator_not_enough(self):
        """Only one PF indicator present -> is_project_finance=False."""
        data = {
            "1.0": {"revenue": D("1000"), "dscr": D("1.5")},
            "2.0": {"revenue": D("1100")},
        }
        result = self.detector.detect(data)
        assert result.is_project_finance is False

    def test_empty_data_not_pf(self):
        """Empty data -> is_project_finance=False."""
        result = self.detector.detect({})
        assert result.is_project_finance is False
        assert result.phases == {}
        assert result.confidence == 0.0


class TestPhaseDetection:
    """Test 7-phase lifecycle detection."""

    def setup_method(self):
        self.detector = LifecycleDetector()

    def test_full_lifecycle_pf_model(self):
        """25-period PF model with construction, ramp-up, operations, tail, post-ops."""
        data = _pf_data_25_periods()
        result = self.detector.detect(data)

        assert result.is_project_finance is True
        # Construction periods
        assert result.phases["1.0"] == "construction"
        assert result.phases["2.0"] == "construction"
        assert result.phases["3.0"] == "construction"
        # Ramp-up
        assert result.phases["4.0"] == "ramp_up"
        # Operations (spot check)
        assert result.phases["10.0"] == "operations"
        assert result.phases["15.0"] == "operations"
        # Post-operations
        assert result.phases["25.0"] == "post_operations"

    def test_construction_detected(self):
        """Zero revenue + high capex = construction."""
        data = {
            "1.0": {"revenue": D("0"), "capex": D("-20000000"), "cfads": D("0"), "dscr": D("0")},
            "2.0": {"revenue": D("0"), "capex": D("-15000000"), "cfads": D("0"), "dscr": D("0")},
            "3.0": {"revenue": D("10000000"), "cfads": D("8000000"), "dscr": D("1.5")},
        }
        result = self.detector.detect(data)
        assert result.phases["1.0"] == "construction"
        assert result.phases["2.0"] == "construction"

    def test_pre_construction_detected(self):
        """Drawdown without capex = pre_construction."""
        data = {
            "1.0": {
                "revenue": D("0"),
                "capex": D("0"),
                "debt_drawdown": D("5000000"),
                "cfads": D("0"),
                "dscr": D("0"),
            },
            "2.0": {"revenue": D("0"), "capex": D("-20000000"), "cfads": D("0"), "dscr": D("0")},
            "3.0": {"revenue": D("10000000"), "cfads": D("8000000"), "dscr": D("1.5")},
        }
        result = self.detector.detect(data)
        assert result.phases["1.0"] == "pre_construction"
        assert result.phases["2.0"] == "construction"

    def test_ramp_up_detected(self):
        """First revenue periods below 50% median = ramp_up."""
        data = {
            "1.0": {"revenue": D("0"), "capex": D("-10000000"), "cfads": D("0"), "dscr": D("0")},
            "2.0": {
                "revenue": D("3000000"),
                "cfads": D("2000000"),
                "dscr": D("1.1"),
            },  # < 50% of 20M
            "3.0": {"revenue": D("20000000"), "cfads": D("15000000"), "dscr": D("1.5")},
            "4.0": {"revenue": D("20000000"), "cfads": D("15000000"), "dscr": D("1.5")},
            "5.0": {"revenue": D("20000000"), "cfads": D("15000000"), "dscr": D("1.5")},
        }
        result = self.detector.detect(data)
        assert result.phases["2.0"] == "ramp_up"
        assert result.phases["3.0"] == "operations"

    def test_operations_steady_state(self):
        """Stable revenue periods = operations."""
        data = {
            "1.0": {"revenue": D("20000000"), "cfads": D("15000000"), "dscr": D("1.5")},
            "2.0": {"revenue": D("21000000"), "cfads": D("16000000"), "dscr": D("1.5")},
            "3.0": {"revenue": D("19000000"), "cfads": D("14000000"), "dscr": D("1.4")},
        }
        result = self.detector.detect(data)
        for p in ["1.0", "2.0", "3.0"]:
            assert result.phases[p] == "operations"

    def test_maintenance_shutdown_detected(self):
        """Zero-revenue dip within ops = maintenance_shutdown."""
        data = {
            "1.0": {"revenue": D("20000000"), "cfads": D("15000000"), "dscr": D("1.5")},
            "2.0": {"revenue": D("20000000"), "cfads": D("15000000"), "dscr": D("1.5")},
            "3.0": {"revenue": D("0"), "cfads": D("0"), "dscr": D("0")},  # shutdown
            "4.0": {"revenue": D("20000000"), "cfads": D("15000000"), "dscr": D("1.5")},
            "5.0": {"revenue": D("20000000"), "cfads": D("15000000"), "dscr": D("1.5")},
        }
        result = self.detector.detect(data)
        assert result.phases["3.0"] == "maintenance_shutdown"
        assert result.phases["2.0"] == "operations"
        assert result.phases["4.0"] == "operations"

    def test_tail_detected(self):
        """Declining revenue below 50% peak at end = tail."""
        data = _pf_data_25_periods()
        result = self.detector.detect(data)
        # Period 23 and 24 have revenues of 8M and 3M vs 20M peak
        # Both < 50% of 20M = 10M, and declining
        assert result.phases["23.0"] == "tail"
        assert result.phases["24.0"] == "tail"

    def test_post_operations_detected(self):
        """Zero revenue after last ops period = post_operations."""
        data = {
            "1.0": {"revenue": D("20000000"), "cfads": D("15000000"), "dscr": D("1.5")},
            "2.0": {"revenue": D("20000000"), "cfads": D("15000000"), "dscr": D("1.5")},
            "3.0": {"revenue": D("0"), "cfads": D("0"), "dscr": D("0")},
        }
        result = self.detector.detect(data)
        assert result.phases["3.0"] == "post_operations"

    def test_no_revenue_returns_empty(self):
        """No revenue data -> empty phases dict."""
        data = {
            "1.0": {"capex": D("-10000000"), "cfads": D("0"), "dscr": D("0")},
            "2.0": {"capex": D("-5000000"), "cfads": D("0"), "dscr": D("0")},
        }
        result = self.detector.detect(data)
        assert result.phases == {}

    def test_all_revenue_positive_all_operations(self):
        """Every period has revenue -> all operations (no construction/post_ops)."""
        data = {
            "1.0": {"revenue": D("20000000"), "cfads": D("15000000"), "dscr": D("1.5")},
            "2.0": {"revenue": D("21000000"), "cfads": D("16000000"), "dscr": D("1.5")},
            "3.0": {"revenue": D("22000000"), "cfads": D("17000000"), "dscr": D("1.6")},
        }
        result = self.detector.detect(data)
        for p in ["1.0", "2.0", "3.0"]:
            assert result.phases[p] == "operations"


class TestBackwardCompatibility:
    """Ensure corporate model detection matches the old 3-phase heuristic."""

    def setup_method(self):
        self.detector = LifecycleDetector()

    def test_corporate_model_simple_phases(self):
        """Non-PF model gets only construction/operations/post_operations."""
        data = {
            "1.0": {"revenue": D("0"), "cogs": D("0")},
            "2.0": {"revenue": D("0"), "cogs": D("0")},
            "3.0": {"revenue": D("1000000"), "cogs": D("600000")},
            "4.0": {"revenue": D("1100000"), "cogs": D("660000")},
            "5.0": {"revenue": D("0"), "cogs": D("0")},
        }
        result = self.detector.detect(data)
        assert result.is_project_finance is False
        assert result.phases["1.0"] == "construction"
        assert result.phases["2.0"] == "construction"
        assert result.phases["3.0"] == "operations"
        assert result.phases["4.0"] == "operations"
        assert result.phases["5.0"] == "post_operations"

    def test_corporate_no_ramp_up(self):
        """Corporate models should NOT get ramp_up phase."""
        data = {
            "1.0": {"revenue": D("0")},
            "2.0": {"revenue": D("100")},  # low revenue
            "3.0": {"revenue": D("1000")},
            "4.0": {"revenue": D("1000")},
        }
        result = self.detector.detect(data)
        assert result.is_project_finance is False
        # Should not have ramp_up
        assert "ramp_up" not in result.phases.values()


class TestConfidence:
    """Test confidence and signals_used."""

    def setup_method(self):
        self.detector = LifecycleDetector()

    def test_confidence_scales_with_signals(self):
        """More signals -> higher confidence."""
        # Only revenue
        data_low = {
            "1.0": {"revenue": D("1000")},
            "2.0": {"revenue": D("1100")},
        }
        result_low = self.detector.detect(data_low)

        # Revenue + capex + dscr
        data_high = {
            "1.0": {"revenue": D("0"), "capex": D("-10000000"), "cfads": D("0"), "dscr": D("0")},
            "2.0": {
                "revenue": D("1000"),
                "capex": D("-500000"),
                "cfads": D("800"),
                "dscr": D("1.5"),
            },
        }
        result_high = self.detector.detect(data_high)

        assert result_high.confidence > result_low.confidence

    def test_signals_used_list(self):
        """signals_used should list the signals that had data."""
        data = {
            "1.0": {"revenue": D("1000"), "capex": D("-500")},
            "2.0": {"revenue": D("1100"), "dscr": D("1.5")},
        }
        result = self.detector.detect(data)
        assert "revenue" in result.signals_used
        assert "capex" in result.signals_used
        assert "dscr" in result.signals_used
        assert "debt_drawdown" not in result.signals_used


class TestPeriodSorting:
    """Test period sorting edge cases."""

    def setup_method(self):
        self.detector = LifecycleDetector()

    def test_numeric_periods_sorted(self):
        """Numeric period keys should be sorted numerically."""
        data = {
            "3.0": {"revenue": D("1000")},
            "1.0": {"revenue": D("0")},
            "2.0": {"revenue": D("500")},
        }
        result = self.detector.detect(data)
        assert result.phases["1.0"] == "construction"
        assert result.phases["2.0"] == "operations"
        assert result.phases["3.0"] == "operations"

    def test_fiscal_year_periods(self):
        """Non-numeric period keys (FY2022, FY2023) should work."""
        data = {
            "FY2022": {"revenue": D("1000")},
            "FY2023": {"revenue": D("1100")},
        }
        result = self.detector.detect(data)
        assert len(result.phases) == 2
        # Both should be operations (all have revenue)
        for phase in result.phases.values():
            assert phase == "operations"
