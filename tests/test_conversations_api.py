"""Tests for the conversations REST API: listing, messages, deletion, isolation."""

import asyncio

import cosmos_memory
from auth import AuthenticatedUser, get_current_user


def run(coro):
    return asyncio.run(coro)


def _as_user(uid: str):
    return lambda: AuthenticatedUser(user_id=uid, username=uid)


def _seed(uid: str, conv_id: str, profile_id: str = "search", profile_name: str = "Search Agent"):
    repo = cosmos_memory.get_conversation_repository()
    run(repo.create(uid, conv_id, profile_id, profile_name))


class _FakeHistory:
    """History provider returning canned messages for any session id."""

    def __init__(self, messages):
        self._messages = messages

    async def get_messages(self, session_id, *, state=None, **kwargs):
        return list(self._messages)

    async def clear(self, session_id):
        return None


# ---------------------------------------------------------------------------
# T018 — GET /api/conversations
# ---------------------------------------------------------------------------

def test_list_returns_only_owner_conversations(client):
    from main import app

    _seed("userA", "a1")
    _seed("userA", "a2")
    _seed("userB", "b1")

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.get("/api/conversations")
        assert resp.status_code == 200
        ids = {c["id"] for c in resp.json()["conversations"]}
        assert ids == {"a1", "a2"}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_orders_by_last_activity_desc(client):
    from main import app

    _seed("userA", "older")
    _seed("userA", "newer")
    run(cosmos_memory.get_conversation_repository().touch("userA", "newer", title="newer one"))

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.get("/api/conversations?limit=10")
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()["conversations"]]
        assert ids[0] == "newer"
        assert set(ids) == {"older", "newer"}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# T024 — GET /api/conversations/{id}/messages
# ---------------------------------------------------------------------------

def test_get_messages_returns_mapped_messages_for_owner(client, monkeypatch):
    from main import app
    from agent_framework._types import Content, Message

    monkeypatch.setattr(
        cosmos_memory,
        "_history_provider",
        _FakeHistory([
            Message(role="user", contents=[Content.from_text("hi")]),
            Message(role="assistant", contents=[Content.from_text("hello there")]),
        ]),
    )
    _seed("userA", "a1")

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        resp = client.get("/api/conversations/a1/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "a1"
        assert [m["role"] for m in data["messages"]] == ["user", "assistant"]
        assert data["messages"][1]["content"] == "hello there"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# T030 — per-user isolation across read / delete
# ---------------------------------------------------------------------------

def test_messages_endpoint_denies_non_owner(client, monkeypatch):
    from main import app

    monkeypatch.setattr(cosmos_memory, "_history_provider", _FakeHistory([]))
    _seed("userA", "a1")

    app.dependency_overrides[get_current_user] = _as_user("userB")
    try:
        assert client.get("/api/conversations/a1/messages").status_code == 404
        assert client.get("/api/conversations/does-not-exist/messages").status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_excludes_other_users(client):
    from main import app

    _seed("userA", "a1")
    _seed("userB", "b1")

    app.dependency_overrides[get_current_user] = _as_user("userB")
    try:
        resp = client.get("/api/conversations")
        ids = {c["id"] for c in resp.json()["conversations"]}
        assert ids == {"b1"}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# T034 — DELETE /api/conversations/{id}
# ---------------------------------------------------------------------------

def test_delete_is_owner_scoped(client, monkeypatch):
    from main import app

    monkeypatch.setattr(cosmos_memory, "_history_provider", _FakeHistory([]))
    _seed("userA", "a1")

    # Non-owner cannot delete
    app.dependency_overrides[get_current_user] = _as_user("userB")
    try:
        assert client.delete("/api/conversations/a1").status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # Owner deletes; afterwards it is gone
    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        assert client.delete("/api/conversations/a1").status_code == 204
        assert client.get("/api/conversations/a1/messages").status_code == 404
        assert client.delete("/api/conversations/a1").status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
