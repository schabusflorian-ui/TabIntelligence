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

    def get_result(self, stage_name: str) -> Dict[str, Any]:
        """Get result from a previous stage."""
        if stage_name not in self.results:
            raise KeyError(
                f"No result for stage '{stage_name}'. "
                f"Available: {list(self.results.keys())}"
            )
        return self.results[stage_name]

    def set_result(self, stage_name: str, result: Dict[str, Any]):
        """Store result from a stage."""
        self.results[stage_name] = result
        self.total_tokens += result.get("tokens", 0)
