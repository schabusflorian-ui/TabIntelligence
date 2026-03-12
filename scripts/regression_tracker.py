#!/usr/bin/env python3
"""
Regression tracker for DebtFund extraction benchmark results.

Compares latest benchmark results against saved baselines to detect
accuracy regressions. Supports per-fixture configurable thresholds.

Usage:
    # Check for regressions against baselines
    python scripts/regression_tracker.py \
        --results-dir data/benchmark_results/ \
        --baselines-dir data/benchmark_baselines/

    # Update baselines from latest results
    python scripts/regression_tracker.py \
        --results-dir data/benchmark_results/ \
        --baselines-dir data/benchmark_baselines/ \
        --update-baselines

    # Check a single fixture
    python scripts/regression_tracker.py \
        --results-dir data/benchmark_results/ \
        --baselines-dir data/benchmark_baselines/ \
        --fixture realistic_model

Exit codes:
    0 - All fixtures pass (or no baselines to compare against)
    1 - One or more fixtures regressed beyond threshold
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Default thresholds: max allowed accuracy drop (as fraction, e.g. 0.02 = 2%)
DEFAULT_THRESHOLDS = {
    "mapping": 0.02,  # 2% mapping accuracy drop
    "triage": 0.00,   # 0% triage accuracy drop (triage should be stable)
}

# Per-fixture threshold overrides for fixtures expected to have lower accuracy
FIXTURE_THRESHOLDS = {
    "realistic_model": {"mapping": 0.02, "triage": 0.00},
    "saas_startup": {"mapping": 0.05, "triage": 0.00},
    "seed_burn": {"mapping": 0.05, "triage": 0.00},
    "european_model": {"mapping": 0.05, "triage": 0.00},
    "edge_cases": {"mapping": 0.05, "triage": 0.05},
    "large_model": {"mapping": 0.03, "triage": 0.00},
    "messy_startup": {"mapping": 0.05, "triage": 0.05},
}


@dataclass
class RegressionResult:
    """Result of comparing a fixture against its baseline."""
    fixture_name: str
    passed: bool
    baseline_mapping: float | None = None
    current_mapping: float | None = None
    mapping_delta: float | None = None
    mapping_threshold: float = 0.02
    baseline_triage: float | None = None
    current_triage: float | None = None
    triage_delta: float | None = None
    triage_threshold: float = 0.00
    reason: str = ""
    warnings: list = field(default_factory=list)


def get_thresholds(fixture_name: str, threshold_file: str | None = None) -> dict:
    """Get thresholds for a fixture, with optional override from file."""
    if threshold_file:
        path = Path(threshold_file)
        if path.exists():
            with open(path) as f:
                custom = json.load(f)
            if fixture_name in custom:
                return custom[fixture_name]

    return FIXTURE_THRESHOLDS.get(fixture_name, DEFAULT_THRESHOLDS)


def load_baselines(baselines_dir: str) -> dict:
    """Load baseline files from directory. Returns {fixture_name: data}."""
    dir_path = Path(baselines_dir)
    if not dir_path.is_dir():
        return {}

    baselines = {}
    for f in dir_path.glob("*.json"):
        if f.name == ".gitkeep":
            continue
        try:
            with open(f) as fh:
                data = json.load(fh)
            baselines[f.stem] = data
        except (json.JSONDecodeError, OSError):
            continue
    return baselines


def load_latest_results(results_dir: str) -> dict:
    """Load the latest result per fixture from results directory.

    Result files are named like 20260310_210742.json and contain a "file" key.
    Returns {fixture_name: data}.
    """
    dir_path = Path(results_dir)
    if not dir_path.is_dir():
        return {}

    # Collect all result files sorted by name (timestamp-based, newest last)
    result_files = sorted(dir_path.glob("*.json"))

    # Keep latest per fixture
    latest = {}
    for f in result_files:
        try:
            with open(f) as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue

        # Extract fixture name from the "file" field (e.g. "realistic_model.xlsx")
        file_name = data.get("file", "")
        if not file_name:
            continue
        fixture_name = Path(file_name).stem
        latest[fixture_name] = data

    return latest


def compare_fixture(
    fixture_name: str,
    result: dict,
    baseline: dict,
    threshold_file: str | None = None,
) -> RegressionResult:
    """Compare a single fixture's result against its baseline."""
    thresholds = get_thresholds(fixture_name, threshold_file)
    mapping_threshold = thresholds.get("mapping", DEFAULT_THRESHOLDS["mapping"])
    triage_threshold = thresholds.get("triage", DEFAULT_THRESHOLDS["triage"])

    reg = RegressionResult(
        fixture_name=fixture_name,
        passed=True,
        mapping_threshold=mapping_threshold,
        triage_threshold=triage_threshold,
    )

    # Extract accuracies from result
    mapping_acc = result.get("mapping_accuracy", {})
    triage_acc = result.get("triage_accuracy", {})
    current_mapping = mapping_acc.get("accuracy")
    current_triage = triage_acc.get("accuracy")

    # Extract accuracies from baseline
    baseline_mapping = baseline.get("mapping_accuracy", {}).get("accuracy")
    baseline_triage = baseline.get("triage_accuracy", {}).get("accuracy")

    reg.current_mapping = current_mapping
    reg.current_triage = current_triage
    reg.baseline_mapping = baseline_mapping
    reg.baseline_triage = baseline_triage

    # Check mapping regression
    if current_mapping is not None and baseline_mapping is not None:
        reg.mapping_delta = current_mapping - baseline_mapping
        if reg.mapping_delta < -mapping_threshold:
            reg.passed = False
            reg.reason = (
                f"Mapping accuracy dropped {abs(reg.mapping_delta):.1%} "
                f"({baseline_mapping:.1%} -> {current_mapping:.1%}), "
                f"threshold: {mapping_threshold:.1%}"
            )
    elif current_mapping is None:
        reg.warnings.append("No mapping accuracy in current result")

    # Check triage regression
    if current_triage is not None and baseline_triage is not None:
        reg.triage_delta = current_triage - baseline_triage
        if reg.triage_delta < -triage_threshold:
            reg.passed = False
            triage_msg = (
                f"Triage accuracy dropped {abs(reg.triage_delta):.1%} "
                f"({baseline_triage:.1%} -> {current_triage:.1%}), "
                f"threshold: {triage_threshold:.1%}"
            )
            if reg.reason:
                reg.reason += "; " + triage_msg
            else:
                reg.reason = triage_msg
    elif current_triage is None:
        reg.warnings.append("No triage accuracy in current result")

    # Note improvements
    if reg.mapping_delta is not None and reg.mapping_delta > 0:
        reg.warnings.append(
            f"Mapping improved +{reg.mapping_delta:.1%}"
        )
    if reg.triage_delta is not None and reg.triage_delta > 0:
        reg.warnings.append(
            f"Triage improved +{reg.triage_delta:.1%}"
        )

    return reg


