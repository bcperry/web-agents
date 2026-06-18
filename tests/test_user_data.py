"""Tests for the per-user data layer: custom agents, agent customizations, profile.

API tests use the in-memory doubles (autouse fixture). The ``@pytest.mark.emulator``
test exercises the real ``CosmosUserScopedRepository`` against the local emulator.
"""

import asyncio
from uuid import uuid4

import pytest

import cosmos_memory
import user_data
from auth import AuthenticatedUser, get_current_user


def _as_user(uid: str):
    return lambda: AuthenticatedUser(user_id=uid, username=uid)


# ---------------------------------------------------------------------------
# API — custom agents
# ---------------------------------------------------------------------------

def test_custom_agents_crud_and_isolation(client):
    from main import app

    agent = {"id": "a1", "name": "Alpha", "systemPrompt": "be alpha"}

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        assert client.get("/api/custom-agents").json()["agents"] == []
        assert client.put("/api/custom-agents/a1", json=agent).status_code == 200
        listed = client.get("/api/custom-agents").json()["agents"]
        assert [a["id"] for a in listed] == ["a1"]
        assert listed[0]["name"] == "Alpha"
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # Isolation: a different user sees nothing.
    app.dependency_overrides[get_current_user] = _as_user("userB")
    try:
        assert client.get("/api/custom-agents").json()["agents"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        assert client.delete("/api/custom-agents/a1").status_code == 204
        assert client.get("/api/custom-agents").json()["agents"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_agent_customizations_crud(client):
    from main import app

    override = {"id": "o1", "baseProfileId": "search", "systemPrompt": "x", "source": "builtin-override"}
    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        assert client.put("/api/agent-customizations/search", json=override).status_code == 200
        listed = client.get("/api/agent-customizations").json()["overrides"]
        assert [o["baseProfileId"] for o in listed] == ["search"]
        assert client.delete("/api/agent-customizations/search").status_code == 204
        assert client.get("/api/agent-customizations").json()["overrides"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_save_rejects_non_object_body(client):
    from main import app

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        assert client.put("/api/custom-agents/a1", json=["not", "an", "object"]).status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Emulator — real CosmosUserScopedRepository CRUD + isolation
# ---------------------------------------------------------------------------

@pytest.mark.emulator
def test_repo_crud_and_isolation(cosmos_emulator):
    async def scenario():
        repo = user_data.get_custom_agents_repository()
        user_a, user_b = f"userA-{uuid4()}", f"userB-{uuid4()}"
        try:
            await repo.upsert(user_a, "a1", {"id": "a1", "name": "Alpha"})
            await repo.upsert(user_a, "a2", {"id": "a2", "name": "Beta"})
            items = await repo.list_for_user(user_a)
            assert {i["id"] for i in items} == {"a1", "a2"}
            assert (await repo.get(user_a, "a1"))["name"] == "Alpha"

            # Per-user isolation.
            assert await repo.get(user_b, "a1") is None
            assert await repo.list_for_user(user_b) == []

            # Update + owner-scoped, idempotent delete.
            await repo.upsert(user_a, "a1", {"id": "a1", "name": "Alpha2"})
            assert (await repo.get(user_a, "a1"))["name"] == "Alpha2"
            assert await repo.delete(user_b, "a1") is False
            assert await repo.delete(user_a, "a1") is True
            assert await repo.delete(user_a, "a1") is False
        finally:
            await repo.delete(user_a, "a1")
            await repo.delete(user_a, "a2")
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())
