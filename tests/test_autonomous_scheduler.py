"""Unit tests for the in-process autonomous scheduler (no real model, no Cosmos).

The scheduler is driven deterministically through its injection seams: a config
loader, an in-memory lease repo double, and a recording cycle runner. Slots are
advanced by passing explicit ``now`` values to ``poll_once``.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from autonomous import AutonomousConfig, Directive
from autonomous_scheduler import AutonomousScheduler, _current_slot, scheduler_enabled
from tests._doubles import InMemoryAutonomousLeaseRepository

SCHEDULE = "0 */15 * * * *"  # every 15 minutes (6-field, seconds-first)
SLOT_0 = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
SLOT_1 = datetime(2026, 6, 19, 12, 15, 0, tzinfo=timezone.utc)
SLOT_2 = datetime(2026, 6, 19, 12, 30, 0, tzinfo=timezone.utc)


def _config(enabled=True, schedule=SCHEDULE):
    directive = Directive(id="watch", profile_id="chief-of-staff", instruction="go", schedule=schedule)
    return AutonomousConfig(enabled=enabled, system_user_id="sys", directives=[directive])


def _loader(enabled=True, schedule=SCHEDULE):
    """Async config loader (the scheduler awaits its config_loader)."""
    cfg = _config(enabled, schedule)

    async def _load():
        return cfg

    return _load


class _Recorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, ctx, directive, *, trigger, logger, config):
        self.calls.append((directive.id, trigger))
        return SimpleNamespace(id=f"run-{len(self.calls)}")


def _make_scheduler(recorder, lease, config_factory):
    return AutonomousScheduler(
        SimpleNamespace(sessions={}),
        config_loader=config_factory,
        lease_repo_factory=lambda: lease,
        cycle_runner=recorder,
    )


# ---------------------------------------------------------------------------
# Slot math + gate
# ---------------------------------------------------------------------------

def test_current_slot_is_inclusive_and_recent():
    assert _current_slot(SCHEDULE, SLOT_1) == SLOT_1
    assert _current_slot(SCHEDULE, SLOT_1 + timedelta(minutes=7)) == SLOT_1


def test_scheduler_enabled_semantics(monkeypatch):
    monkeypatch.delenv("AUTONOMOUS_SCHEDULER_ENABLED", raising=False)
    assert scheduler_enabled() is False  # unset -> off (local default)
    monkeypatch.setenv("AUTONOMOUS_SCHEDULER_ENABLED", "")
    assert scheduler_enabled() is True  # empty -> on (deployed default)
    monkeypatch.setenv("AUTONOMOUS_SCHEDULER_ENABLED", "true")
    assert scheduler_enabled() is True
    monkeypatch.setenv("AUTONOMOUS_SCHEDULER_ENABLED", "false")
    assert scheduler_enabled() is False


# ---------------------------------------------------------------------------
# Firing behavior
# ---------------------------------------------------------------------------

def test_fires_once_per_slot_and_again_next_slot():
    recorder = _Recorder()
    scheduler = _make_scheduler(recorder, InMemoryAutonomousLeaseRepository(), _loader())

    async def scenario():
        await scheduler.seed_baseline(now=SLOT_0)  # current slot handled on start
        await scheduler.poll_once(now=SLOT_0)        # same slot -> no fire
        await scheduler.poll_once(now=SLOT_1)        # advanced -> fire
        await scheduler.poll_once(now=SLOT_1 + timedelta(minutes=5))  # same slot -> no fire
        await scheduler.poll_once(now=SLOT_2)        # advanced -> fire

    asyncio.run(scenario())
    assert recorder.calls == [("watch", "timer"), ("watch", "timer")]


def test_baseline_seeding_skips_current_slot_on_start():
    recorder = _Recorder()
    scheduler = _make_scheduler(recorder, InMemoryAutonomousLeaseRepository(), _loader())

    async def scenario():
        await scheduler.seed_baseline(now=SLOT_1)
        await scheduler.poll_once(now=SLOT_1)  # exactly the seeded slot -> no fire

    asyncio.run(scenario())
    assert recorder.calls == []


def test_disabled_config_never_fires():
    recorder = _Recorder()
    scheduler = _make_scheduler(recorder, InMemoryAutonomousLeaseRepository(), _loader(enabled=False))

    async def scenario():
        await scheduler.poll_once(now=SLOT_1)
        await scheduler.poll_once(now=SLOT_2)

    asyncio.run(scenario())
    assert recorder.calls == []


def test_directive_without_schedule_is_not_scheduled():
    recorder = _Recorder()
    scheduler = _make_scheduler(recorder, InMemoryAutonomousLeaseRepository(), _loader(schedule=None))

    async def scenario():
        await scheduler.seed_baseline(now=SLOT_0)
        await scheduler.poll_once(now=SLOT_1)
        await scheduler.poll_once(now=SLOT_2)

    asyncio.run(scenario())
    assert recorder.calls == []


def test_two_instances_sharing_lease_fire_slot_exactly_once():
    shared_lease = InMemoryAutonomousLeaseRepository()
    rec_a = _Recorder()
    rec_b = _Recorder()
    sched_a = _make_scheduler(rec_a, shared_lease, _loader())
    sched_b = _make_scheduler(rec_b, shared_lease, _loader())

    async def scenario():
        await sched_a.seed_baseline(now=SLOT_0)
        await sched_b.seed_baseline(now=SLOT_0)
        # Both instances see the same advanced slot; only the lease winner fires.
        await sched_a.poll_once(now=SLOT_1)
        await sched_b.poll_once(now=SLOT_1)

    asyncio.run(scenario())
    assert len(rec_a.calls) + len(rec_b.calls) == 1


@pytest.mark.parametrize("during_poll", [False, True])
def test_scheduler_start_stop_is_clean(monkeypatch, during_poll):
    recorder = _Recorder()
    scheduler = AutonomousScheduler(
        SimpleNamespace(sessions={}),
        poll_interval=3600,
        config_loader=_loader(enabled=False),
        lease_repo_factory=InMemoryAutonomousLeaseRepository,
        cycle_runner=recorder,
    )

    async def scenario():
        entered = asyncio.Event()

        async def poll():
            entered.set()
            if during_poll:
                await asyncio.Event().wait()

        monkeypatch.setattr(scheduler, "poll_once", poll)
        await scheduler.start()
        task = scheduler._task
        await asyncio.wait_for(entered.wait(), timeout=1)
        await scheduler.stop()
        assert task.done()
        assert scheduler._task is None
        await scheduler.stop()

    asyncio.run(scenario())
    assert recorder.calls == []
