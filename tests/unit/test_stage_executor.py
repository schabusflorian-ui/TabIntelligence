"""Tests for StageExecutor and ResilientProgressCallback."""
import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.exceptions import ClaudeAPIError, ExtractionError, RateLimitError
from src.extraction.base import ExtractionStage, PipelineContext
from src.extraction.stage_executor import ResilientProgressCallback, StageExecutor


# ---------------------------------------------------------------------------
# Helpers: concrete stage subclass for testing
# ---------------------------------------------------------------------------

class FakeStage(ExtractionStage):
    """Minimal concrete stage for testing."""

    def __init__(
        self,
        name="fake",
        stage_number=1,
        timeout_seconds=None,
        max_retries=2,
        should_skip_val=False,
    ):
        self._name = name
        self._stage_number = stage_number
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._should_skip_val = should_skip_val

    @property
    def name(self):
        return self._name

    @property
    def stage_number(self):
        return self._stage_number

    @property
    def timeout_seconds(self):
        return self._timeout_seconds

    @property
    def max_retries(self):
        return self._max_retries

    def should_skip(self, context):
        return self._should_skip_val

    async def execute(self, context):
        return {"tokens": 100, "input_tokens": 60, "output_tokens": 40}


def _make_context():
    """Create a minimal PipelineContext for testing."""
    return PipelineContext(
        file_bytes=b"fake",
        file_id="test-file",
        job_id="test-job",
    )


# ===========================================================================
# StageExecutor tests
# ===========================================================================


