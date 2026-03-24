"""
Tests for EnhancedMappingStage.execute() and related helper methods.

Focuses on paths not covered by test_enhanced_mapping_stage.py:
  - execute(): full success path, truncation, RateLimitError, APIError
  - should_skip(): with and without candidates
  - _find_remapping_candidates(): validation_result integration
  - _persist_entity_patterns(): with/without entity_id
  - _record_learned_aliases(): with/without entity_id
  - _build_entity_context(): with entity_id + DB patterns
"""

import json
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from src.extraction.base import PipelineContext
from src.extraction.stages.enhanced_mapping import EnhancedMappingStage


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_context(
    mappings=None,
    validation_result=None,
    entity_id=None,
    parse_result=None,
):
    """Build a minimal PipelineContext with pre-set results."""
    context = MagicMock(spec=PipelineContext)
    context.entity_id = entity_id

    default_parse = {
        "sheets": [
            {
                "sheet_name": "IS",
                "rows": [
                    {"label": "Revenue", "hierarchy_level": 1},
                    {"label": "Low Conf Item", "hierarchy_level": 1},
                ],
            }
        ]
    }
    context.get_result.side_effect = lambda key: {
        "parsing": {"parsed": parse_result or default_parse},
        "mapping": {"mappings": mappings or []},
    }.get(key, {})

    context.results = {}
    if validation_result:
        context.results["validation"] = validation_result

    return context


def _make_claude_response(content_json, stop_reason="end_turn"):
    """Build a minimal mock Claude API response."""
    resp = MagicMock()
    resp.stop_reason = stop_reason
    content_block = MagicMock()
    content_block.text = json.dumps(content_json)
    resp.content = [content_block]
    resp.usage = MagicMock(input_tokens=500, output_tokens=200)
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# should_skip
# ─────────────────────────────────────────────────────────────────────────────


