#!/usr/bin/env python3
"""Import real extraction results into PostgreSQL.

Reads JSON results from data/real_extraction_results/ and creates
Entity, File, ExtractionJob, and ExtractionFact records using
existing CRUD functions. Idempotent via content_hash dedup.

Usage:
    python scripts/import_real_results.py              # Import all 10
    python scripts/import_real_results.py 01 05        # Import specific
    python scripts/import_real_results.py --dry-run    # Preview only
"""

import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.session import get_db_sync
from src.db.crud import (
    create_entity,
    create_extraction_job,
    create_file,
    complete_job,
    get_file_by_hash,
    persist_extraction_facts,
)

# ── Entity metadata for each file ───────────────────────────────────

ENTITY_META = {
    "01": {
        "filename": "01_electrolyser_FOAK_singlesheet.xlsx",
        "entity_name": "PEM Electrolyser FOAK",
        "industry": "green_hydrogen",
    },
    "02": {
        "filename": "02_biochar_NOAK_transposed_DE.xlsx",
        "entity_name": "Biochar NOAK (Germany)",
        "industry": "biochar",
    },
    "03": {
        "filename": "03_heat_pump_HaaS_monthly.xlsx",
        "entity_name": "Heat Pump HaaS",
        "industry": "heat_pumps",
    },
    "04": {
        "filename": "04_DAC_prerevenue_multitab.xlsx",
        "entity_name": "DAC Pre-Revenue",
        "industry": "direct_air_capture",
    },
    "05": {
        "filename": "05_pyrolysis_W2E_inline_scenarios.xlsx",
        "entity_name": "Pyrolysis W2E",
        "industry": "waste_to_energy",
    },
    "06": {
        "filename": "06_LDES_hidden_rows_SaaS.xlsx",
        "entity_name": "LDES Grid Storage",
        "industry": "energy_storage",
    },
    "07": {
        "filename": "07_green_ammonia_3scenario_curves.xlsx",
        "entity_name": "Green Ammonia FOAK",
        "industry": "green_ammonia",
    },
    "08": {
        "filename": "08_geothermal_EGS_HoldCo_SPV.xlsx",
        "entity_name": "Geothermal EGS",
        "industry": "geothermal",
    },
    "09": {
        "filename": "09_CCUS_cement_hardcoded_FY.xlsx",
        "entity_name": "CCUS Cement Retrofit",
        "industry": "carbon_capture",
    },
    "10": {
        "filename": "10_wind_nacelle_manufacturing_quarterly.xlsx",
        "entity_name": "Wind Nacelle Manufacturing",
        "industry": "wind_energy",
    },
}

RESULTS_DIR = PROJECT_ROOT / "data" / "real_extraction_results"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "real data"


def normalize_line_items(line_items: list[dict]) -> list[dict]:
    """Remap field names from JSON result format to what persist_extraction_facts expects.

    JSON results use:
        sheet, row, provenance.mapping.method, provenance.mapping.taxonomy_category
    persist_extraction_facts expects:
        sheet_name, row_index, method, taxonomy_category
    """
    normalized = []
    for item in line_items:
        out = {
            "canonical_name": item.get("canonical_name"),
            "original_label": item.get("original_label"),
            "values": item.get("values", {}),
            "confidence": item.get("confidence"),
            "hierarchy_level": item.get("hierarchy_level"),
            # Remap field names
            "sheet_name": item.get("sheet"),
            "row_index": item.get("row"),
        }
        # Extract method and taxonomy_category from nested provenance
        prov = item.get("provenance") or {}
        mapping = prov.get("mapping") or {}
        out["method"] = mapping.get("method")
        out["taxonomy_category"] = mapping.get("taxonomy_category")
        normalized.append(out)
    return normalized


def build_validation_lookup(line_items: list[dict]) -> dict:
    """Build {canonical_name: {passed: bool}} from per-item provenance.validation."""
    lookup = {}
    for item in line_items:
        canonical = item.get("canonical_name")
        if not canonical or canonical == "unmapped":
            continue
        prov = item.get("provenance") or {}
        val = prov.get("validation")
        if val and isinstance(val, dict):
            lookup[canonical] = {"passed": val.get("all_passed", True)}
    return lookup


