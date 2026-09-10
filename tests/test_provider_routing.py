"""Tests for dynamic LLM provider routing via OpenAIChatCompletionClient."""

import pytest
from types import SimpleNamespace
from unittest.mock import patch
from agent_framework.openai import OpenAIChatCompletionClient
from prompt_config import AgentProfile


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

    @patch.dict(
        "os.environ",
        {
            "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.us/",
            "AZURE_OPENAI_MODEL": "gpt-4o",
            "AZURE_OPENAI_API_VERSION": "2024-02-15-preview",
        },
        clear=True,
    )
    def test_azure_openai_managed_identity_instantiation(self) -> None:
        """With no API key, the Azure client authenticates via an Entra token provider."""
        import agent_factory

        client = agent_factory.build_chat_client()
        assert client.client._azure_ad_token_provider is not None

    def test_azure_openai_token_scope_matches_cloud(self) -> None:
        """Azure Government endpoints need the .us cognitive services audience."""
        import agent_factory

        assert agent_factory._openai_token_scope("https://x.openai.azure.us/") == (
            "https://cognitiveservices.azure.us/.default"
        )
        assert agent_factory._openai_token_scope("https://x.openai.azure.com/") == (
            "https://cognitiveservices.azure.com/.default"
        )


def test_create_chat_runtime_binds_profile_tools_and_creates_session(monkeypatch) -> None:
    """Runtime creation should preserve profile tool filtering and agent session creation."""
    import agent_factory

    calls: dict[str, object] = {}

    class FakeAgent:
        context_providers: list[object] = []

        def create_session(self):
            return {"session": "created"}

    class FakeClient:
        def as_agent(self, **kwargs):
            calls["as_agent"] = kwargs
            return FakeAgent()

    allowed_tool = SimpleNamespace(name="allowed_tool")
    denied_tool = SimpleNamespace(name="denied_tool")

    monkeypatch.setattr(agent_factory, "_build_openai_clients", lambda: (FakeClient(), FakeClient()))
    monkeypatch.setattr(agent_factory, "load_agent_profile", lambda chat_profile=None: AgentProfile(
        name="Profile Name",
        description="Profile description",
        system_prompt="System prompt",
        tool_names=["allowed_tool"],
        logical_profile="profile-key",
        temperature=0.4,
    ))

    runtime = agent_factory.create_chat_runtime(
        chat_profile="Profile Name",
        function_tools=[allowed_tool, denied_tool],
    )

    assert runtime.session == {"session": "created"}
    assert runtime.tools == [allowed_tool]
    assert runtime.prompt_logical_profile == "profile-key"
    agent_kwargs = calls["as_agent"]
    assert agent_kwargs["name"] == "Profile_Name"
    assert agent_kwargs["instructions"] == "System prompt"
    assert agent_kwargs["description"] == "Profile description"
    assert agent_kwargs["tools"] == [allowed_tool]
    assert agent_kwargs["default_options"] == {"temperature": 0.4}
