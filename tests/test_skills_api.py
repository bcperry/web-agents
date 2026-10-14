"""Observable skill catalog workflows and authorization boundaries."""

import asyncio
from unittest.mock import Mock

from agent_framework import SkillsSourceContext

from agent_factory import CosmosSkillsSource
from app_context import build_tool_instances
from auth import AuthenticatedUser, get_current_user
from main import app


def test_catalog_lifecycle_preserves_changes_and_rejects_duplicate_creation(skills_client):
    client, _ = skills_client
    assert client.get("/api/skills").json()["skills"] == []
    original = {"name": "workflow-skill", "description": "Guidance", "content": "Original instructions"}
    assert client.post("/api/skills", json=original).status_code == 201
    assert client.get("/api/skills/workflow-skill").json()["content"] == original["content"]
    assert {skill["name"] for skill in client.get("/api/skills").json()["skills"]} == {original["name"]}

    revised = {"description": "Revised guidance", "content": "Revised instructions"}
    assert client.post("/api/skills", json={**original, **revised}).status_code == 409
    assert client.get("/api/skills/workflow-skill").json()["content"] == original["content"]
    assert client.put("/api/skills/workflow-skill", json=revised).status_code == 200
    saved = client.get("/api/skills/workflow-skill").json()
    assert {key: saved[key] for key in revised} == revised

    assert client.delete("/api/skills/workflow-skill").status_code == 204
    assert client.get("/api/skills").json()["skills"] == []
    assert client.get("/api/skills/workflow-skill").status_code == 404
    assert client.put("/api/skills/workflow-skill", json=revised).status_code == 404
    assert client.delete("/api/skills/workflow-skill").status_code == 404


def test_private_skills_remain_owner_scoped_from_creation_through_agent_loading(client, monkeypatch):
    create_skill = next(tool for tool in build_tool_instances(
        {"create_skill"}, session_id="skill-workflow", user_id="dev-user",
    ) if tool.__name__ == "create_skill")
    assert asyncio.run(create_skill("private-skill", "Private guidance", "Private instructions"))["status"] == "created"
    assert client.get("/api/skills/private-skill").json()["scope"] == "user"
    revised = {"description": "Updated guidance", "content": "Updated private instructions"}
    assert client.put("/api/skills/private-skill", json=revised).status_code == 200

    owner_skills = asyncio.run(CosmosSkillsSource("dev-user").get_skills(SkillsSourceContext(agent=Mock())))
    assert next(skill for skill in owner_skills if skill.frontmatter.name == "private-skill").instructions == revised["content"]
    with monkeypatch.context() as context:
        context.setitem(app.dependency_overrides, get_current_user, lambda: AuthenticatedUser("other", "other"))
        assert "private-skill" not in {skill["name"] for skill in client.get("/api/skills").json()["skills"]}
        assert client.get("/api/skills/private-skill").status_code == 404
        assert client.put("/api/skills/private-skill", json=revised).status_code == 404
        assert client.delete("/api/skills/private-skill").status_code == 404
        other_skills = asyncio.run(CosmosSkillsSource("other").get_skills(SkillsSourceContext(agent=Mock())))
        assert "private-skill" not in {skill.frontmatter.name for skill in other_skills}

    assert client.get("/api/skills/private-skill").json()["content"] == revised["content"]
    assert client.delete("/api/skills/private-skill").status_code == 204


def test_rejected_writes_neither_publish_invalid_skills_nor_destroy_existing_content(skills_client):
    client, _ = skills_client
    valid = {"name": "valid-skill", "description": "Guidance", "content": "Keep these instructions"}
    assert client.post("/api/skills", json=valid).status_code == 201
    for invalid_name in ("../escape", "Bad-Name", "a" * 65):
        assert client.post("/api/skills", json={**valid, "name": invalid_name}).status_code == 422
    for invalid_fields in ({"description": ""}, {"description": "d" * 257}, {"content": ""}, {"content": "c" * 65537}):
        assert client.post("/api/skills", json={**valid, "name": "invalid-skill", **invalid_fields}).status_code == 422
        assert client.put("/api/skills/valid-skill", json={**valid, **invalid_fields}).status_code == 422
    assert {skill["name"] for skill in client.get("/api/skills").json()["skills"]} == {"valid-skill"}
    assert client.get("/api/skills/valid-skill").json()["content"] == valid["content"]
