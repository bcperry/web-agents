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
from tests._doubles import InMemoryUserScopedRepository


def _as_user(uid: str):
    return lambda: AuthenticatedUser(user_id=uid, username=uid)


def test_user_scoped_create_preserves_same_owner_duplicate():
    async def scenario():
        repo = InMemoryUserScopedRepository()
        original = {"id": "shared-id", "name": "Original"}

        await repo.create("userA", "shared-id", original)
        with pytest.raises(Exception) as exc_info:
            await repo.create("userA", "shared-id", {"id": "shared-id", "name": "Replacement"})

        assert exc_info.type.__name__ == "CosmosResourceExistsError"
        assert await repo.get("userA", "shared-id") == original

    asyncio.run(scenario())


def test_user_scoped_create_allows_same_id_for_different_owners():
    async def scenario():
        repo = InMemoryUserScopedRepository()

        await repo.create("userA", "shared-id", {"id": "shared-id", "name": "Alpha"})
        await repo.create("userB", "shared-id", {"id": "shared-id", "name": "Beta"})

        assert (await repo.get("userA", "shared-id"))["name"] == "Alpha"
        assert (await repo.get("userB", "shared-id"))["name"] == "Beta"

    asyncio.run(scenario())


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


@pytest.mark.parametrize("base_name", ["Search Agent", "Old display name"])
def test_agent_customizations_crud(client, base_name):
    from main import app

    override = {"id": "o1", "baseProfileId": "search", "baseProfileName": base_name,
                "systemPrompt": "x", "source": "builtin-override"}
    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        assert client.put("/api/agent-customizations/search", json=override).status_code == 200
        listed = client.get("/api/agent-customizations").json()["overrides"]
        assert [o["baseProfileId"] for o in listed] == ["search"]
        assert listed[0]["baseProfileName"] == "Search Agent"
        assert listed[0]["name"] == "Search Agent"
        listed[0]["systemPrompt"] = "Edited after reload"
        saved = client.put("/api/agent-customizations/search", json=listed[0])
        assert saved.status_code == 200
        assert saved.json()["systemPrompt"] == "Edited after reload"
        assert client.delete("/api/agent-customizations/search").status_code == 204
        assert client.get("/api/agent-customizations").json()["overrides"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_customization_save_validates_identity_and_capabilities(client):
    body = {"baseProfileId": "search", "systemPrompt": "Search carefully.", "tools": ["missing-tool"]}
    assert client.put("/api/agent-customizations/search", json=body).status_code == 422
    body["tools"] = []
    assert client.put("/api/agent-customizations/other", json=body).status_code == 400
    body["baseProfileId"] = "missing-profile"
    assert client.put("/api/agent-customizations/missing-profile", json=body).status_code == 400


@pytest.mark.parametrize("path, body", [
    ("/api/agent-customizations/search", {"baseProfileId": "search", "baseProfileName": "Search Agent"}),
    ("/api/custom-agents/planner", {"id": "planner", "name": "Planner"}),
])
def test_agent_saves_still_reject_unknown_fields(client, path, body):
    response = client.put(path, json={**body, "systemPrompt": "Help.", "unexpectedField": True})
    assert response.status_code == 422
    assert response.json()["detail"] == [{
        "field": "unexpectedField", "reason": "Extra inputs are not permitted",
    }]


def test_save_rejects_non_object_body(client):
    from main import app

    app.dependency_overrides[get_current_user] = _as_user("userA")
    try:
        assert client.put("/api/custom-agents/a1", json=["not", "an", "object"]).status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize("path, identity", [
    ("/api/custom-agents/planner", {"id": "planner", "name": "Planner"}),
    ("/api/agent-customizations/search", {"baseProfileId": "search"}),
])
def test_agent_saves_report_nested_validation_errors(client, path, identity):
    response = client.put(path, json={
        **identity, "systemPrompt": "Plan.",
        "starters": [{"label": "Question", "message": {"invalid": "object"}}],
    })
    assert response.status_code == 422
    assert response.json()["detail"] == [{
        "field": "starters.0.message", "reason": "Input should be a valid string",
    }]


def test_custom_agent_save_is_strict_matches_id_and_preserves_created_at(client):
    body = {
        "id": "planner",
        "name": "Planner",
        "description": "Plans work",
        "systemPrompt": "Plan carefully.",
        "tools": [],
        "skills": [],
        "mcpServers": [],
        "useSearchContext": False,
        "icon": "/favicon.png",
        "starters": [],
        "agentsAsTools": [],
        "temperature": 0.2,
        "createdAt": "2000-01-01T00:00:00Z",
        "updatedAt": "2000-01-01T00:00:00Z",
    }
    created = client.put("/api/custom-agents/planner", json=body)
    assert created.status_code == 200
    server_created_at = created.json()["createdAt"]
    assert server_created_at != body["createdAt"]

    body["name"] = "Updated Planner"
    body["createdAt"] = "forged"
    updated = client.put("/api/custom-agents/planner", json=body)
    assert updated.status_code == 200
    assert updated.json()["createdAt"] == server_created_at
    assert updated.json()["name"] == "Updated Planner"

    mismatch = client.put("/api/custom-agents/other", json=body)
    assert mismatch.status_code == 400

    body["tools"] = ["unknown-tool"]
    invalid = client.put("/api/custom-agents/planner", json=body)
    assert invalid.status_code == 422
    assert invalid.json()["detail"][0]["field"] == "tools[0]"


def test_custom_agent_save_sanitizes_store_failures(client, monkeypatch):
    class FailingRepository:
        async def get(self, *_args, **_kwargs):
            raise RuntimeError("credential=SECRET provider diagnostics")

    monkeypatch.setattr(user_data, "_custom_agents_repo", FailingRepository())
    response = client.put("/api/custom-agents/planner", json={
        "id": "planner", "name": "Planner", "systemPrompt": "Plan.",
    })

    assert response.status_code == 503
    assert response.json() == {
        "detail": "User data store is temporarily unavailable. Please try again."
    }
    assert "SECRET" not in response.text


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
