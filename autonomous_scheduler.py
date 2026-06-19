"""In-process scheduler for Autonomous Mode.

A single asyncio background task (:class:`AutonomousScheduler`), started from the
FastAPI lifespan and gated by ``AUTONOMOUS_SCHEDULER_ENABLED``, drives the
autonomous cadence with **no external trigger and no shared secret**. Each tick it
computes the most recent due *slot* for every enabled directive (6-field
seconds-first NCRONTAB via ``croniter``) and runs the cycle when the slot has
advanced. A Cosmos **lease** keyed by ``(directive, slot)`` guarantees
at-most-once execution per slot even across multiple backend instances.

On startup the scheduler seeds the current slot as already-handled so a
redeploy/restart does not immediately re-fire.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from autonomous import AutonomousConfig, Directive, get_autonomous_config, run_autonomous_cycle
from cosmos_memory import get_autonomous_lease_repository

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = float(os.getenv("AUTONOMOUS_SCHEDULER_POLL_SECONDS", "60") or "60")
# Lease TTL: long enough to cover the slot, short enough to self-clean. A slot is
# claimed at most once; the TTL just garbage-collects old lease docs.
LEASE_TTL_SECONDS = int(os.getenv("AUTONOMOUS_LEASE_TTL_SECONDS", "86400") or "86400")


def scheduler_enabled() -> bool:
    """Whether the unattended in-process scheduler should run.

    Semantics match the App Service app-setting convention:

    * unset                 → **off** (the safe local default; no background spend)
    * present but empty (``""``) → **on** (the deployed default in Azure)
    * ``true``/``1``/``yes``/``on`` → on
    * anything else (``false``/``0``/…) → off
    """
    raw = os.getenv("AUTONOMOUS_SCHEDULER_ENABLED")
    if raw is None:
        return False
    raw = raw.strip()
    if raw == "":
        return True
    return raw.lower() in ("true", "1", "yes", "on")


def _current_slot(schedule: str, now: datetime) -> datetime | None:
    """Most recent due fire time at or before ``now`` (inclusive of an exact slot)."""
    try:
        from croniter import croniter

        base = now + timedelta(microseconds=1)
        return croniter(schedule, base, second_at_beginning=True).get_prev(datetime)
    except Exception:  # noqa: BLE001 — a malformed schedule must not crash the loop
        logger.warning("Invalid autonomous schedule %r; skipping", schedule, exc_info=True)
        return None


# Injection seams (kept simple so tests can drive the loop deterministically).
ConfigLoader = Callable[[], Awaitable[AutonomousConfig]]
CycleRunner = Callable[..., Awaitable[Any]]


class AutonomousScheduler:
    """Polls enabled directives and fires due slots once (per slot, across instances)."""

    def __init__(
        self,
        ctx: Any,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        config_loader: ConfigLoader = get_autonomous_config,
        lease_repo_factory: Callable[[], Any] = get_autonomous_lease_repository,
        cycle_runner: CycleRunner = run_autonomous_cycle,
        logger: logging.Logger = logger,
    ) -> None:
        self._ctx = ctx
        self._poll_interval = poll_interval
        self._load_config = config_loader
        self._lease_repo_factory = lease_repo_factory
        self._run_cycle = cycle_runner
        self._logger = logger
        self._last_slot: dict[str, str] = {}
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        """Seed the current slot as handled, then launch the background poll loop."""
        await self.seed_baseline()
        self._task = asyncio.create_task(self._run_loop())

    async def seed_baseline(self, now: datetime | None = None) -> None:
        """Mark the current slot of every scheduled directive as already-handled."""
        now = now or datetime.now(timezone.utc)
        try:
            config = await self._load_config()
        except Exception:  # noqa: BLE001 — never block startup on a bad config
            self._logger.warning("Autonomous scheduler could not load config at start", exc_info=True)
            return
        for directive in config.enabled_directives():
            if not directive.schedule:
                continue
            slot = _current_slot(directive.schedule, now)
            if slot is not None:
                self._last_slot[directive.id] = slot.isoformat()

    async def poll_once(self, now: datetime | None = None) -> None:
        """One scheduler tick: fire any directive whose slot has advanced."""
        now = now or datetime.now(timezone.utc)
        try:
            config = await self._load_config()
        except Exception:  # noqa: BLE001 — a transient config error skips this tick
            self._logger.warning("Autonomous scheduler could not load config", exc_info=True)
            return
        if not config.enabled:
            return
        for directive in config.enabled_directives():
            if not directive.schedule:
                continue
            await self._maybe_fire(directive, config, now)

    async def _maybe_fire(self, directive: Directive, config: AutonomousConfig, now: datetime) -> None:
        slot = _current_slot(directive.schedule, now)
        if slot is None:
            return
        slot_iso = slot.isoformat()
        if self._last_slot.get(directive.id) == slot_iso:
            return  # already handled this slot in this instance
        # Claim the slot across all instances; record it locally either way so we
        # do not re-evaluate the same slot on the next tick.
        self._last_slot[directive.id] = slot_iso
        try:
            won = await self._lease_repo_factory().try_acquire(
                directive.id, slot_iso, ttl=LEASE_TTL_SECONDS
            )
        except Exception:  # noqa: BLE001 — a lease error must not crash the loop
            self._logger.error("Lease acquisition failed for %s @ %s", directive.id, slot_iso, exc_info=True)
            return
        if not won:
            self._logger.info("Slot %s for %s already claimed elsewhere; skipping", slot_iso, directive.id)
            return
        self._logger.info("Autonomous scheduler firing directive=%s slot=%s", directive.id, slot_iso)
        try:
            await self._run_cycle(self._ctx, directive, trigger="timer", logger=self._logger, config=config)
        except Exception:  # noqa: BLE001 — the cycle records its own failures; never crash the loop
            self._logger.error("Scheduled cycle raised for %s", directive.id, exc_info=True)

    async def _run_loop(self) -> None:
        try:
            while not self._stopped.is_set():
                await self.poll_once()
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=self._poll_interval)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:  # pragma: no cover — cooperative shutdown
            pass

    async def stop(self) -> None:
        """Signal and await the background loop's cancellation."""
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:  # pragma: no cover
                pass
            self._task = None


__all__ = ["AutonomousScheduler", "scheduler_enabled"]
