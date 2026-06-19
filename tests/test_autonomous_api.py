"""API tests for the /api/autonomous/* endpoints (normal user auth).

The real agent cycle is replaced at the ``main.run_autonomous_cycle`` seam so
these tests exercise endpoint wiring (directive resolution, gating, wire shape,
persistence read-back) without a live model or Cosmos account.
"""

import asyncio

import pytest

from autonomous import load_autonomous_config
from cosmos_memory import AutonomousRunRecord, get_autonomous_run_repository


def _seed_run(**overrides) -> AutonomousRunRecord:
    base = dict(
        id="seed",
        directive_id="duty-officer-watch",
        profile_id="chief-of-staff",
        session_id="autonomous-duty-officer-watch",
        status="success",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:05+00:00",
        response_text="ok",
        trigger="manual",
        notify_status="logged",
    )
    base.update(overrides)
    record = AutonomousRunRecord(**base)
    asyncio.run(get_autonomous_run_repository().create_run(record))
    return record


# ---------------------------------------------------------------------------
# POST /api/autonomous/run-now (US1)
# ---------------------------------------------------------------------------

def test_run_now_default_runs_first_enabled_directive(client, monkeypatch):
    import main

    captured = {}

    async def fake_cycle(ctx, directive, *, trigger, logger, config):
        captured["directive_id"] = directive.id
        captured["trigger"] = trigger
        return AutonomousRunRecord(
            id="run-1",
            directive_id=directive.id,
            profile_id=directive.profile_id,
            session_id=f"autonomous-{directive.id}",
            status="success",
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:01+00:00",
            response_text="watch complete",
            trigger=trigger,
            notify_status="logged",
        )

    monkeypatch.setattr(main, "run_autonomous_cycle", fake_cycle)

    resp = client.post("/api/autonomous/run-now", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "run-1"
    assert data["status"] == "success"
    assert data["trigger"] == "manual"
    assert data["responseText"] == "watch complete"

    expected_first = load_autonomous_config().enabled_directives()[0].id
    assert captured["directive_id"] == expected_first


def test_run_now_unknown_directive_returns_404(client):
    resp = client.post("/api/autonomous/run-now", json={"directive_id": "does-not-exist"})
    assert resp.status_code == 404


def test_run_now_disabled_returns_409_and_writes_no_record(client, monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_ENABLED", "false")
    resp = client.post("/api/autonomous/run-now", json={})
    assert resp.status_code == 409
    runs = asyncio.run(get_autonomous_run_repository().list_runs())
    assert runs == []


# ---------------------------------------------------------------------------
# GET /api/autonomous/runs (US2)
# ---------------------------------------------------------------------------

def test_list_runs_most_recent_first(client):
    _seed_run(id="old", started_at="2026-01-01T00:00:00+00:00")
    _seed_run(id="new", started_at="2026-01-02T00:00:00+00:00", trigger="timer")

    resp = client.get("/api/autonomous/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert [r["id"] for r in data["runs"]] == ["new", "old"]
    # Wire shape is camelCase and carries no secret fields.
    first = data["runs"][0]
    assert first["directiveId"] == "duty-officer-watch"
    assert "AUTONOMOUS_NOTIFY_WEBHOOK_URL" not in resp.text
    assert set(first.keys()) == {
        "id", "directiveId", "profileId", "sessionId", "status", "startedAt",
        "finishedAt", "responseText", "toolEvents", "usage", "error",
        "notifyStatus", "notifyError", "trigger",
    }


def test_list_runs_honors_limit(client):
    for i in range(3):
        _seed_run(id=f"r{i}", started_at=f"2026-01-0{i + 1}T00:00:00+00:00")
    resp = client.get("/api/autonomous/runs?limit=2")
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


def test_list_runs_filters_by_directive(client):
    _seed_run(id="a", directive_id="dir-a")
    _seed_run(id="b", directive_id="dir-b")
    resp = client.get("/api/autonomous/runs?directive_id=dir-a")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["runs"][0]["directiveId"] == "dir-a"


# ---------------------------------------------------------------------------
# GET /api/autonomous/directives (US4)
# ---------------------------------------------------------------------------

def test_list_directives_shape_no_secrets(client):
    resp = client.get("/api/autonomous/directives")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["systemUserId"] == "autonomous-duty-officer"
    assert len(data["directives"]) >= 1
    directive = data["directives"][0]
    assert set(directive.keys()) == {
        "id", "profileId", "instruction", "instructionSummary", "schedule",
        "nextRun", "enabled", "notify", "notifyWebhook", "updatedAt",
    }
    # notify is a non-secret descriptor, never a URL/secret.
    assert directive["notify"] in ("webhook", "log")
    assert "http" not in directive["notify"]
    # instructionSummary is a truncated preview.
    assert len(directive["instructionSummary"]) <= 161


def test_list_directives_reports_disabled(client, monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_ENABLED", "false")
    resp = client.get("/api/autonomous/directives")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


# ---------------------------------------------------------------------------
# Directive CRUD (manage automations)
# ---------------------------------------------------------------------------

def _create(client, **overrides):
    body = {
        "id": "morning-brief",
        "profile_id": "chief-of-staff",
        "instruction": "Summarize overnight activity.",
        "schedule": "0 0 8 * * *",
        "enabled": True,
    }
    body.update(overrides)
    return client.post("/api/autonomous/directives", json=body)


def test_create_directive_succeeds_and_appears_in_list(client):
    resp = _create(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "morning-brief"
    assert data["profileId"] == "chief-of-staff"
    assert data["enabled"] is True
    assert data["schedule"] == "0 0 8 * * *"
    assert data["nextRun"]  # computed from the schedule

    listed = client.get("/api/autonomous/directives").json()
    assert any(d["id"] == "morning-brief" for d in listed["directives"])


def test_create_directive_rejects_duplicate_id(client):
    assert _create(client).status_code == 201
    dup = _create(client, instruction="different")
    assert dup.status_code == 409


def test_create_directive_rejects_unknown_profile(client):
    resp = _create(client, id="bad-profile", profile_id="no-such-profile")
    assert resp.status_code == 400


def test_create_directive_rejects_bad_id(client):
    resp = _create(client, id="Not A Slug!")
    assert resp.status_code == 400


def test_create_directive_rejects_invalid_schedule(client):
    resp = _create(client, id="bad-sched", schedule="not a cron")
    assert resp.status_code == 400


def test_create_directive_allows_no_schedule(client):
    resp = _create(client, id="manual-only", schedule=None)
    assert resp.status_code == 201
    assert resp.json()["schedule"] is None
    assert resp.json()["nextRun"] is None


def test_update_directive_toggles_enabled(client):
    _create(client)
    resp = client.patch("/api/autonomous/directives/morning-brief", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    # Reflected in the list.
    listed = client.get("/api/autonomous/directives").json()
    entry = next(d for d in listed["directives"] if d["id"] == "morning-brief")
    assert entry["enabled"] is False
    assert entry["nextRun"] is None  # disabled -> no next run


def test_update_directive_changes_schedule(client):
    _create(client)
    resp = client.patch("/api/autonomous/directives/morning-brief", json={"schedule": "0 */30 * * * *"})
    assert resp.status_code == 200
    assert resp.json()["schedule"] == "0 */30 * * * *"


def test_update_directive_rejects_invalid_schedule(client):
    _create(client)
    resp = client.patch("/api/autonomous/directives/morning-brief", json={"schedule": "99 99 99 99 99 99"})
    assert resp.status_code == 400


def test_update_directive_unknown_returns_404(client):
    resp = client.patch("/api/autonomous/directives/ghost", json={"enabled": False})
    assert resp.status_code == 404


def test_delete_directive_removes_it(client):
    _create(client)
    resp = client.delete("/api/autonomous/directives/morning-brief")
    assert resp.status_code == 204
    listed = client.get("/api/autonomous/directives").json()
    assert not any(d["id"] == "morning-brief" for d in listed["directives"])


def test_delete_directive_unknown_returns_404(client):
    resp = client.delete("/api/autonomous/directives/ghost")
    assert resp.status_code == 404
