"""Validation tests for agents.yaml configuration schema."""

from pathlib import Path

import yaml


AGENTS_YAML_PATH = Path(__file__).resolve().parent.parent / "config" / "agents.yaml"
ALLOWED_PROFILES = {"sql", "search", "hybrid", "faa"}
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
        assert profile_key in ALLOWED_PROFILES, (
            f"Profile key '{profile_key}' not in allowed profiles: {ALLOWED_PROFILES}"
        )
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
    assert ALLOWED_PROFILES.issubset(profiles), (
        f"Missing expected profiles: {ALLOWED_PROFILES - profiles}"
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
