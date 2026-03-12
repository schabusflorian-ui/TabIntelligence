"""Unit tests for benchmark_extraction.py helper functions."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.benchmark_extraction import (
    _compare_results,
    _discover_fixtures,
    _evaluate_mapping_accuracy,
    _load_previous_result,
    _print_aggregate_summary,
)


class TestPerStatementAccuracy:
    """Tests for per-statement accuracy grouping."""

    def test_per_statement_accuracy(self):
        """Groups accuracy by sheet field correctly."""
        result = {
            "line_items": [
                {"original_label": "Revenue", "canonical_name": "revenue"},
                {"original_label": "COGS", "canonical_name": "cogs"},
                {"original_label": "Total Assets", "canonical_name": "total_assets"},
                {"original_label": "Cash", "canonical_name": "cash"},
            ]
        }
        expected = {
            "expected_mappings": [
                {"original_label": "Revenue", "canonical_name": "revenue", "sheet": "IS"},
                {"original_label": "COGS", "canonical_name": "cogs", "sheet": "IS"},
                {"original_label": "Total Assets", "canonical_name": "total_assets", "sheet": "BS"},
                {"original_label": "Cash", "canonical_name": "cash", "sheet": "BS"},
            ],
            "acceptable_alternatives": {},
        }

        acc = _evaluate_mapping_accuracy(result, expected)

        assert "per_statement" in acc
        assert "IS" in acc["per_statement"]
        assert "BS" in acc["per_statement"]
        assert acc["per_statement"]["IS"]["correct"] == 2
        assert acc["per_statement"]["IS"]["total"] == 2
        assert acc["per_statement"]["IS"]["accuracy"] == 1.0
        assert acc["per_statement"]["BS"]["correct"] == 2
        assert acc["per_statement"]["BS"]["accuracy"] == 1.0

    def test_per_statement_with_mismatches(self):
        """Mismatches tracked per statement."""
        result = {
            "line_items": [
                {"original_label": "Revenue", "canonical_name": "revenue"},
                {"original_label": "COGS", "canonical_name": "wrong_name"},
            ]
        }
        expected = {
            "expected_mappings": [
                {"original_label": "Revenue", "canonical_name": "revenue", "sheet": "IS"},
                {"original_label": "COGS", "canonical_name": "cogs", "sheet": "IS"},
            ],
            "acceptable_alternatives": {},
        }

        acc = _evaluate_mapping_accuracy(result, expected)

        assert acc["per_statement"]["IS"]["correct"] == 1
        assert acc["per_statement"]["IS"]["total"] == 2
        assert acc["per_statement"]["IS"]["accuracy"] == 0.5
        assert len(acc["per_statement"]["IS"]["mismatches"]) == 1

    def test_per_statement_unknown_sheet(self):
        """Items without sheet field grouped under 'Unknown'."""
        result = {
            "line_items": [
                {"original_label": "Revenue", "canonical_name": "revenue"},
            ]
        }
        expected = {
            "expected_mappings": [
                {"original_label": "Revenue", "canonical_name": "revenue"},
            ],
            "acceptable_alternatives": {},
        }

        acc = _evaluate_mapping_accuracy(result, expected)

        assert "Unknown" in acc["per_statement"]
        assert acc["per_statement"]["Unknown"]["correct"] == 1


class TestCompareResults:
    """Tests for _compare_results delta computation."""

    def test_compare_accuracy_delta(self):
        """Computes mapping accuracy delta between two runs."""
        current = {
            "mapping_accuracy": {"accuracy": 0.85, "mismatches": []},
            "triage_accuracy": {"accuracy": 0.90},
        }
        previous = {
            "mapping_accuracy": {"accuracy": 0.75, "mismatches": []},
            "triage_accuracy": {"accuracy": 0.80},
        }

        diff = _compare_results(current, previous)

        assert diff["mapping_accuracy_delta"] == 0.1
        assert diff["triage_accuracy_delta"] == 0.1

    def test_compare_new_and_resolved_mismatches(self):
        """Identifies regression (new) and progress (resolved) mismatches."""
        current = {
            "mapping_accuracy": {
                "accuracy": 0.80,
                "mismatches": [
                    {"label": "Revenue"},
                    {"label": "EBITDA"},
                ],
            },
        }
        previous = {
            "mapping_accuracy": {
                "accuracy": 0.80,
                "mismatches": [
                    {"label": "Revenue"},
                    {"label": "COGS"},
                ],
            },
        }

        diff = _compare_results(current, previous)

        assert "EBITDA" in diff["new_mismatches"]
        assert "COGS" in diff["resolved_mismatches"]
        assert "Revenue" not in diff["new_mismatches"]

    def test_compare_quality_delta(self):
        """Quality score delta computed correctly."""
        current = {"quality": {"numeric_score": 0.85}}
        previous = {"quality": {"numeric_score": 0.70}}

        diff = _compare_results(current, previous)

        assert diff["quality_score_delta"] == 0.15

    def test_compare_completeness_delta(self):
        """Completeness score delta computed correctly."""
        current = {"completeness": {"overall_score": 0.90}}
        previous = {"completeness": {"overall_score": 0.80}}

        diff = _compare_results(current, previous)

        assert diff["completeness_score_delta"] == 0.10

    def test_compare_duration_delta(self):
        """Duration delta computed correctly."""
        current = {"duration_seconds": 15.0, "tokens_used": 5000}
        previous = {"duration_seconds": 20.0, "tokens_used": 6000}

        diff = _compare_results(current, previous)

        assert diff["duration_delta"] == -5.0
        assert diff["token_delta"] == -1000

    def test_compare_missing_fields_no_crash(self):
        """Missing fields don't cause crashes."""
        diff = _compare_results({}, {})

        assert "mapping_accuracy_delta" not in diff
        assert "triage_accuracy_delta" not in diff
        assert "quality_score_delta" not in diff


