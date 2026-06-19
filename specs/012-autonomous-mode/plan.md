# Implementation Plan: Autonomous Mode (Scheduled Agent Duty Officer)

**Branch**: `012-autonomous-mode` | **Date**: 2026-06-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/012-autonomous-mode/spec.md`

## Summary

Add an **Autonomous Mode** to the platform: an **in-process scheduler in the FastAPI agent
backend** that, on a configurable cadence (or on-demand), executes a pre-defined **standing
directive** (an agent profile + an instruction) and captures the agent's response. The
scheduler **reuses the existing session orchestration and agent runtime** (no fork of agent
logic), persists a durable **autonomous run record** to Cosmos for audit, and delivers the
result to a pluggable **notification sink** (durable+log by default; optional outbound
webhook). A durable **Cosmos lease** keyed by (directive, slot) guarantees at-most-once
execution even when the backend scales to multiple instances. The only HTTP entry point is a
**user-authenticated** `POST /api/autonomous/run-now` (plus read endpoints for directives,
run history, and the shared Duty Officer conversation); the scheduled path runs in-process and
exposes no external trigger. Autonomous activity is owned by a distinct non-human **system
identity** so it never pollutes interactive users' histories. This delivers the
"Schedule → Duty Officer Agent → logs to Cosmos → drafts a notification" slice of the target
NETCOM CCIR triage diagram, with clean seams for the future triage pipeline.

## Technical Context

**Language/Version**: Python 3.12 (backend only); existing TypeScript/React frontend is
untouched by this feature.  
**Primary Dependencies**: FastAPI, `agent-framework` (existing runtime), `azure-cosmos`
(async), `croniter` (NCRONTAB schedule evaluation for the in-process scheduler), `httpx`
(existing, for the webhook sink). No separate deployment unit, so no second dependency manifest.  
**Storage**: Azure Cosmos DB (NoSQL, serverless) in the existing `agent-memory` database and
shared async `CosmosClient` — a new `autonomous-runs` container partitioned by `/directive_id`
(audit) and a new `autonomous-leases` container partitioned by `/directive_id` with per-item
TTL (scheduler at-most-once). Conversation history reuses the existing `CosmosHistoryProvider`.  
**Testing**: `pytest` (offline unit suite with the existing in-memory Cosmos doubles via the
autouse `_cosmos_doubles` fixture, plus an in-memory lease double); `@pytest.mark.emulator`
integration tests against the local Cosmos emulator for the real repositories.  
**Target Platform**: Azure Government (`.azure.us` / `.usgovcloudapi.net`) — the existing App
Service backend (the agent host) runs the scheduler in-process; `always_on` keeps it resident.
Local dev runs the backend with `AUTH_DISABLED=true` and the Cosmos emulator; the scheduler is
off by default locally (`AUTONOMOUS_SCHEDULER_ENABLED`).  
**Project Type**: Two-tier web app (FastAPI backend + React frontend). No new deployable unit —
the scheduler is a background task inside the existing backend.  
**Performance Goals**: Autonomous cycles are low-frequency (minutes-to-hours cadence), not a
throughput path. The scheduler polls cheaply (default 60s) and adds no latency to the
interactive chat path.  
**Constraints**: Reuse the existing agent runtime/tools/memory (no duplicate agent logic); no
secrets in logs/records/responses; Azure Government endpoints; managed identity in production,
keys only for local/emulator; `uv` for backend deps; offline unit suite must pass with no live
cloud.  
**Scale/Scope**: One deployment (possibly multiple instances), a handful of configured
directives, single-digit concurrent autonomous cycles at most. Run-record volume grows slowly
(one per cycle); lease docs self-expire via TTL.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Read-Only Data Access | ✅ PASS | Feature adds no SQL. Autonomous agent reuses existing read-only SQL tools unchanged; run records are app-owned audit writes to Cosmos, not user-database mutations. |
| II. Single-File Agent Definitions | ✅ PASS | No new agent profiles required. Directives reference existing `agents.yaml` profiles by id. Autonomous **directives** live in a separate `config/autonomous.yaml` (operational config, not agent/tool definitions) — tool docs remain in Python. |
| III. Security & Credential Hygiene | ✅ PASS | No service-to-service surface at all: the schedule runs in-process and the only entry point, `POST /api/autonomous/run-now`, uses the existing `get_current_user` auth (rejected outside local dev). No shared autonomous secret to store/rotate/leak. Azure Government endpoints; MI in prod. Only pre-defined directives can run (no arbitrary prompts). |
| IV. Evaluation-Driven Quality | ✅ PASS | No prompt/model/parameter change to existing profiles. The autonomous cycle reuses the same runtime and logs eval-style trace fields (input/output/tools/usage) into the run record. |
| V. Simplicity & Minimalism | ✅ PASS | Reuses `create_chat_session` + `stream_agent_response` (no agent-logic fork). Minimal new surface: two backend modules (`autonomous.py`, `autonomous_scheduler.py`), two small Cosmos repos+containers (runs, leases), one config file. No separate deployable, no service-to-service auth. Webhook sink is the single optional extension. |
| VI. Infrastructure as Code | ✅ PASS | No new compute/identity. The two Cosmos containers (`autonomous-runs`, `autonomous-leases`) are declared in the existing `infra/modules/cosmos` module; the App Service gains an `AUTONOMOUS_SCHEDULER_ENABLED` app setting. No portal clicks. |
| VII. Two-Tier API-First Architecture | ✅ PASS | No third deployable. The scheduler is a background task **inside** the FastAPI backend, so all agent functionality stays in the backend and the strict two-tier shape is preserved. The only external surface is the user-authenticated API. Frontend untouched. |

**Result**: PASS — no deviations. No gate blocks Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/012-autonomous-mode/
├── plan.md              # This file (/speckit.plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── autonomous-api.md        # Backend REST contract (/api/autonomous/*)
│   └── autonomous-config.md     # config/autonomous.yaml schema
├── checklists/
│   └── requirements.md  # Spec quality checklist (/speckit.specify output)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
# Backend (repository root — existing FastAPI app; the single agent host)
autonomous.py              # NEW: core autonomous cycle — run_autonomous_cycle(), directive
                           #      loading, AutonomousRunResult, response collection helper.
autonomous_scheduler.py    # NEW: in-process AutonomousScheduler (poll loop, slot calc via
                           #      croniter, Cosmos-lease claim) + scheduler_enabled() gate.
notifications.py           # NEW: NotificationSink protocol + LoggingSink + WebhookSink.
config/
└── autonomous.yaml        # NEW: directive definitions (id, profile_id, instruction,
                           #      schedule, enabled, notify) + global enabled flag.
cosmos_memory.py           # EDIT: add AutonomousRunRecord + CosmosAutonomousRunRepository +
                           #       CosmosAutonomousLeaseRepository + getters/close wiring.
main.py                    # EDIT: start/stop the scheduler in lifespan (gated); add POST
                           #       /api/autonomous/run-now (user-auth), GET /api/autonomous/runs,
                           #       GET /api/autonomous/directives, GET /api/autonomous/conversations.
session_orchestration.py   # REUSE (no fork): create_chat_session drives the agent cycle.
# auth.py                  # NO new service auth — the scheduler is in-process; run-now uses get_current_user.

# Infrastructure as Code (Terraform) — no new compute, just containers + one app setting
infra/
├── modules/app-service/   # EDIT: add AUTONOMOUS_SCHEDULER_ENABLED app setting.
└── modules/cosmos/        # EDIT: declare autonomous-runs + autonomous-leases containers
                           #       (leases container has default_ttl = -1 for per-item TTL).

# Tests (repository root tests/)
tests/
├── _doubles.py            # EDIT: add InMemoryAutonomousRunRepository + InMemoryAutonomousLeaseRepository.
├── conftest.py            # EDIT: autouse fixture injects the run-record + lease doubles.
├── test_autonomous.py            # NEW: run_autonomous_cycle + notification sink + directive load.
├── test_autonomous_api.py        # NEW: /api/autonomous/* endpoints (user auth).
├── test_autonomous_scheduler.py  # NEW: scheduler slots, lease single-fire, gating (in-process).
└── test_autonomous_runs_cosmos.py # NEW: @pytest.mark.emulator run + lease repo CRUD.
```

**Structure Decision**: Keep the existing two-tier app as the **single agent host** and add
everything **inside the backend**. The core cycle (`autonomous.py`) reuses
`session_orchestration.create_chat_session` and `streaming.stream_agent_response` so there is
**no duplicate agent runtime**. A background `AutonomousScheduler` (`autonomous_scheduler.py`)
started from the FastAPI lifespan wakes on a poll interval, computes due slots with `croniter`,
and claims each slot with a Cosmos lease before running the cycle — guaranteeing at-most-once
execution across instances. Persistence reuses the shared Cosmos client and `agent-memory`
database with two new containers (runs + leases). Infrastructure adds those two containers and
one App Service app setting — no new deployable, identity, or service-to-service auth.

## Complexity Tracking

> No constitutional deviations. An earlier revision proposed an external Azure Functions app
> (a third deployable) to host the timer; that was **reverted** in favor of an in-process
> scheduler because the Function added a deployment unit, a managed identity, and a
> service-to-service auth surface with no benefit over a background task in the backend that
> already owns the agent runtime and Cosmos access. The Cosmos lease provides the
> multi-instance safety the Function's singleton timer would have given, without leaving the
> two-tier shape.
