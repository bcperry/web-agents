"""Owner-aware selected-skill loading contracts."""

import asyncio
from unittest.mock import Mock

import pytest

import agent_factory
import user_data
from agent_factory import CosmosSkillsSource


@pytest.mark.parametrize("chain_options", [
    {"conversation_id": "resp_previous_turn"},
    {"conversation_id": "conv_previous_turn"},
    {"previous_response_id": "resp_previous_turn"},
    {"conversation": "conv_previous_turn"},
])
def test_cosmos_replay_does_not_also_chain_server_history(chain_options):
    from agent_framework import Content, Message

    async def token_provider():
        return "test-token"

    client = agent_factory.build_chat_client(
        azure_endpoint="https://example.openai.azure.us",
        model="gpt-5.6-luna",
        credential=token_provider,
    )
    messages = [Message(role="user", contents=[Content.from_text("Follow-up question")])]
    original_options = {
        **chain_options,
        "store": True,
        "include": ["message.output_text.logprobs"],
        "instructions": "Keep the original agent instructions.",
    }
    options = asyncio.run(client._prepare_options(messages, original_options))
    assert "previous_response_id" not in options
    assert "conversation" not in options
    assert options["store"] is False
    assert options["input"][0]["role"] == "system"
    assert client.STORES_BY_DEFAULT is False
    assert options["include"] == ["message.output_text.logprobs", "reasoning.encrypted_content"]
    assert original_options["store"] is True
    assert original_options["include"] == ["message.output_text.logprobs"]
    assert client._get_conversation_id(Mock(id="resp_new_turn"), None) is None


@pytest.mark.parametrize("second_turn", [False, True])
def test_reasoning_item_fragments_are_replayed_once(second_turn):
    from agent_framework import Content, Message

    async def token_provider():
        return "test-token"

    client = agent_factory.build_chat_client(
        azure_endpoint="https://example.openai.azure.us",
        model="gpt-5.6-luna",
        credential=token_provider,
    )
    message = Message(role="assistant", contents=[
        Content.from_text_reasoning(id="rs_shared", text="First summary"),
        Content.from_text_reasoning(
            id="rs_shared", text="Second summary",
            additional_properties={"encrypted_content": "opaque", "status": "completed"},
        ),
        Content.from_function_call(call_id="call_1", name="database_schema", arguments="{}"),
    ])
    history = [message]
    if second_turn:
        history = [Message.from_dict(message.to_dict())]
        history[0].additional_properties = {"_attribution": {"source_id": "history"}}
        history.extend([
            Message(role="tool", contents=[
                Content.from_function_result(call_id="call_1", result="Schema retrieved"),
            ]),
            Message(role="assistant", contents=[Content.from_text("Here is the first answer.")]),
            Message(role="user", contents=[Content.from_text("What about the next aircraft?")]),
        ])
    original_history = [entry.to_dict() for entry in history]
    prepared = client._prepare_messages_for_openai(history)
    reasoning = [item for item in prepared if item["type"] == "reasoning"]
    assert len(reasoning) == 1
    assert reasoning[0]["summary"] == [
        {"type": "summary_text", "text": "First summary"},
        {"type": "summary_text", "text": "Second summary"},
    ]
    assert reasoning[0]["encrypted_content"] == "opaque"
    assert reasoning[0]["status"] == "completed"
    assert prepared[1]["type"] == "function_call"
    assert prepared[1]["call_id"] == "call_1"
    assert len(message.contents) == 3
    assert [entry.to_dict() for entry in history] == original_history
    assert client._prepare_messages_for_openai(history) == prepared
    if second_turn:
        assert prepared[2]["type"] == "function_call_output"
        assert prepared[2]["call_id"] == "call_1"
        assert prepared[-1]["role"] == "user"
        assert prepared[-1]["content"][0]["text"] == "What about the next aircraft?"


def test_reasoning_merge_preserves_distinct_ids_and_anonymous_items(monkeypatch):
    items = [
        {"type": "reasoning", "id": "rs_first", "summary": []},
        {"type": "reasoning", "id": "rs_second", "summary": []},
        {"type": "reasoning", "summary": []},
        {"type": "reasoning", "summary": []},
        {"type": "reasoning", "id": "rs_first", "summary": []},
        {"type": "function_call", "call_id": "call_1"},
    ]
    monkeypatch.setattr(
        agent_factory._OpenAIChatClient, "_prepare_messages_for_openai",
        lambda self, messages: items,
    )
    client = object.__new__(agent_factory.OpenAIChatClient)
    assert client._prepare_messages_for_openai([]) == items[:4] + items[5:]


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