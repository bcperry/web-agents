"""Owner-aware selected-skill loading contracts."""

import asyncio
from unittest.mock import Mock

import pytest

import agent_factory
import user_data
from agent_factory import CosmosSkillsSource


@pytest.mark.parametrize("temperature", [None, 0.0, 0.2, 1.0])
@pytest.mark.parametrize("model, supports_temperature", [
    ("gpt-5.6", False),
    ("gpt-5.6-luna", False),
    ("gpt-5.6-2026-07-09", False),
    ("gpt-4o", True),
    ("gpt-5.60", True),
])
def test_temperature_options_respect_model_support(model, supports_temperature, temperature):
    client = Mock(model=model)
    expected = {"temperature": temperature} if supports_temperature and temperature is not None else {}
    assert agent_factory._temperature_options(client, temperature) == expected


def test_chat_client_preserves_explicit_credential(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.us")
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    provider = Mock()
    client = Mock()
    credential = object()
    monkeypatch.setattr(agent_factory, "_azure_token_provider", provider)
    monkeypatch.setattr(agent_factory, "OpenAIChatClient", client)

    agent_factory.build_chat_client(credential=credential)

    provider.assert_not_called()
    client.assert_called_once_with(credential=credential)


def test_cosmos_skills_source_loads_global_plus_bound_owner_only():
    repo = user_data.get_user_skills_repository()
    asyncio.run(repo.create("user-a", "owner-a-skill", {
        "id": "owner-a-skill",
        "name": "owner-a-skill",
        "description": "Owner A",
        "content": "Private A instructions",
    }))

    owner_names = {
        skill.frontmatter.name for skill in asyncio.run(CosmosSkillsSource("user-a").get_skills())
    }
    other_names = {
        skill.frontmatter.name for skill in asyncio.run(CosmosSkillsSource("user-b").get_skills())
    }

    assert "owner-a-skill" in owner_names
    assert "owner-a-skill" not in other_names


def test_azure_client_uses_entra_despite_stale_keys(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.us")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "stale-key")
    token_provider = object()
    monkeypatch.setattr(agent_factory, "_azure_token_provider", lambda endpoint: token_provider)
    client = Mock()
    monkeypatch.setattr(agent_factory, "OpenAIChatClient", client)
    agent_factory.build_chat_client(api_key="stale-explicit-key")
    client.assert_called_once_with(credential=token_provider)


def test_search_uses_government_token_scope_despite_stale_key(monkeypatch):
    import mcp_servers

    monkeypatch.setenv("SEARCH_API_KEY", "stale-key")
    credential = Mock()
    monkeypatch.setattr(mcp_servers, "DefaultAzureCredential", Mock(return_value=credential))
    provider = mcp_servers.SearchTokenCredential("https://example.search.azure.us")
    provider.get_token("https://search.azure.com/.default")
    credential.get_token.assert_called_once_with("https://search.azure.us/.default")