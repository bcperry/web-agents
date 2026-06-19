# Quickstart: Autonomous Mode

This guide shows how to run and verify Autonomous Mode locally, and how it is wired in
production. Local development uses `AUTH_DISABLED=true` and the Cosmos emulator; no cloud
account is required.

## Prerequisites

- Backend deps: `uv sync` (and `uv sync --group dev` for tests).
- Azure Cosmos DB Emulator running locally (see `scripts/start_cosmos_emulator.sh`).

## 1. Configure a directive

`config/autonomous.yaml` ships with one default directive (`duty-officer-watch`) that uses
the `chief-of-staff` profile. Adjust the `instruction`, `profile_id`, or add directives as
needed. To turn the whole feature off, set `enabled: false` (or `AUTONOMOUS_ENABLED=false`).

## 2. Run the backend with autonomous enabled

```bash
export AUTH_DISABLED=true
export AZURE_COSMOS_ENDPOINT=https://localhost:8081/   # emulator
export AUTONOMOUS_ENABLED=true
# Leave the unattended scheduler OFF locally (default) to avoid background model spend;
# you can still trigger cycles by hand below. Set AUTONOMOUS_SCHEDULER_ENABLED=true to run it.
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

On startup the log includes an "Autonomous mode" summary line (enabled, directive count,
system identity) — with no secrets.

## 3. Trigger a cycle on demand (no human prompt)

```bash
# Default (first enabled) directive:
curl -s -X POST http://localhost:8000/api/autonomous/run-now \
  -H 'Content-Type: application/json' -d '{}' | jq

# A specific directive:
curl -s -X POST http://localhost:8000/api/autonomous/run-now \
  -H 'Content-Type: application/json' \
  -d '{"directive_id":"duty-officer-watch"}' | jq
```

Expected: a `200` with the run record (`status: "success"`, a `responseText`, `toolEvents`,
`usage`, and `notifyStatus`). The agent produced this **without anyone typing the prompt** —
the directive instruction was the input.

## 4. Verify the audit trail

```bash
curl -s "http://localhost:8000/api/autonomous/runs?limit=10" | jq
curl -s "http://localhost:8000/api/autonomous/directives" | jq
```

Expected: the run you just executed appears most-recent-first; directives lists the
configured standing orders (no secrets). Restart the backend and re-list `/runs` — the run
persists (Cosmos durability).

## 4a. View and chat with the Duty Officer in the UI (all users)

Every authenticated user can see the autonomous agent and ask it questions from the web app —
no admin role required.

1. Open the app and sign in (or run locally with `AUTH_DISABLED=true`).
2. On the agents page, open the **AUTOMATIONS** group and choose the **Duty Officer** card.
3. The Duty Officer page shows, for all users:
   - the master **enabled** status,
   - the configured **standing orders** (directives, no secrets), and
   - the **recent activity** audit trail (most-recent-first). Expand any run to see its
     response, tool count, token usage, and notify status.
4. Use the **Ask the Duty Officer** chat panel to ask the autonomous agent questions; it runs
   the same profile (`chief-of-staff`) the autonomous watch uses. "Ask about this" on an
   expanded run pre-sends a question about that specific cycle.

The page is backed by the existing `GET /api/autonomous/directives` and
`GET /api/autonomous/runs` endpoints (both authenticated as a normal user), and the standard
chat session API. Visual references: `screenshots/012-autonomous-mode/`.

## 5. (Optional) Route output to an external channel

```bash
export AUTONOMOUS_NOTIFY_WEBHOOK_URL=https://<your-logic-app-or-teams-webhook>
```

Re-run a cycle; the result is POSTed to the webhook and `notifyStatus` becomes `delivered`.
If the webhook fails, the run is still recorded with `notifyStatus: "failed"` and a captured
`notifyError` (the cycle is **not** lost).

## 6. (Optional) Exercise the in-process scheduler locally

```bash
# Run the backend with the scheduler on; it polls and fires due directives itself.
AUTONOMOUS_SCHEDULER_ENABLED=true uv run uvicorn main:app --port 8000 --reload
```

The `AutonomousScheduler` evaluates each enabled directive's NCRONTAB `schedule` and runs the
cycle in-process when a slot comes due (recorded as `trigger: "timer"`). No separate process,
host, or key. A Cosmos lease guarantees at-most-once per slot even across multiple instances.

## 7. Run the tests

```bash
# Offline unit suite (in-memory doubles; no cloud):
uv run pytest tests/test_autonomous.py tests/test_autonomous_api.py tests/test_autonomous_scheduler.py -q

# Cosmos emulator integration (run + lease repositories), only if the emulator is up:
uv run pytest tests/test_autonomous_runs_cosmos.py -q -m emulator
```

## Production wiring (summary)

- The backend (App Service, the agent host) runs the `AutonomousScheduler` in-process, gated
  by the `AUTONOMOUS_SCHEDULER_ENABLED` app setting (empty ⇒ enabled in Azure). `always_on`
  keeps the host resident so the scheduler runs.
- No separate deployable, identity, or key. The two Cosmos containers (`autonomous-runs`,
  `autonomous-leases`) are declared in `infra/modules/cosmos`.
- All endpoints target Azure Government; the backend uses managed identity for Cosmos. The
  only HTTP entry point is the user-authenticated `/api/autonomous/*` API.

## How this maps to the target diagram

```text
In-process scheduler (App Service)  ──▶  run_autonomous_cycle()
   │  (poll loop + Cosmos lease per slot)     ├──▶ Agent runtime (reused)
   │                                          ├──▶ Cosmos: autonomous-runs (audit)
   └── at-most-once per slot ◀── Cosmos: autonomous-leases
                                              └──▶ Notification sink ──▶ review channel
```
This is the "Schedule → Duty Officer Agent → logs to Cosmos → drafts a notification for
approval" slice, with seams ready for the full CCIR triage pipeline.
