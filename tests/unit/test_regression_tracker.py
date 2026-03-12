"""Tests for regression_tracker.py."""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.regression_tracker import (
    compare_fixture,
    get_thresholds,
    load_baselines,
    load_latest_results,
    update_baselines,
)


class TestGetThresholds:
    """Tests for threshold loading."""

    def test_default_thresholds(self):
        """Unknown fixture gets default thresholds."""
        t = get_thresholds("unknown_fixture")
        assert t["mapping"] == 0.02
        assert t["triage"] == 0.00

    def test_known_fixture_thresholds(self):
        """Known fixture gets its configured thresholds."""
        t = get_thresholds("edge_cases")
        assert t["mapping"] == 0.05
        assert t["triage"] == 0.05

    def test_threshold_file_override(self, tmp_path):
        """Custom threshold file overrides defaults."""
        threshold_file = tmp_path / "thresholds.json"
        threshold_file.write_text(json.dumps({"my_fixture": {"mapping": 0.10, "triage": 0.03}}))

        t = get_thresholds("my_fixture", str(threshold_file))
        assert t["mapping"] == 0.10
        assert t["triage"] == 0.03

    def test_threshold_file_missing_fixture(self, tmp_path):
        """Fixture not in threshold file falls back to defaults."""
        threshold_file = tmp_path / "thresholds.json"
        threshold_file.write_text(json.dumps({"other": {"mapping": 0.10}}))

        t = get_thresholds("unknown", str(threshold_file))
        assert t["mapping"] == 0.02  # default


class TestLoadBaselines:
    """Tests for baseline loading."""

    def test_load_baselines_missing_dir(self):
        """Returns empty dict when directory doesn't exist."""
        result = load_baselines("/nonexistent/path/baselines")
        assert result == {}

    def test_load_baselines_empty_dir(self, tmp_path):
        """Returns empty dict for empty directory."""
        result = load_baselines(str(tmp_path))
        assert result == {}

    def test_load_baselines_valid(self, tmp_path):
        """Loads baseline JSON files correctly."""
        (tmp_path / "realistic_model.json").write_text(
            json.dumps(
                {
                    "mapping_accuracy": {"accuracy": 0.98},
                    "triage_accuracy": {"accuracy": 1.0},
                }
            )
        )
        (tmp_path / "saas_startup.json").write_text(
            json.dumps(
                {
                    "mapping_accuracy": {"accuracy": 0.85},
                    "triage_accuracy": {"accuracy": 0.90},
                }
            )
        )

        result = load_baselines(str(tmp_path))

        assert len(result) == 2
        assert "realistic_model" in result
        assert "saas_startup" in result
        assert result["realistic_model"]["mapping_accuracy"]["accuracy"] == 0.98

    def test_load_baselines_skips_invalid_json(self, tmp_path):
        """Skips files with invalid JSON."""
        (tmp_path / "good.json").write_text(json.dumps({"foo": "bar"}))
        (tmp_path / "bad.json").write_text("not json{{{")

        result = load_baselines(str(tmp_path))
        assert len(result) == 1
        assert "good" in result


class TestLoadLatestResults:
    """Tests for loading latest results."""

    def test_load_latest_missing_dir(self):
        """Returns empty dict when directory doesn't exist."""
        result = load_latest_results("/nonexistent/path")
        assert result == {}

    def test_load_latest_empty_dir(self, tmp_path):
        """Returns empty dict for empty directory."""
        result = load_latest_results(str(tmp_path))
        assert result == {}

    def test_load_latest_picks_newest_per_fixture(self, tmp_path):
        """Keeps the latest result per fixture (by filename sort)."""
        (tmp_path / "20260101_120000.json").write_text(
            json.dumps(
                {
                    "file": "realistic_model.xlsx",
                    "mapping_accuracy": {"accuracy": 0.90},
                }
            )
        )
        (tmp_path / "20260201_120000.json").write_text(
            json.dumps(
                {
                    "file": "realistic_model.xlsx",
                    "mapping_accuracy": {"accuracy": 0.95},
                }
            )
        )

        result = load_latest_results(str(tmp_path))

        assert len(result) == 1
        assert result["realistic_model"]["mapping_accuracy"]["accuracy"] == 0.95

    def test_load_latest_multiple_fixtures(self, tmp_path):
        """Loads results for multiple fixtures."""
        (tmp_path / "20260101_120000.json").write_text(
            json.dumps(
                {
                    "file": "realistic_model.xlsx",
                    "mapping_accuracy": {"accuracy": 0.95},
                }
            )
        )
        (tmp_path / "20260102_120000.json").write_text(
            json.dumps(
                {
                    "file": "saas_startup.xlsx",
                    "mapping_accuracy": {"accuracy": 0.85},
                }
            )
        )

        result = load_latest_results(str(tmp_path))

        assert len(result) == 2
        assert "realistic_model" in result
        assert "saas_startup" in result


