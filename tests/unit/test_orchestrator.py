"""
Unit tests for the extraction orchestrator.
Tests the 3-stage pipeline: Parse, Triage, Map.
"""
import pytest
import json
from src.extraction.orchestrator import (
    extract,
    stage_1_parsing,
    stage_2_triage,
    stage_3_mapping,
    _extract_json
)


@pytest.mark.asyncio
async def test_parsing_stage_extracts_sheets(mock_anthropic, sample_xlsx):
    """Test Stage 1: Parsing extracts sheet information from Excel file."""
    result = await stage_1_parsing(sample_xlsx)

    assert "parsed" in result
    assert "tokens" in result
    assert "sheets" in result["parsed"]
    assert len(result["parsed"]["sheets"]) > 0

    # Check first sheet has required fields
    first_sheet = result["parsed"]["sheets"][0]
    assert "sheet_name" in first_sheet
    assert "sheet_type" in first_sheet
    assert "rows" in first_sheet


@pytest.mark.asyncio
async def test_parsing_stage_returns_token_count(mock_anthropic, sample_xlsx):
    """Test that parsing stage returns token usage."""
    result = await stage_1_parsing(sample_xlsx)

    assert "tokens" in result
    assert isinstance(result["tokens"], int)
    assert result["tokens"] > 0


@pytest.mark.asyncio
async def test_triage_stage_assigns_tiers(mock_anthropic, mock_claude_parsing_response):
    """Test Stage 2: Triage assigns tier levels to sheets."""
    result = await stage_2_triage(mock_claude_parsing_response)

    assert "triage" in result
    assert "tokens" in result
    assert isinstance(result["triage"], list)

    for sheet_triage in result["triage"]:
        assert "sheet_name" in sheet_triage
        assert "tier" in sheet_triage
        assert sheet_triage["tier"] in [1, 2, 3, 4]
        assert "decision" in sheet_triage
        assert "confidence" in sheet_triage


@pytest.mark.asyncio
async def test_triage_classifies_scratch_as_tier_4(mock_anthropic, mock_claude_parsing_response):
    """Test that scratch/working sheets are classified as Tier 4 (SKIP)."""
    # Add a scratch sheet to the mock response
    mock_claude_parsing_response["sheets"].append({
        "sheet_name": "Scratch - Working",
        "sheet_type": "scratch",
        "rows": []
    })

    result = await stage_2_triage(mock_claude_parsing_response)

    scratch_triage = [t for t in result["triage"] if "scratch" in t["sheet_name"].lower()]
    if scratch_triage:
        assert scratch_triage[0]["tier"] == 4
        assert scratch_triage[0]["decision"] == "SKIP"


@pytest.mark.asyncio
async def test_mapping_stage_uses_canonical_names(mock_anthropic, mock_claude_parsing_response):
    """Test Stage 3: Mapping produces canonical taxonomy names."""
    result = await stage_3_mapping(mock_claude_parsing_response)

    assert "mappings" in result
    assert "tokens" in result
    assert isinstance(result["mappings"], list)

    if result["mappings"]:
        mapping = result["mappings"][0]
        assert "original_label" in mapping
        assert "canonical_name" in mapping
        assert "confidence" in mapping

        # Check canonical names are lowercase with underscores
        canonical = mapping["canonical_name"]
        assert canonical == canonical.lower()
        assert " " not in canonical  # No spaces


@pytest.mark.asyncio
async def test_full_extraction_pipeline(mock_anthropic, sample_xlsx):
    """Test end-to-end extraction pipeline (Stages 1-3)."""
    result = await extract(sample_xlsx, file_id="test-123", entity_id="test-entity")

    # Check top-level structure
    assert "file_id" in result
    assert result["file_id"] == "test-123"
    assert "sheets" in result
    assert "triage" in result
    assert "line_items" in result
    assert "tokens_used" in result
    assert "cost_usd" in result

    # Check data types
    assert isinstance(result["sheets"], list)
    assert isinstance(result["triage"], list)
    assert isinstance(result["line_items"], list)
    assert isinstance(result["tokens_used"], int)
    assert isinstance(result["cost_usd"], float)


@pytest.mark.asyncio
async def test_extraction_skips_tier_4_sheets(mock_anthropic, sample_xlsx):
    """Test that Tier 4 sheets are skipped in line item extraction."""
    result = await extract(sample_xlsx, file_id="test-123")

    # Tier 4 sheets should not have line items extracted
    tier_4_sheets = [t["sheet_name"] for t in result["triage"] if t.get("tier") == 4]

    for line_item in result["line_items"]:
        assert line_item["sheet"] not in tier_4_sheets


@pytest.mark.asyncio
async def test_extraction_tracks_cost(mock_anthropic, sample_xlsx):
    """Test that extraction tracks token usage and estimated cost."""
    result = await extract(sample_xlsx, file_id="test-123")

    assert result["tokens_used"] > 0
    assert result["cost_usd"] > 0
    assert result["cost_usd"] < 1.0  # Sanity check - should be small for test file


def test_extract_json_handles_plain_json():
    """Test JSON extraction from plain JSON string."""
    json_str = '{"key": "value", "number": 42}'
    result = _extract_json(json_str)

    assert result == {"key": "value", "number": 42}


def test_extract_json_handles_markdown_code_blocks():
    """Test JSON extraction from markdown code blocks."""
    markdown_json = '''```json
{
    "key": "value",
    "number": 42
}
```'''
    result = _extract_json(markdown_json)

    assert result == {"key": "value", "number": 42}


def test_extract_json_handles_generic_code_blocks():
    """Test JSON extraction from generic code blocks."""
    generic_code = '''```
{"key": "value"}
```'''
    result = _extract_json(generic_code)

    assert result == {"key": "value"}


def test_extract_json_returns_empty_dict_on_invalid_json():
    """Test that invalid JSON returns empty dict instead of crashing."""
    invalid_json = "This is not JSON at all"
    result = _extract_json(invalid_json)

    assert result == {}


@pytest.mark.asyncio
async def test_line_items_include_provenance(mock_anthropic, sample_xlsx):
    """Test that extracted line items include provenance information."""
    result = await extract(sample_xlsx, file_id="test-123")

    if result["line_items"]:
        line_item = result["line_items"][0]

        # Check provenance fields
        assert "sheet" in line_item
        assert "row" in line_item
        assert "original_label" in line_item
        assert "canonical_name" in line_item
        assert "confidence" in line_item


@pytest.mark.asyncio
async def test_extraction_handles_empty_file_gracefully(mock_anthropic):
    """Test that extraction handles edge case of empty/minimal file."""
    # Create minimal Excel file bytes
    empty_bytes = b"PK\x03\x04"  # Minimal Excel file header

    # Should not crash, but may return empty results
    result = await extract(empty_bytes, file_id="test-empty")

    assert "file_id" in result
    assert isinstance(result["sheets"], list)
    assert isinstance(result["line_items"], list)