class TestLoadPreviousResult:
    """Tests for _load_previous_result."""

    def test_load_latest_no_directory(self, tmp_path):
        """Returns None when directory doesn't exist."""
        with patch("scripts.benchmark_extraction.PROJECT_ROOT", tmp_path):
            result = _load_previous_result("latest")
        assert result is None

    def test_load_latest_no_files(self, tmp_path):
        """Returns None when directory is empty."""
        results_dir = tmp_path / "data" / "benchmark_results"
        results_dir.mkdir(parents=True)
        with patch("scripts.benchmark_extraction.PROJECT_ROOT", tmp_path):
            result = _load_previous_result("latest")
        assert result is None

    def test_load_latest_picks_most_recent(self, tmp_path):
        """Picks the most recent file by filename sort."""
        results_dir = tmp_path / "data" / "benchmark_results"
        results_dir.mkdir(parents=True)

        (results_dir / "20240101_120000.json").write_text(
            json.dumps({"timestamp": "2024-01-01", "run": 1})
        )
        (results_dir / "20240201_120000.json").write_text(
            json.dumps({"timestamp": "2024-02-01", "run": 2})
        )

        with patch("scripts.benchmark_extraction.PROJECT_ROOT", tmp_path):
            result = _load_previous_result("latest")

        assert result is not None
        assert result["run"] == 2

    def test_load_specific_path(self, tmp_path):
        """Loads a specific file path."""
        f = tmp_path / "specific.json"
        f.write_text(json.dumps({"foo": "bar"}))

        result = _load_previous_result(str(f))

        assert result == {"foo": "bar"}

    def test_load_missing_path(self):
        """Returns None for non-existent path."""
        result = _load_previous_result("/nonexistent/file.json")
        assert result is None


