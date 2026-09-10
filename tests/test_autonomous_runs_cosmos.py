"""Emulator-backed integration tests for the autonomous Cosmos repositories.

These exercise the REAL ``CosmosAutonomousRunRepository`` and
``CosmosAutonomousLeaseRepository`` against the local Azure Cosmos DB Emulator.
They auto-skip (via the ``cosmos_emulator`` fixture) when the emulator is not
reachable, so the offline unit suite is unaffected.
"""

import asyncio
from uuid import uuid4

import pytest

import cosmos_memory
from cosmos_memory import AutonomousRunRecord


def test_execution_lease_release_checks_owner_and_etag():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from azure.core import MatchConditions
    from azure.cosmos.exceptions import CosmosResourceExistsError, CosmosAccessConditionFailedError

    async def scenario():
        container = SimpleNamespace(
            create_item=AsyncMock(),
            read_item=AsyncMock(return_value={"run_id": "owner", "_etag": "version"}),
            delete_item=AsyncMock(),
        )
        repo = cosmos_memory.CosmosAutonomousLeaseRepository(None, "test", "leases")
        repo._container = container
        assert await repo.try_start("directive", "owner", ttl=60)
        container.create_item.side_effect = CosmosResourceExistsError(status_code=409)
        assert not await repo.try_start("directive", "other", ttl=60)
        await repo.finish("directive", "other")
        container.delete_item.assert_not_awaited()
        await repo.finish("directive", "owner")
        container.delete_item.assert_awaited_once_with(
            item="execution", partition_key="directive", etag="version",
            match_condition=MatchConditions.IfNotModified,
        )
        container.delete_item.side_effect = CosmosAccessConditionFailedError(status_code=412)
        await repo.finish("directive", "owner")

    asyncio.run(scenario())


@pytest.mark.emulator
def test_run_repo_create_list_get_round_trip(cosmos_emulator):
    async def scenario():
        repo = cosmos_memory.get_autonomous_run_repository()
        directive_id = f"dir-{uuid4()}"
        try:
            record = AutonomousRunRecord(
                id=uuid4().hex,
                directive_id=directive_id,
                profile_id="chief-of-staff",
                session_id=f"autonomous-{directive_id}",
                status="success",
                started_at="2026-06-19T12:00:00+00:00",
                finished_at="2026-06-19T12:00:05+00:00",
                response_text="watch complete",
                tool_events=[{"name": "noop", "arguments": "{}", "result": "ok"}],
                usage={"input_token_count": 10, "output_token_count": 5, "total_token_count": 15},
                trigger="timer",
                notify_status="logged",
            )
            await repo.create_run(record)

            listed = await repo.list_runs(directive_id=directive_id)
            assert len(listed) == 1
            assert listed[0].id == record.id
            assert listed[0].trigger == "timer"
            assert listed[0].usage["total_token_count"] == 15

            got = await repo.get_run(record.id, directive_id)
            assert got is not None
            assert got.response_text == "watch complete"
            assert got.tool_events[0]["name"] == "noop"

            missing = await repo.get_run("no-such-run", directive_id)
            assert missing is None
        finally:
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())


@pytest.mark.emulator
def test_run_repo_partition_scoped_listing(cosmos_emulator):
    async def scenario():
        repo = cosmos_memory.get_autonomous_run_repository()
        dir_a, dir_b = f"dir-a-{uuid4()}", f"dir-b-{uuid4()}"
        try:
            await repo.create_run(_run(dir_a, "2026-06-19T12:00:00+00:00"))
            await repo.create_run(_run(dir_b, "2026-06-19T12:05:00+00:00"))
            only_a = await repo.list_runs(directive_id=dir_a)
            assert [r.directive_id for r in only_a] == [dir_a]
        finally:
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())


@pytest.mark.emulator
def test_lease_try_acquire_is_atomic_once(cosmos_emulator):
    async def scenario():
        repo = cosmos_memory.get_autonomous_lease_repository()
        directive_id = f"dir-{uuid4()}"
        slot = "2026-06-19T12:15:00+00:00"
        try:
            first = await repo.try_acquire(directive_id, slot, ttl=60)
            second = await repo.try_acquire(directive_id, slot, ttl=60)
            assert first is True
            assert second is False
            # A different slot for the same directive is independently claimable.
            other = await repo.try_acquire(directive_id, "2026-06-19T12:30:00+00:00", ttl=60)
            assert other is True
            assert await repo.try_start(directive_id, "first", ttl=60)
            assert not await repo.try_start(directive_id, "second", ttl=60)
            await repo.finish(directive_id, "second")
            assert not await repo.try_start(directive_id, "second", ttl=60)
            await repo.finish(directive_id, "first")
            assert await repo.try_start(directive_id, "second", ttl=60)
            await repo.finish(directive_id, "second")
        finally:
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())


@pytest.mark.emulator
def test_directive_repo_crud_round_trip(cosmos_emulator):
    async def scenario():
        repo = cosmos_memory.get_autonomous_directive_repository()
        directive_id = f"dir-{uuid4()}"
        doc = {
            "id": directive_id,
            "profile_id": "chief-of-staff",
            "instruction": "Run the watch.",
            "schedule": "0 */15 * * * *",
            "enabled": True,
            "notify": {"webhook": "AUTONOMOUS_NOTIFY_WEBHOOK_URL"},
            "created_at": "2026-06-19T12:00:00+00:00",
            "updated_at": "2026-06-19T12:00:00+00:00",
            "doc_type": "autonomous_directive",
            "schema_version": 1,
        }
        try:
            await repo.upsert(doc)
            got = await repo.get(directive_id)
            assert got is not None
            assert got["profile_id"] == "chief-of-staff"

            listed = await repo.list_all()
            assert any(d["id"] == directive_id for d in listed)

            # Update (disable) round-trips.
            doc["enabled"] = False
            await repo.upsert(doc)
            assert (await repo.get(directive_id))["enabled"] is False

            assert await repo.delete(directive_id) is True
            assert await repo.get(directive_id) is None
            assert await repo.delete(directive_id) is False
        finally:
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())


def _run(directive_id: str, started_at: str) -> AutonomousRunRecord:
    return AutonomousRunRecord(
        id=uuid4().hex,
        directive_id=directive_id,
        profile_id="chief-of-staff",
        session_id=f"autonomous-{directive_id}",
        status="success",
        started_at=started_at,
        finished_at=started_at,
        trigger="timer",
        notify_status="logged",
    )
