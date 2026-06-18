"""Tests for Agent Skills integration."""

from pathlib import Path


class TestAgentProfileSkills:
    """Test AgentProfile.skills field parsing from agents.yaml."""

    def test_sql_profile_has_table_usage_skill(self):
        from prompt_config import load_agent_profile, get_profile_display_name

        display = get_profile_display_name("sql")
        profile = load_agent_profile(display)
        assert profile.skills == ["table-usage"]

    def test_search_profile_empty_skills(self):
        from prompt_config import load_agent_profile, get_profile_display_name

        display = get_profile_display_name("search")
        profile = load_agent_profile(display)
        assert profile.skills == []

    def test_hybrid_profile_has_table_usage_skill(self):
        from prompt_config import load_agent_profile, get_profile_display_name

        display = get_profile_display_name("hybrid")
        profile = load_agent_profile(display)
        assert profile.skills == ["table-usage"]


class TestBuildSkillsProvider:
    """Test _build_skills_provider() function."""

    def test_returns_none_when_no_skills_requested(self):
        from agent_factory import _build_skills_provider

        assert _build_skills_provider(None) is None
        assert _build_skills_provider([]) is None

    def test_returns_provider_when_skills_requested(self):
        from agent_framework import SkillsProvider
        from agent_factory import _build_skills_provider

        # The built-in FilteringSkillsSource advertises nothing for unknown names,
        # but a provider is still returned whenever skills are requested.
        provider = _build_skills_provider(["nonexistent-skill"])
        assert isinstance(provider, SkillsProvider)

    def test_returns_provider_with_table_usage_skill(self):
        from agent_framework import SkillsProvider
        from agent_factory import _build_skills_provider

        provider = _build_skills_provider(["table-usage"])
        assert provider is not None
        assert isinstance(provider, SkillsProvider)
