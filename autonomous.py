"""Autonomous Mode — the core duty-officer cycle and its configuration layer.

This module is the heart of Autonomous Mode. It:

* loads operational **directives** from ``config/autonomous.yaml`` (a standing
  order = an agent profile + an instruction + an optional schedule/notify),
* owns a synthetic **system identity** (the "Autonomous Duty Officer") so
  autonomous activity never appears in interactive users' histories, and
* runs one **cycle** (:func:`run_autonomous_cycle`) by *reusing* the existing
  session orchestration and streaming runtime — no fork of agent logic — then
  records a single durable audit record and delivers the result to a sink.

The scheduled path (``autonomous_scheduler``) and the user-authenticated
``run-now`` endpoint both call :func:`run_autonomous_cycle`; it never raises to
its caller — dependency/profile failures become a recorded ``failure`` run.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agent_framework._types import Content

from auth import AuthenticatedUser
from cosmos_memory import (
    AutonomousRunRecord,
    get_autonomous_run_repository,
    get_conversation_repository,
)
from mcp_servers import cleanup_mcp_servers
from notifications import build_notification_sink, notify_descriptor, sanitize_error
from prompt_config import load_agents_yaml
from session_orchestration import create_chat_session
from streaming import (
    USAGE_INPUT_KEY,
    USAGE_OUTPUT_KEY,
    USAGE_TOTAL_KEY,
    stream_agent_response,
    usage_value,
    with_user_time,
)

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_USER_ID = "autonomous-duty-officer"
SYSTEM_USERNAME = "Autonomous Duty Officer"
_INSTRUCTION_SUMMARY_CHARS = 160


# ---------------------------------------------------------------------------
# Configuration model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Directive:
    """A standing order: one unit of autonomous work (config, not persisted)."""

    id: str
    profile_id: str
    instruction: str
    schedule: str | None = None
    enabled: bool = True
    notify: dict[str, Any] | None = None


@dataclass(frozen=True)
class AutonomousConfig:
    """Loaded ``config/autonomous.yaml`` (with env overrides applied)."""

    enabled: bool
    system_user_id: str
    directives: list[Directive]
    schema_version: int = 1

    def enabled_directives(self) -> list[Directive]:
        """Directives that can actually run (master gate AND per-directive gate)."""
        if not self.enabled:
            return []
        return [d for d in self.directives if d.enabled]

    def find_directive(self, directive_id: str) -> Directive | None:
        for directive in self.directives:
            if directive.id == directive_id:
                return directive
        return None


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent / "config" / "autonomous.yaml"


def _env_bool(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().lower() in ("true", "1", "yes", "on")


def load_autonomous_config(path: Path | None = None) -> AutonomousConfig:
    """Load and validate the autonomous config, applying env overrides.

    A missing file is a safe **disabled no-op** (zero directives), not an error.
    Duplicate directive ids are rejected. ``AUTONOMOUS_ENABLED`` /
    ``AUTONOMOUS_USER_ID`` override the file values.
    """
    cfg_path = path or _default_config_path()

    env_user = (os.getenv("AUTONOMOUS_USER_ID") or "").strip()
    env_enabled = _env_bool("AUTONOMOUS_ENABLED")

    if not cfg_path.exists():
        return AutonomousConfig(
            enabled=bool(env_enabled) if env_enabled is not None else False,
            system_user_id=env_user or DEFAULT_SYSTEM_USER_ID,
            directives=[],
        )

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("config/autonomous.yaml must be a mapping at the top level")

    schema_version = int(raw.get("schema_version", 1) or 1)
    if schema_version != 1:
        raise ValueError(f"Unsupported autonomous schema_version: {schema_version}")

    file_enabled = bool(raw.get("enabled", True))
    enabled = env_enabled if env_enabled is not None else file_enabled
    system_user_id = env_user or str(raw.get("system_user_id") or DEFAULT_SYSTEM_USER_ID).strip()

    directives: list[Directive] = []
    seen_ids: set[str] = set()
    for entry in raw.get("directives") or []:
        if not isinstance(entry, dict):
            raise ValueError("Each directive must be a mapping")
        directive_id = str(entry.get("id") or "").strip()
        profile_id = str(entry.get("profile_id") or "").strip()
        instruction = str(entry.get("instruction") or "").strip()
        if not directive_id or not profile_id or not instruction:
            raise ValueError("Each directive requires non-empty id, profile_id, and instruction")
        if directive_id in seen_ids:
            raise ValueError(f"Duplicate directive id: {directive_id}")
        seen_ids.add(directive_id)
        notify = entry.get("notify")
        directives.append(
            Directive(
                id=directive_id,
                profile_id=profile_id,
                instruction=instruction,
                schedule=(str(entry["schedule"]).strip() if entry.get("schedule") else None),
                enabled=bool(entry.get("enabled", True)),
                notify=notify if isinstance(notify, dict) else None,
            )
        )

    return AutonomousConfig(
        enabled=enabled,
        system_user_id=system_user_id,
        directives=directives,
        schema_version=schema_version,
    )


def load_directives(path: Path | None = None) -> list[Directive]:
    """Convenience accessor: all configured directives (enabled or not)."""
    return load_autonomous_config(path).directives


# ---------------------------------------------------------------------------
# System identity
# ---------------------------------------------------------------------------

def system_user(config: AutonomousConfig) -> AuthenticatedUser:
    """The synthetic, non-human identity that owns all autonomous data."""
    return AuthenticatedUser(user_id=config.system_user_id, username=SYSTEM_USERNAME)


# ---------------------------------------------------------------------------
# Directive presentation (for the directives API + scheduler)
# ---------------------------------------------------------------------------

def compute_next_run(schedule: str | None, *, now: datetime | None = None) -> str | None:
    """Next scheduled fire time (UTC ISO-8601) for a 6-field seconds-first NCRONTAB."""
    if not schedule:
        return None
    try:
        from croniter import croniter

        base = now or datetime.now(timezone.utc)
        nxt = croniter(schedule, base, second_at_beginning=True).get_next(datetime)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=timezone.utc)
        return nxt.astimezone(timezone.utc).isoformat()
    except Exception:  # noqa: BLE001 — a bad schedule must not break the listing
        logger.debug("Could not compute next run for schedule %r", schedule, exc_info=True)
        return None


def _summarize_instruction(instruction: str) -> str:
    collapsed = " ".join((instruction or "").split())
    if len(collapsed) <= _INSTRUCTION_SUMMARY_CHARS:
        return collapsed
    return collapsed[:_INSTRUCTION_SUMMARY_CHARS].rstrip() + "…"


def directive_to_wire(directive: Directive, *, now: datetime | None = None) -> dict[str, Any]:
    """Sanitized directive shape for the API (no secrets; ``notify`` is a descriptor)."""
    return {
        "id": directive.id,
        "profileId": directive.profile_id,
        "instructionSummary": _summarize_instruction(directive.instruction),
        "schedule": directive.schedule,
        "nextRun": compute_next_run(directive.schedule, now=now) if directive.enabled else None,
        "enabled": directive.enabled,
        "notify": notify_descriptor(directive),
    }


# ---------------------------------------------------------------------------
# The autonomous cycle
# ---------------------------------------------------------------------------

def _resolve_profile_name(profile_id: str) -> str | None:
    """Return the display name if the profile resolves (by id or name), else None."""
    profiles = (load_agents_yaml().get("profiles") or {})
    if profile_id in profiles and isinstance(profiles[profile_id], dict):
        return str(profiles[profile_id].get("name", profile_id))
    normalized = " ".join(profile_id.strip().lower().split())
    for key, entry in profiles.items():
        if not isinstance(entry, dict):
            continue
        name = " ".join(str(entry.get("name", "")).strip().lower().split())
        if name and name == normalized:
            return str(entry.get("name", key))
    return None


def _usage_to_dict(usage: Any) -> dict[str, int]:
    if usage is None:
        return {}
    return {
        USAGE_INPUT_KEY: usage_value(usage, USAGE_INPUT_KEY),
        USAGE_OUTPUT_KEY: usage_value(usage, USAGE_OUTPUT_KEY),
        USAGE_TOTAL_KEY: usage_value(usage, USAGE_TOTAL_KEY),
    }


async def collect_agent_response(agent: Any, contents: list[Content], session: Any) -> dict[str, Any]:
    """Drive the agent unattended by consuming the SSE stream, discarding events.

    Reuses the exact streaming/usage/tool-event extraction the interactive
    ``send_message`` endpoint uses, then reads the final aggregate the streamer
    publishes on ``stream_agent_response._last_result``.
    """
    async for _event in stream_agent_response(agent, contents, session):
        pass
    return getattr(stream_agent_response, "_last_result", None) or {
        "text": "",
        "tool_events": [],
        "usage": None,
    }


async def _ensure_conversation(
    sys_user: AuthenticatedUser,
    session_id: str,
    directive: Directive,
    profile_name: str,
) -> None:
    """Ensure the deterministic ongoing conversation exists, owned by the system identity."""
    conversations = get_conversation_repository()
    existing = await conversations.get_owned(sys_user.user_id, session_id)
    if existing is None:
        await conversations.create(
            sys_user.user_id,
            session_id,
            directive.profile_id,
            profile_name,
        )


async def run_autonomous_cycle(
    ctx: Any,
    directive: Directive,
    *,
    trigger: str = "manual",
    logger: logging.Logger = logger,
    config: AutonomousConfig | None = None,
) -> AutonomousRunRecord:
    """Execute one autonomous cycle for a directive and return its audit record.

    Reuses ``create_chat_session`` + ``stream_agent_response`` (no agent-logic
    fork). Persists exactly one run record at the end (success or caught
    failure) and delivers the result to a notification sink (failure non-fatal).
    Never raises to the caller.
    """
    config = config or load_autonomous_config()
    sys_user = system_user(config)
    run_id = uuid.uuid4().hex
    session_id = f"autonomous-{directive.id}"
    started = datetime.now(timezone.utc)

    logger.info(
        "Autonomous cycle start: directive=%s profile=%s trigger=%s run=%s",
        directive.id,
        directive.profile_id,
        trigger,
        run_id,
    )

    record = AutonomousRunRecord(
        id=run_id,
        directive_id=directive.id,
        profile_id=directive.profile_id,
        session_id=session_id,
        status="failure",
        started_at=started.isoformat(),
        finished_at=started.isoformat(),
        trigger=trigger,
    )

    profile_name = _resolve_profile_name(directive.profile_id)
    if profile_name is None:
        record.error = f"Unknown profile: {directive.profile_id}"
        logger.error("Autonomous cycle aborted: %s", record.error)
        return await _finalize(record, directive, config, started, logger)

    try:
        await _ensure_conversation(sys_user, session_id, directive, profile_name)
        await create_chat_session(
            ctx,
            body={"profile_id": directive.profile_id, "conversation_id": session_id},
            auth_header="",
            user=sys_user,
            logger=logger,
        )
        session_data = ctx.sessions.get(session_id)
        if session_data is None:
            raise RuntimeError("Autonomous session was not created")

        when = started.strftime("%Y-%m-%d %H:%M:%S UTC")
        contents: list[Content] = [Content.from_text(with_user_time(directive.instruction, when))]
        try:
            result = await collect_agent_response(
                session_data.agent, contents, session_data.agent_session
            )
            record.status = "success"
            record.response_text = result.get("text") or ""
            record.tool_events = result.get("tool_events") or []
            record.usage = _usage_to_dict(result.get("usage"))
            try:
                await get_conversation_repository().touch(sys_user.user_id, session_id)
            except Exception:  # noqa: BLE001 — index touch is best-effort
                logger.debug("Failed to touch autonomous conversation %s", session_id, exc_info=True)
        finally:
            # Reuse durable Cosmos history next cycle; tear down this run's live
            # session + MCP connections so they do not leak across cycles.
            stale = ctx.sessions.pop(session_id, None)
            if stale is not None and getattr(stale, "mcp_tools", None):
                try:
                    await cleanup_mcp_servers(stale.mcp_tools)
                except Exception:  # noqa: BLE001 — cleanup is best-effort
                    logger.debug("MCP cleanup failed for %s", session_id, exc_info=True)
    except Exception as exc:  # noqa: BLE001 — never raise to the caller (FR: recorded failure)
        record.status = "failure"
        record.error = sanitize_error(str(exc))
        logger.error(
            "Autonomous cycle failed: directive=%s run=%s error=%s",
            directive.id,
            run_id,
            record.error,
            exc_info=True,
        )

    return await _finalize(record, directive, config, started, logger)


async def _finalize(
    record: AutonomousRunRecord,
    directive: Directive,
    config: AutonomousConfig,
    started: datetime,
    logger: logging.Logger,
) -> AutonomousRunRecord:
    """Deliver the notification, persist the single run record, and log the result."""
    record.finished_at = datetime.now(timezone.utc).isoformat()

    if record.status == "success":
        try:
            sink = build_notification_sink(directive, config)
            outcome = await sink.deliver(record.to_wire())
            record.notify_status = outcome.status
            record.notify_error = outcome.error
        except Exception as exc:  # noqa: BLE001 — delivery must never lose the audit record
            record.notify_status = "failed"
            record.notify_error = sanitize_error(str(exc))
            logger.warning("Autonomous notification raised unexpectedly: %s", record.notify_error)
    else:
        record.notify_status = "skipped"

    try:
        await get_autonomous_run_repository().create_run(record)
    except Exception:  # noqa: BLE001 — log but still return the in-memory record
        logger.error("Failed to persist autonomous run record %s", record.id, exc_info=True)

    duration = (datetime.now(timezone.utc) - started).total_seconds()
    logger.info(
        "Autonomous cycle finish: directive=%s status=%s notify=%s duration=%.2fs run=%s",
        record.directive_id,
        record.status,
        record.notify_status,
        duration,
        record.id,
    )
    return record


__all__ = [
    "AutonomousConfig",
    "Directive",
    "collect_agent_response",
    "compute_next_run",
    "directive_to_wire",
    "load_autonomous_config",
    "load_directives",
    "run_autonomous_cycle",
    "system_user",
]
