"""Owner-aware selected-skill loading contracts."""

import asyncio
from unittest.mock import Mock

import agent_factory
import user_data
from agent_factory import CosmosSkillsSource


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