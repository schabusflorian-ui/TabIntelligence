"""
Real Claude E2E test -- sends actual Excel files to the real Anthropic API.

Skips automatically if ANTHROPIC_API_KEY is not set or is a placeholder.
Costs ~$0.02-0.10 per run depending on model complexity.

Run:
    pytest tests/e2e/test_real_claude.py -v -s
    pytest tests/e2e/test_real_claude.py -v -s -m real_claude
"""

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# Load .env so ANTHROPIC_API_KEY is available via os.getenv
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_model.xlsx"
REALISTIC_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "realistic_model.xlsx"
EXPECTED_PATH = Path(__file__).parent.parent / "fixtures" / "realistic_model_expected.json"


def _get_api_key():
    """Return real API key or None."""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key or "your-api-key" in key or not key.startswith("sk-ant-"):
        return None
    return key


# Skip entire module if no real API key
pytestmark = [
    pytest.mark.skipif(
        _get_api_key() is None, reason="ANTHROPIC_API_KEY not set or is placeholder"
    ),
    pytest.mark.real_claude,
    pytest.mark.slow,
]


@pytest.fixture
def real_extract():
    """Run the extraction pipeline with the REAL Claude API.

    Patches save_to_db since we don't have a matching job record in the DB.
    The lineage is still tracked in-memory and validated -- only DB persistence is skipped.
    """
    from src.extraction.orchestrator import extract

    async def _run(file_bytes, file_id="real-e2e-test"):
        with patch("src.lineage.tracker.LineageTracker.save_to_db"):
            return await extract(file_bytes, file_id=file_id)

    return _run


@pytest.fixture
def expected_results():
    """Load expected results for accuracy comparison."""
    if not EXPECTED_PATH.exists():
        pytest.skip(f"Expected results file not found: {EXPECTED_PATH}")
    with open(EXPECTED_PATH) as f:
        return json.load(f)


# =========================================================================
# Original test: sample_model.xlsx (simple 4-sheet model)
# =========================================================================


def test_real_extraction_produces_valid_output(real_extract):
    """Send sample_model.xlsx through the real 5-stage pipeline and validate."""
    assert FIXTURE_PATH.exists(), f"Fixture missing: {FIXTURE_PATH}"
    file_bytes = FIXTURE_PATH.read_bytes()

    print(f"\n  Sending {FIXTURE_PATH.name} ({len(file_bytes)} bytes) to real Claude API...")

    result = asyncio.run(real_extract(file_bytes))

    # --- Structure ---
    assert "sheets" in result
    assert "line_items" in result
    assert "triage" in result
    assert "validation" in result
    assert "tokens_used" in result
    assert "cost_usd" in result
    assert "lineage_summary" in result

    print(f"  Sheets found: {result['sheets']}")
    print(f"  Triage decisions: {len(result['triage'])}")
    print(f"  Line items extracted: {len(result['line_items'])}")
    print(f"  Tokens used: {result['tokens_used']}")
    print(f"  Cost: ${result['cost_usd']:.4f}")

    # --- Sheets ---
    assert len(result["sheets"]) >= 1, "Should find at least 1 sheet"

    # --- Triage ---
    assert len(result["triage"]) >= 1, "Should triage at least 1 sheet"
    for entry in result["triage"]:
        assert "sheet_name" in entry
        assert "tier" in entry
        assert entry["tier"] in (1, 2, 3, 4)

    # --- Line items ---
    assert len(result["line_items"]) >= 1, "Should extract at least 1 line item"
    items_with_values = 0
    for item in result["line_items"]:
        assert "original_label" in item
        assert "canonical_name" in item
        assert "confidence" in item
        assert "values" in item
        assert 0 <= item["confidence"] <= 1.0
        if len(item["values"]) >= 1:
            items_with_values += 1
    # Header/category rows (e.g. "Operating Expenses") may have no values -- that's fine.
    # But most items should have values.
    assert items_with_values >= len(result["line_items"]) * 0.5, (
        f"Too few items with values: {items_with_values}/{len(result['line_items'])}"
    )

    # --- Should find revenue somewhere ---
    canonical_names = {li["canonical_name"] for li in result["line_items"]}
    print(f"  Canonical names: {canonical_names}")
    assert "revenue" in canonical_names, (
        f"Expected 'revenue' in extracted items. Got: {canonical_names}"
    )

    # --- Validation ---
    validation = result["validation"]
    assert "overall_confidence" in validation
    assert 0.0 <= validation["overall_confidence"] <= 1.0

    # --- Time-Series Validation ---
    assert "time_series" in validation, "Missing time_series in validation output"
    ts = validation["time_series"]
    assert "consistency_score" in ts
    assert 0.0 <= ts["consistency_score"] <= 1.0
    print(
        f"  Time-series: {ts['total_checks']} checks, "
        f"{len(ts['flags'])} flags, "
        f"score={ts['consistency_score']:.3f}"
    )

    # --- Completeness Scoring ---
    assert "completeness" in validation, "Missing completeness in validation output"
    comp = validation["completeness"]
    assert "overall_score" in comp
    assert 0.0 <= comp["overall_score"] <= 1.0
    print(
        f"  Completeness: score={comp['overall_score']:.3f}, "
        f"statements={comp['detected_statements']}, "
        f"found={comp['total_found']}/{comp['total_expected']}"
    )

    # --- Quality Score ---
    assert "quality" in validation, "Missing quality in validation output"
    q = validation["quality"]
    assert q["letter_grade"] in ("A", "B", "C", "D", "F")
    assert q["label"] in ("trustworthy", "needs_review", "unreliable")
    print(f"  Quality: {q['numeric_score']:.3f} ({q['letter_grade']}) - {q['label']}")

    # --- Lineage ---
    summary = result["lineage_summary"]
    assert summary["total_events"] == 5, "All 5 stages should produce lineage"
    assert sorted(summary["stages"]) == [1, 2, 3, 4, 5]

    # --- Cost sanity check ---
    assert result["tokens_used"] > 0
    assert result["cost_usd"] > 0
    assert result["cost_usd"] < 1.0, "Single extraction should cost well under $1"

    print("\n  REAL E2E PASSED!")
    print(f"  {len(result['line_items'])} items extracted from {len(result['sheets'])} sheets")
    print(f"  Validation confidence: {validation['overall_confidence']:.1%}")