class TestStageExecutor:
    """Tests for the StageExecutor class."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Stage executes and caches result on success."""
        stage = FakeStage()
        ctx = _make_context()
        executor = StageExecutor()

        result = await executor.execute(stage, ctx)

        assert result["tokens"] == 100
        assert ctx.get_cached_result("fake") == result

    @pytest.mark.asyncio
    async def test_returns_cached_result(self):
        """Should return cached result without calling execute."""
        stage = FakeStage()
        ctx = _make_context()
        cached = {"tokens": 0, "cached": True}
        ctx.cache_result("fake", cached)

        executor = StageExecutor()
        result = await executor.execute(stage, ctx)

        assert result is cached

    @pytest.mark.asyncio
    async def test_retries_on_extraction_error(self):
        """Should retry on ExtractionError and succeed on later attempt."""
        call_count = 0

        class RetryStage(FakeStage):
            async def execute(self, context):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ExtractionError("transient", stage="fake")
                return {"tokens": 0}

        stage = RetryStage(max_retries=3)
        ctx = _make_context()
        executor = StageExecutor()

        result = await executor.execute(stage, ctx)

        assert call_count == 3
        assert result["tokens"] == 0

    @pytest.mark.asyncio
    async def test_retries_on_claude_api_error(self):
        """Should retry on ClaudeAPIError."""
        call_count = 0

        class RetryStage(FakeStage):
            async def execute(self, context):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise ClaudeAPIError("api fail", stage="fake")
                return {"tokens": 0}

        stage = RetryStage(max_retries=2)
        ctx = _make_context()
        executor = StageExecutor()

        result = await executor.execute(stage, ctx)

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_error(self):
        """Should retry on RateLimitError."""
        call_count = 0

        class RetryStage(FakeStage):
            async def execute(self, context):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise RateLimitError("rate limit", stage="fake")
                return {"tokens": 0}

        stage = RetryStage(max_retries=2)
        ctx = _make_context()
        executor = StageExecutor()

        result = await executor.execute(stage, ctx)

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_code_bug(self):
        """Non-retryable errors (TypeError, etc.) should propagate immediately."""
        call_count = 0

        class BuggyStage(FakeStage):
            async def execute(self, context):
                nonlocal call_count
                call_count += 1
                raise TypeError("code bug")

        stage = BuggyStage(max_retries=3)
        ctx = _make_context()
        executor = StageExecutor()

        with pytest.raises(TypeError, match="code bug"):
            await executor.execute(stage, ctx)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        """Should raise after exhausting all retries."""

        class AlwaysFailStage(FakeStage):
            async def execute(self, context):
                raise ExtractionError("permanent", stage="fake")

        stage = AlwaysFailStage(max_retries=2)
        ctx = _make_context()
        executor = StageExecutor()

        with pytest.raises(ExtractionError, match="permanent"):
            await executor.execute(stage, ctx)

    @pytest.mark.asyncio
    async def test_timeout_triggers_retry(self):
        """Should retry when stage times out."""
        call_count = 0

        class SlowStage(FakeStage):
            async def execute(self, context):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    await asyncio.sleep(10)  # will be cancelled by timeout
                return {"tokens": 0}

        stage = SlowStage(timeout_seconds=0.05, max_retries=2)
        ctx = _make_context()
        executor = StageExecutor()

        result = await executor.execute(stage, ctx)

        assert call_count == 2
        assert result["tokens"] == 0

    @pytest.mark.asyncio
    async def test_timeout_raises_extraction_error_after_retries(self):
        """Should raise ExtractionError after all timeout retries exhausted."""

        class AlwaysSlowStage(FakeStage):
            async def execute(self, context):
                await asyncio.sleep(10)

        stage = AlwaysSlowStage(timeout_seconds=0.05, max_retries=2)
        ctx = _make_context()
        executor = StageExecutor()

        with pytest.raises(ExtractionError, match="timed out"):
            await executor.execute(stage, ctx)

    @pytest.mark.asyncio
    async def test_no_timeout_when_none(self):
        """Should not apply timeout when timeout_seconds is None."""
        stage = FakeStage(timeout_seconds=None)
        ctx = _make_context()
        executor = StageExecutor()

        result = await executor.execute(stage, ctx)

        assert result["tokens"] == 100

    @pytest.mark.asyncio
    async def test_skips_when_should_skip_true(self):
        """Should return skip result when should_skip returns True."""
        stage = FakeStage(should_skip_val=True)
        ctx = _make_context()
        executor = StageExecutor()

        result = await executor.execute(stage, ctx)

        assert result["skipped"] is True
        assert result["tokens"] == 0

    @pytest.mark.asyncio
    async def test_should_skip_exception_defaults_to_no_skip(self):
        """If should_skip raises, stage should still execute normally."""

        class BadSkipStage(FakeStage):
            def should_skip(self, context):
                raise RuntimeError("skip check failed")

        stage = BadSkipStage()
        ctx = _make_context()
        executor = StageExecutor()

        result = await executor.execute(stage, ctx)

        assert result["tokens"] == 100


# ===========================================================================
# ResilientProgressCallback tests
# ===========================================================================


