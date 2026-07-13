"""Real Cosmos contracts for owner-scoped atomic definition creation."""

import asyncio
from uuid import uuid4

import pytest

import cosmos_memory
import user_data
from definition_creation import (
    AgentCreationRequest,
    AgentCreationService,
    SkillCreationRequest,
    SkillCreationService,
)


@pytest.mark.emulator
def test_user_skill_atomic_create_partition_isolation_and_fresh_repository(cosmos_emulator):
    async def scenario():
        repo = user_data.get_user_skills_repository()
        user_a = f"skill-a-{uuid4()}"
        user_b = f"skill-b-{uuid4()}"
        item_id = f"shared-{uuid4()}"
        request = SkillCreationRequest(
            name=item_id, description="first", content="body"
        )
        global_repo = cosmos_memory.get_skill_repository()

        async def create_for_a():
            return await SkillCreationService(user_a, global_repo, repo).create(request)

        try:
            outcomes = await asyncio.gather(create_for_a(), create_for_a())
            assert [result.status for result in outcomes].count("created") == 1
            assert [getattr(result, "code", None) for result in outcomes].count("duplicate") == 1

            other = await SkillCreationService(user_b, global_repo, repo).create(request)
            assert other.status == "created"
            assert (await repo.get(user_b, item_id))["description"] == "first"
            assert len(await repo.list_for_user(user_a)) == 1
            assert len(await repo.list_for_user(user_b)) == 1

            fresh = user_data.CosmosUserScopedRepository(repo._container_name)
            assert (await fresh.get(user_a, item_id))["description"] == "first"
            container = await fresh._get_container()
            properties = await container.read()
            assert properties["partitionKey"]["paths"] == ["/user_id"]
        finally:
            await repo.delete(user_a, item_id)
            await repo.delete(user_b, item_id)
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())


@pytest.mark.emulator
def test_custom_agent_atomic_create_same_owner_conflict(cosmos_emulator):
    async def scenario():
        repo = user_data.get_custom_agents_repository()
        user_id = f"agent-{uuid4()}"
        item_id = f"planner-{uuid4()}"

        request = AgentCreationRequest(id=item_id, name="Planner", systemPrompt="Plan.")

        async def create():
            return await AgentCreationService(user_id, custom_repo=repo).create(request)

        try:
            outcomes = await asyncio.gather(create(), create())
            assert [result.status for result in outcomes].count("created") == 1
            assert [getattr(result, "code", None) for result in outcomes].count("duplicate") == 1
            assert (await repo.get(user_id, item_id))["name"] == "Planner"
        finally:
            await repo.delete(user_id, item_id)
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())