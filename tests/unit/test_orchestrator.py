"""
Unit tests for the extraction orchestrator.
Tests the 3-stage pipeline: Parse, Triage, Map.
"""
import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock

from src.extraction.orchestrator import extract, ExtractionResult
from src.extraction.registry import registry
from src.extraction.utils import extract_json


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
    empty_bytes = b"PK\x03\x04"

    result = await extract(empty_bytes, file_id="test-empty")

    assert "file_id" in result
    assert isinstance(result["sheets"], list)
    assert isinstance(result["line_items"], list)


def test_registry_has_stages():
    """Test that the stage registry has all 3 stages registered."""
    stages = registry.registered_stages
    assert "parsing" in stages
    assert "triage" in stages
    assert "mapping" in stages


def test_pipeline_order():
    """Test that pipeline stages are returned in correct order."""
    pipeline = registry.get_pipeline()
    assert len(pipeline) >= 3
    assert pipeline[0].name == "parsing"
    assert pipeline[1].name == "triage"
    assert pipeline[2].name == "mapping"


def test_extract_json_handles_plain_json():
    """Test JSON extraction from plain JSON string."""
    json_str = '{"key": "value", "number": 42}'
    result = extract_json(json_str)

    assert result == {"key": "value", "number": 42}


def test_extract_json_handles_markdown_code_blocks():
    """Test JSON extraction from markdown code blocks."""
    markdown_json = '''```json
{
    "key": "value",
    "number": 42
}
```'''
    result = extract_json(markdown_json)

    assert result == {"key": "value", "number": 42}


def test_extract_json_handles_generic_code_blocks():
    """Test JSON extraction from generic code blocks."""
    generic_code = '''```
{"key": "value"}
```'''
    result = extract_json(generic_code)

    assert result == {"key": "value"}


def test_extract_json_raises_on_invalid_json():
    """Test that invalid JSON raises ExtractionError."""
    from src.core.exceptions import ExtractionError

    invalid_json = "This is not JSON at all"
    with pytest.raises(ExtractionError):
        extract_json(invalid_json)


def test_extraction_result_to_dict():
    """Test ExtractionResult dataclass serialization."""
    result = ExtractionResult(
        file_id="test-123",
        sheets=["Sheet1"],
        triage=[{"sheet_name": "Sheet1", "tier": 1}],
        line_items=[],
        tokens_used=100,
        cost_usd=0.001,
    )
    d = result.to_dict()
    assert d["file_id"] == "test-123"
    assert d["tokens_used"] == 100
    assert isinstance(d, dict)


# ============================================================================
# Progress callback and partial lineage tests
# ============================================================================


@pytest.mark.asyncio
async def test_progress_callback_called_after_each_stage(mock_anthropic, sample_xlsx):
    """Test that progress_callback is called after each stage completes."""
    callback = MagicMock()

    result = await extract(
        sample_xlsx, file_id="test-progress",
        progress_callback=callback,
    )

    # Pipeline has 5 stages; callback should be called once per stage
    assert callback.call_count == 5

    # Verify each call received (stage_name, progress_percent)
    stage_names = [call.args[0] for call in callback.call_args_list]
    assert "parsing" in stage_names
    assert "triage" in stage_names
    assert "mapping" in stage_names

    # All progress values should be integers between 0 and 100
    for call in callback.call_args_list:
        stage_name, progress_percent = call.args
        assert isinstance(stage_name, str)
        assert isinstance(progress_percent, int)
        assert 0 < progress_percent <= 100


@pytest.mark.asyncio
async def test_progress_callback_failure_does_not_abort_pipeline(mock_anthropic, sample_xlsx):
    """Test that a failing progress callback does not abort the pipeline."""
    callback = MagicMock(side_effect=RuntimeError("callback failed"))

    # Pipeline should still complete even though callback raises
    result = await extract(
        sample_xlsx, file_id="test-callback-fail",
        progress_callback=callback,
    )

    assert "file_id" in result
    assert result["file_id"] == "test-callback-fail"


@pytest.mark.asyncio
async def test_no_progress_callback_by_default(mock_anthropic, sample_xlsx):
    """Test that extract works without a progress callback (backward compat)."""
    # Should work exactly as before, no callback
    result = await extract(sample_xlsx, file_id="test-no-callback")

    assert "file_id" in result
    assert result["file_id"] == "test-no-callback"


@pytest.mark.asyncio
async def test_partial_lineage_saved_on_stage_failure(mock_anthropic, sample_xlsx):
    """Test that lineage events from completed stages are saved when a later stage fails."""
    from src.lineage.tracker import LineageTracker
    from src.core.exceptions import ExtractionError

    # Track whether save_to_db was called and with how many events
    save_calls = []

    original_init = LineageTracker.__init__

    def mock_tracker_init(self, job_id):
        original_init(self, job_id)

        def tracking_save():
            save_calls.append(len(self.events))

        self.save_to_db = tracking_save

    with patch.object(LineageTracker, "__init__", mock_tracker_init):
        # Make the triage stage (stage 2) fail after parsing (stage 1) succeeds
        from src.extraction.stages.triage import TriageStage

        async def failing_triage_execute(self, context):
            raise ExtractionError("Triage boom", stage="triage")

        with patch.object(TriageStage, "execute", failing_triage_execute):
            with pytest.raises(ExtractionError, match="Triage boom"):
                await extract(sample_xlsx, file_id="test-partial-lineage")

    # save_to_db should have been called once (partial save) with >= 1 event (parsing)
    assert len(save_calls) == 1
    assert save_calls[0] >= 1  # At least the parsing stage lineage event
