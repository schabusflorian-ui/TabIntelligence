"""
Prompt template loader with versioning.

Loads prompts from .txt files in the prompts/templates/ directory.
Supports variable substitution via str.format().

To modify a prompt, edit the corresponding .txt file - no code changes needed.
When a database is available, this can be extended to load from a prompt_templates table.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from src.core.logging import get_logger

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class PromptTemplate:
    """A versioned prompt template."""
    name: str
    version: str
    content: str
    source: str  # "file" or "database"

    def render(self, **kwargs) -> str:
        """Render the template with variable substitution."""
        try:
            return self.content.format(**kwargs)
        except KeyError as e:
            raise ValueError(
                f"Missing template variable {e} for prompt '{self.name}'. "
                f"Available keys: {list(kwargs.keys())}"
            )


# Cache loaded templates
_cache: Dict[str, PromptTemplate] = {}


def get_prompt(name: str, version: str = "v1") -> PromptTemplate:
    """
    Load a prompt template by name.

    Looks for templates at: src/extraction/prompts/templates/{name}.{version}.txt

    Args:
        name: Template name (e.g., 'parsing', 'triage', 'mapping')
        version: Template version (default 'v1')

    Returns:
        PromptTemplate with content loaded from file
    """
    cache_key = f"{name}:{version}"

    if cache_key in _cache:
        return _cache[cache_key]

    # Look for versioned file first, then unversioned
    versioned_path = TEMPLATES_DIR / f"{name}.{version}.txt"
    unversioned_path = TEMPLATES_DIR / f"{name}.txt"

    if versioned_path.exists():
        path = versioned_path
    elif unversioned_path.exists():
        path = unversioned_path
    else:
        raise FileNotFoundError(
            f"Prompt template not found: {name} (looked in {TEMPLATES_DIR}). "
            f"Expected file: {versioned_path} or {unversioned_path}"
        )

    content = path.read_text(encoding="utf-8").strip()

    template = PromptTemplate(
        name=name,
        version=version,
        content=content,
        source="file",
    )

    _cache[cache_key] = template
    logger.debug(f"Loaded prompt template: {name} ({version}) from {path.name}")

    return template


def clear_cache():
    """Clear the template cache (useful for testing or hot-reloading)."""
    _cache.clear()


def list_templates() -> list:
    """List all available template files."""
    if not TEMPLATES_DIR.exists():
        return []
    return sorted(
        f.stem for f in TEMPLATES_DIR.glob("*.txt")
    )
