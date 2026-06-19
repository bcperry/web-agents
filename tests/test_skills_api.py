"""Tests for Skills CRUD API endpoints (Cosmos-backed, durable store)."""

import os

os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("AZURE_SQL_CONNECTIONSTRING", "")


# ---------------------------------------------------------------------------
# GET /api/skills — list
# ---------------------------------------------------------------------------

def test_get_skills_list_empty(skills_client):
    client, _repo = skills_client
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    assert resp.json() == {"skills": []}


def test_get_skills_list_populated(skills_client, make_skill):
    client, repo = skills_client
    make_skill(repo, "alpha", "Alpha skill")
    make_skill(repo, "beta", "Beta skill")
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["skills"]}
    assert "alpha" in names
    assert "beta" in names


# ---------------------------------------------------------------------------
# GET /api/skills/{name} — single skill
# ---------------------------------------------------------------------------

def test_get_skill_success(skills_client, make_skill):
    client, repo = skills_client
    make_skill(repo, "my-skill", "My description", "# Docs\nSome content.")
    resp = client.get("/api/skills/my-skill")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "my-skill"
    assert data["description"] == "My description"
    assert "Some content." in data["content"]


def test_get_skill_not_found(skills_client):
    client, _ = skills_client
    resp = client.get("/api/skills/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/skills — create
# ---------------------------------------------------------------------------

def test_create_skill_success_is_durable(skills_client):
    client, _repo = skills_client
    payload = {"name": "new-skill", "description": "A new skill", "content": "# Hello\nWorld."}
    resp = client.post("/api/skills", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "new-skill"
    assert data["description"] == "A new skill"
    # Durability: a subsequent read is served from the (Cosmos) store, not request state.
    read_back = client.get("/api/skills/new-skill")
    assert read_back.status_code == 200
    assert read_back.json()["content"] == "# Hello\nWorld."
    listed = {s["name"] for s in client.get("/api/skills").json()["skills"]}
    assert "new-skill" in listed


def test_create_skill_duplicate_returns_409(skills_client, make_skill):
    client, repo = skills_client
    make_skill(repo, "existing")
    payload = {"name": "existing", "description": "Another", "content": "# Content"}
    resp = client.post("/api/skills", json=payload)
    assert resp.status_code == 409


def test_create_skill_invalid_name_returns_422(skills_client):
    client, _ = skills_client
    payload = {"name": "Bad-Name", "description": "desc", "content": "body"}
    resp = client.post("/api/skills", json=payload)
    assert resp.status_code == 422


def test_create_skill_name_with_uppercase_invalid(skills_client):
    client, _ = skills_client
    payload = {"name": "INVALID", "description": "desc", "content": "body"}
    resp = client.post("/api/skills", json=payload)
    assert resp.status_code == 422


def test_create_skill_name_starting_with_dash_invalid(skills_client):
    client, _ = skills_client
    payload = {"name": "-bad", "description": "desc", "content": "body"}
    resp = client.post("/api/skills", json=payload)
    assert resp.status_code == 422


def test_create_skill_name_too_long_returns_422(skills_client):
    client, _ = skills_client
    long_name = "a" * 65
    payload = {"name": long_name, "description": "desc", "content": "body"}
    resp = client.post("/api/skills", json=payload)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /api/skills/{name} — update
# ---------------------------------------------------------------------------

def test_update_skill_success(skills_client, make_skill):
    client, repo = skills_client
    make_skill(repo, "editable", "Old description", "Old content.")
    payload = {"description": "New description", "content": "New content."}
    resp = client.put("/api/skills/editable", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "New description"
    assert data["content"] == "New content."
    # Durability: the change is reflected on a fresh read.
    assert client.get("/api/skills/editable").json()["description"] == "New description"


def test_update_skill_not_found_returns_404(skills_client):
    client, _ = skills_client
    payload = {"description": "desc", "content": "body"}
    resp = client.put("/api/skills/nonexistent", json=payload)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/skills/{name} — delete
# ---------------------------------------------------------------------------

def test_delete_skill_success(skills_client, make_skill):
    client, repo = skills_client
    make_skill(repo, "to-delete")
    resp = client.delete("/api/skills/to-delete")
    assert resp.status_code == 204
    # Durability: a subsequent fetch returns not-found from the store.
    assert client.get("/api/skills/to-delete").status_code == 404


def test_delete_skill_not_found_returns_404(skills_client):
    client, _ = skills_client
    resp = client.delete("/api/skills/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Name validation prevents path-traversal-style ids
# ---------------------------------------------------------------------------

def test_create_skill_path_traversal_rejected(skills_client):
    client, _ = skills_client
    # Dots are not in the allowed character set so the name regex rejects this.
    payload = {"name": "../etc", "description": "desc", "content": "body"}
    resp = client.post("/api/skills", json=payload)
    assert resp.status_code == 422


def test_get_skill_path_traversal_rejected(skills_client):
    client, _ = skills_client
    resp = client.get("/api/skills/../etc/passwd")
    # FastAPI URL routing normalises ../ in paths, so it 404s rather than serve a file.
    assert resp.status_code in (404, 400, 422)
