"""Tests for sub-agent tool wiring in agent_factory (feature 008, US1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

import agent_factory
from prompt_config import (
    AgentProfile,
    BuiltinAgentRef,
    CustomAgentRef,
    SubAgentToolRef,
)


# ---------------------------------------------------------------------------
# Fakes / fixtures
# ---------------------------------------------------------------------------


@dataclass
class _FakeSession:
    pass


class _FakeTool:
    """Stand-in for an agent_framework FunctionTool."""

    def __init__(self, name: str, description: str, arg_name: str, arg_description: str | None) -> None:
        self.name = name
        self.description = description
        self.arg_name = arg_name
        self.arg_description = arg_description


class _FakeAgent:
    """Minimal fake of agent_framework.Agent that records as_tool calls."""

    raise_on_as_tool: bool = False

    def __init__(self, name: str, instructions: str, description: str, default_options: dict | None = None) -> None:
        self.name = name
        self.instructions = instructions
        self.description = description
        self.default_options = default_options or {}
        self.context_providers: list[Any] = []

    def as_tool(self, *, name: str, description: str, arg_name: str = "task", arg_description: str | None = None, **_: Any) -> _FakeTool:
        if type(self).raise_on_as_tool:
            raise RuntimeError("simulated as_tool failure")
        return _FakeTool(name=name, description=description, arg_name=arg_name, arg_description=arg_description)

    def create_session(self) -> _FakeSession:
        return _FakeSession()


class _FakeClient:
    """Stand-in for OpenAIChatClient that returns _FakeAgent instances."""

    def __init__(self) -> None:
        self.as_agent_calls: list[dict[str, Any]] = []

    def as_agent(
        self,
        *,
        name: str,
        instructions: str,
        description: str = "",
        tools: list[Any] | None = None,
        default_options: dict | None = None,
        context_providers: list[Any] | None = None,
        **_: Any,
    ) -> _FakeAgent:
        self.as_agent_calls.append({
            "name": name,
            "instructions": instructions,
            "description": description,
            "tools": tools or [],
            "default_options": default_options or {},
            "context_providers": context_providers or [],
        })
        agent = _FakeAgent(name=name, instructions=instructions, description=description, default_options=default_options)
        agent.context_providers = context_providers or []
        return agent


@pytest.fixture
def fake_clients(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    """Replace OpenAI client construction so tests run offline."""
    client = _FakeClient()
    monkeypatch.setattr(agent_factory, "_build_openai_clients", lambda: (client, client))
    monkeypatch.setattr(agent_factory, "_build_context_providers", lambda **_: [])
    # Reset class-level error-injection switch between tests.
    _FakeAgent.raise_on_as_tool = False
    return client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _builtin_profile_loader(profiles: dict[str, AgentProfile]):
    def loader(chat_profile: str | None = None, workspace_root: Any = None) -> AgentProfile:
        if chat_profile in profiles:
            return profiles[chat_profile]
        raise ValueError(f"profile not found: {chat_profile}")
    return loader


# ---------------------------------------------------------------------------
# T011 — wrap-via-as_tool tests
# ---------------------------------------------------------------------------


def test_no_sub_agent_refs_produces_no_extra_tools(fake_clients: _FakeClient) -> None:
    runtime = agent_factory.create_chat_runtime(
        custom_name="Parent",
        custom_instructions="You are the parent.",
    )
    assert runtime.sub_agent_tool_names == []
    assert runtime.tools == []


@pytest.mark.parametrize("override", [False, True])
def test_profile_delegate_defaults_and_overrides_are_not_mutated(fake_clients, monkeypatch, override):
    default_ref = SubAgentToolRef(agent_ref=CustomAgentRef(
        custom_agent_id="default", definition={"name": "Default", "systemPrompt": "Help."},
    ))
    override_ref = SubAgentToolRef(agent_ref=CustomAgentRef(
        custom_agent_id="override", definition={"name": "Override", "systemPrompt": "Help."},
    ))
    profile = AgentProfile(name="Parent", logical_profile="parent", system_prompt="Coordinate.",
                           description="Parent", tool_names=[], agents_as_tools=[default_ref])
    monkeypatch.setattr(agent_factory, "load_agent_profile", _builtin_profile_loader({"parent": profile}))
    supplied = (override_ref,) if override else ()

    runtime = agent_factory.create_chat_runtime(chat_profile="parent", agents_as_tools=supplied)

    assert runtime.sub_agent_tool_names == (["override"] if override else ["default"])
    assert profile.agents_as_tools == [default_ref]
    assert supplied == ((override_ref,) if override else ())


def test_delegate_does_not_shadow_parent_function(fake_clients: _FakeClient) -> None:
    def get_user_profile():
        return {}

    runtime = agent_factory.create_chat_runtime(
        custom_name="Parent", custom_instructions="Coordinate.",
        function_tools=[get_user_profile],
        agents_as_tools=[SubAgentToolRef(agent_ref=CustomAgentRef(
            custom_agent_id="child",
            definition={"name": "Get User Profile", "systemPrompt": "Help."},
        ))],
    )

    assert runtime.tools[0] is get_user_profile
    assert runtime.sub_agent_tool_names == ["get_user_profile_2"]
    assert runtime.tools[1].name == "get_user_profile_2"


def test_builtin_sub_agent_ref_is_wrapped_via_as_tool(
    fake_clients: _FakeClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = AgentProfile(
        name="Azure Government Specialist",
        logical_profile="azgov",
        system_prompt="You are an Azure Government specialist.",
        description="Specialist for Azure Government cloud questions.",
        tool_names=[],
    )
    monkeypatch.setattr(agent_factory, "load_agent_profile", _builtin_profile_loader({"azgov": target}))

    runtime = agent_factory.create_chat_runtime(
        custom_name="Parent",
        custom_instructions="You coordinate.",
        agents_as_tools=[SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="azgov"))],
    )

    assert runtime.sub_agent_tool_names == ["azure_government_specialist"]
    assert len(runtime.tools) == 1
    tool = runtime.tools[0]
    assert isinstance(tool, _FakeTool)
    assert tool.name == "azure_government_specialist"
    assert tool.description == "Specialist for Azure Government cloud questions."
    assert tool.arg_name == "request"
    assert "azure_government_specialist" in tool.arg_description


@pytest.mark.parametrize("temperature, options", [
    (0.7, {"temperature": 0.7}),
    ("0.7", {"temperature": 0.7}),
    ("invalid", {}),
    (None, {}),
])
def test_custom_sub_agent_ref_uses_inlined_definition(fake_clients: _FakeClient, temperature, options) -> None:
    custom_def = {
        "id": "blaine-bot",
        "name": "Blaine Bot",
        "description": "Be Blaine.",
        "systemPrompt": "You are Blaine.",
        "temperature": temperature,
    }
    runtime = agent_factory.create_chat_runtime(
        custom_name="Parent",
        custom_instructions="You coordinate.",
        agents_as_tools=[
            SubAgentToolRef(agent_ref=CustomAgentRef(custom_agent_id="blaine-bot", definition=custom_def)),
        ],
    )

    assert runtime.sub_agent_tool_names == ["blaine_bot"]
    assert len(fake_clients.as_agent_calls) == 2
    sub_call = next(c for c in fake_clients.as_agent_calls if c["instructions"] == "You are Blaine.")
    assert sub_call["default_options"] == options


def test_custom_sub_agent_receives_owner_bound_selected_skills(
    fake_clients: _FakeClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_provider = object()
    calls: list[tuple[list[str] | None, str | None]] = []

    def fake_skills_provider(skill_names=None, user_id=None):
        calls.append((skill_names, user_id))
        return sentinel_provider

    monkeypatch.setattr(agent_factory, "_build_skills_provider", fake_skills_provider)
    runtime = agent_factory.create_chat_runtime(
        custom_name="Parent",
        custom_instructions="Coordinate.",
        user_id="user-a",
        agents_as_tools=[SubAgentToolRef(agent_ref=CustomAgentRef(
            custom_agent_id="child",
            definition={
                "id": "child",
                "name": "Child",
                "systemPrompt": "Use the selected skill.",
                "skills": ["owner-skill", None, 7],
            },
        ))],
    )

    assert runtime.sub_agent_tool_names == ["child"]
    assert (["owner-skill"], "user-a") in calls
    child_call = next(call for call in fake_clients.as_agent_calls if call["instructions"] == "Use the selected skill.")
    assert child_call["context_providers"] == [sentinel_provider]


@pytest.mark.parametrize("with_resources", [False, True])
def test_builtin_delegate_receives_only_resolved_resources(fake_clients, monkeypatch, with_resources):
    target = AgentProfile(name="Child", logical_profile="child", system_prompt="Help.",
                          description="Child", tool_names=[], skills=["selected"], temperature=0)
    monkeypatch.setattr(agent_factory, "load_agent_profile", _builtin_profile_loader({"child": target}))
    search, skills, function_tool, mcp_tool = object(), object(), object(), object()
    monkeypatch.setattr(agent_factory, "get_search_context_provider", lambda: search)
    skill_requests = []

    def build_skills(names, user_id):
        skill_requests.append((names, user_id))
        return skills if names else None

    monkeypatch.setattr(agent_factory, "_build_skills_provider", build_skills)
    resources = {"child": agent_factory.SubAgentResources(
        function_tools=[function_tool], mcp_tools=[mcp_tool],
        skill_names=["selected"], enable_search_context=True,
    )} if with_resources else None
    agent_factory.create_chat_runtime(
        custom_name="Parent", custom_instructions="Coordinate.", user_id="owner",
        agents_as_tools=[SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="child"))],
        sub_agent_resources=resources,
    )

    child = fake_clients.as_agent_calls[0]
    assert child["default_options"] == {"temperature": 0}
    assert child["tools"] == ([function_tool, mcp_tool] if with_resources else [])
    assert child["context_providers"] == ([search, skills] if with_resources else [])
    assert skill_requests == [(["selected"] if with_resources else None, "owner")]


def test_disambiguates_colliding_derived_tool_names(
    fake_clients: _FakeClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two sub-agents whose names slugify identically must get distinct tool names."""
    target_a = AgentProfile(
        name="Specialist Agent",
        logical_profile="a",
        system_prompt="A",
        description="A desc",
        tool_names=[],
    )
    target_b = AgentProfile(
        name="specialist agent",  # slugifies to the same string
        logical_profile="b",
        system_prompt="B",
        description="B desc",
        tool_names=[],
    )
    monkeypatch.setattr(
        agent_factory, "load_agent_profile", _builtin_profile_loader({"a": target_a, "b": target_b})
    )

    runtime = agent_factory.create_chat_runtime(
        custom_name="Parent",
        custom_instructions="prompt",
        agents_as_tools=[
            SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="a")),
            SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="missing")),
            SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="b")),
        ],
    )

    assert runtime.sub_agent_tool_names == ["specialist_agent", "specialist_agent_2"]
    assert [tool.description for tool in runtime.tools] == ["A desc", "B desc"]


