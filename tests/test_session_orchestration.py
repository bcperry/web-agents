"""Tests for session orchestration helpers."""

import asyncio
import logging

import pytest
from fastapi import HTTPException

import session_orchestration
from mcp_servers import sanitize_mcp_result_error
from prompt_config import AgentProfile, BuiltinAgentRef, CustomAgentRef
from session_orchestration import (
    _build_validated_sub_agent_refs,
    _create_conversation_index,
    _owner_scoped_sub_agent_payload,
    _resolve_session_id,
)


def test_sanitize_mcp_result_error_removes_credentials_and_tokens():
    error = (
        "GET https://example.test/mcp?api_key=secret&code=abc failed "
        "Authorization: Bearer eyJsecret token password=hidden connectionString=Server=tcp"
    )

    sanitized = sanitize_mcp_result_error(error)

    assert "secret" not in sanitized
    assert "Bearer" not in sanitized
    assert "api_key=" not in sanitized
    assert "code=" not in sanitized
    assert "password=" not in sanitized
    assert "connectionString=" not in sanitized
    assert "https://example.test/mcp" in sanitized


def test_overlapping_session_replacements_dispose_displaced_runtime(monkeypatch):
    from types import SimpleNamespace
    import session_data

    async def scenario():
        closing = asyncio.Event()
        release = asyncio.Event()
        closed = []

        async def cleanup(tools):
            if tools == ["old"]:
                closing.set()
                await release.wait()
            closed.extend(tools)

        monkeypatch.setattr(session_data, "cleanup_mcp_servers", cleanup)
        old, first, second = [
            SimpleNamespace(session_id="same", mcp_tools=[name])
            for name in ("old", "first", "second")
        ]
        sessions = {"same": old}
        replacing = asyncio.create_task(session_data.replace_session(first, sessions=sessions))
        await closing.wait()
        await session_data.replace_session(second, sessions=sessions)
        release.set()
        await replacing
        assert sessions["same"] is second
        assert sorted(closed) == ["first", "old"]
        await session_data.close_session("same", sessions=sessions, expected=first)
        assert sessions["same"] is second

    asyncio.run(scenario())


@pytest.mark.parametrize("replace_again", [False, True])
def test_cancelled_replacement_cleans_only_owned_resources(monkeypatch, replace_again):
    from types import SimpleNamespace
    import session_data

    async def scenario():
        closing = asyncio.Event()
        release = asyncio.Event()
        closed = []

        async def cleanup(tools):
            if tools == ["old"]:
                closing.set()
                await release.wait()
            closed.extend(tools)

        monkeypatch.setattr(session_data, "cleanup_mcp_servers", cleanup)
        old, first, second = [
            SimpleNamespace(session_id="same", mcp_tools=[name])
            for name in ("old", "first", "second")
        ]
        sessions = {"same": old}
        replacing = asyncio.create_task(session_data.replace_session(first, sessions=sessions))
        await closing.wait()
        replacing.cancel()
        if replace_again:
            await session_data.replace_session(second, sessions=sessions)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await replacing
        assert sessions == ({"same": second} if replace_again else {})
        assert sorted(closed) == ["first", "old"]

    asyncio.run(scenario())


def test_mcp_environment_expansion_requires_trusted_configuration(monkeypatch):
    from mcp_servers import parse_mcp_server_configs

    monkeypatch.setenv("REVIEW_DUMMY_VALUE", "dummy-value")
    payload = {"mcp_servers": [{"name": "test", "transport": "http", "url": "https://example.test/${REVIEW_DUMMY_VALUE}"}]}
    assert parse_mcp_server_configs(payload)[0].url.endswith("${REVIEW_DUMMY_VALUE}")
    assert parse_mcp_server_configs(payload, interpolate_env=True)[0].url.endswith("dummy-value")