class TestCompareFixture:
    """Tests for fixture comparison logic."""

    def test_no_regression_passes(self):
        """Same accuracy as baseline passes."""
        result = {
            "mapping_accuracy": {"accuracy": 0.95},
            "triage_accuracy": {"accuracy": 1.0},
        }
        baseline = {
            "mapping_accuracy": {"accuracy": 0.95},
            "triage_accuracy": {"accuracy": 1.0},
        }

        reg = compare_fixture("realistic_model", result, baseline)
        assert reg.passed is True
        assert reg.mapping_delta == 0.0
        assert reg.triage_delta == 0.0

    def test_regression_within_threshold_passes(self):
        """1% drop with 2% threshold passes."""
        result = {
            "mapping_accuracy": {"accuracy": 0.94},
            "triage_accuracy": {"accuracy": 1.0},
        }
        baseline = {
            "mapping_accuracy": {"accuracy": 0.95},
            "triage_accuracy": {"accuracy": 1.0},
        }

        reg = compare_fixture("realistic_model", result, baseline)
        assert reg.passed is True
        assert reg.mapping_delta == pytest.approx(-0.01)

    def test_regression_exceeds_threshold_fails(self):
        """3% drop with 2% threshold fails."""
        result = {
            "mapping_accuracy": {"accuracy": 0.92},
            "triage_accuracy": {"accuracy": 1.0},
        }
        baseline = {
            "mapping_accuracy": {"accuracy": 0.95},
            "triage_accuracy": {"accuracy": 1.0},
        }

        reg = compare_fixture("realistic_model", result, baseline)
        assert reg.passed is False
        assert "Mapping accuracy dropped" in reg.reason

    def test_improvement_passes(self):
        """Accuracy going up always passes."""
        result = {
            "mapping_accuracy": {"accuracy": 0.98},
            "triage_accuracy": {"accuracy": 1.0},
        }
        baseline = {
            "mapping_accuracy": {"accuracy": 0.95},
            "triage_accuracy": {"accuracy": 0.90},
        }

        reg = compare_fixture("realistic_model", result, baseline)
        assert reg.passed is True
        assert reg.mapping_delta == pytest.approx(0.03)
        assert any("improved" in w for w in reg.warnings)

    def test_triage_regression_fails(self):
        """Triage regression with 0% threshold fails on any drop."""
        result = {
            "mapping_accuracy": {"accuracy": 0.95},
            "triage_accuracy": {"accuracy": 0.875},
        }
        baseline = {
            "mapping_accuracy": {"accuracy": 0.95},
            "triage_accuracy": {"accuracy": 1.0},
        }

        reg = compare_fixture("realistic_model", result, baseline)
        assert reg.passed is False
        assert "Triage accuracy dropped" in reg.reason

    def test_per_fixture_thresholds(self):
        """Edge cases fixture has 5% threshold."""
        result = {
            "mapping_accuracy": {"accuracy": 0.80},
            "triage_accuracy": {"accuracy": 0.90},
        }
        baseline = {
            "mapping_accuracy": {"accuracy": 0.84},
            "triage_accuracy": {"accuracy": 0.94},
        }

        # 4% mapping drop, within 5% threshold
        reg = compare_fixture("edge_cases", result, baseline)
        assert reg.passed is True

    def test_per_fixture_thresholds_exceeded(self):
        """Edge cases fixture fails when threshold exceeded."""
        result = {
            "mapping_accuracy": {"accuracy": 0.75},
            "triage_accuracy": {"accuracy": 1.0},
        }
        baseline = {
            "mapping_accuracy": {"accuracy": 0.84},
            "triage_accuracy": {"accuracy": 1.0},
        }

        # 9% mapping drop exceeds 5% threshold
        reg = compare_fixture("edge_cases", result, baseline)
        assert reg.passed is False

    def test_missing_accuracy_warns(self):
        """Missing accuracy fields produce warnings."""
        result = {}
        baseline = {
            "mapping_accuracy": {"accuracy": 0.95},
            "triage_accuracy": {"accuracy": 1.0},
        }

        reg = compare_fixture("test", result, baseline)
        assert reg.passed is True  # No data to compare, passes
        assert any("No mapping accuracy" in w for w in reg.warnings)


class TestUpdateBaselines:
    """Tests for baseline update."""

    def test_update_baselines_writes_files(self, tmp_path):
        """Writes baseline files correctly."""
        results = {
            "realistic_model": {
                "mapping_accuracy": {"accuracy": 0.98},
                "triage_accuracy": {"accuracy": 1.0},
            },
            "saas_startup": {
                "mapping_accuracy": {"accuracy": 0.85},
            },
        }

        written = update_baselines(results, str(tmp_path / "baselines"))

        assert len(written) == 2
        assert (tmp_path / "baselines" / "realistic_model.json").exists()
        assert (tmp_path / "baselines" / "saas_startup.json").exists()

        # Verify content
        with open(tmp_path / "baselines" / "realistic_model.json") as f:
            data = json.load(f)
        assert data["mapping_accuracy"]["accuracy"] == 0.98

    def test_update_baselines_creates_dir(self, tmp_path):
        """Creates baselines directory if it doesn't exist."""
        baselines_dir = tmp_path / "new" / "baselines"
        assert not baselines_dir.exists()

        update_baselines({"test": {"foo": "bar"}}, str(baselines_dir))

        assert baselines_dir.exists()
        assert (baselines_dir / "test.json").exists()