class TestResilientProgressCallback:
    """Tests for the ResilientProgressCallback wrapper."""

    def test_calls_callback_on_success(self):
        """Should call the wrapped callback directly."""
        inner = MagicMock()
        cb = ResilientProgressCallback(inner)

        cb("parsing", 20)

        inner.assert_called_once_with("parsing", 20)

    def test_noop_when_no_callback(self):
        """Should not raise when callback is None."""
        cb = ResilientProgressCallback(None)
        cb("parsing", 20)  # Should not raise

    def test_queues_on_failure(self):
        """Failed update should be queued for later retry."""
        inner = MagicMock(side_effect=RuntimeError("db down"))
        cb = ResilientProgressCallback(inner)

        cb("parsing", 20)

        assert len(cb._queue) == 1
        assert cb._queue[0] == ("parsing", 20)

    def test_flushes_queue_on_next_success(self):
        """Queued updates should be flushed when connection recovers."""
        call_count = 0

        def flaky_callback(stage, progress):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("db down")
            # Success on subsequent calls

        cb = ResilientProgressCallback(flaky_callback)

        # First call fails → queued
        cb("parsing", 20)
        assert len(cb._queue) == 1

        # Second call succeeds → should flush queue first
        cb("triage", 30)
        assert len(cb._queue) == 0

    def test_stops_flushing_after_max_failures(self):
        """Should stop flushing queue after max consecutive failures."""
        inner = MagicMock(side_effect=RuntimeError("db down"))
        cb = ResilientProgressCallback(inner, max_consecutive_failures=2)

        cb("parsing", 20)
        cb("triage", 30)

        # After 2 consecutive failures, queue should still have items
        # but no more flush attempts
        assert cb._consecutive_failures == 2

        # Third call — should NOT try to flush (failures >= max)
        cb("mapping", 55)
        assert cb._consecutive_failures == 3
        assert len(cb._queue) == 3

    def test_tracks_heartbeat(self):
        """Should update last_heartbeat after successful call."""
        inner = MagicMock()
        cb = ResilientProgressCallback(inner)

        assert cb.last_heartbeat is None

        cb("parsing", 20)

        assert cb.last_heartbeat is not None

    def test_no_heartbeat_on_failure(self):
        """Should not update last_heartbeat on failure."""
        inner = MagicMock(side_effect=RuntimeError("fail"))
        cb = ResilientProgressCallback(inner)

        cb("parsing", 20)

        assert cb.last_heartbeat is None

    def test_queue_bounded_by_max_size(self):
        """Queue should not grow beyond max_queue_size."""
        inner = MagicMock(side_effect=RuntimeError("fail"))
        cb = ResilientProgressCallback(inner, max_queue_size=3)

        for i in range(5):
            cb(f"stage_{i}", i * 10)

        assert len(cb._queue) == 3


# ===========================================================================
# PipelineContext preload_results tests
# ===========================================================================


class TestPreloadResults:
    """Tests for PipelineContext.preload_results token handling."""

    def test_preload_does_not_accumulate_tokens(self):
        """Preloaded checkpoint results must NOT inflate token totals."""
        ctx = _make_context()
        assert ctx.total_tokens == 0

        partial = {
            "_stage_results": {
                "parsing": {"tokens": 500, "input_tokens": 300, "output_tokens": 200},
                "triage": {"tokens": 100, "input_tokens": 60, "output_tokens": 40},
            }
        }
        ctx.preload_results(partial, ["parsing", "triage"])

        # Token totals should remain zero — preloaded stages were already billed
        assert ctx.total_tokens == 0
        assert ctx.total_input_tokens == 0
        assert ctx.total_output_tokens == 0

    def test_preload_makes_results_available(self):
        """Preloaded results should be accessible via get_result."""
        ctx = _make_context()
        partial = {
            "_stage_results": {
                "parsing": {"tokens": 500, "data": "parsed"},
            }
        }
        ctx.preload_results(partial, ["parsing"])

        result = ctx.get_result("parsing")
        assert result["data"] == "parsed"

    def test_preload_populates_cache_and_completed(self):
        """Preloaded stages should be in cache and completed_stages."""
        ctx = _make_context()
        partial = {
            "_stage_results": {
                "parsing": {"tokens": 500},
                "triage": {"tokens": 100},
            }
        }
        ctx.preload_results(partial, ["parsing", "triage"])

        assert ctx.get_cached_result("parsing") is not None
        assert ctx.get_cached_result("triage") is not None
        assert "parsing" in ctx.completed_stages
        assert "triage" in ctx.completed_stages

    def test_preload_then_new_stage_only_counts_new_tokens(self):
        """After preload, only newly executed stages should add to token total."""
        ctx = _make_context()
        partial = {
            "_stage_results": {
                "parsing": {"tokens": 500, "input_tokens": 300, "output_tokens": 200},
            }
        }
        ctx.preload_results(partial, ["parsing"])

        # Simulate a new stage completing
        ctx.set_result("triage", {"tokens": 100, "input_tokens": 60, "output_tokens": 40})

        assert ctx.total_tokens == 100
        assert ctx.total_input_tokens == 60
        assert ctx.total_output_tokens == 40

    def test_preload_skips_missing_stages(self):
        """If a stage name isn't in partial result, it's silently skipped."""
        ctx = _make_context()
        partial = {"_stage_results": {"parsing": {"tokens": 500}}}
        ctx.preload_results(partial, ["parsing", "triage", "mapping"])

        assert "parsing" in ctx.completed_stages
        assert "triage" not in ctx.completed_stages
        assert "mapping" not in ctx.completed_stages


