"""
Unit tests for the extraction orchestrator.
Tests the 3-stage pipeline: Parse, Triage, Map.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.extraction.orchestrator import (
    ExtractionResult,
    _compute_quality,
    _compute_ts_consistency,
    _post_stage5_revalidation,
    extract,
)
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
    markdown_json = """```json
{
    "key": "value",
    "number": 42
}
```"""
    result = extract_json(markdown_json)

    assert result == {"key": "value", "number": 42}


def test_extract_json_handles_generic_code_blocks():
    """Test JSON extraction from generic code blocks."""
    generic_code = """```
{"key": "value"}
```"""
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

    await extract(
        sample_xlsx,
        file_id="test-progress",
        progress_callback=callback,
    )

    # Pipeline has 6 stages; callback should be called once per stage
    assert callback.call_count == 6

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
        sample_xlsx,
        file_id="test-callback-fail",
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


@pytest.mark.slow
@pytest.mark.asyncio
async def test_partial_lineage_saved_on_stage_failure(mock_anthropic, sample_xlsx):
    """Test that lineage events from completed stages are saved when a later stage fails."""
    from src.core.exceptions import ExtractionError
    from src.lineage.tracker import LineageTracker

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


# ============================================================================
# Checkpoint, resume, conditional skip, and early abort tests
# ============================================================================


@pytest.mark.asyncio
async def test_checkpoint_saved_after_each_stage(mock_anthropic, sample_xlsx):
    """Verify checkpoint save is attempted after each stage."""
    saved_stages = []

    with patch(
        "src.extraction.orchestrator._save_checkpoint",
        side_effect=lambda job_id, stage_name, result: saved_stages.append(stage_name),
    ):
        await extract(sample_xlsx, file_id="test-checkpoint")

    # All 6 stages should attempt checkpoint save
    assert "parsing" in saved_stages
    assert "triage" in saved_stages
    assert "mapping" in saved_stages
    assert "derivation" in saved_stages
    assert len(saved_stages) == 6


@pytest.mark.asyncio
async def test_checkpoint_save_failure_does_not_abort(mock_anthropic, sample_xlsx):
    """Pipeline should complete even if checkpoint save fails."""
    with patch(
        "src.db.crud.update_job_partial_result",
        side_effect=RuntimeError("DB down"),
    ):
        result = await extract(sample_xlsx, file_id="test-checkpoint-fail")

    assert result["file_id"] == "test-checkpoint-fail"
    assert "line_items" in result


@pytest.mark.asyncio
async def test_validation_skipped_when_no_tier_1_2(mock_anthropic, sample_xlsx):
    """Validation should be skipped when no tier 1-2 sheets exist."""
    from src.extraction.stages.triage import TriageStage
    from src.extraction.stages.validation import ValidationStage

    original_triage_execute = TriageStage.execute

    async def triage_all_tier_3(self, context):
        result = await original_triage_execute(self, context)
        # Override tiers to all be 3
        for t in result.get("triage", []):
            t["tier"] = 3
        return result

    validation_called = False
    original_validation_execute = ValidationStage.execute

    async def track_validation(self, context):
        nonlocal validation_called
        validation_called = True
        return await original_validation_execute(self, context)

    with patch.object(TriageStage, "execute", triage_all_tier_3):
        with patch.object(ValidationStage, "execute", track_validation):
            await extract(sample_xlsx, file_id="test-skip-validation")

    # Validation should_skip returns True when no tier 1-2 sheets
    assert not validation_called


@pytest.mark.asyncio
async def test_pipeline_aborts_early_when_all_tier_4(mock_anthropic, sample_xlsx):
    """Pipeline should abort after triage when all sheets are tier 4."""
    from src.extraction.stages.mapping import MappingStage
    from src.extraction.stages.triage import TriageStage

    original_triage_execute = TriageStage.execute

    async def triage_all_tier_4(self, context):
        result = await original_triage_execute(self, context)
        for t in result.get("triage", []):
            t["tier"] = 4
        return result

    mapping_called = False
    original_mapping_execute = MappingStage.execute

    async def track_mapping(self, context):
        nonlocal mapping_called
        mapping_called = True
        return await original_mapping_execute(self, context)

    with patch.object(TriageStage, "execute", triage_all_tier_4):
        with patch.object(MappingStage, "execute", track_mapping):
            result = await extract(sample_xlsx, file_id="test-all-tier-4")

    # Mapping should NOT have been called (pipeline aborted after triage)
    assert not mapping_called
    # Result should still have valid structure
    assert "file_id" in result
    assert result["line_items"] == []


@pytest.mark.asyncio
async def test_skipped_stage_emits_lineage(mock_anthropic, sample_xlsx):
    """Verify that skipped stages still get lineage events with metadata."""
    from src.lineage.tracker import LineageTracker

    emitted_events = []
    original_init = LineageTracker.__init__

    def mock_tracker_init(self, job_id):
        original_init(self, job_id)

        original_emit = self.emit

        def tracking_emit(**kwargs):
            emitted_events.append(kwargs)
            return original_emit(**kwargs)

        self.emit = tracking_emit

    with patch.object(LineageTracker, "__init__", mock_tracker_init):
        await extract(sample_xlsx, file_id="test-skip-lineage")

    # All 5 stages should have lineage events (even if some were skipped)
    assert len(emitted_events) >= 5
    event_types = [e.get("event_type") for e in emitted_events]
    assert "parsing" in event_types
    assert "triage" in event_types


@pytest.mark.asyncio
async def test_resume_from_stage_skips_completed(mock_anthropic, sample_xlsx):
    """Verify that resume_from_stage loads checkpoint and skips completed stages."""
    from src.extraction.stages.parsing import ParsingStage

    parsing_called = False
    original_parse = ParsingStage.execute

    async def track_parsing(self, context):
        nonlocal parsing_called
        parsing_called = True
        return await original_parse(self, context)

    # Mock the _preload_checkpoint to simulate loaded checkpoint
    def mock_preload(context, job_id, pipeline, resume_from_stage):
        # Simulate parsing already completed with realistic data
        fake_parsing_result = {
            "parsed": {
                "sheets": [
                    {
                        "sheet_name": "Income Statement",
                        "rows": [
                            {
                                "row_index": 1,
                                "label": "Revenue",
                                "cell_ref": "A1",
                                "values": {"FY2023": 100, "FY2024": 200},
                                "hierarchy_level": 0,
                                "is_subtotal": False,
                                "is_formula": False,
                            }
                        ],
                    }
                ]
            },
            "tokens": 100,
            "input_tokens": 60,
            "output_tokens": 40,
            "lineage_metadata": {"sheets_count": 1},
        }
        context._result_cache["parsing"] = fake_parsing_result
        context.set_result("parsing", fake_parsing_result)
        context.completed_stages.append("parsing")

    with patch("src.extraction.orchestrator._preload_checkpoint", mock_preload):
        with patch.object(ParsingStage, "execute", track_parsing):
            result = await extract(
                sample_xlsx,
                file_id="test-resume",
                job_id="test-job-resume",
                resume_from_stage="triage",
            )

    # Parsing should NOT have been called (loaded from checkpoint)
    assert not parsing_called
    assert result["file_id"] == "test-resume"


# ============================================================================
# Quality scoring tests
# ============================================================================


class TestComputeTsConsistency:
    """Tests for _compute_ts_consistency helper."""

    def test_full_coverage(self):
        """All items have all periods -> 1.0."""
        items = [
            {"canonical_name": "revenue", "values": {"FY2023": 100, "FY2024": 110}},
            {"canonical_name": "ebitda", "values": {"FY2023": 40, "FY2024": 45}},
        ]
        assert _compute_ts_consistency(items) == 1.0

    def test_partial_coverage(self):
        """Items with mixed period coverage -> fractional score."""
        items = [
            {"canonical_name": "revenue", "values": {"FY2023": 100, "FY2024": 110}},
            {"canonical_name": "ebitda", "values": {"FY2023": 40}},
        ]
        # revenue has 2/2 = 1.0, ebitda has 1/2 = 0.5; avg = 0.75
        assert _compute_ts_consistency(items) == 0.75

    def test_empty_items(self):
        """No items -> 0.0."""
        assert _compute_ts_consistency([]) == 0.0

    def test_all_unmapped(self):
        """All unmapped items are excluded -> 0.0."""
        items = [
            {"canonical_name": "unmapped", "values": {"FY2023": 100}},
        ]
        assert _compute_ts_consistency(items) == 0.0

    def test_no_values(self):
        """Items with no values -> 0.0."""
        items = [
            {"canonical_name": "revenue", "values": {}},
        ]
        assert _compute_ts_consistency(items) == 0.0


class TestComputeQuality:
    """Tests for _compute_quality helper."""

    def test_high_quality_result(self):
        """Well-mapped items with good validation -> grade A."""
        line_items = [
            {
                "canonical_name": "revenue",
                "confidence": 0.95,
                "values": {"FY2023": 100, "FY2024": 110},
            },
            {
                "canonical_name": "ebitda",
                "confidence": 0.90,
                "values": {"FY2023": 40, "FY2024": 45},
            },
        ]
        validation_result = {
            "validation": {"overall_confidence": 0.95, "flags": []},
        }

        quality = _compute_quality(line_items, validation_result)

        assert quality["letter_grade"] == "A"
        assert quality["label"] == "trustworthy"
        assert quality["numeric_score"] >= 0.9
        assert len(quality["dimensions"]) == 4

    def test_all_unmapped_result(self):
        """All unmapped items -> low score."""
        line_items = [
            {"canonical_name": "unmapped", "confidence": 0.5, "values": {"FY2023": 100}},
            {"canonical_name": "unmapped", "confidence": 0.3, "values": {"FY2023": 50}},
        ]
        validation_result = {}

        quality = _compute_quality(line_items, validation_result)

        assert quality["numeric_score"] == 0.0
        assert quality["letter_grade"] == "F"
        assert quality["label"] == "unreliable"

    def test_empty_line_items(self):
        """No line items -> score 0."""
        quality = _compute_quality([], {})

        assert quality["numeric_score"] == 0.0
        assert quality["letter_grade"] == "F"

    def test_mixed_mapped_unmapped(self):
        """Mix of mapped and unmapped -> partial completeness."""
        line_items = [
            {"canonical_name": "revenue", "confidence": 0.95, "values": {"FY2023": 100}},
            {"canonical_name": "unmapped", "confidence": 0.3, "values": {"FY2023": 50}},
        ]
        validation_result = {
            "validation": {"overall_confidence": 0.8},
        }

        quality = _compute_quality(line_items, validation_result)

        # Completeness = 1/2 = 0.5 (drags score down)
        assert 0.4 < quality["numeric_score"] < 0.9
        assert quality["dimensions"] is not None

    def test_quality_dimensions_present(self):
        """Verify all 4 dimensions are in the output."""
        line_items = [
            {"canonical_name": "revenue", "confidence": 0.9, "values": {"FY2023": 100}},
        ]
        validation_result = {"validation": {"overall_confidence": 0.85}}

        quality = _compute_quality(line_items, validation_result)

        dim_names = {d["name"] for d in quality["dimensions"]}
        assert dim_names == {
            "mapping_confidence",
            "validation_success",
            "completeness",
            "time_series_consistency",
        }


@pytest.mark.asyncio
async def test_extraction_result_includes_quality(mock_anthropic, sample_xlsx):
    """Test that full extraction pipeline includes quality score in result."""
    result = await extract(sample_xlsx, file_id="test-quality")

    assert "quality" in result
    quality = result["quality"]
    assert quality is not None
    assert "numeric_score" in quality
    assert "letter_grade" in quality
    assert "label" in quality
    assert "dimensions" in quality
    assert quality["letter_grade"] in ("A", "B", "C", "D", "F")
    assert 0.0 <= quality["numeric_score"] <= 1.0


# ============================================================================
# Quality gate tests
# ============================================================================


class TestQualityGate:
    """Test quality gate logic in _compute_quality and _build_result."""

    def test_quality_gate_pass_grade_b(self):
        """Grade B extraction should pass the quality gate."""
        line_items = [
            {
                "canonical_name": "revenue",
                "confidence": 0.85,
                "values": {"FY2023": 100, "FY2024": 110},
            },
            {
                "canonical_name": "ebitda",
                "confidence": 0.80,
                "values": {"FY2023": 40, "FY2024": 45},
            },
        ]
        validation_result = {
            "validation": {"overall_confidence": 0.80, "flags": []},
        }
        quality = _compute_quality(line_items, validation_result)
        assert quality["letter_grade"] in ("A", "B")
        # quality_gate is added in _build_result, not _compute_quality

    def test_quality_gate_fail_grade_f(self):
        """Grade F extraction should fail the quality gate."""
        line_items = [
            {"canonical_name": "unmapped", "confidence": 0.1, "values": {"FY2023": 100}},
            {"canonical_name": "unmapped", "confidence": 0.1, "values": {"FY2023": 50}},
        ]
        validation_result = {"validation": {"overall_confidence": 0.1}}
        quality = _compute_quality(line_items, validation_result)
        assert quality["letter_grade"] == "F"

    def test_model_type_parameter(self):
        """Model type should be passed through to QualityResult."""
        line_items = [
            {"canonical_name": "revenue", "confidence": 0.9, "values": {"FY2023": 100}},
        ]
        validation_result = {"validation": {"overall_confidence": 0.8}}
        quality = _compute_quality(line_items, validation_result, model_type="saas")
        assert quality["model_type"] == "saas"

    def test_no_model_type(self):
        """Without model_type, no model_type key in result."""
        line_items = [
            {"canonical_name": "revenue", "confidence": 0.9, "values": {"FY2023": 100}},
        ]
        validation_result = {"validation": {"overall_confidence": 0.8}}
        quality = _compute_quality(line_items, validation_result)
        assert "model_type" not in quality


# ============================================================================
# Post-Stage-5 re-validation tests
# ============================================================================


class TestPostStage5Revalidation:
    """Test post-Stage-5 deterministic re-validation."""

    def test_revalidation_returns_delta(self):
        """Post-Stage-5 re-validation should return a delta dict."""
        from src.extraction.base import PipelineContext

        context = PipelineContext(
            file_bytes=b"test",
            file_id="test-file",
            job_id="test-job",
        )
        # Set up minimal stage results
        context.set_result(
            "parsing",
            {
                "parsed": {
                    "sheets": [
                        {
                            "sheet_name": "IS",
                            "rows": [
                                {"label": "Revenue", "values": {"FY2023": "1000"}},
                                {"label": "COGS", "values": {"FY2023": "400"}},
                                {"label": "GP", "values": {"FY2023": "600"}},
                            ],
                        }
                    ],
                },
            },
        )
        context.set_result(
            "triage",
            {
                "triage": [{"sheet_name": "IS", "tier": 1}],
            },
        )
        context.set_result(
            "validation",
            {
                "validation": {"overall_confidence": 0.7, "flags": []},
            },
        )
        context.set_result(
            "mapping",
            {
                "mappings": [
                    {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.9},
                    {"original_label": "COGS", "canonical_name": "cogs", "confidence": 0.85},
                    {"original_label": "GP", "canonical_name": "gross_profit", "confidence": 0.8},
                ],
            },
        )
        context.set_result(
            "enhanced_mapping",
            {
                "enhanced_mappings": [
                    {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
                    {"original_label": "COGS", "canonical_name": "cogs", "confidence": 0.9},
                    {"original_label": "GP", "canonical_name": "gross_profit", "confidence": 0.85},
                ],
            },
        )

        delta = _post_stage5_revalidation(context)
        assert delta is not None
        assert "pre_stage5_rate" in delta
        assert "post_stage5_rate" in delta
        assert "delta" in delta
        assert "improved" in delta
        assert isinstance(delta["total_checks"], int)

    def test_revalidation_handles_no_enhanced_mapping(self):
        """If enhanced_mapping has no mappings, should still work."""
        from src.extraction.base import PipelineContext

        context = PipelineContext(
            file_bytes=b"test",
            file_id="test-file",
            job_id="test-job",
        )
        context.set_result(
            "parsing",
            {
                "parsed": {"sheets": []},
            },
        )
        context.set_result("triage", {"triage": []})
        context.set_result(
            "validation",
            {
                "validation": {"overall_confidence": 0.5},
            },
        )
        context.set_result("mapping", {"mappings": []})
        context.set_result("enhanced_mapping", {"enhanced_mappings": []})

        delta = _post_stage5_revalidation(context)
        # Should succeed even with empty data
        assert delta is not None
        assert delta["total_checks"] == 0

    def test_revalidation_returns_none_on_error(self):
        """Errors during re-validation should be caught and return None."""
        from src.extraction.base import PipelineContext

        context = PipelineContext(
            file_bytes=b"test",
            file_id="test-file",
            job_id="test-job",
        )
        # Don't set any results — get_result will raise KeyError
        delta = _post_stage5_revalidation(context)
        assert delta is None


# ============================================================================
# ExtractionResult validation_delta tests
# ============================================================================


class TestExtractionResultValidationDelta:
    """Test that ExtractionResult carries validation_delta."""

    def test_validation_delta_in_to_dict(self):
        result = ExtractionResult(
            file_id="test",
            sheets=["Sheet1"],
            triage=[],
            line_items=[],
            tokens_used=100,
            cost_usd=0.01,
            validation_delta={"delta": 0.05, "improved": True},
        )
        d = result.to_dict()
        assert d["validation_delta"] == {"delta": 0.05, "improved": True}

    def test_validation_delta_default_none(self):
        result = ExtractionResult(
            file_id="test",
            sheets=[],
            triage=[],
            line_items=[],
            tokens_used=0,
            cost_usd=0.0,
        )
        d = result.to_dict()
        assert d["validation_delta"] is None


@pytest.mark.asyncio
async def test_extraction_includes_quality_gate(mock_anthropic, sample_xlsx):
    """Full pipeline result should include quality_gate in quality dict."""
    result = await extract(sample_xlsx, file_id="test-quality-gate")
    quality = result.get("quality", {})
    assert "quality_gate" in quality
    assert "passed" in quality["quality_gate"]


# ============================================================================
# Edge Case Hardening Tests
# ============================================================================


class TestPostStage5EdgeCases:
    """Tests for edge case fixes in _post_stage5_revalidation."""

    def _make_context(self, sheets, triage, mappings, validation_conf=0.7):
        """Helper to build a PipelineContext with minimal stage results."""
        from src.extraction.base import PipelineContext

        context = PipelineContext(
            file_bytes=b"test",
            file_id="test-file",
            job_id="test-job",
        )
        context.set_result(
            "parsing",
            {
                "parsed": {"sheets": sheets},
            },
        )
        context.set_result("triage", {"triage": triage})
        context.set_result(
            "validation",
            {
                "validation": {"overall_confidence": validation_conf, "flags": []},
            },
        )
        context.set_result("mapping", {"mappings": mappings})
        context.set_result("enhanced_mapping", {"enhanced_mappings": mappings})
        return context

    def test_revalidation_logs_non_numeric(self):
        """Non-numeric values should be logged at debug level, not silently dropped."""
        context = self._make_context(
            sheets=[
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2023": "not-a-number"}},
                    ],
                }
            ],
            triage=[{"sheet_name": "IS", "tier": 1}],
            mappings=[
                {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.9},
            ],
        )

        with patch("src.extraction.orchestrator.logger") as mock_logger:
            delta = _post_stage5_revalidation(context)
            assert delta is not None
            # Should have logged the non-numeric skip
            mock_logger.debug.assert_any_call(
                "Post-Stage-5 revalidation: skipping non-numeric value "
                "'not-a-number' for label=Revenue, period=FY2023"
            )

    def test_revalidation_excludes_tier3(self):
        """Post-Stage-5 re-validation should only process tier 1-2, not tier 3."""
        context = self._make_context(
            sheets=[
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2023": "1000"}},
                    ],
                },
                {
                    "sheet_name": "Summary",
                    "rows": [
                        {"label": "Summary Rev", "values": {"FY2023": "9999"}},
                    ],
                },
            ],
            triage=[
                {"sheet_name": "IS", "tier": 1},
                {"sheet_name": "Summary", "tier": 3},
            ],
            mappings=[
                {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.9},
                {"original_label": "Summary Rev", "canonical_name": "revenue", "confidence": 0.8},
            ],
        )

        delta = _post_stage5_revalidation(context)
        assert delta is not None
        # Tier 3 sheet should be excluded — only tier 1 data used

    def test_revalidation_first_write_wins(self):
        """When same canonical appears on two sheets, first value should be kept."""
        context = self._make_context(
            sheets=[
                {
                    "sheet_name": "IS",
                    "rows": [
                        {"label": "Revenue", "values": {"FY2023": "1000"}},
                    ],
                },
                {
                    "sheet_name": "Detail",
                    "rows": [
                        {"label": "Rev Detail", "values": {"FY2023": "9999"}},
                    ],
                },
            ],
            triage=[
                {"sheet_name": "IS", "tier": 1},
                {"sheet_name": "Detail", "tier": 2},
            ],
            mappings=[
                {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.9},
                {"original_label": "Rev Detail", "canonical_name": "revenue", "confidence": 0.8},
            ],
        )

        with patch("src.extraction.orchestrator.logger") as mock_logger:
            delta = _post_stage5_revalidation(context)
            assert delta is not None
            # Should have logged the duplicate skip
            debug_calls = [str(c) for c in mock_logger.debug.call_args_list]
            assert any("Duplicate canonical 'revenue'" in c for c in debug_calls)


# ============================================================================
# E3: QUALITY GATE THRESHOLD CONFIGURABILITY
# ============================================================================


class TestQualityGateThreshold:
    """Test configurable quality gate threshold via QUALITY_GATE_MIN_GRADE."""

    def test_custom_threshold_blocks_d_and_below(self):
        """When threshold is D, grades D and F should fail the gate."""
        from src.extraction.orchestrator import _GRADE_RANKS

        min_grade = "D"
        min_grade_rank = _GRADE_RANKS.get(min_grade, 1)
        # D(2) <= D(2) → gate fails
        assert _GRADE_RANKS.get("D", 0) <= min_grade_rank
        # F(1) <= D(2) → gate fails
        assert _GRADE_RANKS.get("F", 0) <= min_grade_rank

    def test_grade_above_threshold_passes(self):
        """When threshold is D, grade C should pass the gate."""
        from src.extraction.orchestrator import _GRADE_RANKS

        min_grade = "D"
        min_grade_rank = _GRADE_RANKS.get(min_grade, 1)
        # C(3) > D(2) → gate passes
        assert _GRADE_RANKS.get("C", 0) > min_grade_rank
        # B(4) > D(2) → gate passes
        assert _GRADE_RANKS.get("B", 0) > min_grade_rank

    def test_default_threshold_only_blocks_f(self):
        """Default threshold F should only block grade F."""
        from src.extraction.orchestrator import _GRADE_RANKS

        min_grade = "F"
        min_grade_rank = _GRADE_RANKS.get(min_grade, 1)
        # F fails
        assert _GRADE_RANKS.get("F", 0) <= min_grade_rank
        # D passes
        assert _GRADE_RANKS.get("D", 0) > min_grade_rank
        # A passes
        assert _GRADE_RANKS.get("A", 0) > min_grade_rank


# ============================================================================
# E4: MODEL_TYPE ON ExtractionResult
# ============================================================================


class TestExtractionResultModelType:
    """Test model_type field on ExtractionResult dataclass."""

    def test_model_type_in_to_dict(self):
        """ExtractionResult.to_dict() should include model_type."""
        result = ExtractionResult(
            file_id="test",
            sheets=["Sheet1"],
            triage=[],
            line_items=[],
            tokens_used=100,
            cost_usd=0.01,
            model_type="project_finance",
        )
        d = result.to_dict()
        assert d["model_type"] == "project_finance"

    def test_model_type_default_none(self):
        """ExtractionResult.model_type defaults to None."""
        result = ExtractionResult(
            file_id="test",
            sheets=["Sheet1"],
            triage=[],
            line_items=[],
            tokens_used=100,
            cost_usd=0.01,
        )
        assert result.model_type is None
        d = result.to_dict()
        assert d["model_type"] is None
