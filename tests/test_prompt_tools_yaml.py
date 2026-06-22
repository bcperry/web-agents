"""Validation tests for agents.yaml configuration schema."""

from pathlib import Path

import yaml


AGENTS_YAML_PATH = Path(__file__).resolve().parent.parent / "config" / "agents.yaml"
REQUIRED_PROFILES = {"sql", "search", "hybrid", "faa", "azure-gov", "drone", "orchestrator"}
REQUIRED_PROFILE_FIELDS = {"name", "description", "tools", "system_prompt"}


def _load_agents_yaml() -> dict:
    with AGENTS_YAML_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise AssertionError("agents.yaml must parse to a mapping")
    return data


def test_agents_yaml_exists() -> None:
    assert AGENTS_YAML_PATH.exists(), f"Expected agents config at {AGENTS_YAML_PATH}"


def test_agents_yaml_top_level_shape() -> None:
    payload = _load_agents_yaml()
    assert isinstance(payload.get("schema_version"), int), "schema_version must be an integer"
    assert isinstance(payload.get("description"), str) and payload["description"].strip(), "description must be non-empty"
    assert isinstance(payload.get("profiles"), dict) and payload["profiles"], "profiles must be a non-empty mapping"


def test_each_profile_has_required_fields() -> None:
    payload = _load_agents_yaml()
    profiles = payload["profiles"]

    for profile_key, entry in profiles.items():
        assert isinstance(entry, dict), f"profiles.{profile_key} must be an object"

        missing = sorted(REQUIRED_PROFILE_FIELDS - set(entry.keys()))
        assert not missing, f"profiles.{profile_key} is missing required fields: {', '.join(missing)}"

        assert isinstance(entry["name"], str) and entry["name"].strip(), (
            f"profiles.{profile_key}.name must be a non-empty string"
        )
        assert isinstance(entry["description"], str) and entry["description"].strip(), (
            f"profiles.{profile_key}.description must be a non-empty string"
        )
        assert isinstance(entry["system_prompt"], str) and entry["system_prompt"].strip(), (
            f"profiles.{profile_key}.system_prompt must be a non-empty string"
        )
        assert isinstance(entry["tools"], list), (
            f"profiles.{profile_key}.tools must be a list"
        )
        for tool_name in entry["tools"]:
            assert isinstance(tool_name, str) and tool_name.strip(), (
                f"profiles.{profile_key}.tools entries must be non-empty strings"
            )


def test_all_expected_profiles_present() -> None:
    payload = _load_agents_yaml()
    profiles = set(payload["profiles"].keys())
    assert REQUIRED_PROFILES.issubset(profiles), (
        f"Missing expected profiles: {REQUIRED_PROFILES - profiles}"
    )


def test_optional_temperature_field_is_valid() -> None:
    payload = _load_agents_yaml()
    profiles = payload["profiles"]

    for profile_key, entry in profiles.items():
        temp = entry.get("temperature")
        if temp is not None:
            assert isinstance(temp, (int, float)), (
                f"profiles.{profile_key}.temperature must be a number, got {type(temp).__name__}"
            )
            assert 0.0 <= float(temp) <= 2.0, (
                f"profiles.{profile_key}.temperature must be between 0.0 and 2.0, got {temp}"
            )


# ---------------------------------------------------------------------------
# T010 — agents_as_tools field round-trip (feature 008)
# ---------------------------------------------------------------------------


def test_existing_profiles_default_agents_as_tools_to_empty_list() -> None:
    """Profiles without agents_as_tools must load with an empty list (FR-004)."""
    from prompt_config import load_agent_profile

    profile = load_agent_profile("sql")
    assert profile.agents_as_tools == []


def test_loads_agents_as_tools_from_yaml(tmp_path) -> None:
    """A YAML profile with an agents_as_tools entry round-trips to AgentProfile."""
    from prompt_config import BuiltinAgentRef, SubAgentToolRef, load_agent_profile

    yaml_text = """
schema_version: 1
description: test
profiles:
  parent:
    name: Parent
    description: parent agent
    tools: []
    system_prompt: |
      You are the parent.
    agents_as_tools:
      - agent_ref:
          kind: builtin
          profile_id: child
  child:
    name: Child
    description: child agent
    tools: []
    system_prompt: |
      You are the child.
"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agents.yaml").write_text(yaml_text, encoding="utf-8")

    profile = load_agent_profile("parent", workspace_root=tmp_path)
    assert len(profile.agents_as_tools) == 1
    ref = profile.agents_as_tools[0]
    assert isinstance(ref, SubAgentToolRef)
    assert isinstance(ref.agent_ref, BuiltinAgentRef)
    assert ref.agent_ref.profile_id == "child"


def test_invalid_agent_ref_kind_raises(tmp_path) -> None:
    """Unknown agent_ref.kind must surface as an error rather than silently dropping."""
    import pytest

    from prompt_config import load_agent_profile

    yaml_text = """
schema_version: 1
description: test
profiles:
  parent:
    name: Parent
    description: parent
    tools: []
    system_prompt: |
      You are the parent.
    agents_as_tools:
      - agent_ref:
          kind: bogus
          profile_id: x
"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agents.yaml").write_text(yaml_text, encoding="utf-8")

    with pytest.raises(ValueError, match="agent_ref.kind"):
        load_agent_profile("parent", workspace_root=tmp_path)
