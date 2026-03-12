#!/usr/bin/env python3
"""
Run the extraction pipeline on all 10 real Excel files with real Claude API calls.

Usage:
    python scripts/run_real_extractions.py              # Run all 10
    python scripts/run_real_extractions.py 01 05 09     # Run specific files
    python scripts/run_real_extractions.py --dry-run     # Parse only, no Claude

Requires ANTHROPIC_API_KEY in environment or .env file.
Results saved to data/real_extraction_results/
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

ROOT = Path(__file__).parent.parent
REAL_DATA_DIR = ROOT / "tests" / "real data"
OUTPUT_DIR = ROOT / "data" / "real_extraction_results"

FILES = {
    "01": "01_electrolyser_FOAK_singlesheet.xlsx",
    "02": "02_biochar_NOAK_transposed_DE.xlsx",
    "03": "03_heat_pump_HaaS_monthly.xlsx",
    "04": "04_DAC_prerevenue_multitab.xlsx",
    "05": "05_pyrolysis_W2E_inline_scenarios.xlsx",
    "06": "06_LDES_hidden_rows_SaaS.xlsx",
    "07": "07_green_ammonia_3scenario_curves.xlsx",
    "08": "08_geothermal_EGS_HoldCo_SPV.xlsx",
    "09": "09_CCUS_cement_hardcoded_FY.xlsx",
    "10": "10_wind_nacelle_manufacturing_quarterly.xlsx",
}


def progress_callback(stage_name: str, progress: int):
    """Print extraction progress."""
    print(f"  [{progress:3d}%] {stage_name}")


async def run_extraction(file_num: str, file_bytes: bytes) -> dict:
    """Run the full extraction pipeline on a single file."""
    from src.extraction.orchestrator import extract

    file_id = f"real-{file_num}"

    # Patch DB saves — we don't have matching job records
    with (
        patch("src.lineage.tracker.LineageTracker.save_to_db"),
        patch("src.extraction.stages.enhanced_mapping.EnhancedMappingStage._persist_entity_patterns"),
        patch("src.extraction.stages.enhanced_mapping.EnhancedMappingStage._record_learned_aliases"),
    ):
        result = await extract(
            file_bytes,
            file_id=file_id,
            progress_callback=progress_callback,
        )

    return result


def print_summary(result: dict, file_num: str, filename: str, duration: float):
    """Print a concise summary of extraction results."""
    line_items = result.get("line_items", [])
    quality = result.get("quality", {})
    validation = result.get("validation", {})
    tokens = result.get("tokens_used", 0)
    cost = result.get("cost_usd", 0)

    mapped = sum(1 for li in line_items if li.get("canonical_name") != "unmapped")
    unmapped = sum(1 for li in line_items if li.get("canonical_name") == "unmapped")
    avg_conf = (
        sum(li.get("confidence", 0) for li in line_items) / len(line_items)
        if line_items
        else 0
    )

    grade = quality.get("letter_grade", "?")
    score = quality.get("numeric_score", 0)

    triage = result.get("triage", [])
    tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for t in triage:
        tier = t.get("tier", 4)
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    flags = validation.get("flags", [])
    errors = sum(1 for f in flags if f.get("severity") == "error")
    warnings = sum(1 for f in flags if f.get("severity") == "warning")

    print(f"\n{'='*70}")
    print(f"  FILE {file_num}: {filename}")
    print(f"{'='*70}")
    print(f"  Sheets:      {len(result.get('sheets', []))}")
    print(f"  Triage:      T1={tier_counts[1]} T2={tier_counts[2]} T3={tier_counts[3]} T4={tier_counts[4]}")
    print(f"  Line items:  {len(line_items)} ({mapped} mapped, {unmapped} unmapped)")
    print(f"  Avg conf:    {avg_conf:.2%}")
    print(f"  Quality:     {grade} ({score:.2f})")
    print(f"  Validation:  {errors} errors, {warnings} warnings")
    print(f"  Tokens:      {tokens:,}")
    print(f"  Cost:        ${cost:.4f}")
    print(f"  Duration:    {duration:.1f}s")

    # List unmapped items
    if unmapped > 0:
        print(f"\n  Unmapped labels:")
        for li in line_items:
            if li.get("canonical_name") == "unmapped":
                print(f"    - {li.get('original_label', '?')} (sheet: {li.get('sheet', '?')})")

    # List validation errors
    if errors > 0:
        print(f"\n  Validation errors:")
        for f in flags:
            if f.get("severity") == "error":
                print(f"    - [{f.get('period', '?')}] {f.get('item', '?')}: {f.get('message', '?')}")


async def main():
    """Main entry point."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or not api_key.startswith("sk-ant-"):
        print("ERROR: ANTHROPIC_API_KEY not set or invalid.")
        print("Set it in .env or environment before running.")
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    # Select files to run
    if args:
        selected = {k: v for k, v in FILES.items() if k in args}
    else:
        selected = FILES

    if not selected:
        print(f"No matching files. Available: {', '.join(FILES.keys())}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    total_tokens = 0
    total_cost = 0.0
    total_items = 0
    total_mapped = 0
    results_summary = []

    print(f"Running extraction on {len(selected)} file(s)...")
    if dry_run:
        print("(DRY RUN — parsing only, no Claude calls)")
    print()

    for file_num, filename in sorted(selected.items()):
        filepath = REAL_DATA_DIR / filename
        if not filepath.exists():
            print(f"SKIP: {filename} not found")
            continue

        print(f"\n--- File {file_num}: {filename} ---")
        file_bytes = filepath.read_bytes()
        print(f"  Size: {len(file_bytes):,} bytes")

        if dry_run:
            # Just parse, don't call Claude
            from src.extraction.stages.parsing import ParsingStage
            structured = ParsingStage._excel_to_structured_repr(file_bytes)
            sheets = structured.get("sheets", [])
            print(f"  Sheets: {len(sheets)}")
            for s in sheets:
                rows = s.get("rows", [])
                print(f"    {s['sheet_name']}: {len(rows)} rows")
            continue

        start = time.time()
        try:
            result = await run_extraction(file_num, file_bytes)
            duration = time.time() - start

            # Save full result
            output_path = OUTPUT_DIR / f"{file_num}_result.json"
            with open(output_path, "w") as f:
                json.dump(result, f, indent=2, default=str)

            print_summary(result, file_num, filename, duration)

            tokens = result.get("tokens_used", 0)
            cost = result.get("cost_usd", 0)
            items = result.get("line_items", [])
            mapped = sum(1 for li in items if li.get("canonical_name") != "unmapped")

            total_tokens += tokens
            total_cost += cost
            total_items += len(items)
            total_mapped += mapped

            quality = result.get("quality", {})
            results_summary.append({
                "file": file_num,
                "name": filename,
                "sheets": len(result.get("sheets", [])),
                "line_items": len(items),
                "mapped": mapped,
                "unmapped": len(items) - mapped,
                "avg_confidence": (
                    sum(li.get("confidence", 0) for li in items) / len(items)
                    if items else 0
                ),
                "quality_grade": quality.get("letter_grade", "?"),
                "quality_score": quality.get("numeric_score", 0),
                "tokens": tokens,
                "cost_usd": cost,
                "duration_s": round(duration, 1),
                "validation_errors": sum(
                    1 for f in result.get("validation", {}).get("flags", [])
                    if f.get("severity") == "error"
                ),
            })

        except Exception as e:
            duration = time.time() - start
            print(f"  FAILED after {duration:.1f}s: {e}")
            import traceback
            traceback.print_exc()
            results_summary.append({
                "file": file_num,
                "name": filename,
                "error": str(e),
                "duration_s": round(duration, 1),
            })

    # Save summary
    if not dry_run and results_summary:
        summary_path = OUTPUT_DIR / "summary.json"
        with open(summary_path, "w") as f:
            json.dump({
                "timestamp": time.strftime("%Y%m%d_%H%M%S"),
                "files_run": len(results_summary),
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost, 4),
                "total_line_items": total_items,
                "total_mapped": total_mapped,
                "mapping_rate": round(total_mapped / total_items * 100, 1) if total_items else 0,
                "results": results_summary,
            }, f, indent=2)
        print(f"\n{'='*70}")
        print(f"  TOTALS")
        print(f"{'='*70}")
        print(f"  Files:       {len(results_summary)}")
        print(f"  Line items:  {total_items} ({total_mapped} mapped, {total_items - total_mapped} unmapped)")
        print(f"  Mapping:     {total_mapped / total_items * 100:.1f}%" if total_items else "  Mapping:     N/A")
        print(f"  Tokens:      {total_tokens:,}")
        print(f"  Cost:        ${total_cost:.4f}")
        print(f"\nResults saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