class TestDiscoverFixtures:
    """Tests for _discover_fixtures directory scanning."""

    def test_discover_fixtures_finds_pairs(self, tmp_path):
        """Discovers xlsx files with matching expected JSON."""
        (tmp_path / "model_a.xlsx").write_bytes(b"fake xlsx")
        (tmp_path / "model_a_expected.json").write_text("{}")
        (tmp_path / "model_b.xlsx").write_bytes(b"fake xlsx")
        (tmp_path / "model_b_expected.json").write_text("{}")

        pairs = _discover_fixtures(str(tmp_path))

        assert len(pairs) == 2
        names = [p[0].stem for p in pairs]
        assert "model_a" in names
        assert "model_b" in names

    def test_discover_fixtures_skips_without_expected(self, tmp_path):
        """Skips xlsx files that have no matching expected JSON."""
        (tmp_path / "has_expected.xlsx").write_bytes(b"fake xlsx")
        (tmp_path / "has_expected_expected.json").write_text("{}")
        (tmp_path / "no_expected.xlsx").write_bytes(b"fake xlsx")

        pairs = _discover_fixtures(str(tmp_path))

        assert len(pairs) == 1
        assert pairs[0][0].stem == "has_expected"

    def test_discover_fixtures_empty_dir(self, tmp_path):
        """Returns empty list for directory with no xlsx files."""
        pairs = _discover_fixtures(str(tmp_path))
        assert pairs == []

    def test_discover_fixtures_sorted(self, tmp_path):
        """Results are sorted alphabetically."""
        for name in ["zebra", "alpha", "middle"]:
            (tmp_path / f"{name}.xlsx").write_bytes(b"fake xlsx")
            (tmp_path / f"{name}_expected.json").write_text("{}")

        pairs = _discover_fixtures(str(tmp_path))

        names = [p[0].stem for p in pairs]
        assert names == ["alpha", "middle", "zebra"]


class TestAggregateSummary:
    """Tests for _print_aggregate_summary computation."""

    def test_aggregate_summary_weighted_accuracy(self, capsys):
        """Weighted average is computed correctly across fixtures."""
        results = [
            {
                "fixture_name": "fixture_a",
                "failed": False,
                "triage_acc": {"correct": 8, "total": 8, "accuracy": 1.0},
                "mapping_acc": {"correct": 50, "total": 50, "accuracy": 1.0},
                "tokens_used": 10000,
                "cost_usd": 0.50,
                "duration": 30.0,
                "line_items_count": 50,
            },
            {
                "fixture_name": "fixture_b",
                "failed": False,
                "triage_acc": {"correct": 4, "total": 5, "accuracy": 0.80},
                "mapping_acc": {"correct": 40, "total": 50, "accuracy": 0.80},
                "tokens_used": 8000,
                "cost_usd": 0.40,
                "duration": 25.0,
                "line_items_count": 50,
            },
        ]

        _print_aggregate_summary(results)
        output = capsys.readouterr().out

        # Overall mapping: 90/100 = 90%
        assert "90.0%" in output
        # Overall triage: 12/13 = 92.3%
        assert "92.3%" in output

    def test_aggregate_summary_excludes_failed(self, capsys):
        """Failed fixtures are excluded from accuracy computation."""
        results = [
            {
                "fixture_name": "good",
                "failed": False,
                "triage_acc": {"correct": 5, "total": 5, "accuracy": 1.0},
                "mapping_acc": {"correct": 20, "total": 20, "accuracy": 1.0},
                "tokens_used": 5000,
                "cost_usd": 0.25,
                "duration": 15.0,
                "line_items_count": 20,
            },
            {
                "fixture_name": "bad",
                "failed": True,
                "triage_acc": None,
                "mapping_acc": None,
                "tokens_used": 0,
                "cost_usd": 0,
                "duration": 0,
                "line_items_count": 0,
            },
        ]

        _print_aggregate_summary(results)
        output = capsys.readouterr().out

        assert "1 passed, 1 failed" in output
        assert "100.0%" in output