def test_mcp_connection_cancellation_propagates(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import mcp_servers

    tool = SimpleNamespace(connect=AsyncMock(side_effect=asyncio.CancelledError()))
    monkeypatch.setattr(mcp_servers, "create_mcp_tool", lambda *args, **kwargs: tool)
    config = mcp_servers.MCPServerConfig(name="test", transport="http", url="https://example.test")
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(mcp_servers.connect_mcp_servers([config]))


@pytest.mark.parametrize("transport", ["http", "stdio"])
@pytest.mark.parametrize("allowed_tools", [None, [], ["lookup"]])
def test_mcp_allowlist_preserves_empty_collection(transport, allowed_tools):
    from mcp_servers import create_mcp_tool, parse_mcp_server_configs

    entry = {"name": "test", "transport": transport, "url": "https://example.test", "command": "unused"}
    if allowed_tools is not None:
        entry["allowed_tools"] = allowed_tools
    config = parse_mcp_server_configs({"mcp_servers": [entry]})[0]
    assert config.allowed_tools == allowed_tools
    tool = create_mcp_tool(config)
    if allowed_tools is None:
        assert tool.allowed_tools is None
    else:
        assert tool.allowed_tools is not None
        assert set(tool.allowed_tools) == set(allowed_tools)


def test_unknown_sub_agent_profile_does_not_fall_back():
    with pytest.raises(HTTPException) as error:
        _build_validated_sub_agent_refs("parent", [{"agentRef": {"kind": "builtin", "profileId": "missing-profile"}}], logging.getLogger("test"))
    assert error.value.status_code == 400


@pytest.mark.parametrize("allowed_tools", ["lookup", 42, {}, [None], ["lookup", 1]])
def test_invalid_mcp_allowlist_is_rejected_before_connect(client, monkeypatch, allowed_tools):
    from unittest.mock import AsyncMock
    from mcp_servers import parse_mcp_server_configs

    payload = {"mcp_servers": [{"name": "test", "transport": "http",
        "url": "https://example.test", "allowed_tools": allowed_tools}]}
    with pytest.raises(ValueError, match="allowed_tools must be"):
        parse_mcp_server_configs(payload)
    connect = AsyncMock()
    monkeypatch.setattr("api_routes.profiles.connect_mcp_servers", connect)
    response = client.post("/api/mcp/test", json=payload)
    assert response.status_code == 400
    connect.assert_not_called()


@pytest.mark.parametrize("failure_stage", ["runtime", "index"])
def test_session_setup_rolls_back_connected_resources(monkeypatch, failure_stage):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    from session_data import SessionData

    close = AsyncMock()
    dependencies = session_orchestration.RuntimeDependencies(
        function_tools=[], tool_names=[], mcp_tools=[], session_mcp_tools=[object()],
        mcp_results=[], profile_context="", sub_agent_resources={},
    )
    runtime = SimpleNamespace(agent=object(), tools=[], prompt_logical_profile="custom", sub_agent_tool_names=[])
    monkeypatch.setattr(session_orchestration, "_resolve_runtime_dependencies", AsyncMock(return_value=dependencies))
    monkeypatch.setattr(session_orchestration, "cleanup_mcp_servers", close)
    monkeypatch.setattr(session_orchestration, "create_chat_runtime", Mock(
        return_value=runtime, side_effect=RuntimeError("test failure") if failure_stage == "runtime" else None,
    ))
    monkeypatch.setattr(session_orchestration, "_create_conversation_index", AsyncMock(side_effect=HTTPException(503, "test failure")))
    ctx = session_orchestration.SessionContext({}, SessionData, lambda *args, **kwargs: [], lambda _: "")
    with pytest.raises(HTTPException) as error:
        asyncio.run(session_orchestration._start_session(
            ctx, body={}, user=_SimpleUser(), logger=logging.getLogger("test"),
            definition=session_orchestration.SessionDefinition(
                profile_id="custom", mcp_configs=[],
                profile=AgentProfile(name="Test", logical_profile="custom", system_prompt="Help",
                                     description="Test", tool_names=[]),
            ), user_bearer_token=None,
        ))
    assert error.value.status_code == (500 if failure_stage == "runtime" else 503)
    assert ctx.sessions == {}
    close.assert_awaited_once_with(dependencies.session_mcp_tools)


# ---------------------------------------------------------------------------
# T012 — agents_as_tools wire format → validated SubAgentToolRef list
# ---------------------------------------------------------------------------


def test_build_validated_sub_agent_refs_accepts_camel_case_custom_inline_definition():
    payload = [
        {
            "agentRef": {
                "kind": "custom",
                "customAgentId": "blaine-bot",
                "definition": {
                    "id": "blaine-bot",
                    "name": "Blaine Bot",
                    "description": "Be Blaine.",
                    "systemPrompt": "You are Blaine.",
                },
            }
        }
    ]
    refs = _build_validated_sub_agent_refs(
        parent_id="custom:Parent", raw_payload=payload, logger=logging.getLogger("test")
    )
    assert len(refs) == 1
    assert isinstance(refs[0].agent_ref, CustomAgentRef)
    assert refs[0].agent_ref.custom_agent_id == "blaine-bot"
    assert refs[0].agent_ref.definition["systemPrompt"] == "You are Blaine."


def test_build_validated_sub_agent_refs_returns_empty_for_missing_payload():
    refs = _build_validated_sub_agent_refs(
        parent_id="custom:Parent", raw_payload=None, logger=logging.getLogger("test")
    )
    assert refs == []


def test_build_validated_sub_agent_refs_rejects_self_reference_for_builtin():
    """A built-in profile that lists itself MUST be flagged (V2)."""
    payload = [{"agentRef": {"kind": "builtin", "profileId": "azgov"}}]
    with pytest.raises(HTTPException) as exc_info:
        _build_validated_sub_agent_refs(
            parent_id="azgov", raw_payload=payload, logger=logging.getLogger("test")
        )
    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    codes = {e["code"] for e in detail["errors"]}
    assert "self_reference" in codes


def test_build_validated_sub_agent_refs_rejects_non_list_payload():
    with pytest.raises(HTTPException) as exc_info:
        _build_validated_sub_agent_refs(
            parent_id="x", raw_payload="not-a-list", logger=logging.getLogger("test")
        )
    assert exc_info.value.status_code == 400


def test_build_validated_sub_agent_refs_flags_custom_self_reference_via_id_match():
    """A custom agent referencing itself by id MUST be flagged."""
    payload = [
        {
            "agentRef": {
                "kind": "custom",
                "customAgentId": "blaine-bot",
                "definition": {
                    "id": "blaine-bot",
                    "name": "Blaine Bot",
                    "systemPrompt": "x",
                },
            }
        }
    ]
    with pytest.raises(HTTPException) as exc_info:
        _build_validated_sub_agent_refs(
            parent_id="blaine-bot",
            raw_payload=payload,
            logger=logging.getLogger("test"),
        )
    codes = {e["code"] for e in exc_info.value.detail["errors"]}
    assert "self_reference" in codes


def test_build_validated_sub_agent_refs_flags_duplicate_targets():
    payload = [
        {"agentRef": {"kind": "custom", "customAgentId": "x", "definition": {"id": "x", "name": "X", "systemPrompt": "p"}}},
        {"agentRef": {"kind": "custom", "customAgentId": "x", "definition": {"id": "x", "name": "X", "systemPrompt": "p"}}},
    ]
    with pytest.raises(HTTPException) as exc_info:
        _build_validated_sub_agent_refs(
            parent_id="custom:Parent",
            raw_payload=payload,
            logger=logging.getLogger("test"),
        )
    codes = {e["code"] for e in exc_info.value.detail["errors"]}
    assert "duplicate_target" in codes


# ---------------------------------------------------------------------------
# Conversation-store error paths must surface a clean 503 (regression: the
# module-level `logger` was undefined, so the error branch raised NameError
# instead of HTTPException 503).
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


class _SimpleUser:
    def __init__(self, user_id="user-1"):
        self.user_id = user_id


class _BoomConversations:
    """Conversation store whose every call fails, to exercise the error/log path."""

    async def get_owned(self, user_id, conversation_id):
        raise RuntimeError("store down")

    async def create(self, *args, **kwargs):
        raise RuntimeError("store down")


def test_session_orchestration_defines_module_logger():
    assert isinstance(session_orchestration.logger, logging.Logger)


def test_resolve_session_id_maps_store_error_to_503():
    with pytest.raises(HTTPException) as exc_info:
        _run(
            _resolve_session_id(
                _BoomConversations(), _SimpleUser(), {"conversation_id": "c1"}
            )
        )
    assert exc_info.value.status_code == 503


def test_create_conversation_index_maps_store_error_to_503():
    with pytest.raises(HTTPException) as exc_info:
        _run(
            _create_conversation_index(
                _BoomConversations(),
                user=_SimpleUser(),
                session_id="c1",
                profile_id="search",
                profile_name="Search Agent",
            )
        )
    assert exc_info.value.status_code == 503


def test_owner_scoped_sub_agent_payload_ignores_untrusted_inline_definition():
    import user_data

    asyncio.run(user_data.get_custom_agents_repository().create(
        "user-a", "owned", {"id": "owned", "name": "Durable", "systemPrompt": "owner data"}
    ))
    supplied = [{"agentRef": {
        "kind": "custom",
        "customAgentId": "owned",
        "definition": {"id": "owned", "name": "Forged", "systemPrompt": "client data"},
    }}]

    scoped = asyncio.run(_owner_scoped_sub_agent_payload(supplied, "user-a"))
    denied = asyncio.run(_owner_scoped_sub_agent_payload(supplied, "user-b"))

    assert scoped[0]["agent_ref"]["definition"]["name"] == "Durable"
    assert denied[0]["agent_ref"]["definition"] == {"id": "owned"}
