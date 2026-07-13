"""Focused contracts for durable skill and custom-agent creation services."""

import asyncio

import pytest
from pydantic import ValidationError

from definition_creation import (
    AgentCreationRequest,
    AgentCreationService,
    SkillCreationRequest,
    SkillCreationService,
)
from tests._doubles import InMemoryByIdRepository, InMemoryUserScopedRepository


def _run(coro):
    return asyncio.run(coro)


def test_skill_creation_is_bounded_durable_and_owner_scoped():
    global_repo = InMemoryByIdRepository()
    user_repo = InMemoryUserScopedRepository()
    request = SkillCreationRequest(
        name="incident-summary",
        description="Summarize incident notes.",
        content="# Incident Summary\nFull private instructions.",
    )

    result = _run(SkillCreationService("user-a", global_repo, user_repo).create(request))

    assert result.model_dump(exclude_none=True) == {
        "status": "created",
        "kind": "skill",
        "id": "incident-summary",
        "name": "incident-summary",
        "message": "Created skill 'incident-summary'.",
    }
    stored = _run(user_repo.get("user-a", "incident-summary"))
    assert stored["content"] == request.content
    assert _run(user_repo.get("user-b", "incident-summary")) is None


def test_skill_creation_rejects_invalid_and_global_or_owner_duplicates_without_overwrite():
    global_repo = InMemoryByIdRepository([{"id": "global-name", "description": "global"}])
    user_repo = InMemoryUserScopedRepository()
    service = SkillCreationService("user-a", global_repo, user_repo)

    invalid = _run(service.create(SkillCreationRequest(name="Bad Name", description="", content="")))
    assert invalid.code == "validation_error"
    assert invalid.retryable is False
    assert {issue.field for issue in invalid.issues} == {"name", "description", "content"}
    assert _run(user_repo.list_for_user("user-a")) == []

    global_duplicate = _run(service.create(SkillCreationRequest(
        name="global-name", description="description", content="content"
    )))
    assert global_duplicate.code == "duplicate"

    original_request = SkillCreationRequest(name="owned", description="first", content="original")
    assert _run(service.create(original_request)).status == "created"
    duplicate = _run(service.create(SkillCreationRequest(
        name="owned", description="second", content="replacement"
    )))
    assert duplicate.code == "duplicate"
    assert _run(user_repo.get("user-a", "owned"))["content"] == "original"


def test_agent_creation_applies_defaults_and_strict_capability_validation():
    custom_repo = InMemoryUserScopedRepository()
    global_skills = InMemoryByIdRepository([{
        "id": "table-usage", "description": "Tables", "content": "Use tables."
    }])
    user_skills = InMemoryUserScopedRepository()
    service = AgentCreationService(
        "user-a", custom_repo=custom_repo, global_skills_repo=global_skills,
        user_skills_repo=user_skills,
    )

    bad = _run(service.create(AgentCreationRequest(
        id="planner", name="Planner", systemPrompt="Plan.", tools=["missing-tool"]
    )))
    assert bad.code == "validation_error"
    assert bad.issues[0].field == "tools[0]"
    assert _run(custom_repo.list_for_user("user-a")) == []

    result = _run(service.create(AgentCreationRequest(
        id="planner", name="Planner", systemPrompt="Plan.", skills=["table-usage"]
    )))
    assert result.status == "created"
    stored = _run(custom_repo.get("user-a", "planner"))
    assert stored["id"] == "planner"
    assert stored["tools"] == []
    assert stored["skills"] == ["table-usage"]
    assert stored["mcpServers"] == []
    assert stored["agentsAsTools"] == []
    assert stored["useSearchContext"] is False
    assert stored["temperature"] == 0.2
    assert stored["source"] == "custom"
    assert stored["createdAt"] == stored["updatedAt"]


def test_agent_creation_persists_complete_canonical_definition():
    custom_repo = InMemoryUserScopedRepository()
    global_skills = InMemoryByIdRepository([{
        "id": "table-usage", "description": "Tables", "content": "Use tables."
    }])
    result = _run(AgentCreationService(
        "user-a", custom_repo=custom_repo, global_skills_repo=global_skills,
        user_skills_repo=InMemoryUserScopedRepository(),
    ).create(AgentCreationRequest(
        id="complete-agent",
        name="Complete Agent",
        description="Exercises every supported field.",
        group="Operations",
        systemPrompt="Always follow the complete operating procedure.",
        tools=["create_skill"],
        skills=["table-usage"],
        mcpServers=[{
            "name": "operations", "transport": "http", "url": "https://example.test/mcp",
            "authenticated": True, "authScope": "api://operations/.default",
        }],
        useSearchContext=True,
        icon="/icons/custom.svg",
        starters=[{"label": "Summarize", "message": "Summarize the current situation."}],
        temperature=0.4,
    )))

    assert result.status == "created"
    stored = _run(custom_repo.get("user-a", "complete-agent"))
    assert stored["name"] == "Complete Agent"
    assert stored["description"] == "Exercises every supported field."
    assert stored["group"] == "Operations"
    assert stored["systemPrompt"] == "Always follow the complete operating procedure."
    assert stored["tools"] == ["create_skill"]
    assert stored["skills"] == ["table-usage"]
    assert stored["mcpServers"] == [{
        "name": "operations", "transport": "http", "url": "https://example.test/mcp",
        "authenticated": True, "authScope": "api://operations/.default",
    }]
    assert stored["useSearchContext"] is True
    assert stored["icon"] == "/icons/custom.svg"
    assert stored["starters"] == [{
        "label": "Summarize", "message": "Summarize the current situation."
    }]
    assert stored["temperature"] == 0.4
    assert stored["agentsAsTools"] == []


