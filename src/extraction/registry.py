"""Stage registry for managing extraction pipeline stages."""

from typing import Dict, List, Optional

from src.core.logging import get_logger
from src.extraction.base import ExtractionStage

logger = get_logger(__name__)


class StageRegistry:
    """Central registry for extraction stages."""

    def __init__(self):
        self._stages: Dict[str, ExtractionStage] = {}

    def register(self, stage: ExtractionStage) -> None:
        """Register an extraction stage."""
        if stage.name in self._stages:
            logger.warning(f"Overwriting existing stage: {stage.name}")
        self._stages[stage.name] = stage
        logger.info(f"Registered stage: {stage.description}")

    def get(self, name: str) -> ExtractionStage:
        """Get a stage by name."""
        if name not in self._stages:
            raise KeyError(f"Stage '{name}' not registered. Available: {list(self._stages.keys())}")
        return self._stages[name]

    def get_pipeline(self, stage_names: Optional[List[str]] = None) -> List[ExtractionStage]:
        """
        Get ordered list of stages for pipeline execution.

        Args:
            stage_names: Optional explicit ordering. If None, returns all
                         stages sorted by stage_number.
        """
        if stage_names:
            return [self.get(name) for name in stage_names]
        return sorted(self._stages.values(), key=lambda s: s.stage_number)

    @property
    def registered_stages(self) -> List[str]:
        """List of registered stage names."""
        return list(self._stages.keys())


# Global registry instance
registry = StageRegistry()
