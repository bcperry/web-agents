"""Unit tests for the autonomous cycle, notification sinks, and config loader.

These run fully offline: the agent runtime is replaced at the
``create_chat_session`` / ``stream_agent_events`` seams, and the autouse
``_cosmos_doubles`` fixture supplies in-memory run + conversation repositories.
"""

import asyncio
from types import SimpleNamespace

import pytest

import autonomous
from autonomous import (
    AutonomousConfig,
    Directive,
    load_autonomous_config,
    run_autonomous_cycle,
)
from streaming import create_usage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_session_builder(ctx, *, body, auth_header, user, logger):
    """Stand-in for create_chat_session: stores a dummy session in ctx.sessions."""
    async def _build():
        session_id = body["conversation_id"]
        ctx.sessions[session_id] = SimpleNamespace(
            agent=object(), agent_session=object(), mcp_tools=[]
        )
        return {"session_id": session_id, "profile_id": body["profile_id"]}

    return _build()


def _make_fake_stream(text, tool_events, usage):
    async def fake_stream(agent, contents, session, *, result):
        result.update({"text": text, "tool_events": tool_events, "usage": usage})
        if False:  # pragma: no cover — make this an async generator that yields nothing
            yield

    return fake_stream


# ---------------------------------------------------------------------------
# run_autonomous_cycle (US1 / US2)
# ---------------------------------------------------------------------------

def test_run_autonomous_cycle_success(monkeypatch):
    ctx = SimpleNamespace(sessions={})
    monkeypatch.setattr(autonomous, "create_chat_session", _fake_session_builder)
    monkeypatch.setattr(
        autonomous,
        "stream_agent_events",
        _make_fake_stream(
            "Watch summary: all quiet.",
            [{"name": "noop", "arguments": "{}", "result": "ok"}],
            create_usage(input_token_count=10, output_token_count=5, total_token_count=15),
        ),
    )
    directive = Directive(id="watch-1", profile_id="chief-of-staff", instruction="Run the watch.")
    config = AutonomousConfig(enabled=True, system_user_id="sys-officer", directives=[directive])

    record = asyncio.run(run_autonomous_cycle(ctx, directive, trigger="manual", config=config))

    assert record.status == "success"
    assert record.response_text == "Watch summary: all quiet."
    assert record.tool_events[0]["name"] == "noop"
    assert record.usage["total_token_count"] == 15
    assert record.session_id == "autonomous-watch-1"
    assert record.trigger == "manual"
    assert record.notify_status == "logged"
    assert record.error is None
    # The live session was torn down so it does not leak across cycles.
    assert "autonomous-watch-1" not in ctx.sessions


def test_run_autonomous_cycle_persists_one_record(monkeypatch):
    import cosmos_memory

    ctx = SimpleNamespace(sessions={})
    monkeypatch.setattr(autonomous, "create_chat_session", _fake_session_builder)
    monkeypatch.setattr(
        autonomous, "stream_agent_events", _make_fake_stream("done", [], None)
    )
    directive = Directive(id="watch-2", profile_id="chief-of-staff", instruction="Go.")
    config = AutonomousConfig(enabled=True, system_user_id="sys", directives=[directive])

    record = asyncio.run(run_autonomous_cycle(ctx, directive, trigger="timer", config=config))

    repo = cosmos_memory.get_autonomous_run_repository()
    stored = asyncio.run(repo.list_runs(directive_id="watch-2"))
    assert len(stored) == 1
    assert stored[0].id == record.id
    assert stored[0].trigger == "timer"


def test_overlapping_manual_and_timer_runs_are_rejected_and_lease_released(monkeypatch):
    from fastapi import HTTPException

    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        async def execute(*args, **kwargs):
            started.set()
            await release.wait()
            return "finished"
        monkeypatch.setattr(autonomous, "_execute_autonomous_cycle", execute)
        directive = Directive(id="overlap", profile_id="hybrid", instruction="go")
        config = AutonomousConfig(True, "sys", [directive])
        first = asyncio.create_task(run_autonomous_cycle(None, directive, config=config))
        await started.wait()
        with pytest.raises(HTTPException) as error:
            await run_autonomous_cycle(None, directive, config=config, trigger="timer")
        assert error.value.status_code == 409
        release.set()
        assert await first == "finished"
        assert await run_autonomous_cycle(None, directive, config=config) == "finished"
    asyncio.run(scenario())


