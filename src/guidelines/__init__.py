"""
Guidelines module for TabIntelligence extraction system.

Provides taxonomy management for the guided hybrid extraction approach.
Entity pattern learning is handled by sync CRUD functions in src.db.crud.

Components:
    - TaxonomyManager: Canonical taxonomy operations (DB-backed)
    - load_taxonomy_for_stage3: Convenience function for Stage 3 mapping
"""

from src.guidelines.taxonomy import TaxonomyManager, load_taxonomy_for_stage3

__all__ = [
    "TaxonomyManager",
    "load_taxonomy_for_stage3",
]
