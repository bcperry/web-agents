"""Tests for the agent view API: ownership, the permission broker, and limits.

The broker is the security boundary of the dynamic UI pane: a rendered view may
only reach tools the rendering agent already has, as the signed-in owner.
"""

import asyncio

import pytest

import agent_views
import cosmos_memory
import user_data
from auth import AuthenticatedUser, get_current_user
from tests._doubles import InMemoryAgentViewRepository


def run(coro):
    return asyncio.run(coro)


def _as_user(uid: str):
    return lambda: AuthenticatedUser(user_id=uid, username=uid)


def _seed_conversation(uid: str, conv_id: str) -> None:
    run(cosmos_memory.get_conversation_repository().create(uid, conv_id, "hybrid", "Hybrid Agent"))


def _seed_view(uid: str, conv_id: str, title: str = "Readiness") -> str:
    record = run(agent_views.save_view(
        user_id=uid, conversation_id=conv_id, title=title, html="<p>hi</p>", profile_id="hybrid"
    ))
    return record.id


class _FakeSession:
    """Stand-in for SessionData: only the broker-relevant attributes."""

    def __init__(self, tools):
        self.tools = tools
        self.profile_id = "hybrid"
        self.eval_trace_logger = None


async def get_user_profile() -> str:
    return '{"name": "Alex"}'


@pytest.fixture(autouse=True)
def _views_repo(monkeypatch):
    monkeypatch.setattr(user_data, "_agent_views_repo", InMemoryAgentViewRepository())
    agent_views.clear_view_data_budget("conv-1")


def _activate_session(session_id: str, tools) -> None:
    from session_data import _sessions

    _sessions[session_id] = _FakeSession(tools)


# ---------------------------------------------------------------------------
# Reads — ownership and conversation scoping
# ---------------------------------------------------------------------------

def test_list_views_returns_summaries_without_html(client):
    from main import app

    _seed_conversation("userA", "conv-1")
    _seed_view("userA", "conv-1")

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.get("/api/sessions/conv-1/views")
        assert resp.status_code == 200
        views = resp.json()["views"]
        assert len(views) == 1
        assert views[0]["title"] == "Readiness"
        assert "html" not in views[0]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_views_of_another_user_are_not_reachable(client):
    from main import app

    _seed_conversation("userA", "conv-1")
    view_id = _seed_view("userA", "conv-1")

    app.dependency_overrides[get_current_user] = _as_user("userB")
    try:
        assert client.get("/api/sessions/conv-1/views").status_code == 404
        assert client.get(f"/api/sessions/conv-1/views/{view_id}").status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_get_view_returns_html_for_the_owner(client):
    from main import app

    _seed_conversation("userA", "conv-1")
    view_id = _seed_view("userA", "conv-1")

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.get(f"/api/sessions/conv-1/views/{view_id}")
        assert resp.status_code == 200
        assert resp.json()["html"] == "<p>hi</p>"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Broker — permission enforcement
# ---------------------------------------------------------------------------

