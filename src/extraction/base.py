"""Base classes for extraction pipeline stages."""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from src.lineage.tracker import LineageTracker


class ExtractionStage(ABC):
    """Abstract base class for all extraction pipeline stages."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique stage name (e.g., 'parsing', 'triage', 'mapping')."""
        ...

    @property
    @abstractmethod
    def stage_number(self) -> int:
        """Stage number in pipeline order."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description."""
        return f"Stage {self.stage_number}: {self.name}"

    @property
    def timeout_seconds(self) -> Optional[float]:
        """Default maximum seconds for this stage. None means no timeout."""
        return None

    def get_timeout(self, context: "PipelineContext") -> Optional[float]:
        """Compute timeout for this execution, optionally using context.

        Override for adaptive timeouts based on file size or prior results.
        Falls back to the static timeout_seconds property.
        """
        return self.timeout_seconds

    @property
    def max_retries(self) -> int:
        """Maximum retry attempts for this stage."""
        return 2

    def should_skip(self, context: "PipelineContext") -> bool:
        """Check if this stage should be skipped. Override in subclasses."""
        return False

    def validate_output(self, result: Dict[str, Any]) -> Optional[str]:
        """Validate stage output meets minimum requirements.

        Returns None if valid, or an error message string if the output
        is too degraded for downstream stages to use meaningfully.
        Override in subclasses for stage-specific checks.
        """
        return None

    @abstractmethod
    async def execute(self, context: "PipelineContext") -> Dict[str, Any]:
        """
        Execute this stage.

        Args:
            context: Pipeline context with input data and results from prior stages.

        Returns:
            Dict with stage results. Must include 'tokens' key for cost tracking.
            May include 'lineage_metadata' dict for extra lineage info.
        """
        ...


class PipelineContext:
    """Shared context passed through the extraction pipeline."""

    def __init__(
        self,
        file_bytes: bytes,
        file_id: str,
        job_id: str,
        entity_id: Optional[str] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ):
        self.file_bytes = file_bytes
        self.file_id = file_id
        self.job_id = job_id
        self.entity_id = entity_id
        self.progress_callback = progress_callback
        self.tracker = LineageTracker(job_id=job_id)
        self.results: Dict[str, Dict[str, Any]] = {}
        self.total_tokens = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self._result_cache: Dict[str, Dict[str, Any]] = {}
        self.completed_stages: List[str] = []
        self.taxonomy_version: Optional[str] = None
        self.taxonomy_checksum: Optional[str] = None

    def get_result(self, stage_name: str) -> Dict[str, Any]:
        """Get result from a previous stage."""
        if stage_name not in self.results:
            raise KeyError(
                f"No result for stage '{stage_name}'. Available: {list(self.results.keys())}"
            )
        return self.results[stage_name]

    def set_result(self, stage_name: str, result: Dict[str, Any]):
        """Store result from a stage."""
        self.results[stage_name] = result
        self.total_tokens += result.get("tokens", 0)
        self.total_input_tokens += result.get("input_tokens", 0)
        self.total_output_tokens += result.get("output_tokens", 0)

    def cache_result(self, stage_name: str, result: Dict[str, Any]):
        """Cache a stage result for retry/resume scenarios."""
        self._result_cache[stage_name] = result

    def get_cached_result(self, stage_name: str) -> Optional[Dict[str, Any]]:
        """Get a cached result, or None if not cached."""
        return self._result_cache.get(stage_name)

    def preload_results(self, partial_result: Dict[str, Any], stage_names: List[str]):
        """Load checkpoint data from job.result into cache and results.

        Unlike set_result(), this does NOT accumulate tokens into the totals,
        because the preloaded stages were already billed in the original run.
        """
        stage_results = partial_result.get("_stage_results", {})
        for stage_name in stage_names:
            if stage_name in stage_results:
                result = stage_results[stage_name]
                self._result_cache[stage_name] = result
                # Store result for downstream stages to read, but skip
                # token accumulation — those tokens were already counted.
                self.results[stage_name] = result
                self.completed_stages.append(stage_name)
