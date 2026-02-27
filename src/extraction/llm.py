"""
LLM Provider abstraction.

Provides a provider-agnostic interface for LLM calls so the extraction
pipeline can work with different models (Claude, GPT-4, Gemini, etc.).

Currently implements ClaudeProvider. To add a new provider:
1. Create a class implementing LLMProvider
2. Register it with set_provider()
"""
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LLMResponse:
    """Standardized LLM response across providers."""
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    raw_response: Any = None  # Provider-specific response object

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMProvider(ABC):
    """Abstract interface for LLM providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (e.g., 'claude', 'openai')."""
        ...

    @abstractmethod
    def complete(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """
        Send a completion request.

        Args:
            messages: List of message dicts (provider-agnostic format).
            model: Model override. If None, uses provider default.
            max_tokens: Maximum output tokens.

        Returns:
            Standardized LLMResponse.
        """
        ...

    @abstractmethod
    def complete_with_document(
        self,
        document_bytes: bytes,
        media_type: str,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """
        Send a completion request with a document attachment.

        Args:
            document_bytes: Raw document bytes.
            media_type: MIME type of the document.
            prompt: Text prompt to accompany the document.
            model: Model override.
            max_tokens: Maximum output tokens.

        Returns:
            Standardized LLMResponse.
        """
        ...


class ClaudeProvider(LLMProvider):
    """Anthropic Claude LLM provider."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(self, api_key: Optional[str] = None):
        import anthropic
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._client = anthropic.Anthropic(api_key=self._api_key)
        logger.info(f"ClaudeProvider initialized (model: {self.DEFAULT_MODEL})")

    @property
    def provider_name(self) -> str:
        return "claude"

    def complete(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a text completion request to Claude."""
        response = self._client.messages.create(
            model=model or self.DEFAULT_MODEL,
            max_tokens=max_tokens,
            messages=messages,
        )
        return LLMResponse(
            content=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=model or self.DEFAULT_MODEL,
            raw_response=response,
        )

    def complete_with_document(
        self,
        document_bytes: bytes,
        media_type: str,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """Send a document + prompt completion request to Claude."""
        import base64
        file_base64 = base64.standard_b64encode(document_bytes).decode("utf-8")

        response = self._client.messages.create(
            model=model or self.DEFAULT_MODEL,
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": file_base64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return LLMResponse(
            content=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=model or self.DEFAULT_MODEL,
            raw_response=response,
        )


# Global provider instance (singleton)
_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    """Get the current LLM provider. Defaults to ClaudeProvider."""
    global _provider
    if _provider is None:
        _provider = ClaudeProvider()
    return _provider


def set_llm_provider(provider: LLMProvider) -> None:
    """Set a custom LLM provider (useful for testing or swapping providers)."""
    global _provider
    _provider = provider
    logger.info(f"LLM provider set to: {provider.provider_name}")