def test_run_autonomous_cycle_unknown_profile_records_failure(monkeypatch):
    ctx = SimpleNamespace(sessions={})
    # create_chat_session should never be reached for an unknown profile.
    directive = Directive(id="bad", profile_id="no-such-profile", instruction="x")
    config = AutonomousConfig(enabled=True, system_user_id="sys", directives=[directive])

    record = asyncio.run(run_autonomous_cycle(ctx, directive, config=config))

    assert record.status == "failure"
    assert "Unknown profile" in (record.error or "")
    assert record.notify_status == "skipped"


def test_run_autonomous_cycle_agent_error_is_recorded(monkeypatch):
    ctx = SimpleNamespace(sessions={})
    monkeypatch.setattr(autonomous, "create_chat_session", _fake_session_builder)

    async def boom(agent, contents, session, *, result):
        raise RuntimeError("model exploded")
        if False:  # pragma: no cover
            yield

    monkeypatch.setattr(autonomous, "stream_agent_events", boom)
    directive = Directive(id="watch-3", profile_id="chief-of-staff", instruction="Go.")
    config = AutonomousConfig(enabled=True, system_user_id="sys", directives=[directive])

    record = asyncio.run(run_autonomous_cycle(ctx, directive, config=config))

    assert record.status == "failure"
    assert "model exploded" in (record.error or "")
    assert record.notify_status == "skipped"


# ---------------------------------------------------------------------------
# Notification sinks (US3)
# ---------------------------------------------------------------------------

def test_logging_sink_returns_logged():
    from notifications import LoggingSink

    result = asyncio.run(
        LoggingSink().deliver({"directiveId": "d", "status": "success", "toolEvents": []})
    )
    assert result.status == "logged"
    assert result.error is None


def test_webhook_sink_success_returns_delivered(monkeypatch):
    import httpx

    from notifications import WebhookSink

    class _FakeResp:
        def raise_for_status(self):
            return None

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            return _FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    result = asyncio.run(WebhookSink("https://example.test/hook").deliver({"status": "success"}))
    assert result.status == "delivered"
    assert result.error is None


def test_webhook_sink_failure_is_sanitized_and_nonfatal(monkeypatch):
    import httpx

    from notifications import WebhookSink

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            raise RuntimeError("failed to connect to https://secret.example/path?token=abc123")

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    result = asyncio.run(WebhookSink("https://example.test/hook").deliver({"status": "success"}))
    assert result.status == "failed"
    assert result.error is not None
    # The URL/token must be scrubbed from the recorded error.
    assert "secret.example" not in result.error
    assert "token=abc123" not in result.error
    assert "[URL]" in result.error


def test_build_notification_sink_prefers_webhook(monkeypatch):
    from notifications import LoggingSink, WebhookSink, build_notification_sink

    directive = Directive(id="d", profile_id="p", instruction="i", notify={"webhook": "MY_HOOK"})
    monkeypatch.setenv("MY_HOOK", "https://hook.test/in")
    assert isinstance(build_notification_sink(directive), WebhookSink)

    monkeypatch.delenv("MY_HOOK", raising=False)
    monkeypatch.delenv("AUTONOMOUS_NOTIFY_WEBHOOK_URL", raising=False)
    assert isinstance(build_notification_sink(directive), LoggingSink)


# ---------------------------------------------------------------------------
# Config loader (US4)
# ---------------------------------------------------------------------------

def test_missing_config_is_disabled_noop(tmp_path):
    config = load_autonomous_config(tmp_path / "absent.yaml")
    assert config.enabled is False
    assert config.directives == []


