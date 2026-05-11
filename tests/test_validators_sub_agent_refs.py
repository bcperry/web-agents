"""Tests for validate_sub_agent_tool_refs (feature 008)."""

from __future__ import annotations

from typing import Any, Optional

from prompt_config import (
    AgentProfile,
    BuiltinAgentRef,
    CustomAgentRef,
    SubAgentToolRef,
)
from validators import validate_sub_agent_tool_refs


def _resolver(table: dict[tuple[str, str], Any]):
    def resolve(kind: str, target_id: str) -> Optional[Any]:
        return table.get((kind, target_id))
    return resolve


def _profile(agents_as_tools: list[SubAgentToolRef] | None = None) -> AgentProfile:
    return AgentProfile(
        name="X",
        logical_profile="x",
        system_prompt="prompt",
        description="desc",
        tool_names=[],
        agents_as_tools=agents_as_tools or [],
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_refs_produce_no_errors() -> None:
    refs = [SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="child"))]
    errors = validate_sub_agent_tool_refs(
        parent_id="parent",
        refs=refs,
        resolve_target=_resolver({("builtin", "child"): _profile()}),
    )
    assert errors == []


def test_empty_refs_produce_no_errors() -> None:
    assert validate_sub_agent_tool_refs("parent", [], _resolver({})) == []


# ---------------------------------------------------------------------------
# V1 unresolved_agent_ref
# ---------------------------------------------------------------------------


def test_v1_unresolved_target() -> None:
    refs = [SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="ghost"))]
    errors = validate_sub_agent_tool_refs("parent", refs, _resolver({}))
    assert len(errors) == 1
    assert errors[0].code == "unresolved_agent_ref"
    assert "ghost" in errors[0].message


def test_v1_missing_agent_ref_field() -> None:
    refs = [{"foo": "bar"}]  # raw dict missing agent_ref
    errors = validate_sub_agent_tool_refs("parent", refs, _resolver({}))
    assert len(errors) == 1
    assert errors[0].code == "unresolved_agent_ref"


# ---------------------------------------------------------------------------
# V2 self_reference
# ---------------------------------------------------------------------------


def test_v2_self_reference_builtin() -> None:
    refs = [SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="parent"))]
    errors = validate_sub_agent_tool_refs(
        "parent", refs, _resolver({("builtin", "parent"): _profile()})
    )
    assert len(errors) == 1
    assert errors[0].code == "self_reference"


def test_v2_self_reference_custom_via_raw_payload() -> None:
    refs = [{
        "agentRef": {
            "kind": "custom",
            "customAgentId": "abc-123",
            "definition": {"id": "abc-123"},
        }
    }]
    errors = validate_sub_agent_tool_refs("abc-123", refs, _resolver({}))
    # self_reference triggers before unresolved (cheaper / more specific)
    assert len(errors) == 1
    assert errors[0].code == "self_reference"


# ---------------------------------------------------------------------------
# V3 direct_cycle
# ---------------------------------------------------------------------------


def test_v3_direct_cycle_detected() -> None:
    # Target B already references parent A
    target_b = _profile([SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="A"))])
    refs = [SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="B"))]
    errors = validate_sub_agent_tool_refs(
        "A", refs, _resolver({("builtin", "B"): target_b})
    )
    assert len(errors) == 1
    assert errors[0].code == "direct_cycle"


def test_v3_no_cycle_when_target_has_no_back_ref() -> None:
    target_b = _profile([])
    refs = [SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="B"))]
    errors = validate_sub_agent_tool_refs(
        "A", refs, _resolver({("builtin", "B"): target_b})
    )
    assert errors == []


def test_v3_direct_cycle_via_dict_target() -> None:
    """Target may be a raw dict (custom-agent inlined definition path)."""
    target_b = {
        "id": "B",
        "agentsAsTools": [{"agentRef": {"kind": "custom", "customAgentId": "A"}}],
    }
    refs = [{"agentRef": {"kind": "custom", "customAgentId": "B", "definition": {"id": "B"}}}]
    errors = validate_sub_agent_tool_refs("A", refs, _resolver({("custom", "B"): target_b}))
    assert len(errors) == 1
    assert errors[0].code == "direct_cycle"


# ---------------------------------------------------------------------------
# V4 duplicate_target
# ---------------------------------------------------------------------------


def test_v4_duplicate_target_blocks() -> None:
    refs = [
        SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="child")),
        SubAgentToolRef(agent_ref=BuiltinAgentRef(profile_id="child")),
    ]
    errors = validate_sub_agent_tool_refs(
        "parent", refs, _resolver({("builtin", "child"): _profile()})
    )
    assert len(errors) == 1
    assert errors[0].code == "duplicate_target"
    assert errors[0].field == "agentsAsTools[1].agentRef"


# ---------------------------------------------------------------------------
# V5 definition_id_mismatch
# ---------------------------------------------------------------------------


def test_v5_definition_id_mismatch() -> None:
    refs = [{
        "agentRef": {
            "kind": "custom",
            "customAgentId": "real-id",
            "definition": {"id": "tampered"},
        }
    }]
    errors = validate_sub_agent_tool_refs("parent", refs, _resolver({}))
    assert len(errors) == 1
    assert errors[0].code == "definition_id_mismatch"


def test_v5_matching_ids_pass_through_to_resolution() -> None:
    refs = [{
        "agentRef": {
            "kind": "custom",
            "customAgentId": "x",
            "definition": {"id": "x"},
        }
    }]
    target = {"id": "x", "agentsAsTools": []}
    errors = validate_sub_agent_tool_refs("parent", refs, _resolver({("custom", "x"): target}))
    assert errors == []


# ---------------------------------------------------------------------------
# Cross-rule: dataclass and dict shapes are interchangeable
# ---------------------------------------------------------------------------


def test_dataclass_custom_ref_resolves() -> None:
    refs = [SubAgentToolRef(agent_ref=CustomAgentRef(custom_agent_id="x", definition={"id": "x"}))]
    target = {"id": "x", "agentsAsTools": []}
    errors = validate_sub_agent_tool_refs("parent", refs, _resolver({("custom", "x"): target}))
    assert errors == []
