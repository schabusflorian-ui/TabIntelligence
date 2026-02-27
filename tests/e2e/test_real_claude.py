"""
Real Claude E2E test — sends actual Excel file to the real Anthropic API.

Skips automatically if ANTHROPIC_API_KEY is not set or is a placeholder.
Costs ~$0.02-0.05 per run.

Run:
    pytest tests/e2e/test_real_claude.py -v -s
"""
import asyncio
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


def _get_api_key():
    """Return real API key or None."""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key or "your-api-key" in key or not key.startswith("sk-ant-"):
        return None
    return key


# Skip entire module if no real API key
pytestmark = pytest.mark.skipif(
    _get_api_key() is None,
    reason="ANTHROPIC_API_KEY not set or is placeholder"
)


@pytest.fixture
def real_extract():
    """Run the extraction pipeline with the REAL Claude API.

    Patches save_to_db since we don't have a matching job record in the DB.
    The lineage is still tracked in-memory and validated — only DB persistence is skipped.
    """
    from src.extraction.orchestrator import extract

    async def _run(file_bytes, file_id="real-e2e-test"):
        with patch("src.lineage.tracker.LineageTracker.save_to_db"):
            return await extract(file_bytes, file_id=file_id)

    return _run


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
    for item in result["line_items"]:
        assert "original_label" in item
        assert "canonical_name" in item
        assert "confidence" in item
        assert "values" in item
        assert 0 <= item["confidence"] <= 1.0
        assert len(item["values"]) >= 1, f"Line item '{item['original_label']}' has no values"

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

    # --- Lineage ---
    summary = result["lineage_summary"]
    assert summary["total_events"] == 5, "All 5 stages should produce lineage"
    assert sorted(summary["stages"]) == [1, 2, 3, 4, 5]

    # --- Cost sanity check ---
    assert result["tokens_used"] > 0
    assert result["cost_usd"] > 0
    assert result["cost_usd"] < 1.0, "Single extraction should cost well under $1"

    print(f"\n  REAL E2E PASSED!")
    print(f"  {len(result['line_items'])} items extracted from {len(result['sheets'])} sheets")
    print(f"  Validation confidence: {validation['overall_confidence']:.1%}")