def test_broker_runs_a_permitted_tool(client):
    from main import app
    from session_data import _sessions

    _seed_conversation("userA", "conv-1")
    view_id = _seed_view("userA", "conv-1")
    _activate_session("conv-1", [get_user_profile])

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.post(
            f"/api/sessions/conv-1/views/{view_id}/data",
            json={"tool": "get_user_profile", "arguments": {}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"] == '{"name": "Alex"}'
        assert body["truncated"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        _sessions.pop("conv-1", None)


def test_broker_refuses_a_tool_the_agent_does_not_have(client):
    from main import app
    from session_data import _sessions

    _seed_conversation("userA", "conv-1")
    view_id = _seed_view("userA", "conv-1")
    _activate_session("conv-1", [get_user_profile])

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.post(
            f"/api/sessions/conv-1/views/{view_id}/data",
            json={"tool": "save_user_profile", "arguments": {"name": "Mallory"}},
        )
        assert resp.status_code == 403
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "not_permitted"
        assert "data" not in body
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        _sessions.pop("conv-1", None)


def test_broker_refuses_the_render_tool_itself(client):
    from main import app
    from session_data import _sessions

    _seed_conversation("userA", "conv-1")
    view_id = _seed_view("userA", "conv-1")

    async def render_agent_view(title: str, html: str) -> dict:
        return {"status": "rendered"}

    _activate_session("conv-1", [render_agent_view])

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.post(
            f"/api/sessions/conv-1/views/{view_id}/data",
            json={"tool": "render_agent_view", "arguments": {"title": "x", "html": "<p>x</p>"}},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "not_permitted"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        _sessions.pop("conv-1", None)


def test_broker_refuses_when_the_session_is_not_active(client):
    from main import app

    _seed_conversation("userA", "conv-1")
    view_id = _seed_view("userA", "conv-1")

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.post(
            f"/api/sessions/conv-1/views/{view_id}/data",
            json={"tool": "get_user_profile", "arguments": {}},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "session_inactive"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_broker_rejects_non_object_arguments(client):
    from main import app
    from session_data import _sessions

    _seed_conversation("userA", "conv-1")
    view_id = _seed_view("userA", "conv-1")
    _activate_session("conv-1", [get_user_profile])

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.post(
            f"/api/sessions/conv-1/views/{view_id}/data",
            json={"tool": "get_user_profile", "arguments": ["not", "an", "object"]},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "invalid_arguments"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        _sessions.pop("conv-1", None)


def test_broker_rejects_unexpected_tool_arguments(client):
    from main import app
    from session_data import _sessions

    _seed_conversation("userA", "conv-1")
    view_id = _seed_view("userA", "conv-1")
    _activate_session("conv-1", [get_user_profile])

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.post(
            f"/api/sessions/conv-1/views/{view_id}/data",
            json={"tool": "get_user_profile", "arguments": {"unexpected": 1}},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "invalid_arguments"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        _sessions.pop("conv-1", None)


def test_broker_requires_a_view_the_caller_owns(client):
    from main import app
    from session_data import _sessions

    _seed_conversation("userA", "conv-1")
    _activate_session("conv-1", [get_user_profile])

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.post(
            "/api/sessions/conv-1/views/does-not-exist/data",
            json={"tool": "get_user_profile", "arguments": {}},
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        _sessions.pop("conv-1", None)


def test_broker_enforces_the_request_budget(client, monkeypatch):
    from main import app
    from session_data import _sessions

    monkeypatch.setattr(agent_views, "MAX_VIEW_DATA_REQUESTS_PER_MINUTE", 2)
    _seed_conversation("userA", "conv-1")
    view_id = _seed_view("userA", "conv-1")
    _activate_session("conv-1", [get_user_profile])

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        payload = {"tool": "get_user_profile", "arguments": {}}
        url = f"/api/sessions/conv-1/views/{view_id}/data"
        assert client.post(url, json=payload).status_code == 200
        assert client.post(url, json=payload).status_code == 200
        limited = client.post(url, json=payload)
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"
        assert limited.headers["Retry-After"] == "60"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        _sessions.pop("conv-1", None)
        agent_views.clear_view_data_budget("conv-1")


def test_broker_truncates_oversize_results(client, monkeypatch):
    from main import app
    from session_data import _sessions

    monkeypatch.setattr(agent_views, "MAX_VIEW_DATA_RESPONSE_CHARS", 10)

    async def get_user_profile() -> str:
        return "x" * 500

    _seed_conversation("userA", "conv-1")
    view_id = _seed_view("userA", "conv-1")
    _activate_session("conv-1", [get_user_profile])

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.post(
            f"/api/sessions/conv-1/views/{view_id}/data",
            json={"tool": "get_user_profile", "arguments": {}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["truncated"] is True
        assert len(body["data"]) == 10
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        _sessions.pop("conv-1", None)


def test_broker_sanitizes_tool_failures(client):
    from main import app
    from session_data import _sessions

    async def get_user_profile() -> str:
        raise RuntimeError("Server=tcp:secret.database.usgovcloudapi.net;Password=hunter2")

    _seed_conversation("userA", "conv-1")
    view_id = _seed_view("userA", "conv-1")
    _activate_session("conv-1", [get_user_profile])

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.post(
            f"/api/sessions/conv-1/views/{view_id}/data",
            json={"tool": "get_user_profile", "arguments": {}},
        )
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["code"] == "tool_failed"
        assert "hunter2" not in body["error"]["message"]
        assert "usgovcloudapi" not in body["error"]["message"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        _sessions.pop("conv-1", None)


# ---------------------------------------------------------------------------
# Tool resolution
# ---------------------------------------------------------------------------

def test_resolve_view_tool_ignores_unregistered_session_entries():
    class _McpServer:
        name = "aircraft-data-mcp"

        def __call__(self, **kwargs):
            raise AssertionError("MCP servers must not be callable from a view")

    assert agent_views.resolve_view_tool([_McpServer()], "aircraft-data-mcp") is None
    assert agent_views.resolve_view_tool([get_user_profile], "get_user_profile") is get_user_profile
    assert agent_views.resolve_view_tool([], "get_user_profile") is None


# ---------------------------------------------------------------------------
# Capability grant — the tools[] entry is the only switch
# ---------------------------------------------------------------------------

def test_tools_inventory_advertises_the_view_capability(client):
    from main import app

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.get("/api/tools")
        assert resp.status_code == 200
        entry = next(t for t in resp.json()["tools"] if t["name"] == "render_agent_view")
        assert entry["description"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_render_tool_is_built_only_when_granted():
    from app_context import build_tool_instances

    without = build_tool_instances({"get_user_profile"}, session_id="conv-1", user_id="userA")
    granted = build_tool_instances(
        {"get_user_profile", "render_agent_view"}, session_id="conv-1", user_id="userA"
    )

    assert [t.__name__ for t in without] == ["get_user_profile"]
    assert "render_agent_view" in [t.__name__ for t in granted]


def test_views_stay_readable_after_the_grant_is_revoked(client):
    from main import app
    from session_data import _sessions

    _seed_conversation("userA", "conv-1")
    view_id = _seed_view("userA", "conv-1")
    # Session rebuilt after the grant was removed: no render tool present.
    _activate_session("conv-1", [get_user_profile])

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        assert client.get("/api/sessions/conv-1/views").status_code == 200
        assert client.get(f"/api/sessions/conv-1/views/{view_id}").status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        _sessions.pop("conv-1", None)


# ---------------------------------------------------------------------------
# Restore — what a reopened conversation gets back
# ---------------------------------------------------------------------------

def test_restored_views_are_oldest_first_and_capped(client, monkeypatch):
    from main import app

    monkeypatch.setattr(agent_views, "MAX_AGENT_VIEWS_PER_CONVERSATION", 3)
    _seed_conversation("userA", "conv-1")
    for i in range(5):
        _seed_view("userA", "conv-1", title=f"V{i}")

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.get("/api/sessions/conv-1/views")
        assert resp.status_code == 200
        assert [v["title"] for v in resp.json()["views"]] == ["V2", "V3", "V4"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_unattended_views_round_trip_their_source(client):
    from main import app

    _seed_conversation("sys", "autonomous-duty-officer")
    run(agent_views.save_view(
        user_id="sys",
        conversation_id="autonomous-duty-officer",
        title="Overnight summary",
        html="<p>hi</p>",
    ))

    app.dependency_overrides[get_current_user] = _as_user("sys")
    try:
        resp = client.get("/api/sessions/autonomous-duty-officer/views")
        assert resp.status_code == 200
        assert resp.json()["views"][0]["source"] == "autonomous"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_deleting_a_conversation_deletes_its_views(client, monkeypatch):
    from main import app
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    clear_history = AsyncMock()
    monkeypatch.setattr("api_routes.sessions.get_history_provider", lambda: SimpleNamespace(clear=clear_history))

    _seed_conversation("userA", "conv-1")
    _seed_conversation("userA", "conv-2")
    _seed_view("userA", "conv-1")
    keeper = _seed_view("userA", "conv-2")

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        assert client.delete("/api/conversations/conv-1").status_code == 204
        clear_history.assert_awaited_once_with("conv-1")
        assert run(agent_views.list_views("userA", "conv-1")) == []
        assert run(agent_views.get_view("userA", "conv-2", keeper)) is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)