class TestShouldSkip:
    """Test the should_skip decision."""

    def test_skip_when_all_high_confidence(self):
        """All mappings confident → skip stage 5."""
        stage = EnhancedMappingStage()
        ctx = _make_context(
            mappings=[
                {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
                {"original_label": "COGS", "canonical_name": "cogs", "confidence": 0.90},
            ]
        )
        assert stage.should_skip(ctx) is True

    def test_no_skip_when_low_confidence(self):
        """Low-confidence item → do NOT skip."""
        stage = EnhancedMappingStage()
        ctx = _make_context(
            mappings=[
                {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
                {"original_label": "Foo", "canonical_name": "unmapped", "confidence": 0.0},
            ]
        )
        assert stage.should_skip(ctx) is False

    def test_no_skip_when_unmapped(self):
        """Unmapped item → do NOT skip."""
        stage = EnhancedMappingStage()
        ctx = _make_context(
            mappings=[
                {"original_label": "Mystery", "canonical_name": "unmapped", "confidence": 0.0},
            ]
        )
        assert stage.should_skip(ctx) is False

    def test_skip_when_mappings_missing_from_context(self):
        """KeyError from context → skip (graceful fallback)."""
        stage = EnhancedMappingStage()
        ctx = MagicMock(spec=PipelineContext)
        ctx.get_result.side_effect = KeyError("mapping")
        ctx.results = {}
        assert stage.should_skip(ctx) is False


# ─────────────────────────────────────────────────────────────────────────────
# execute() — success path
# ─────────────────────────────────────────────────────────────────────────────


class TestExecuteSuccess:
    """Test execute() with a mocked successful Claude response."""

    @pytest.mark.asyncio
    async def test_execute_returns_enhanced_mappings(self):
        """execute() should return enhanced mappings with remapped_count."""
        stage = EnhancedMappingStage()
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "Umsatz", "canonical_name": "unmapped", "confidence": 0.0},
        ]
        ctx = _make_context(mappings=mappings)

        enhanced_response = [
            {"original_label": "Umsatz", "canonical_name": "revenue", "confidence": 0.88},
        ]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_claude_response(enhanced_response)

        with (
            patch("src.extraction.stages.enhanced_mapping.get_claude_client", return_value=mock_client),
            patch("src.extraction.stages.enhanced_mapping.format_taxonomy_detailed", return_value="taxonomy text"),
            patch("src.extraction.stages.enhanced_mapping.validate_canonical_names"),
            patch.object(stage, "_persist_entity_patterns", return_value=0),
        ):
            result = await stage.execute(ctx)

        assert "enhanced_mappings" in result
        assert result["remapped_count"] == 1
        assert result["tokens"] > 0
        final = {m["original_label"]: m for m in result["enhanced_mappings"]}
        assert final["Umsatz"]["canonical_name"] == "revenue"
        assert final["Revenue"]["canonical_name"] == "revenue"

    @pytest.mark.asyncio
    async def test_execute_skips_lower_confidence_remapping(self):
        """Claude suggestion with lower confidence should be rejected."""
        stage = EnhancedMappingStage()
        mappings = [
            {"original_label": "SGA", "canonical_name": "sga", "confidence": 0.75},
        ]
        ctx = _make_context(mappings=mappings)

        # Claude suggests lower confidence
        enhanced_response = [
            {"original_label": "SGA", "canonical_name": "other_expenses", "confidence": 0.60},
        ]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_claude_response(enhanced_response)

        with (
            patch("src.extraction.stages.enhanced_mapping.get_claude_client", return_value=mock_client),
            patch("src.extraction.stages.enhanced_mapping.format_taxonomy_detailed", return_value="t"),
            patch("src.extraction.stages.enhanced_mapping.validate_canonical_names"),
            patch.object(stage, "_persist_entity_patterns", return_value=0),
        ):
            result = await stage.execute(ctx)

        assert result["remapped_count"] == 0
        # Original mapping should be kept
        assert result["enhanced_mappings"][0]["canonical_name"] == "sga"

    @pytest.mark.asyncio
    async def test_execute_no_candidates_returns_early(self):
        """If no candidates remain, return original mappings without Claude call."""
        stage = EnhancedMappingStage()
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
        ]
        ctx = _make_context(mappings=mappings)

        mock_client = MagicMock()

        with (
            patch("src.extraction.stages.enhanced_mapping.get_claude_client", return_value=mock_client),
            patch.object(stage, "_persist_entity_patterns", return_value=0),
        ):
            result = await stage.execute(ctx)

        # Claude should NOT be called
        mock_client.messages.create.assert_not_called()
        assert result["remapped_count"] == 0
        assert result["lineage_metadata"]["skipped"] is True

    @pytest.mark.asyncio
    async def test_execute_handles_non_list_claude_response(self):
        """Non-list Claude response should not raise; use empty enhanced_lookup."""
        stage = EnhancedMappingStage()
        mappings = [
            {"original_label": "X", "canonical_name": "unmapped", "confidence": 0.0},
        ]
        ctx = _make_context(mappings=mappings)

        mock_client = MagicMock()
        # Return a dict instead of list
        mock_client.messages.create.return_value = _make_claude_response({"error": "not a list"})

        with (
            patch("src.extraction.stages.enhanced_mapping.get_claude_client", return_value=mock_client),
            patch("src.extraction.stages.enhanced_mapping.format_taxonomy_detailed", return_value="t"),
            patch("src.extraction.stages.enhanced_mapping.validate_canonical_names"),
            patch.object(stage, "_persist_entity_patterns", return_value=0),
        ):
            result = await stage.execute(ctx)

        assert result["remapped_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# execute() — error handling paths
# ─────────────────────────────────────────────────────────────────────────────


class TestExecuteErrorHandling:
    """Test execute() error paths (truncation, rate limit, API error)."""

    @pytest.mark.asyncio
    async def test_execute_raises_extraction_error_on_truncation(self):
        """max_tokens stop_reason should raise ExtractionError."""
        from src.core.exceptions import ExtractionError

        stage = EnhancedMappingStage()
        mappings = [
            {"original_label": "X", "canonical_name": "unmapped", "confidence": 0.0},
        ]
        ctx = _make_context(mappings=mappings)

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_claude_response(
            [], stop_reason="max_tokens"
        )

        with (
            patch("src.extraction.stages.enhanced_mapping.get_claude_client", return_value=mock_client),
            patch("src.extraction.stages.enhanced_mapping.format_taxonomy_detailed", return_value="t"),
            pytest.raises(ExtractionError, match="truncated"),
        ):
            await stage.execute(ctx)

    @pytest.mark.asyncio
    async def test_execute_raises_rate_limit_error(self):
        """anthropic.RateLimitError should be converted to RateLimitError."""
        from src.core.exceptions import RateLimitError as AppRateLimitError

        stage = EnhancedMappingStage()
        mappings = [
            {"original_label": "X", "canonical_name": "unmapped", "confidence": 0.0},
        ]
        ctx = _make_context(mappings=mappings)

        # Build a REAL exception subclass — MagicMock can't be raised
        class FakeRateLimitError(anthropic.RateLimitError):
            def __init__(self):
                self.response = MagicMock(headers={"retry-after": "30"})
                self.status_code = 429
                self.message = "rate limit"
                self.body = None

            def __str__(self):
                return "rate limit"

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = FakeRateLimitError()

        with (
            patch("src.extraction.stages.enhanced_mapping.get_claude_client", return_value=mock_client),
            patch("src.extraction.stages.enhanced_mapping.format_taxonomy_detailed", return_value="t"),
            pytest.raises(AppRateLimitError),
        ):
            await stage.execute(ctx)

    @pytest.mark.asyncio
    async def test_execute_raises_claude_api_error(self):
        """anthropic.APIError should be converted to ClaudeAPIError."""
        from src.core.exceptions import ClaudeAPIError

        stage = EnhancedMappingStage()
        mappings = [
            {"original_label": "X", "canonical_name": "unmapped", "confidence": 0.0},
        ]
        ctx = _make_context(mappings=mappings)

        # Build a REAL exception subclass — MagicMock can't be raised
        class FakeAPIError(anthropic.APIError):
            def __init__(self):
                self.status_code = 500
                self.message = "Internal Server Error"
                self.body = None
                self.response = MagicMock()

            def __str__(self):
                return "Internal Server Error"

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = FakeAPIError()

        with (
            patch("src.extraction.stages.enhanced_mapping.get_claude_client", return_value=mock_client),
            patch("src.extraction.stages.enhanced_mapping.format_taxonomy_detailed", return_value="t"),
            pytest.raises(ClaudeAPIError),
        ):
            await stage.execute(ctx)

    @pytest.mark.asyncio
    async def test_execute_wraps_generic_exception(self):
        """Unexpected exception should be converted to ExtractionError."""
        from src.core.exceptions import ExtractionError

        stage = EnhancedMappingStage()
        mappings = [
            {"original_label": "X", "canonical_name": "unmapped", "confidence": 0.0},
        ]
        ctx = _make_context(mappings=mappings)

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("unexpected")

        with (
            patch("src.extraction.stages.enhanced_mapping.get_claude_client", return_value=mock_client),
            patch("src.extraction.stages.enhanced_mapping.format_taxonomy_detailed", return_value="t"),
            pytest.raises(ExtractionError, match="Enhanced mapping failed"),
        ):
            await stage.execute(ctx)


# ─────────────────────────────────────────────────────────────────────────────
# _find_remapping_candidates — validation_result integration
# ─────────────────────────────────────────────────────────────────────────────


class TestFindRemappingCandidatesWithValidation:
    """Test that validation failures escalate items to candidates."""

    def setup_method(self):
        self.stage = EnhancedMappingStage()

    def test_validation_failed_item_becomes_candidate(self):
        """High-confidence item with error-severity validation flag → candidate."""
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
            {"original_label": "EBITDA", "canonical_name": "ebitda", "confidence": 0.92},
        ]
        validation_result = {
            "validation": {
                "flags": [
                    {
                        "severity": "error",
                        "item": "ebitda",
                        "rule": "IS-3: ebitda != ebit + d&a",
                    }
                ]
            }
        }
        candidates = self.stage._find_remapping_candidates(mappings, validation_result)
        assert len(candidates) == 1
        assert candidates[0]["original_label"] == "EBITDA"
        assert candidates[0]["validation_context"]["validation_failed"] is True
        assert "IS-3" in candidates[0]["validation_context"]["failed_rule"]

    def test_warning_severity_not_a_candidate(self):
        """Warning-severity flags should NOT escalate items to candidates."""
        mappings = [
            {"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95},
        ]
        validation_result = {
            "validation": {
                "flags": [
                    {
                        "severity": "warning",
                        "item": "revenue",
                        "rule": "Revenue growth > 300%",
                    }
                ]
            }
        }
        candidates = self.stage._find_remapping_candidates(mappings, validation_result)
        assert len(candidates) == 0

    def test_duplicate_labels_deduplicated(self):
        """Same label appearing twice should only be added once."""
        mappings = [
            {"original_label": "Revenue", "canonical_name": "unmapped", "confidence": 0.0},
            {"original_label": "Revenue", "canonical_name": "unmapped", "confidence": 0.0},
        ]
        candidates = self.stage._find_remapping_candidates(mappings)
        assert len(candidates) == 1

    def test_empty_validation_result(self):
        """Empty validation_result dict handled gracefully."""
        mappings = [
            {"original_label": "EBITDA", "canonical_name": "ebitda", "confidence": 0.95},
        ]
        candidates = self.stage._find_remapping_candidates(mappings, {})
        assert candidates == []


# ─────────────────────────────────────────────────────────────────────────────
# _persist_entity_patterns — no entity_id path
# ─────────────────────────────────────────────────────────────────────────────


class TestPersistEntityPatterns:
    """Test _persist_entity_patterns skips when no entity_id."""

    def test_no_entity_id_returns_zero(self):
        stage = EnhancedMappingStage()
        ctx = MagicMock(spec=PipelineContext)
        ctx.entity_id = None
        result = stage._persist_entity_patterns(ctx, [])
        assert result == 0

    def test_db_error_returns_zero(self):
        """DB error during persist → returns 0 (no exception raised)."""
        stage = EnhancedMappingStage()
        ctx = MagicMock(spec=PipelineContext)
        ctx.entity_id = "some-entity-id"

        with patch("src.extraction.stages.enhanced_mapping.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                taxonomy_pattern_persist_confidence=0.85,
                taxonomy_learned_alias_confidence=0.90,
            )
            with patch("src.db.session.get_db_sync") as mock_db_ctx:
                mock_db_ctx.side_effect = Exception("DB connection failed")
                result = stage._persist_entity_patterns(ctx, [])

        assert result == 0


# ─────────────────────────────────────────────────────────────────────────────
# _record_learned_aliases — no entity_id path
# ─────────────────────────────────────────────────────────────────────────────


class TestRecordLearnedAliases:
    """Test _record_learned_aliases skips when no entity_id."""

    def test_no_entity_id_returns_zero(self):
        stage = EnhancedMappingStage()
        ctx = MagicMock(spec=PipelineContext)
        ctx.entity_id = None
        result = stage._record_learned_aliases(ctx, [])
        assert result == 0

    def test_db_error_returns_zero(self):
        """DB error → returns 0 gracefully."""
        stage = EnhancedMappingStage()
        ctx = MagicMock(spec=PipelineContext)
        ctx.entity_id = "entity-123"

        with (
            patch("src.extraction.stages.enhanced_mapping.get_settings") as mock_settings,
            patch("src.extraction.stages.enhanced_mapping.load_taxonomy_json", return_value={"categories": {}}),
        ):
            mock_settings.return_value = MagicMock(
                taxonomy_learned_alias_confidence=0.90,
            )
            with patch("src.db.session.get_db_sync") as mock_db:
                mock_db.side_effect = Exception("DB error")
                result = stage._record_learned_aliases(ctx, [])

        assert result == 0


# ─────────────────────────────────────────────────────────────────────────────
# _build_entity_context — with entity_id (DB loading path)
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildEntityContextWithDB:
    """Test _build_entity_context loads patterns from DB when entity_id is available."""

    def test_with_entity_id_attempts_db_load(self):
        """Should attempt to load patterns from DB if entity_id present."""
        from uuid import uuid4
        stage = EnhancedMappingStage()
        ctx = MagicMock(spec=PipelineContext)
        ctx.entity_id = str(uuid4())  # Must be a valid UUID

        mock_pattern = MagicMock()
        mock_pattern.original_label = "Revenue"
        mock_pattern.canonical_name = "revenue"
        mock_pattern.confidence = 0.95
        mock_pattern.occurrence_count = 10

        with (
            patch("src.db.session.get_db_sync") as mock_db_ctx,
            patch("src.db.crud.get_entity_patterns", return_value=[mock_pattern]) as mock_get,
        ):
            mock_db = MagicMock()
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = stage._build_entity_context(ctx, [])

        assert "Known patterns" in result

    def test_db_error_falls_back_gracefully(self):
        """DB error during pattern load should not raise."""
        from uuid import uuid4
        stage = EnhancedMappingStage()
        ctx = MagicMock(spec=PipelineContext)
        ctx.entity_id = str(uuid4())

        with patch("src.db.session.get_db_sync") as mock_db:
            mock_db.side_effect = Exception("DB down")
            result = stage._build_entity_context(
                ctx,
                [{"original_label": "Revenue", "canonical_name": "revenue", "confidence": 0.95}],
            )

        # Should still return something with the current high-conf mappings
        assert "Revenue" in result or "Known patterns" in result


# ─────────────────────────────────────────────────────────────────────────────
# execute() — validation_context items forwarded to Claude prompt
# ─────────────────────────────────────────────────────────────────────────────


class TestExecuteValidationContextItems:
    """Ensure validation-failed items get annotated before being sent to Claude."""

    @pytest.mark.asyncio
    async def test_validation_failed_label_annotated_in_prompt(self):
        """High-confidence item that fails validation is sent to Claude annotated."""
        stage = EnhancedMappingStage()
        # EBITDA is high-confidence but has an error-severity validation flag
        mappings = [
            {"original_label": "EBITDA", "canonical_name": "ebitda", "confidence": 0.92},
        ]
        # Pass the validation result so _find_remapping_candidates detects the flag
        validation_result = {
            "validation": {
                "flags": [
                    {"severity": "error", "item": "ebitda", "rule": "IS-3"}
                ]
            }
        }
        ctx = _make_context(mappings=mappings, validation_result=validation_result)

        captured_items = []

        def capture_create(**kwargs):
            # Extract the items_to_remap JSON from the rendered prompt
            content = kwargs["messages"][0]["content"]
            captured_items.append(content)
            return _make_claude_response([
                {
                    "original_label": "EBITDA [VALIDATION FAILED: IS-3]",
                    "canonical_name": "ebitda",
                    "confidence": 0.95,  # Higher than 0.92 → accepted
                },
            ])

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = capture_create

        with (
            patch("src.extraction.stages.enhanced_mapping.get_claude_client", return_value=mock_client),
            patch("src.extraction.stages.enhanced_mapping.format_taxonomy_detailed", return_value="t"),
            patch(
                "src.extraction.stages.enhanced_mapping.get_prompt",
                return_value=MagicMock(render=lambda **kwargs: kwargs["items_to_remap"]),
            ),
            patch("src.extraction.stages.enhanced_mapping.validate_canonical_names"),
            patch.object(stage, "_persist_entity_patterns", return_value=0),
        ):
            result = await stage.execute(ctx)

        assert len(captured_items) > 0
        assert "VALIDATION FAILED" in captured_items[0]