def test_orphaned_builtin_ref_is_skipped_not_fatal(
    fake_clients: _FakeClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reference to a missing profile must NOT crash the parent (FR-008)."""
    monkeypatch.setattr(agent_factory, "load_agent_profile", _builtin_profile_loader({}))

    runtime = agent_factory.create_chat_runtime(
        custom_name="Parent",
        custom_instructions="prompt",
        agents_as_tools=[SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="ghost"))],
    )

    assert runtime.sub_agent_tool_names == []
    assert runtime.tools == []


def test_orphaned_custom_ref_with_empty_prompt_is_skipped(fake_clients: _FakeClient) -> None:
    bad_def = {"id": "x", "name": "X", "description": "no prompt"}
    runtime = agent_factory.create_chat_runtime(
        custom_name="Parent",
        custom_instructions="prompt",
        agents_as_tools=[
            SubAgentToolRef(agent_ref=CustomAgentRef(custom_agent_id="x", definition=bad_def)),
        ],
    )
    assert runtime.sub_agent_tool_names == []


# ---------------------------------------------------------------------------
# T018 — error handling: as_tool failure
# ---------------------------------------------------------------------------


def test_as_tool_failure_does_not_crash_parent(
    fake_clients: _FakeClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If wrapping a sub-agent throws, parent runtime must still build (FR-009/SC-006)."""
    target = AgentProfile(
        name="Flaky", logical_profile="flaky",
        system_prompt="x", description="d", tool_names=[],
    )
    monkeypatch.setattr(agent_factory, "load_agent_profile", _builtin_profile_loader({"flaky": target}))
    _FakeAgent.raise_on_as_tool = True

    runtime = agent_factory.create_chat_runtime(
        custom_name="Parent",
        custom_instructions="prompt",
        agents_as_tools=[SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="flaky"))],
    )

    assert runtime.sub_agent_tool_names == []
    assert runtime.tools == []