def test_duplicate_directive_ids_rejected(tmp_path):
    path = tmp_path / "dup.yaml"
    path.write_text(
        "directives:\n"
        "  - {id: x, profile_id: p, instruction: one}\n"
        "  - {id: x, profile_id: q, instruction: two}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_autonomous_config(path)


def test_env_override_disables(tmp_path, monkeypatch):
    path = tmp_path / "on.yaml"
    path.write_text(
        "enabled: true\n"
        "directives:\n  - {id: x, profile_id: chief-of-staff, instruction: go}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTONOMOUS_ENABLED", "false")
    assert load_autonomous_config(path).enabled is False
    monkeypatch.setenv("AUTONOMOUS_ENABLED", "true")
    assert load_autonomous_config(path).enabled is True


def test_enabled_directives_respects_master_gate(tmp_path):
    path = tmp_path / "mix.yaml"
    path.write_text(
        "enabled: true\n"
        "directives:\n"
        "  - {id: a, profile_id: p, instruction: i, enabled: true}\n"
        "  - {id: b, profile_id: p, instruction: j, enabled: false}\n",
        encoding="utf-8",
    )
    config = load_autonomous_config(path)
    assert [d.id for d in config.enabled_directives()] == ["a"]


# ---------------------------------------------------------------------------
# Validators + durable directive store (manage automations)
# ---------------------------------------------------------------------------

def test_validate_directive_id():
    from autonomous import validate_directive_id

    assert validate_directive_id("Morning-Brief") == "morning-brief"
    for bad in ("", "has space", "UPPER ONLY!", "-leading", "a" * 65):
        with pytest.raises(ValueError):
            validate_directive_id(bad)


def test_validate_schedule():
    from autonomous import validate_schedule

    validate_schedule("0 */15 * * * *")  # valid 6-field seconds-first
    for bad in ("0 0 8 * *", "not a cron", "99 99 99 99 99 99"):
        with pytest.raises(ValueError):
            validate_schedule(bad)


def test_validate_notify_webhook():
    from autonomous import validate_notify_webhook

    assert validate_notify_webhook("AUTONOMOUS_NOTIFY_WEBHOOK_URL") == {
        "webhook": "AUTONOMOUS_NOTIFY_WEBHOOK_URL"
    }
    assert validate_notify_webhook("https://hooks.test/in") == {"webhook": "https://hooks.test/in"}
    with pytest.raises(ValueError):
        validate_notify_webhook("not-a-name-or-url")


def test_validate_profile_id():
    from autonomous import validate_profile_id

    assert validate_profile_id("chief-of-staff")  # resolves to a display name
    with pytest.raises(ValueError):
        validate_profile_id("no-such-profile")


def test_get_autonomous_config_reads_from_cosmos_store():
    import cosmos_memory
    from autonomous import Directive, get_autonomous_config

    async def scenario():
        repo = cosmos_memory.get_autonomous_directive_repository()
        await repo.upsert(
            Directive(id="extra", profile_id="chief-of-staff", instruction="hi").to_doc()
        )
        config = await get_autonomous_config()
        return {d.id for d in config.directives}

    ids = asyncio.run(scenario())
    assert "extra" in ids


def test_seed_autonomous_directives_is_idempotent(monkeypatch, tmp_path):
    import cosmos_memory
    from tests._doubles import InMemoryByIdRepository
    import autonomous

    path = tmp_path / "seed.yaml"
    path.write_text(
        "enabled: true\n"
        "directives:\n  - {id: seeded-one, profile_id: chief-of-staff, instruction: go}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(autonomous, "_default_config_path", lambda: path)
    # Start from an empty store so seeding has work to do.
    monkeypatch.setattr(cosmos_memory, "_autonomous_directive_repo", InMemoryByIdRepository())

    async def scenario():
        first = await autonomous.seed_autonomous_directives()
        second = await autonomous.seed_autonomous_directives()  # idempotent
        docs = await cosmos_memory.get_autonomous_directive_repository().list_all()
        return first, second, [d["id"] for d in docs]

    first, second, ids = asyncio.run(scenario())
    assert first == 1
    assert second == 0
    assert ids == ["seeded-one"]
