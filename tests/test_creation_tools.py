"""Contracts for optional owner-bound definition-creation tools."""

import asyncio
import inspect

import user_data
from app_context import build_tool_instances, function_tool_registry
from definition_creation import AgentCreationRequest


def _run(coro):
    return asyncio.run(coro)


def _by_name(tools):
    return {getattr(tool, "name", None) or tool.__name__: tool for tool in tools}


def test_creation_tools_are_registered_but_never_implicitly_granted():
    registry = function_tool_registry()
    assert "create_skill" in registry
    assert "create_agent" in registry
    assert "edit_skill" in registry
    assert "edit_agent" in registry
    assert "durable user-owned skill" in registry["create_skill"].description
    assert "durable user-owned custom agent" in registry["create_agent"].description

    assert _by_name(build_tool_instances(set(), session_id="s", user_id="user-a")) == {}
    assert set(_by_name(build_tool_instances({"create_skill"}, session_id="s", user_id="user-a"))) == {"create_skill"}
    assert set(_by_name(build_tool_instances({"create_agent"}, session_id="s", user_id="user-a"))) == {"create_agent"}
    assert set(_by_name(build_tool_instances(
        {"create_skill", "create_agent"}, session_id="s", user_id="user-a"
    ))) == {"create_skill", "create_agent"}
    assert set(_by_name(build_tool_instances(
        {"edit_skill", "edit_agent"}, session_id="s", user_id="user-a"
    ))) == {"edit_skill", "edit_agent"}


def test_creation_tool_schemas_do_not_expose_owner_authority():
    tools = _by_name(build_tool_instances(
        {"create_skill", "create_agent"}, session_id="s", user_id="user-a"
    ))
    for tool in tools.values():
        parameter_names = set(inspect.signature(tool).parameters)
        assert not parameter_names & {"user_id", "owner", "owner_id", "tenant_id"}


def test_create_skill_tool_uses_immutable_bound_owner():
    tool = _by_name(build_tool_instances(
        {"create_skill"}, session_id="s", user_id="user-a"
    ))["create_skill"]

    result = _run(tool("tool-skill", "A tool-created skill.", "Private instructions."))

    assert result == {
        "status": "created",
        "kind": "skill",
        "id": "tool-skill",
        "name": "tool-skill",
        "message": "Created skill 'tool-skill'.",
    }


def test_unbound_creation_tool_returns_sanitized_unauthorized_result():
    tool = _by_name(build_tool_instances(
        {"create_skill"}, session_id="discovery", user_id=""
    ))["create_skill"]

    result = _run(tool("tool-skill", "description", "content"))

    assert result == {
        "status": "error",
        "kind": "skill",
        "code": "unauthorized",
        "message": "An authenticated user is required to create a skill.",
        "retryable": False,
    }


def test_create_agent_tool_has_complete_schema_and_independent_grant():
    tool = _by_name(build_tool_instances(
        {"create_agent"}, session_id="s", user_id="user-a"
    ))["create_agent"]
    assert set(inspect.signature(tool).parameters) == {
        "id", "name", "description", "group", "systemPrompt", "tools", "skills",
        "mcpServers", "useSearchContext", "icon", "starters", "temperature", "agentsAsTools",
    }

    result = _run(tool(id="created-agent", name="Created Agent", systemPrompt="Help the user."))
    assert result["status"] == "created"
    assert result["kind"] == "agent"
    assert "systemPrompt" not in result
    assert _run(user_data.get_custom_agents_repository().get("user-a", "created-agent")) is not None


def test_create_agent_nested_capabilities_have_explicit_json_schemas():
    schema = AgentCreationRequest.model_json_schema()
    definitions = schema["$defs"]

    assert set(definitions["StarterQuestionRequest"]["required"]) == {"label", "message"}
    assert set(definitions["HttpMcpServerRequest"]["required"]) == {"name", "url"}
    agent_ref_schema = definitions["AgentToolRefRequest"]["properties"]["agentRef"]
    assert agent_ref_schema["discriminator"]["propertyName"] == "kind"


