"""Owner-aware selected-skill loading contracts."""

import asyncio

import user_data
from agent_factory import CosmosSkillsSource


def test_cosmos_skills_source_loads_global_plus_bound_owner_only():
    repo = user_data.get_user_skills_repository()
    asyncio.run(repo.create("user-a", "owner-a-skill", {
        "id": "owner-a-skill",
        "name": "owner-a-skill",
        "description": "Owner A",
        "content": "Private A instructions",
    }))

    owner_names = {
        skill.frontmatter.name for skill in asyncio.run(CosmosSkillsSource("user-a").get_skills())
    }
    other_names = {
        skill.frontmatter.name for skill in asyncio.run(CosmosSkillsSource("user-b").get_skills())
    }

    assert "owner-a-skill" in owner_names
    assert "owner-a-skill" not in other_names