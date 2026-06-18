"""Tests for session orchestration helpers."""

import asyncio
import logging

import pytest
from fastapi import HTTPException

import session_orchestration
from prompt_config import BuiltinAgentRef, CustomAgentRef
from session_orchestration import (
    _build_validated_sub_agent_refs,
    _create_conversation_index,
    _resolve_session_id,
    sanitize_mcp_result_error,
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
