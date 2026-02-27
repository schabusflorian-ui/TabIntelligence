"""
Guidelines module for DebtFund extraction system.

This module provides taxonomy management and entity pattern handling
for the guided hybrid extraction approach (Agent 4: Guidelines Manager).

Components:
    - TaxonomyManager: Canonical taxonomy operations
    - EntityPatternManager: Entity-specific pattern learning (STUB for Week 4)
    - load_taxonomy_for_stage3: Convenience function for Stage 3 mapping
    - augment_taxonomy_with_patterns: Entity-specific taxonomy augmentation (STUB)
"""

from src.guidelines.taxonomy import TaxonomyManager, load_taxonomy_for_stage3
from src.guidelines.entity_patterns import (
    EntityPattern,
    EntityPatternManager,
    augment_taxonomy_with_patterns
)

__all__ = [
    "TaxonomyManager",
    "load_taxonomy_for_stage3",
    "EntityPattern",
    "EntityPatternManager",
    "augment_taxonomy_with_patterns"
]
