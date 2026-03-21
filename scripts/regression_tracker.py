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
    "triage": 0.00,  # 0% triage accuracy drop (triage should be stable)
    "f1": 0.02,      # 2% F1 drop
    "recall": 0.03,  # 3% recall drop (slightly more lenient — remapping can shift)
}

# Looser thresholds applied when taxonomy version changes between runs
TAXONOMY_CHANGE_THRESHOLDS = {
    "mapping": 0.05,
    "triage": 0.02,
    "f1": 0.05,
    "recall": 0.05,
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
    # F1 and recall
    baseline_f1: float | None = None
    current_f1: float | None = None
    f1_delta: float | None = None
    f1_threshold: float = 0.02
    baseline_recall: float | None = None
    current_recall: float | None = None
    recall_delta: float | None = None
    recall_threshold: float = 0.03
    # Taxonomy version tracking
    taxonomy_version_changed: bool = False
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
    """Compare a single fixture's result against its baseline.

    Checks mapping accuracy, F1, recall, and triage accuracy. If the
    taxonomy version changed between baseline and current, applies looser
    thresholds from TAXONOMY_CHANGE_THRESHOLDS.
    """
    thresholds = get_thresholds(fixture_name, threshold_file)

    # Detect taxonomy version change → apply looser thresholds
    current_tax_ver = result.get("taxonomy_version") or result.get("metadata", {}).get("taxonomy_version")
    baseline_tax_ver = baseline.get("taxonomy_version") or baseline.get("metadata", {}).get("taxonomy_version")
    taxonomy_changed = (
        current_tax_ver is not None
        and baseline_tax_ver is not None
        and current_tax_ver != baseline_tax_ver
    )

    if taxonomy_changed:
        effective_thresholds = {**thresholds}
        for key, val in TAXONOMY_CHANGE_THRESHOLDS.items():
            effective_thresholds[key] = max(effective_thresholds.get(key, val), val)
    else:
        effective_thresholds = thresholds

    mapping_threshold = effective_thresholds.get("mapping", DEFAULT_THRESHOLDS["mapping"])
    triage_threshold = effective_thresholds.get("triage", DEFAULT_THRESHOLDS["triage"])
    f1_threshold = effective_thresholds.get("f1", DEFAULT_THRESHOLDS["f1"])
    recall_threshold = effective_thresholds.get("recall", DEFAULT_THRESHOLDS["recall"])

    reg = RegressionResult(
        fixture_name=fixture_name,
        passed=True,
        mapping_threshold=mapping_threshold,
        triage_threshold=triage_threshold,
        f1_threshold=f1_threshold,
        recall_threshold=recall_threshold,
        taxonomy_version_changed=taxonomy_changed,
    )

    if taxonomy_changed:
        reg.warnings.append(
            f"Taxonomy version changed ({baseline_tax_ver} -> {current_tax_ver}), using looser thresholds"
        )

    # Extract accuracies from result (supports both old and new formats)
    mapping_acc = result.get("mapping_accuracy", {})
    triage_acc = result.get("triage_accuracy", {})
    current_mapping = mapping_acc.get("accuracy")
    current_triage = triage_acc.get("accuracy")
    current_f1 = mapping_acc.get("f1")
    current_recall = mapping_acc.get("recall")

    # Also check new-format evaluation results
    if current_f1 is None and "mapping" in result:
        current_f1 = result["mapping"].get("f1")
    if current_recall is None and "mapping" in result:
        current_recall = result["mapping"].get("recall")

    # Extract accuracies from baseline
    baseline_mapping = baseline.get("mapping_accuracy", {}).get("accuracy")
    baseline_triage = baseline.get("triage_accuracy", {}).get("accuracy")
    baseline_f1 = baseline.get("mapping_accuracy", {}).get("f1")
    baseline_recall = baseline.get("mapping_accuracy", {}).get("recall")

    if baseline_f1 is None and "mapping" in baseline:
        baseline_f1 = baseline["mapping"].get("f1")
    if baseline_recall is None and "mapping" in baseline:
        baseline_recall = baseline["mapping"].get("recall")

    reg.current_mapping = current_mapping
    reg.current_triage = current_triage
    reg.current_f1 = current_f1
    reg.current_recall = current_recall
    reg.baseline_mapping = baseline_mapping
    reg.baseline_triage = baseline_triage
    reg.baseline_f1 = baseline_f1
    reg.baseline_recall = baseline_recall

    failures = []

    # Check mapping regression
    if current_mapping is not None and baseline_mapping is not None:
        reg.mapping_delta = current_mapping - baseline_mapping
        if reg.mapping_delta < -mapping_threshold:
            failures.append(
                f"Mapping accuracy dropped {abs(reg.mapping_delta):.1%} "
                f"({baseline_mapping:.1%} -> {current_mapping:.1%}), "
                f"threshold: {mapping_threshold:.1%}"
            )
    elif current_mapping is None:
        reg.warnings.append("No mapping accuracy in current result")

    # Check F1 regression
    if current_f1 is not None and baseline_f1 is not None:
        reg.f1_delta = current_f1 - baseline_f1
        if reg.f1_delta < -f1_threshold:
            failures.append(
                f"F1 dropped {abs(reg.f1_delta):.1%} "
                f"({baseline_f1:.1%} -> {current_f1:.1%}), "
                f"threshold: {f1_threshold:.1%}"
            )

    # Check recall regression
    if current_recall is not None and baseline_recall is not None:
        reg.recall_delta = current_recall - baseline_recall
        if reg.recall_delta < -recall_threshold:
            failures.append(
                f"Recall dropped {abs(reg.recall_delta):.1%} "
                f"({baseline_recall:.1%} -> {current_recall:.1%}), "
                f"threshold: {recall_threshold:.1%}"
            )

    # Check triage regression
    if current_triage is not None and baseline_triage is not None:
        reg.triage_delta = current_triage - baseline_triage
        if reg.triage_delta < -triage_threshold:
            failures.append(
                f"Triage accuracy dropped {abs(reg.triage_delta):.1%} "
                f"({baseline_triage:.1%} -> {current_triage:.1%}), "
                f"threshold: {triage_threshold:.1%}"
            )
    elif current_triage is None:
        reg.warnings.append("No triage accuracy in current result")

    if failures:
        reg.passed = False
        reg.reason = "; ".join(failures)

    # Note improvements
    if reg.mapping_delta is not None and reg.mapping_delta > 0:
        reg.warnings.append(f"Mapping improved +{reg.mapping_delta:.1%}")
    if reg.f1_delta is not None and reg.f1_delta > 0:
        reg.warnings.append(f"F1 improved +{reg.f1_delta:.1%}")
    if reg.recall_delta is not None and reg.recall_delta > 0:
        reg.warnings.append(f"Recall improved +{reg.recall_delta:.1%}")
    if reg.triage_delta is not None and reg.triage_delta > 0:
        reg.warnings.append(f"Triage improved +{reg.triage_delta:.1%}")

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

    print("\n" + "=" * 100)
    print("REGRESSION CHECK RESULTS")
    print("=" * 100)

    # Header
    print(f"{'Fixture':<22} {'Status':<7} {'Mapping':<16} {'F1':<16} {'Recall':<16} {'Triage':<16}")
    print("-" * 100)

    def _metric_str(current, baseline, delta):
        if current is not None and baseline is not None:
            d = f"{delta:+.1%}" if delta else "+0.0%"
            return f"{current:.1%} ({d})"
        elif current is not None:
            return f"{current:.1%} (new)"
        return "N/A"

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        mapping_str = _metric_str(r.current_mapping, r.baseline_mapping, r.mapping_delta)
        f1_str = _metric_str(r.current_f1, r.baseline_f1, r.f1_delta)
        recall_str = _metric_str(r.current_recall, r.baseline_recall, r.recall_delta)
        triage_str = _metric_str(r.current_triage, r.baseline_triage, r.triage_delta)

        print(f"{r.fixture_name:<22} {status:<7} {mapping_str:<16} {f1_str:<16} {recall_str:<16} {triage_str:<16}")

        if not r.passed:
            print(f"  >> {r.reason}")
        for w in r.warnings:
            print(f"  -- {w}")

    print("=" * 100)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{passed}/{total} fixtures passed regression check.")


def main():
    parser = argparse.ArgumentParser(description="Check benchmark results for accuracy regressions")
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
            reg = compare_fixture(fixture_name, result, baseline, args.threshold_file)
            regression_results.append(reg)

    print_results(regression_results)

    # Exit code
    if all(r.passed for r in regression_results):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
