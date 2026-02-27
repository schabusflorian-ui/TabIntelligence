"""
Claude API client management.

Backward-compatible wrapper. New code should use
src.extraction.llm.get_llm_provider() for the provider-agnostic interface.
"""
import os

import anthropic

# Module-level client cache (singleton)
_client = None


def get_claude_client() -> anthropic.Anthropic:
    """Get or create the Anthropic Claude client (lazy initialization)."""
    global _client
    if _client is None:
        base_url = os.getenv("ANTHROPIC_BASE_URL")
        _client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            base_url=base_url if base_url else None,
        )
    return _client