def update_baselines(results: dict, baselines_dir: str) -> list:
    """Write current results as new baselines. Returns list of written files."""
    dir_path = Path(baselines_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    written = []
    for fixture_name, data in results.items():
        out_path = dir_path / f"{fixture_name}.json"
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)
        written.append(str(out_path))
    return written


def print_results(results: list[RegressionResult]):
    """Print regression check results as a formatted table."""
    if not results:
        print("No results to display.")
        return

    print("\n" + "=" * 80)
    print("REGRESSION CHECK RESULTS")
    print("=" * 80)

    # Header
    print(f"{'Fixture':<25} {'Status':<8} {'Mapping':<20} {'Triage':<20}")
    print("-" * 80)

    for r in results:
        status = "PASS" if r.passed else "FAIL"

        if r.baseline_mapping is not None and r.current_mapping is not None:
            delta_str = f"{r.mapping_delta:+.1%}" if r.mapping_delta else "+0.0%"
            mapping_str = f"{r.current_mapping:.1%} ({delta_str})"
        elif r.current_mapping is not None:
            mapping_str = f"{r.current_mapping:.1%} (new)"
        else:
            mapping_str = "N/A"

        if r.baseline_triage is not None and r.current_triage is not None:
            delta_str = f"{r.triage_delta:+.1%}" if r.triage_delta else "+0.0%"
            triage_str = f"{r.current_triage:.1%} ({delta_str})"
        elif r.current_triage is not None:
            triage_str = f"{r.current_triage:.1%} (new)"
        else:
            triage_str = "N/A"

        print(f"{r.fixture_name:<25} {status:<8} {mapping_str:<20} {triage_str:<20}")

        if not r.passed:
            print(f"  >> {r.reason}")
        for w in r.warnings:
            print(f"  -- {w}")

    print("=" * 80)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{passed}/{total} fixtures passed regression check.")


def main():
    parser = argparse.ArgumentParser(
        description="Check benchmark results for accuracy regressions"
    )
    parser.add_argument(
        "--results-dir",
        default="data/benchmark_results/",
        help="Directory containing benchmark result JSON files",
    )
    parser.add_argument(
        "--baselines-dir",
        default="data/benchmark_baselines/",
        help="Directory containing baseline JSON files",
    )
    parser.add_argument(
        "--threshold-file",
        help="JSON file with per-fixture threshold overrides",
    )
    parser.add_argument(
        "--update-baselines",
        action="store_true",
        help="Save current results as new baselines",
    )
    parser.add_argument(
        "--fixture",
        help="Check only a specific fixture (by name, without extension)",
    )
    args = parser.parse_args()

    # Load data
    baselines = load_baselines(args.baselines_dir)
    latest_results = load_latest_results(args.results_dir)

    if not latest_results:
        print(f"No benchmark results found in {args.results_dir}")
        sys.exit(0)

    # Filter to single fixture if requested
    if args.fixture:
        if args.fixture not in latest_results:
            print(f"No results found for fixture: {args.fixture}")
            print(f"Available: {', '.join(sorted(latest_results.keys()))}")
            sys.exit(1)
        latest_results = {args.fixture: latest_results[args.fixture]}

    # Update baselines mode
    if args.update_baselines:
        written = update_baselines(latest_results, args.baselines_dir)
        print(f"Updated {len(written)} baselines:")
        for w in written:
            print(f"  {w}")
        sys.exit(0)

    # Compare against baselines
    regression_results = []
    for fixture_name, result in sorted(latest_results.items()):
        baseline = baselines.get(fixture_name)
        if baseline is None:
            # No baseline — first run, pass with warning
            reg = RegressionResult(
                fixture_name=fixture_name,
                passed=True,
                current_mapping=result.get("mapping_accuracy", {}).get("accuracy"),
                current_triage=result.get("triage_accuracy", {}).get("accuracy"),
            )
            reg.warnings.append("No baseline — first run, skipping comparison")
            regression_results.append(reg)
        else:
            reg = compare_fixture(
                fixture_name, result, baseline, args.threshold_file
            )
            regression_results.append(reg)

    print_results(regression_results)

    # Exit code
    if all(r.passed for r in regression_results):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