# ===========================================================================
# Jitter backoff tests
# ===========================================================================


class TestBackoffJitter:
    """Tests that retry backoff includes randomized jitter."""

    @pytest.mark.asyncio
    async def test_retry_backoff_includes_jitter(self):
        """Backoff sleep should include random jitter component."""
        call_count = 0

        class RetryStage(FakeStage):
            async def execute(self, context):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise ExtractionError("transient", stage="fake")
                return {"tokens": 0}

        stage = RetryStage(max_retries=2)
        ctx = _make_context()
        executor = StageExecutor()

        sleep_args = []
        original_sleep = asyncio.sleep

        async def mock_sleep(seconds):
            sleep_args.append(seconds)
            # Don't actually sleep

        with patch("src.extraction.stage_executor.asyncio.sleep", mock_sleep), \
             patch("src.extraction.stage_executor.random.uniform", return_value=0.42):
            result = await executor.execute(stage, ctx)

        assert call_count == 2
        # Backoff = 2^(1-1) + 0.42 = 1.42
        assert len(sleep_args) == 1
        assert abs(sleep_args[0] - 1.42) < 0.01

    @pytest.mark.asyncio
    async def test_timeout_retry_backoff_includes_jitter(self):
        """Timeout retry backoff should also include jitter."""
        stage = FakeStage(timeout_seconds=5.0, max_retries=2)
        ctx = _make_context()
        executor = StageExecutor()

        sleep_args = []
        original_wait_for = asyncio.wait_for
        wait_for_call = 0

        async def mock_sleep(seconds):
            sleep_args.append(seconds)

        async def mock_wait_for(coro, *, timeout):
            nonlocal wait_for_call
            wait_for_call += 1
            if wait_for_call == 1:
                coro.close()
                raise asyncio.TimeoutError()
            return await original_wait_for(coro, timeout=timeout)

        with patch("src.extraction.stage_executor.asyncio.wait_for", mock_wait_for), \
             patch("src.extraction.stage_executor.asyncio.sleep", mock_sleep), \
             patch("src.extraction.stage_executor.random.uniform", return_value=0.77):
            result = await executor.execute(stage, ctx)

        assert result["tokens"] == 100
        # Backoff = 2^(1-1) + 0.77 = 1.77
        assert len(sleep_args) == 1
        assert abs(sleep_args[0] - 1.77) < 0.01


# ===========================================================================
# Output validation tests
# ===========================================================================


class TestOutputValidation:
    """Tests for stage output validation in StageExecutor."""

    @pytest.mark.asyncio
    async def test_valid_output_passes(self):
        """Stage with passing validate_output should succeed normally."""
        class ValidStage(FakeStage):
            def validate_output(self, result):
                return None  # Valid

        stage = ValidStage()
        ctx = _make_context()
        executor = StageExecutor()
        result = await executor.execute(stage, ctx)
        assert result["tokens"] == 100

    @pytest.mark.asyncio
    async def test_invalid_output_triggers_retry(self):
        """Stage with failing validate_output should retry."""
        call_count = 0

        class BadThenGoodStage(FakeStage):
            async def execute(self, context):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    return {"tokens": 0, "parsed": {}}  # empty = invalid
                return {"tokens": 100, "parsed": {"sheets": [{"rows": [1]}]}}

            def validate_output(self, result):
                sheets = result.get("parsed", {}).get("sheets", [])
                if not sheets:
                    return "No sheets"
                return None

        stage = BadThenGoodStage(max_retries=3)
        ctx = _make_context()
        executor = StageExecutor()
        result = await executor.execute(stage, ctx)

        assert call_count == 2
        assert result["parsed"]["sheets"]

    @pytest.mark.asyncio
    async def test_invalid_output_exhausts_retries(self):
        """Always-invalid output should exhaust retries and raise."""

        class AlwaysBadStage(FakeStage):
            async def execute(self, context):
                return {"tokens": 0, "empty": True}

            def validate_output(self, result):
                return "Output is empty"

        stage = AlwaysBadStage(max_retries=2)
        ctx = _make_context()
        executor = StageExecutor()

        with pytest.raises(ExtractionError, match="output validation failed"):
            await executor.execute(stage, ctx)


