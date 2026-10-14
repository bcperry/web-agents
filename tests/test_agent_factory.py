"""Owner-aware selected-skill loading contracts."""

import asyncio
from unittest.mock import Mock

import pytest

import agent_factory
import user_data
from agent_factory import CosmosSkillsSource


def test_failed_tool_turn_remains_available_on_retry(monkeypatch):
    from agent_framework import ChatResponse, ChatResponseUpdate, Content, ResponseStream
    from agent_framework.openai import OpenAIChatClient
    from prompt_config import AgentProfile

    async def scenario():
        model = OpenAIChatClient(model="offline", api_key="offline", base_url="https://example.invalid/v1")
        calls = 0
        retry_messages = []

        def model_response(*, messages, **kwargs):
            nonlocal calls
            calls += 1
            current = calls
            if current == 3:
                retry_messages.extend(messages)

            async def updates():
                if current == 1:
                    yield ChatResponseUpdate(contents=[Content.from_function_call("search-1", "lookup", arguments={})])
                elif current == 2:
                    raise RuntimeError("Model stream failed after successful search")
                else:
                    yield ChatResponseUpdate(contents=[Content.from_text("Recovered answer")])

            return ResponseStream(updates(), finalizer=ChatResponse.from_updates)

        def lookup() -> str:
            return "Search succeeded"

        monkeypatch.setattr(model, "_inner_get_response", model_response)
        monkeypatch.setattr(agent_factory, "_build_openai_clients", lambda: (model, model))
        runtime = agent_factory.create_chat_runtime(
            profile=AgentProfile(name="Recovery", logical_profile="custom", system_prompt="Use lookup",
                                 description="Recovery workflow", tool_names=["lookup"]),
            function_tools=[lookup],
        )
        try:
            with pytest.raises(RuntimeError, match="failed after successful search"):
                async for _update in runtime.agent.run("Original question about a picture", session=runtime.session, stream=True):
                    pass
            stream = runtime.agent.run("try again", session=runtime.session, stream=True)
            async for _update in stream:
                pass
            assert (await stream.get_final_response()).text == "Recovered answer"
            assert sum(message.text == "Original question about a picture" for message in retry_messages) == 1
            assert retry_messages[-1].text == "try again"
            calls_in_history = [content for message in retry_messages for content in message.contents
                                if content.type == "function_call"]
            assert [content.call_id for content in calls_in_history] == ["search-1"]
        finally:
            await runtime.agent.close()

    asyncio.run(scenario())


def test_framework_client_supports_application_owned_history():
    from agent_framework import Content, Message
    from agent_framework.openai import OpenAIChatClient

    async def token_provider():
        return "test-token"

    client = agent_factory.build_chat_client(
        azure_endpoint="https://example.openai.azure.us",
        model="gpt-5.6-luna",
        credential=token_provider,
    )
    assert type(client) is OpenAIChatClient
    messages = [Message(role="user", contents=[Content.from_text("Follow-up question")])]
    original_options = {
        "store": False,
        "include": ["message.output_text.logprobs"],
        "instructions": "Keep the original agent instructions.",
    }
    options = asyncio.run(client._prepare_options(messages, original_options))
    assert "previous_response_id" not in options
    assert "conversation" not in options
    assert options["store"] is False
    assert options["instructions"] == original_options["instructions"]
    assert options["input"][0]["role"] == "user"
    assert options["include"] == ["message.output_text.logprobs", "reasoning.encrypted_content"]
    assert original_options["store"] is False
    assert original_options["include"] == ["message.output_text.logprobs"]
    assert client._get_conversation_id(Mock(id="resp_new_turn"), False) is None


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
    prepared = client._prepare_messages_for_openai(
        history, request_uses_service_side_storage=False,
    )
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
    assert client._prepare_messages_for_openai(
        history, request_uses_service_side_storage=False,
    ) == prepared
    if second_turn:
        assert prepared[2]["type"] == "function_call_output"
        assert prepared[2]["call_id"] == "call_1"
        assert prepared[-1]["role"] == "user"
        assert prepared[-1]["content"][0]["text"] == "What about the next aircraft?"


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
        skill.frontmatter.name for skill in asyncio.run(CosmosSkillsSource("user-a").get_skills(Mock()))
    }
    other_names = {
        skill.frontmatter.name for skill in asyncio.run(CosmosSkillsSource("user-b").get_skills(Mock()))
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