# =========================================================================
# New tests: realistic_model.xlsx (8-sheet mid-market LBO model)
# =========================================================================


def test_realistic_model_extraction(real_extract):
    """Send realistic_model.xlsx through the pipeline and validate structure."""
    if not REALISTIC_FIXTURE_PATH.exists():
        pytest.skip(f"Realistic fixture missing: {REALISTIC_FIXTURE_PATH}")

    file_bytes = REALISTIC_FIXTURE_PATH.read_bytes()
    print(
        f"\n  Sending {REALISTIC_FIXTURE_PATH.name} ({len(file_bytes)} bytes) to real Claude API..."
    )

    result = asyncio.run(real_extract(file_bytes))

    # Basic structure assertions
    assert "sheets" in result
    assert "line_items" in result
    assert "triage" in result
    assert "validation" in result
    assert "lineage_summary" in result

    # Should detect all 8 sheets
    assert len(result["sheets"]) == 8, (
        f"Expected 8 sheets, got {len(result['sheets'])}: {result['sheets']}"
    )

    # Should triage all sheets (may produce section-level entries, so >= 8)
    triage_sheets = {t["sheet_name"] for t in result["triage"]}
    assert len(triage_sheets) == 8, (
        f"Expected 8 triaged sheets, got {len(triage_sheets)}: {triage_sheets}"
    )
    assert len(result["triage"]) >= 8, f"Expected >= 8 triage entries, got {len(result['triage'])}"

    # Should extract a meaningful number of line items (the model has ~100+ data rows)
    assert len(result["line_items"]) >= 15, (
        f"Expected >= 15 line items, got {len(result['line_items'])}"
    )

    # Lineage completeness
    summary = result["lineage_summary"]
    assert summary["total_events"] == 5
    assert sorted(summary["stages"]) == [1, 2, 3, 4, 5]

    # Cost should be reasonable
    assert result["cost_usd"] < 2.0, f"Cost too high: ${result['cost_usd']:.4f}"

    # --- New Validation Layers ---
    validation = result["validation"]
    assert "time_series" in validation
    assert "completeness" in validation
    assert "quality" in validation

    ts = validation["time_series"]
    comp = validation["completeness"]
    q = validation["quality"]

    print(f"  Sheets: {result['sheets']}")
    print(f"  Line items: {len(result['line_items'])}")
    print(f"  Tokens: {result['tokens_used']:,}")
    print(f"  Cost: ${result['cost_usd']:.4f}")
    print(f"  Validation confidence: {validation.get('overall_confidence', 0):.1%}")
    print(
        f"  Time-series: {ts['total_checks']} checks, "
        f"{len(ts['flags'])} flags, "
        f"score={ts['consistency_score']:.3f}"
    )
    print(
        f"  Completeness: score={comp['overall_score']:.3f}, "
        f"statements={comp['detected_statements']}, "
        f"found={comp['total_found']}/{comp['total_expected']}"
    )
    print(f"  Quality: {q['numeric_score']:.3f} ({q['letter_grade']}) - {q['label']}")