# ===========================================================================
# Adaptive timeout tests
# ===========================================================================


class TestAdaptiveTimeout:
    """Tests for get_timeout context-aware timeouts."""

    @pytest.mark.asyncio
    async def test_get_timeout_used_over_property(self):
        """StageExecutor should use get_timeout(context) not timeout_seconds."""

        class AdaptiveStage(FakeStage):
            @property
            def timeout_seconds(self):
                return 10.0

            def get_timeout(self, context):
                return 999.0  # Very different from property

        stage = AdaptiveStage()
        ctx = _make_context()
        executor = StageExecutor()

        # Track what timeout is passed to wait_for
        timeouts_seen = []
        original_wait_for = asyncio.wait_for

        async def spy_wait_for(coro, *, timeout):
            timeouts_seen.append(timeout)
            return await original_wait_for(coro, timeout=timeout)

        with patch("src.extraction.stage_executor.asyncio.wait_for", spy_wait_for):
            await executor.execute(stage, ctx)

        assert timeouts_seen == [999.0]

    def test_base_get_timeout_falls_back_to_property(self):
        """Base class get_timeout should return timeout_seconds."""
        stage = FakeStage(timeout_seconds=42.0)
        ctx = _make_context()
        assert stage.get_timeout(ctx) == 42.0


# ===========================================================================
# Rate limit retry-after tests
# ===========================================================================


class TestRetryAfterBackoff:
    """Tests for server-provided retry-after in rate limit handling."""

    @pytest.mark.asyncio
    async def test_rate_limit_with_retry_after_uses_server_delay(self):
        """When RateLimitError has retry_after, use it instead of exponential backoff."""
        call_count = 0

        class RateLimitStage(FakeStage):
            async def execute(self, context):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise RateLimitError(
                        "Rate limit", stage="fake", retry_after=30
                    )
                return {"tokens": 0}

        stage = RateLimitStage(max_retries=2)
        ctx = _make_context()
        executor = StageExecutor()

        sleep_args = []

        async def mock_sleep(seconds):
            sleep_args.append(seconds)

        with patch("src.extraction.stage_executor.asyncio.sleep", mock_sleep), \
             patch("src.extraction.stage_executor.random.uniform", return_value=0.5):
            await executor.execute(stage, ctx)

        # Should use retry_after (30) + jitter (0.5) = 30.5
        assert len(sleep_args) == 1
        assert abs(sleep_args[0] - 30.5) < 0.01

    @pytest.mark.asyncio
    async def test_rate_limit_without_retry_after_uses_exponential(self):
        """When RateLimitError has no retry_after, fall back to exponential backoff."""
        call_count = 0

        class RateLimitStage(FakeStage):
            async def execute(self, context):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise RateLimitError("Rate limit", stage="fake")
                return {"tokens": 0}

        stage = RateLimitStage(max_retries=2)
        ctx = _make_context()
        executor = StageExecutor()

        sleep_args = []

        async def mock_sleep(seconds):
            sleep_args.append(seconds)

        with patch("src.extraction.stage_executor.asyncio.sleep", mock_sleep), \
             patch("src.extraction.stage_executor.random.uniform", return_value=0.42):
            await executor.execute(stage, ctx)

        # Should use 2^0 + 0.42 = 1.42 (exponential backoff)
        assert len(sleep_args) == 1
        assert abs(sleep_args[0] - 1.42) < 0.01