def test_agent_creation_rejects_malformed_starter_questions():
    with pytest.raises(ValidationError) as invalid:
        AgentCreationRequest(
            id="bad-starters",
            name="Bad Starters",
            systemPrompt="Help.",
            starters=[{"title": "Undefined", "prompt": "Wrong keys"}],
        )
    assert {error["loc"][-1] for error in invalid.value.errors()} >= {"label", "message"}


def test_agent_creation_rejects_non_http_mcp_servers_at_the_schema_boundary():
    with pytest.raises(ValidationError) as invalid:
        AgentCreationRequest(
            id="unsafe-mcp",
            name="Unsafe MCP",
            systemPrompt="Help.",
            mcpServers=[{"name": "unsafe", "transport": "stdio"}],
        )

    assert {error["loc"][-1] for error in invalid.value.errors()} >= {"transport", "url"}


def test_agent_creation_duplicate_is_non_destructive_and_cross_owner_ids_are_independent():
    repo = InMemoryUserScopedRepository()
    request = AgentCreationRequest(id="planner", name="Planner", systemPrompt="Plan.")

    first = _run(AgentCreationService("user-a", custom_repo=repo).create(request))
    second = _run(AgentCreationService("user-a", custom_repo=repo).create(
        AgentCreationRequest(id="planner", name="Replacement", systemPrompt="Replace.")
    ))
    other_owner = _run(AgentCreationService("user-b", custom_repo=repo).create(request))

    assert first.status == "created"
    assert second.code == "duplicate"
    assert other_owner.status == "created"
    assert _run(repo.get("user-a", "planner"))["name"] == "Planner"


def test_agent_creation_rejects_temperature_mcp_self_cycle_and_cross_owner_delegates():
    custom_repo = InMemoryUserScopedRepository()
    _run(custom_repo.create("user-b", "foreign", {
        "id": "foreign", "name": "Foreign", "systemPrompt": "Private."
    }))
    _run(custom_repo.create("user-a", "cycle-target", {
        "id": "cycle-target",
        "name": "Cycle Target",
        "systemPrompt": "Target.",
        "agentsAsTools": [{"agentRef": {"kind": "custom", "customAgentId": "parent"}}],
    }))
    service = AgentCreationService("user-a", custom_repo=custom_repo)
    request = AgentCreationRequest(
        id="parent",
        name="Parent",
        systemPrompt="Coordinate.",
        temperature=2.5,
        agentsAsTools=[
            {"agentRef": {"kind": "custom", "customAgentId": "parent"}},
            {"agentRef": {"kind": "custom", "customAgentId": "foreign"}},
            {"agentRef": {"kind": "custom", "customAgentId": "cycle-target"}},
        ],
    )

    result = _run(service.create(request))

    assert result.code == "validation_error"
    fields = {issue.field for issue in result.issues}
    assert "temperature" in fields
    assert "agentsAsTools[0].agentRef" in fields
    assert "agentsAsTools[1].agentRef" in fields
    assert "agentsAsTools[2].agentRef" in fields
    assert _run(custom_repo.get("user-a", "parent")) is None


def test_storage_failures_are_sanitized_and_log_only_exception_class(caplog):
    class FailingRepository(InMemoryUserScopedRepository):
        async def create(self, *_args, **_kwargs):
            raise RuntimeError("credential=SECRET full private content")

    service = SkillCreationService(
        "user-a", InMemoryByIdRepository(), FailingRepository()
    )

    result = _run(service.create(SkillCreationRequest(
        name="safe-id", description="description", content="private content"
    )))

    assert result.code == "temporarily_unavailable"
    assert result.retryable is True
    assert "SECRET" not in result.message
    assert "SECRET" not in caplog.text
    assert "private content" not in caplog.text
    assert "RuntimeError" in caplog.text