def compute_content_hash(filepath: Path) -> str:
    """SHA-256 hex digest of file contents."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def import_file(file_num: str, dry_run: bool = False) -> Optional[dict]:
    """Import a single extraction result into PostgreSQL.

    Returns dict with entity_id, file_id, job_id, fact_count on success.
    Returns None if skipped (already imported or missing data).
    """
    meta = ENTITY_META.get(file_num)
    if not meta:
        print(f"  [SKIP] Unknown file number: {file_num}")
        return None

    result_path = RESULTS_DIR / f"{file_num}_result.json"
    if not result_path.exists():
        print(f"  [SKIP] No result file: {result_path}")
        return None

    excel_path = FIXTURES_DIR / meta["filename"]
    if not excel_path.exists():
        print(f"  [SKIP] No Excel file: {excel_path}")
        return None

    # Load extraction result
    with open(result_path) as f:
        result = json.load(f)

    line_items = result.get("line_items", [])
    tokens_used = result.get("tokens_used", 0)
    cost_usd = result.get("cost_usd", 0.0)
    quality = result.get("quality", {})
    quality_grade = quality.get("letter_grade")

    # Compute content hash for dedup
    content_hash = compute_content_hash(excel_path)
    file_size = excel_path.stat().st_size

    mapped_count = sum(1 for li in line_items if li.get("canonical_name") != "unmapped")

    print(f"  Entity:    {meta['entity_name']} ({meta['industry']})")
    print(f"  File:      {meta['filename']} ({file_size:,} bytes)")
    print(f"  Items:     {len(line_items)} total, {mapped_count} mapped")
    print(f"  Quality:   {quality_grade} ({quality.get('numeric_score', '?')})")
    print(f"  Tokens:    {tokens_used:,}  Cost: ${cost_usd:.4f}")
    print(f"  Hash:      {content_hash[:16]}...")

    if dry_run:
        print("  [DRY RUN] Would import this file")
        return {"file_num": file_num, "dry_run": True}

    with get_db_sync() as db:
        # Idempotency: skip if file already imported
        existing = get_file_by_hash(db, content_hash)
        if existing:
            print(f"  [SKIP] Already imported (file_id={existing.file_id})")
            return None

        # 1. Create entity
        entity = create_entity(db, name=meta["entity_name"], industry=meta["industry"])
        print(f"  Created entity: {entity.id}")

        # 2. Create file record (no S3)
        file_rec = create_file(
            db,
            filename=meta["filename"],
            file_size=file_size,
            s3_key=None,
            entity_id=entity.id,
            content_hash=content_hash,
        )
        print(f"  Created file:   {file_rec.file_id}")

        # 3. Create extraction job
        job = create_extraction_job(db, file_id=file_rec.file_id)
        print(f"  Created job:    {job.job_id}")

        # 4. Complete job with result
        complete_job(
            db,
            job_id=job.job_id,
            result=result,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            quality_grade=quality_grade,
        )
        print(f"  Job completed:  status={job.status.value if hasattr(job.status, 'value') else job.status}")

        # 5. Persist extraction facts
        normalized = normalize_line_items(line_items)
        validation_lookup = build_validation_lookup(line_items)
        fact_count = persist_extraction_facts(
            db,
            job_id=job.job_id,
            entity_id=entity.id,
            line_items=normalized,
            validation_lookup=validation_lookup,
        )
        print(f"  Facts:          {fact_count} rows")

        return {
            "file_num": file_num,
            "entity_id": str(entity.id),
            "entity_name": meta["entity_name"],
            "file_id": str(file_rec.file_id),
            "job_id": str(job.job_id),
            "fact_count": fact_count,
            "quality_grade": quality_grade,
        }


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    file_nums = [a for a in args if a != "--dry-run"]

    if not file_nums:
        file_nums = sorted(ENTITY_META.keys())

    print("=" * 60)
    print("Import Real Extraction Results into PostgreSQL")
    print("=" * 60)
    if dry_run:
        print("[DRY RUN MODE — no database writes]\n")
    else:
        print()

    results = []
    for num in file_nums:
        print(f"\n── File {num} ─────────────────────────────────")
        try:
            info = import_file(num, dry_run=dry_run)
            if info:
                results.append(info)
        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print("\n" + "=" * 60)
    print("IMPORT SUMMARY")
    print("=" * 60)
    print(f"Imported: {len(results)} / {len(file_nums)} files")

    if results and not dry_run:
        total_facts = sum(r.get("fact_count", 0) for r in results)
        print(f"Total facts: {total_facts}")
        print()

        # Entity UUIDs
        print("Entity IDs:")
        entity_ids = []
        for r in results:
            print(f"  {r['entity_name']:35s} {r['entity_id']}")
            entity_ids.append(r["entity_id"])

        # Sample curl commands
        print("\nVerification commands:")
        print(f'  curl -H "X-API-Key: <key>" localhost:8000/api/v1/analytics/portfolio/summary')
        if len(entity_ids) >= 2:
            ids = ",".join(entity_ids[:2])
            print(f'  curl -H "X-API-Key: <key>" "localhost:8000/api/v1/analytics/compare?entity_ids={ids}&canonical_names=revenue,ebitda&period=2025"')
        print(f'  curl -H "X-API-Key: <key>" "localhost:8000/api/v1/analytics/facts?limit=20"')


if __name__ == "__main__":
    main()
