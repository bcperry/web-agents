"""Skill publishing and selection workflows; no assertions about instructional prose."""

import asyncio
from unittest.mock import AsyncMock, Mock

from agent_framework import ChatResponse, Content, Message, SkillsSourceContext
from agent_framework.openai import OpenAIChatClient

from agent_factory import CosmosSkillsSource, _build_skills_provider
from prompt_config import load_agent_profile, load_agents_yaml


def test_configured_skills_are_available_to_the_agent(client):
    skills = asyncio.run(CosmosSkillsSource().get_skills(SkillsSourceContext(agent=Mock())))
    runtime_skills = {skill.frontmatter.name: skill for skill in skills}
    assert runtime_skills
    for profile_id in load_agents_yaml()["profiles"]:
        profile = load_agent_profile(profile_id)
        for name in profile.skills:
            response = client.get(f"/api/skills/{name}")
            assert response.status_code == 200, (profile_id, name)
            content = response.json()["content"]
            assert content.strip(), (profile_id, name)
            assert runtime_skills[name].instructions == content


def test_published_skill_edits_and_deletion_reach_selected_agents(client, monkeypatch):
    payload = {"name": "workflow-skill", "description": "Workflow guidance", "content": "Original instructions"}
    assert client.post("/api/skills", json=payload).status_code == 201
    assert client.post("/api/skills", json={**payload, "name": "unselected-skill"}).status_code == 201
    model = OpenAIChatClient(model="offline", api_key="offline", base_url="https://example.invalid/v1")
    reply = AsyncMock(return_value=ChatResponse(messages=[
        Message(role="assistant", contents=[Content.from_text("Done")]),
    ]))
    monkeypatch.setattr(model, "get_response", reply)

    for instructions in ("Original instructions", "Revised instructions"):
        assert client.put("/api/skills/workflow-skill", json={
            "description": payload["description"], "content": instructions,
        }).status_code == 200
        agent = model.as_agent(context_providers=[_build_skills_provider(["workflow-skill", "missing-skill"])])
        asyncio.run(agent.run("Use the selected skill", stream=False))
        options = reply.call_args.kwargs["options"]
        assert "workflow-skill" in options["instructions"]
        assert "unselected-skill" not in options["instructions"]
        assert "missing-skill" not in options["instructions"]
        load_skill = next(tool for tool in options["tools"] if tool.name == "load_skill")
        loaded = asyncio.run(load_skill.invoke(arguments={"skill_name": "workflow-skill"}))
        assert instructions in Message(role="tool", contents=loaded).text

    assert client.delete("/api/skills/workflow-skill").status_code == 204
    agent = model.as_agent(context_providers=[_build_skills_provider(["workflow-skill"])])
    asyncio.run(agent.run("Use the selected skill", stream=False))
    assert "workflow-skill" not in (reply.call_args.kwargs["options"].get("instructions") or "")
