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

    def test_sap_force_equipment_profile_has_domain_skill(self):
        from prompt_config import get_profile_display_name, load_agent_profile, load_agents_yaml

        display = get_profile_display_name("sap_force_equipment")
        profile = load_agent_profile(display)
        profile_entry = load_agents_yaml()["profiles"]["sap_force_equipment"]

        assert profile.skills == ["sap-force-equipment-analysis"]
        assert {"database_schema", "database_query", "render_agent_view"}.issubset(
            profile.tool_names
        )
        assert profile_entry["group"] == "SAP"
        assert [starter["label"] for starter in profile_entry["starters"]] == [
            "Equipment by unit",
            "Readiness summary",
            "Maintenance priorities",
            "Readiness forecast",
        ]
        forecast_prompt = profile_entry["starters"][-1]["message"].lower()
        assert not {"render", "dashboard", "visualization", "chart"}.intersection(
            forecast_prompt.split()
        )

    def test_sap_financial_execution_profile_has_domain_skill(self):
        from prompt_config import get_profile_display_name, load_agent_profile, load_agents_yaml

        display = get_profile_display_name("sap_financial_execution")
        profile = load_agent_profile(display)
        profile_entry = load_agents_yaml()["profiles"]["sap_financial_execution"]

        assert profile.skills == ["sap-financial-execution-analysis"]
        assert {"database_schema", "database_query", "render_agent_view"}.issubset(
            profile.tool_names
        )
        assert profile_entry["group"] == "SAP"
        assert [starter["label"] for starter in profile_entry["starters"]] == [
            "Budget posture",
            "Appropriation execution",
            "Lines requiring review",
            "Year-end execution forecast",
        ]
        forecast_prompt = profile_entry["starters"][-1]["message"].lower()
        assert not {"render", "dashboard", "visualization", "chart"}.intersection(
            forecast_prompt.split()
        )


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


class TestCosmosSkillsSource:
    """Test the Cosmos-backed skills source that loads agent skills at run time."""

    def test_get_skills_returns_seeded_skills(self):
        import asyncio

        from agent_factory import CosmosSkillsSource

        skills = asyncio.run(CosmosSkillsSource().get_skills())
        names = {skill.frontmatter.name for skill in skills}
        # The filesystem defaults are seeded into the (in-memory) Cosmos double.
        assert "table-usage" in names
        assert "sap-force-equipment-analysis" in names
        assert "sap-financial-execution-analysis" in names

    def test_sap_force_equipment_skill_contains_reporting_contract(self):
        import asyncio

        from agent_factory import CosmosSkillsSource

        skills = asyncio.run(CosmosSkillsSource().get_skills())
        skill = next(
            skill
            for skill in skills
            if skill.frontmatter.name == "sap-force-equipment-analysis"
        )

        assert "[reporting].[FORCE_EQUIPMENT]" in skill.instructions
        assert "FORCE_ID" in skill.instructions
        assert "Non-Mission Capable Maint" in skill.instructions
        assert "truncated" in skill.instructions
        assert "Aggregate first" in skill.instructions
        assert "Do not attempt to enumerate an entire fleet" in skill.instructions
        assert "TOP (20)" in skill.instructions
        assert "Predictive Analytics" in skill.instructions
        assert "render_agent_view" in skill.instructions
        assert "only when the user explicitly asks" in skill.instructions
        assert "No-Fail Query Recovery" in skill.instructions
        assert "make up to three materially different repair attempts" in skill.instructions
        assert "does not mean the data is unavailable" in skill.instructions
        assert "synthetic" not in skill.instructions.lower()

    def test_sap_financial_execution_skill_contains_reporting_contract(self):
        import asyncio

        from agent_factory import CosmosSkillsSource

        skills = asyncio.run(CosmosSkillsSource().get_skills())
        skill = next(
            skill
            for skill in skills
            if skill.frontmatter.name == "sap-financial-execution-analysis"
        )

        assert "[reporting].[FINANCIAL_EXECUTION]" in skill.instructions
        assert "AVAILABLE_AMOUNT" in skill.instructions
        assert "Weighted portfolio execution" in skill.instructions
        assert "legal funds-control determination" in skill.instructions
        assert "TOP (20)" in skill.instructions
        assert "Predictive Analytics" in skill.instructions
        assert "render_agent_view" in skill.instructions
        assert "only when the user explicitly asks" in skill.instructions
        assert "synthetic" not in skill.instructions.lower()

    def test_filtering_source_omits_unknown_names(self):
        import asyncio

        from agent_framework import FilteringSkillsSource
        from agent_factory import CosmosSkillsSource

        selected = {"table-usage"}
        source = FilteringSkillsSource(
            CosmosSkillsSource(),
            predicate=lambda skill: skill.frontmatter.name in selected,
        )
        skills = asyncio.run(source.get_skills())
        names = {skill.frontmatter.name for skill in skills}
        assert names == {"table-usage"}