def test_realistic_model_triage_accuracy(real_extract, expected_results):
    """Validate that triage correctly classifies the 8 sheets (>= 60% accuracy)."""
    if not REALISTIC_FIXTURE_PATH.exists():
        pytest.skip(f"Realistic fixture missing: {REALISTIC_FIXTURE_PATH}")

    file_bytes = REALISTIC_FIXTURE_PATH.read_bytes()
    result = asyncio.run(real_extract(file_bytes))

    # Build lookup of actual triage
    actual_triage = {t["sheet_name"]: t for t in result.get("triage", [])}
    expected_triage = expected_results.get("expected_triage", [])

    correct = 0
    total = len(expected_triage)

    print("\n  Triage accuracy check:")
    for exp in expected_triage:
        sheet = exp["sheet_name"]
        exp_tier = exp["tier"]
        actual = actual_triage.get(sheet, {})
        act_tier = actual.get("tier")
        match = act_tier == exp_tier
        if match:
            correct += 1
        status = "OK" if match else "MISS"
        print(f"    [{status}] {sheet}: expected tier {exp_tier}, got tier {act_tier}")

    accuracy = correct / max(total, 1)
    print(f"\n  Triage accuracy: {correct}/{total} ({accuracy:.1%})")

    # Conservative starting target: 60%
    assert accuracy >= 0.60, (
        f"Triage accuracy {accuracy:.1%} below 60% threshold. {correct}/{total} correct."
    )


def test_realistic_model_mapping_accuracy(real_extract, expected_results):
    """Validate that mapping correctly identifies financial line items (>= 50% accuracy)."""
    if not REALISTIC_FIXTURE_PATH.exists():
        pytest.skip(f"Realistic fixture missing: {REALISTIC_FIXTURE_PATH}")

    file_bytes = REALISTIC_FIXTURE_PATH.read_bytes()
    result = asyncio.run(real_extract(file_bytes))

    # Build lookup from actual results
    actual_mappings = {}
    for item in result.get("line_items", []):
        label = item.get("original_label", "")
        canonical = item.get("canonical_name", "unmapped")
        if label and label not in actual_mappings:
            actual_mappings[label] = canonical

    expected_mappings = expected_results.get("expected_mappings", [])
    acceptable_alts = expected_results.get("acceptable_alternatives", {})

    correct = 0
    total = len(expected_mappings)
    unmapped = 0
    mismatches = []

    print("\n  Mapping accuracy check:")
    for exp in expected_mappings:
        label = exp["original_label"]
        exp_canonical = exp["canonical_name"]
        act_canonical = actual_mappings.get(label)

        alts = acceptable_alts.get(exp_canonical, [exp_canonical])

        if act_canonical is None or act_canonical == "unmapped":
            unmapped += 1
            print(f'    [UNMAPPED] "{label}" -> unmapped (expected: {exp_canonical})')
        elif act_canonical in alts:
            correct += 1
            print(f'    [OK]       "{label}" -> {act_canonical}')
        else:
            mismatches.append((label, exp_canonical, act_canonical))
            print(f'    [MISS]     "{label}" -> {act_canonical} (expected: {exp_canonical})')

    accuracy = correct / max(total, 1)
    print(f"\n  Mapping accuracy: {correct}/{total} ({accuracy:.1%})")
    print(f"  Unmapped: {unmapped}")
    print(f"  Mismatches: {len(mismatches)}")

    # Conservative starting target: 50%
    assert accuracy >= 0.50, (
        f"Mapping accuracy {accuracy:.1%} below 50% threshold. "
        f"{correct}/{total} correct, {unmapped} unmapped, {len(mismatches)} mismatches."
    )
