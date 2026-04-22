"""Tests for dynamic LLM provider routing via OpenAIChatCompletionClient."""

import pytest
from unittest.mock import patch
from agent_framework.openai import OpenAIChatCompletionClient


class TestProviderRouting:
    """Verify OpenAIChatCompletionClient instantiates correctly for each provider path."""

    @patch.dict(
        "os.environ",
        {
            "OPENAI_API_KEY": "ollama",
            "OPENAI_BASE_URL": "http://localhost:11434/v1",
            "OPENAI_MODEL": "llama3",
        },
        clear=True,
    )
    def test_openai_compatible_provider_instantiation(self) -> None:
        """Client instantiates with only OPENAI_* env vars (Ollama / OpenAI-compatible)."""
        client = OpenAIChatCompletionClient()
        assert client is not None

    @patch.dict(
        "os.environ",
        {
            "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.us/",
            "AZURE_OPENAI_MODEL": "gpt-4o",
            "AZURE_OPENAI_API_KEY": "test-key",
            "AZURE_OPENAI_API_VERSION": "2024-02-15-preview",
        },
        clear=True,
    )
    def test_azure_openai_provider_instantiation(self) -> None:
        """Client instantiates with only AZURE_OPENAI_* env vars."""
        client = OpenAIChatCompletionClient()
        assert client is not None
