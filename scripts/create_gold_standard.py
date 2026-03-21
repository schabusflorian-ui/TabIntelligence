#!/usr/bin/env python3
"""
Create or upgrade gold standard datasets for extraction accuracy benchmarking.

Gold standards extend the existing *_expected.json format with:
- expected_values: numeric values per canonical name, per period, with tolerances
- expected_parsing: parsing expectations (bold, formula, subtotal flags)
- expected_completeness: minimum expected coverage per statement type

Usage:
    # Create from existing expected.json + benchmark result (pre-populate values)
    python scripts/create_gold_standard.py \\
        --expected tests/fixtures/realistic_model_expected.json \\
        --result data/benchmark_results/20260312_131754.json \\
        --output data/gold_standards/realistic_model_gold.json

    # Upgrade existing expected.json only (no values pre-populated)
    python scripts/create_gold_standard.py \\
        --expected tests/fixtures/seed_burn_expected.json \\
        --output data/gold_standards/seed_burn_gold.json

    # Batch: create gold standards for all fixtures with expected.json
    python scripts/create_gold_standard.py \\
        --fixture-dir tests/fixtures/ \\
        --result-dir data/benchmark_results/ \\
        --output-dir data/gold_standards/
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _find_latest_result(result_dir: Path, fixture_name: str) -> Path | None:
    """Find the latest benchmark result for a fixture."""
    candidates = sorted(result_dir.glob("*.json"), reverse=True)
    for c in candidates:
        try:
            data = _load_json(c)
            if fixture_name in data.get("file", ""):
                return c
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def _extract_values_from_result(result: dict) -> dict:
    """Extract expected values from a benchmark result's line items.

    Returns dict: {canonical_name: {period: value, ...}, ...}
    """
    values = {}
    for item in result.get("sample_line_items", result.get("line_items", [])):
        canonical = item.get("canonical_name", "unmapped")
        if canonical == "unmapped":
            continue

        item_values = item.get("values", {})
        if item_values:
            values[canonical] = {}
            for period, val in item_values.items():
                if val is not None and isinstance(val, (int, float)):
                    values[canonical][period] = {
                        "value": val,
                        "tolerance_pct": 1.0,  # 1% default tolerance
                        "tolerance_abs": max(abs(val) * 0.01, 0.5),
                    }
    return values


def _extract_parsing_from_result(result: dict) -> list:
    """Extract expected parsing attributes from benchmark result line items."""
    parsing = []
    for item in result.get("sample_line_items", result.get("line_items", [])):
        canonical = item.get("canonical_name", "unmapped")
        if canonical == "unmapped":
            continue

        prov = item.get("provenance", {}).get("parsing", {})
        if prov:
            parsing.append({
                "canonical_name": canonical,
                "sheet": item.get("sheet", ""),
                "original_label": item.get("original_label", ""),
                "is_bold": prov.get("is_bold", False),
                "is_formula": prov.get("is_formula", False),
                "is_subtotal": prov.get("is_subtotal", False),
                "hierarchy_level": prov.get("hierarchy_level", 0),
            })
    return parsing


def create_gold_standard(
    expected: dict,
    result: dict | None = None,
) -> dict:
    """Create a gold standard dataset from expected.json + optional benchmark result.

    The gold standard extends the expected.json schema with:
    - expected_values: numeric values per canonical name per period
    - expected_parsing: parsing expectations for key items
    - expected_completeness: minimum coverage per statement type
    - metadata: creation timestamp, source files, version
    """
    gold = {
        "version": "1.0.0",
        "description": expected.get("description", "Gold standard dataset"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_info": expected.get("model_info", {}),

        # Carry forward from expected.json
        "expected_triage": expected.get("expected_triage", []),
        "expected_mappings": expected.get("expected_mappings", []),
        "acceptable_alternatives": expected.get("acceptable_alternatives", {}),
    }

    # Derive completeness expectations from mappings
    statement_counts = {}
    for m in gold["expected_mappings"]:
        sheet = m.get("sheet", "Unknown")
        statement_counts.setdefault(sheet, 0)
        statement_counts[sheet] += 1

    gold["expected_completeness"] = {
        "statements": {
            sheet: {
                "min_items": count,
                "min_coverage_pct": 80.0,
            }
            for sheet, count in statement_counts.items()
        },
        "total_min_items": len(gold["expected_mappings"]),
        "total_min_coverage_pct": 75.0,
    }

    # Pre-populate values and parsing from benchmark result if available
    if result:
        gold["expected_values"] = _extract_values_from_result(result)
        gold["expected_parsing"] = _extract_parsing_from_result(result)
        gold["metadata"] = {
            "source_result": result.get("file", ""),
            "source_timestamp": result.get("timestamp", ""),
            "values_verified": False,
            "notes": "Values auto-populated from extraction result. Review and verify before use.",
        }
    else:
        gold["expected_values"] = {}
        gold["expected_parsing"] = []
        gold["metadata"] = {
            "values_verified": False,
            "notes": "No values pre-populated. Add expected_values manually.",
        }

    return gold


def main():
    parser = argparse.ArgumentParser(
        description="Create gold standard datasets for benchmarking"
    )
    parser.add_argument("--expected", type=Path, help="Path to *_expected.json")
    parser.add_argument("--result", type=Path, help="Path to benchmark result JSON")
    parser.add_argument("--output", type=Path, help="Output gold standard path")
    parser.add_argument("--fixture-dir", type=Path, help="Process all fixtures in dir")
    parser.add_argument("--result-dir", type=Path, help="Dir with benchmark results")
    parser.add_argument("--output-dir", type=Path, help="Output dir for gold standards")
    args = parser.parse_args()

    if args.fixture_dir:
        # Batch mode
        fixture_dir = args.fixture_dir
        result_dir = args.result_dir or PROJECT_ROOT / "data" / "benchmark_results"
        output_dir = args.output_dir or PROJECT_ROOT / "data" / "gold_standards"
        output_dir.mkdir(parents=True, exist_ok=True)

        expected_files = sorted(fixture_dir.glob("*_expected.json"))
        if not expected_files:
            print(f"No *_expected.json files found in {fixture_dir}")
            sys.exit(1)

        for exp_path in expected_files:
            fixture_name = exp_path.stem.replace("_expected", "")
            print(f"Processing {fixture_name}...")

            expected = _load_json(exp_path)

            result = None
            result_path = _find_latest_result(result_dir, fixture_name)
            if result_path:
                print(f"  Using result: {result_path.name}")
                result = _load_json(result_path)
            else:
                print("  No benchmark result found, creating without values")

            gold = create_gold_standard(expected, result)
            out_path = output_dir / f"{fixture_name}_gold.json"
            with open(out_path, "w") as f:
                json.dump(gold, f, indent=2)
            print(f"  Saved: {out_path}")

        print(f"\nCreated {len(expected_files)} gold standards in {output_dir}")

    elif args.expected:
        # Single file mode
        expected = _load_json(args.expected)

        result = None
        if args.result:
            result = _load_json(args.result)

        gold = create_gold_standard(expected, result)

        output = args.output
        if not output:
            name = args.expected.stem.replace("_expected", "")
            output = PROJECT_ROOT / "data" / "gold_standards" / f"{name}_gold.json"
            output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w") as f:
            json.dump(gold, f, indent=2)
        print(f"Gold standard saved: {output}")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
