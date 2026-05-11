"""Unit tests for sub_agent_tools (derivation + disambiguation)."""

from __future__ import annotations

import pytest

from sub_agent_tools import derive_sub_agent_tool_surface, disambiguate_tool_names


# ---------------------------------------------------------------------------
# derive_sub_agent_tool_surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "agent_name,expected",
    [
        ("Azure Government Specialist", "azure_government_specialist"),
        ("SQL Query Agent", "sql_query_agent"),
        ("FAA Aviation AI", "faa_aviation_ai"),
        ("Mixed   Whitespace", "mixed_whitespace"),
        ("Hyphen-And.Dot/Slash", "hyphen_and_dot_slash"),
        ("___leading and trailing___", "leading_and_trailing"),
    ],
)
def test_slugifies_typical_names(agent_name: str, expected: str) -> None:
    tool_name, _, _ = derive_sub_agent_tool_surface(agent_name, "desc", "fallback_id")
    assert tool_name == expected


def test_digit_leading_name_gets_prefix() -> None:
    tool_name, _, _ = derive_sub_agent_tool_surface("123 Tools", "desc", "fid")
    assert tool_name == "a_123_tools"


def test_empty_name_falls_back_to_id() -> None:
    tool_name, _, _ = derive_sub_agent_tool_surface("", "desc", "blaine_bot")
    assert tool_name == "blaine_bot"


def test_empty_name_and_id_falls_back_to_literal() -> None:
    tool_name, _, _ = derive_sub_agent_tool_surface("", "desc", "")
    assert tool_name == "sub_agent"


def test_long_name_truncated_to_64_chars() -> None:
    long_name = "x" * 200
    tool_name, _, _ = derive_sub_agent_tool_surface(long_name, "desc", "fid")
    assert len(tool_name) == 64
    assert tool_name == "x" * 64


def test_description_truncated_to_500_chars() -> None:
    desc = "y" * 800
    _, tool_desc, _ = derive_sub_agent_tool_surface("Agent", desc, "fid")
    assert len(tool_desc) == 500
    assert tool_desc == "y" * 500


def test_empty_description_fallback_uses_name() -> None:
    _, tool_desc, _ = derive_sub_agent_tool_surface("Coordinator", "", "fid")
    assert tool_desc == "Delegate to the Coordinator agent."


def test_empty_description_and_name_fallback_uses_id() -> None:
    _, tool_desc, _ = derive_sub_agent_tool_surface("", "", "blaine_bot")
    assert tool_desc == "Delegate to the blaine_bot agent."


def test_arg_description_references_tool_name() -> None:
    tool_name, _, arg_desc = derive_sub_agent_tool_surface("My Agent", "desc", "fid")
    assert arg_desc == f"Request for the {tool_name} agent."


# ---------------------------------------------------------------------------
# disambiguate_tool_names
# ---------------------------------------------------------------------------


def test_disambiguate_no_collisions_unchanged() -> None:
    assert disambiguate_tool_names(["a", "b", "c"]) == ["a", "b", "c"]


def test_disambiguate_collisions_get_numeric_suffix() -> None:
    assert disambiguate_tool_names(["a", "b", "a", "a"]) == ["a", "b", "a_2", "a_3"]


def test_disambiguate_skips_existing_suffixed_names() -> None:
    # If the second element is already 'a_2', the third 'a' must become 'a_3'.
    assert disambiguate_tool_names(["a", "a_2", "a"]) == ["a", "a_2", "a_3"]


def test_disambiguate_preserves_input_order() -> None:
    result = disambiguate_tool_names(["x", "y", "x", "z", "y"])
    assert result == ["x", "y", "x_2", "z", "y_2"]


def test_disambiguate_empty_input() -> None:
    assert disambiguate_tool_names([]) == []
