"""
Tests for Claude client lazy initialization.
"""
import pytest
from unittest.mock import patch, MagicMock
import src.extraction.claude_client as client_module


class TestGetClaudeClient:
    """Test lazy initialization of Claude API client."""

    def setup_method(self):
        """Reset singleton before each test."""
        client_module._client = None

    def teardown_method(self):
        """Reset singleton after each test."""
        client_module._client = None

    def test_creates_client_on_first_call(self):
        """Test client is created on first call."""
        mock_client = MagicMock()

        with patch("src.extraction.claude_client.anthropic") as mock_anthropic, \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test123"}):
            mock_anthropic.Anthropic.return_value = mock_client

            result = client_module.get_claude_client()

        assert result is mock_client
        mock_anthropic.Anthropic.assert_called_once()

    def test_returns_cached_client_on_subsequent_calls(self):
        """Test singleton: second call returns cached client."""
        mock_client = MagicMock()

        with patch("src.extraction.claude_client.anthropic") as mock_anthropic, \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test123"}):
            mock_anthropic.Anthropic.return_value = mock_client

            first = client_module.get_claude_client()
            second = client_module.get_claude_client()

        assert first is second
        # Should only create once
        mock_anthropic.Anthropic.assert_called_once()

    def test_passes_base_url_when_set(self):
        """Test ANTHROPIC_BASE_URL is passed when environment variable is set."""
        with patch("src.extraction.claude_client.anthropic") as mock_anthropic, \
             patch.dict("os.environ", {
                 "ANTHROPIC_API_KEY": "sk-ant-test123",
                 "ANTHROPIC_BASE_URL": "http://localhost:8080",
             }):
            mock_anthropic.Anthropic.return_value = MagicMock()

            client_module.get_claude_client()

        call_kwargs = mock_anthropic.Anthropic.call_args[1]
        assert call_kwargs["api_key"] == "sk-ant-test123"
        assert call_kwargs["base_url"] == "http://localhost:8080"

    def test_no_base_url_when_not_set(self):
        """Test base_url is omitted when ANTHROPIC_BASE_URL is not set."""
        with patch("src.extraction.claude_client.anthropic") as mock_anthropic, \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
            # Ensure ANTHROPIC_BASE_URL is not set
            import os
            os.environ.pop("ANTHROPIC_BASE_URL", None)

            mock_anthropic.Anthropic.return_value = MagicMock()
            client_module.get_claude_client()

        call_kwargs = mock_anthropic.Anthropic.call_args[1]
        assert call_kwargs.get("base_url") is None
