"""Stage execution engine with retry, timeout, caching, and skip logic."""

import asyncio
import random
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional, Tuple

from src.api.metrics import extraction_stage_timeouts_total
from src.core.exceptions import ClaudeAPIError, ExtractionError, RateLimitError
from src.core.logging import extraction_logger as logger
from src.extraction.base import ExtractionStage, PipelineContext


class StageExecutor:
    """Executes a pipeline stage with retry, timeout, caching, and skip support."""

    async def execute(
        self,
        stage: ExtractionStage,
        context: PipelineContext,
    ) -> Dict[str, Any]:
        """
        Execute a stage with retry, timeout, caching, and skip support.

        Returns the stage result dict. If skipped, returns a synthetic result
        with ``skipped=True``.
        """
        # 1. Check cache (for resume scenarios)
        cached = context.get_cached_result(stage.name)
        if cached is not None:
            logger.info(f"Using cached result for {stage.name}")
            return cached

        # 2. Check skip condition
        try:
            if stage.should_skip(context):
                logger.info(f"Skipping {stage.description} (should_skip=True)")
                return {
                    "skipped": True,
                    "tokens": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "lineage_metadata": {"skipped": True},
                }
        except Exception as skip_err:
            logger.warning(f"should_skip() raised for {stage.name}, proceeding: {skip_err}")

        # 3. Execute with retry
        max_retries = stage.max_retries
        timeout = stage.get_timeout(context)
        last_exception: Optional[Exception] = None

        for attempt in range(1, max_retries + 1):
            try:
                if timeout:
                    result = await asyncio.wait_for(
                        stage.execute(context),
                        timeout=timeout,
                    )
                else:
                    result = await stage.execute(context)

                # Validate output before accepting
                validation_error = stage.validate_output(result)
                if validation_error:
                    raise ExtractionError(
                        f"{stage.name} output validation failed: {validation_error}",
                        stage=stage.name,
                    )

                # Cache on success
                context.cache_result(stage.name, result)
                return result

            except asyncio.TimeoutError:
                extraction_stage_timeouts_total.labels(stage=stage.name).inc()
                last_exception = ExtractionError(
                    f"Stage {stage.name} timed out after {timeout}s",
                    stage=stage.name,
                )
                logger.warning(f"{stage.description} timed out (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    backoff = 2 ** (attempt - 1) + random.uniform(0, 1)
                    await asyncio.sleep(backoff)

            except (RateLimitError, ClaudeAPIError, ExtractionError) as e:
                last_exception = e
                if attempt < max_retries:
                    # Prefer server-provided retry-after for rate limits
                    server_delay = (
                        e.details.get("retry_after") if isinstance(e, RateLimitError) else None
                    )
                    backoff = (
                        float(server_delay) + random.uniform(0, 1)
                        if server_delay
                        else 2 ** (attempt - 1) + random.uniform(0, 1)
                    )
                    logger.warning(
                        f"{stage.description} failed "
                        f"(attempt {attempt}/{max_retries}), "
                        f"retrying in {backoff:.1f}s: {e}"
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"{stage.description} failed after {max_retries} attempts: {e}")

        raise last_exception  # type: ignore[misc]


class ResilientProgressCallback:
    """Wraps a progress callback with retry queuing and heartbeat tracking."""

    def __init__(
        self,
        callback: Optional[Callable[[str, int], None]],
        max_queue_size: int = 10,
        max_consecutive_failures: int = 3,
    ):
        self._callback = callback
        self._queue: Deque[Tuple[str, int]] = deque(maxlen=max_queue_size)
        self._consecutive_failures = 0
        self._max_consecutive_failures = max_consecutive_failures
        self.last_heartbeat: Optional[float] = None

    def __call__(self, stage_name: str, progress_percent: int):
        if self._callback is None:
            return

        # Flush queue first if connection seems healthy
        if self._queue and self._consecutive_failures < self._max_consecutive_failures:
            self._flush_queue()

        # Send current update
        try:
            self._callback(stage_name, progress_percent)
            self._consecutive_failures = 0
            self.last_heartbeat = time.time()
        except Exception as e:
            self._consecutive_failures += 1
            self._queue.append((stage_name, progress_percent))
            logger.warning(f"Progress callback failed ({self._consecutive_failures}x): {e}")

    def _flush_queue(self):
        """Try to send queued updates."""
        while self._queue:
            stage_name, progress = self._queue[0]
            try:
                self._callback(stage_name, progress)  # type: ignore[misc]
                self._queue.popleft()
                self._consecutive_failures = 0
                self.last_heartbeat = time.time()
            except Exception:
                break