def test_edit_tools_update_only_bound_owner_definitions():
    tools = _by_name(build_tool_instances(
        {"create_skill", "edit_skill", "create_agent", "edit_agent"},
        session_id="s",
        user_id="user-a",
    ))

    assert _run(tools["create_skill"]("editable-skill", "Original", "Original content"))["status"] == "created"
    skill_result = _run(tools["edit_skill"]("editable-skill", "Updated", "Updated content"))
    assert skill_result["status"] == "updated"
    assert _run(user_data.get_user_skills_repository().get(
        "user-a", "editable-skill"
    ))["content"] == "Updated content"

    assert _run(tools["create_agent"](
        id="editable-agent", name="Original Agent", systemPrompt="Original prompt."
    ))["status"] == "created"
    agent_result = _run(tools["edit_agent"](
        id="editable-agent", name="Updated Agent", systemPrompt="Updated prompt.",
        skills=["editable-skill"],
    ))
    assert agent_result["status"] == "updated"
    stored_agent = _run(user_data.get_custom_agents_repository().get("user-a", "editable-agent"))
    assert stored_agent["name"] == "Updated Agent"
    assert stored_agent["systemPrompt"] == "Updated prompt."
    assert stored_agent["skills"] == ["editable-skill"]

    missing_skill = _run(tools["edit_skill"]("missing-skill", "Missing", "Missing"))
    missing_agent = _run(tools["edit_agent"](
        id="missing-agent", name="Missing", systemPrompt="Missing."
    ))
    assert missing_skill["code"] == "not_found"
    assert missing_agent["code"] == "not_found"

    other_tools = _by_name(build_tool_instances(
        {"edit_skill", "edit_agent"}, session_id="other", user_id="user-b"
    ))
    assert _run(other_tools["edit_skill"](
        "editable-skill", "Foreign edit", "Foreign content"
    ))["code"] == "not_found"
    assert _run(other_tools["edit_agent"](
        id="editable-agent", name="Foreign edit", systemPrompt="Foreign prompt."
    ))["code"] == "not_found"
    assert _run(user_data.get_user_skills_repository().get(
        "user-a", "editable-skill"
    ))["content"] == "Updated content"
    assert _run(user_data.get_custom_agents_repository().get(
        "user-a", "editable-agent"
    ))["name"] == "Updated Agent"


def test_expected_error_envelopes_are_bounded_and_non_destructive(monkeypatch):
    skill_tool = _by_name(build_tool_instances(
        {"create_skill"}, session_id="s", user_id="user-a"
    ))["create_skill"]

    invalid = _run(skill_tool("Bad Name", "", ""))
    assert invalid["code"] == "validation_error"
    assert invalid["retryable"] is False
    assert invalid["issues"]

    assert _run(skill_tool("duplicate-skill", "description", "original"))["status"] == "created"
    duplicate = _run(skill_tool("duplicate-skill", "description", "replacement"))
    assert duplicate == {
        "status": "error",
        "kind": "skill",
        "code": "duplicate",
        "message": "A skill named 'duplicate-skill' already exists.",
        "retryable": False,
    }
    assert _run(user_data.get_user_skills_repository().get(
        "user-a", "duplicate-skill"
    ))["content"] == "original"

    class FailingRepository:
        async def create(self, *_args, **_kwargs):
            raise RuntimeError("provider token=SECRET connection=PRIVATE")

    monkeypatch.setattr(user_data, "_user_skills_repo", FailingRepository())
    unavailable = _run(skill_tool("store-failure", "description", "private content"))
    assert unavailable["code"] == "temporarily_unavailable"
    assert unavailable["retryable"] is True
    assert "SECRET" not in str(unavailable)
    assert "PRIVATE" not in str(unavailable)