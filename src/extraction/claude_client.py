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
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client
