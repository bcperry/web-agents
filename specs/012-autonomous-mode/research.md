# Phase 0 Research: Autonomous Mode

This document resolves the technical unknowns and records the key decisions (with
rationale and rejected alternatives) that shape the implementation plan.

## R1 — Where does the agent run, and what drives the schedule?

**Decision**: Both the agent **and** the schedule run **in the existing FastAPI backend**
(the App Service "agent host"). The reusable cycle logic lives in `autonomous.py`
(`run_autonomous_cycle`), invoking `session_orchestration.create_chat_session` +
`streaming.stream_agent_response`; an in-process `AutonomousScheduler`
(`autonomous_scheduler.py`) started from the FastAPI lifespan drives the cadence. There is
**no external trigger** and **no service-to-service HTTP hop**.

**Rationale**:
- The agent host is the App Service; the cadence is just a background task in that same
  process, reusing the entire agent runtime, tools, MCP connections, sub-agents, skills, and
  durable Cosmos memory with **zero duplication** (Constitution V).
- Removing the external trigger removes a whole deployment unit, a managed identity, and a
  service-to-service auth surface — none of which earned their keep (see R3, R10).
- The scheduler and cycle are fully unit-testable in-process with the existing test doubles
  (no Azure runtime needed).

**Alternatives rejected**:
- *External Azure Functions timer calling the backend over HTTP* (the original design): adds
  a deployable, an identity, and a shared-key/managed-identity auth surface for no benefit
  over a background task in the process that already owns the runtime. Multi-instance safety
  is instead provided by a Cosmos lease (R8).
- *Run the agent inside a Function*: duplicates the runtime surface and forks deployment.

## R2 — In-process scheduling mechanism

**Decision**: A single asyncio background task (`AutonomousScheduler`) started/stopped from the
FastAPI **lifespan**, gated by `AUTONOMOUS_SCHEDULER_ENABLED` (off by default locally). It
**polls** on a fixed interval (default 60s); each tick it computes, per enabled directive, the
most recent due "slot" from the directive's NCRONTAB `schedule` using `croniter`
(`second_at_beginning=True`), and runs the cycle when the slot has advanced since the last one
it handled. On startup it seeds the current slot as already-handled so a redeploy/restart does
not immediately re-fire.

**Rationale**:
- A background task is the minimal mechanism for a low-cadence schedule — no new runtime,
  deployable, or framework. `croniter` evaluates the same 6-field NCRONTAB the directives use.
- Polling (rather than sleeping until the next fire) is simple, restart-safe, and bounds firing
  latency to the poll interval — fine for a minutes-to-hours cadence.
- Lifespan start/stop gives deterministic startup/shutdown and clean cancellation.

**Alternatives rejected**:
- *External Azure Functions timer*: see R1/R10 — a deployable + auth surface for no benefit.
- *APScheduler / a scheduler-thread library*: heavier than a ~150-line asyncio loop; the lease
  (R8), not a scheduler library, provides multi-instance safety.

## R3 — Authentication (no service-to-service surface)

**Decision**: Because the schedule runs **in-process**, there is no trigger-to-backend call to
authenticate and **no shared key**. The only HTTP entry point is the user-initiated
`POST /api/autonomous/run-now`, guarded by the existing `get_current_user` dependency (Azure AD
bearer in prod, `AUTH_DISABLED=true` bypass locally) — identical to every other user endpoint.
Read endpoints (`/runs`, `/directives`, `/conversations`) likewise use `get_current_user`.

**Rationale**:
- Deleting the external trigger deletes the service-to-service auth problem entirely — the
  strongest possible credential-hygiene outcome (Constitution III): there is no autonomous
  secret to store, rotate, or leak.
- `run-now` is just a normal authenticated action; it can only select a *pre-configured*
  directive, never a free-form prompt (FR-013).

**Alternatives rejected** (considered while the external trigger still existed, then made moot
by R1):
- *Shared `X-Autonomous-Key` header*: a static secret to leak/rotate.
- *Managed-identity bearer token (Function MI → backend app registration + app role)*: the
  "correct" service-to-service control, but it required Entra app-role assignment and a second
  identity for a call that no longer exists.

## R4 — How to collect the agent's full response without SSE

**Decision**: Reuse `streaming.stream_agent_response(agent, contents, session)` and
**accumulate** its `text` events server-side, then read the function attribute
`stream_agent_response._last_result` (`{text, tool_events, usage}`) that it already sets at
stream completion. Wrap in a small `collect_agent_response(...)` helper in `autonomous.py`.

**Rationale**:
- Reuses the exact, already-tested streaming/usage/tool-event extraction path the
  interactive `send_message` endpoint uses — no second code path for agent invocation
  (Constitution V, FR-004).
- `_last_result` already exposes the final text, tool events, and merged usage needed for the
  run record and notification.

**Alternatives rejected**:
- *Call `agent.run(...)` non-streaming directly*: would create a second invocation path with
  separate usage/tool-event handling to maintain and test.
- *Parse the SSE wire text*: brittle; the in-process accumulation is direct.

## R5 — Autonomous run audit storage (Cosmos)

**Decision**: A new Cosmos container **`autonomous-runs`** in the existing `agent-memory`
database, partitioned by **`/directive_id`**. New `AutonomousRunRecord` dataclass and
`CosmosAutonomousRunRepository` in `cosmos_memory.py`, following the existing
`CosmosConversationRepository` pattern (shared async client, `create_container_if_not_exists`,
`upsert_item`, partition-scoped queries). `get_autonomous_run_repository()` singleton +
`close`/clear wiring. An `InMemoryAutonomousRunRepository` double mirrors it for the offline
suite (registered in the autouse fixture).

**Rationale**:
- Reuses the established repo pattern, the shared client, serverless billing, and the same
  durability/auth model (MI in prod, emulator key locally) — Constitution VI and the Cosmos
  data-modeling guidance (partition on a high-cardinality key matching the dominant query).
- Partitioning by `/directive_id` matches "list runs for a directive" and keeps a single
  directive's history co-located; a global most-recent-first list is a cross-partition query
  bounded by `limit` (low volume, acceptable).
- New container (not a new account/db) keeps cost and surface minimal.

**Alternatives rejected**:
- *Reuse the `conversations` container*: conflates the per-user chat index with audit;
  different partition semantics and ownership.
- *Partition by run date*: weaker cardinality and worse for per-directive queries; the
  primary access pattern is per-directive and recency.

## R6 — Directive configuration format

**Decision**: A new `config/autonomous.yaml` with a top-level `enabled` flag and a
`directives:` list. Each directive: `id`, `profile_id` (references `agents.yaml`),
`instruction` (the standing prompt), `schedule` (NCRONTAB hint / human cadence note),
`enabled`, and optional `notify` (`{webhook: <env-var-name|url>}`). Loaded and validated by
`autonomous.py` (`load_directives()`), with an env override `AUTONOMOUS_ENABLED`.

**Rationale**:
- YAML config matches the project's existing `config/agents.yaml` convention; directives are
  *operational* config, not agent/tool definitions, so a separate file respects Constitution
  II (single `agents.yaml` is for agent profiles + tool lists).
- Referencing existing profiles by id avoids new agent definitions and keeps tool docs in
  Python.

**Alternatives rejected**:
- *Encode directives in `agents.yaml`*: mixes operational scheduling with agent definitions;
  muddies the single-purpose agent config.
- *Environment-variable-only directives*: not expressive enough for multiple directives and
  per-directive routing.

## R7 — Notification sink design

**Decision**: A `NotificationSink` Protocol in `notifications.py` with two implementations:
`LoggingSink` (default — logs a structured summary; the durable record is the Cosmos run
record) and `WebhookSink` (POST JSON to a configured URL via `httpx`, used when a directive's
`notify.webhook` or the global `AUTONOMOUS_NOTIFY_WEBHOOK_URL` resolves to a URL). Delivery
failures are caught, recorded on the run record (`notify_status`/`notify_error`), and never
abort the cycle (FR-009).

**Rationale**:
- Minimal, pluggable seam that satisfies "default safe sink + optional external channel"
  (FR-008) and the "drafts a notification" diagram step, without committing to Teams Adaptive
  Card formatting yet (out of scope).
- Reuses `httpx` (already a dependency). Webhook URL/secret resolved from env, never logged.

**Alternatives rejected**:
- *Hard-wire Teams/Bot Service now*: out of scope and environment-specific; the webhook seam
  can target a Logic App or Teams Incoming Webhook today and an Adaptive Card formatter later.

## R8 — Overlap, multi-instance concurrency, and idempotency

**Decision**: Each directive runs in **one ongoing conversation** (a deterministic
`autonomous-{directive_id}` id that is *resumed* every cycle, so the agent accumulates memory
like a human reopening a saved chat), while each **run** writes its own audit record keyed by a
unique run id. At-most-once execution per scheduled slot — including across multiple backend
instances — is guaranteed by a **Cosmos lease**: before running a slot, the scheduler atomically
`create_item`s a document keyed `{directive_id}:{slot}`; the first writer wins, a `409` means
another instance (or an earlier tick) already claimed it, so the slot is skipped. Lease docs
carry a per-item TTL so they self-clean. The scheduler also tracks the last slot it handled to
avoid re-claiming within an instance.

**Rationale**:
- The lease is the multi-instance safety the original design leaned on the Functions timer's
  singleton behavior for — but it holds for *any* number of App Service instances and is
  independent of the hosting model.
- Per-run unique audit ids mean overlapping work can never corrupt a shared record
  (FR-016/FR-017); the ongoing per-directive conversation gives the duty officer continuity.

**Alternatives rejected**:
- *Rely on a singleton timer / single instance*: couples correctness to the hosting model and
  breaks the moment the App Service scales out.
- *Distributed lock service*: unnecessary; an atomic Cosmos create IS the lock, no new
  dependency.

## R9 — System identity for autonomous activity

**Decision**: A synthetic `AuthenticatedUser(user_id=AUTONOMOUS_USER_ID,
username="Autonomous Duty Officer")`, default id `autonomous-duty-officer`, constructed in
`autonomous.py`. All autonomous conversations and run records are owned by this id.

**Rationale**:
- Satisfies FR-014/SC-007: autonomous history is isolated and never appears in interactive
  users' conversation lists (those are partitioned by the real user's id).
- Reuses the existing `AuthenticatedUser`/ownership model unchanged.

**Alternatives rejected**:
- *Reuse a real user id*: pollutes that user's history and audit ownership.

## R10 — Infrastructure shape (no new compute)

**Decision**: No new compute or identity. The scheduler runs in the existing App Service
(which already has `always_on = true` and the Cosmos data role). Infrastructure adds only:
(1) two Cosmos containers declared in `infra/modules/cosmos` — `autonomous-runs` (partition
`/directive_id`) and `autonomous-leases` (partition `/directive_id`, `default_ttl = -1` so
per-item TTL applies); and (2) an `AUTONOMOUS_SCHEDULER_ENABLED` app setting on the App Service
(empty defaults to enabled in Azure).

**Rationale**:
- Containers must be declared in IaC because the app's data-plane role cannot create containers
  when account-key auth is disabled (`local_authentication_disabled = true`); lazy
  `create_container_if_not_exists` only covers the emulator/local path.
- Reuses the backend's existing managed identity and Cosmos data role — least privilege with no
  new principal.

**Alternatives rejected**:
- *A `function-app` Terraform module + second managed identity*: provisions a deployable and an
  identity for a trigger that no longer exists.

## Summary of decisions

| # | Decision |
|---|----------|
| R1 | Agent **and** schedule run in the backend; no external trigger, no HTTP hop. |
| R2 | In-process `AutonomousScheduler` (asyncio lifespan task, croniter slots, poll loop, gated). |
| R3 | No service-to-service auth surface; `run-now` uses the normal user session. No shared key. |
| R4 | Reuse `stream_agent_response` + `_last_result` to collect the response. |
| R5 | `autonomous-runs` Cosmos container, partition `/directive_id`; repo + in-memory double. |
| R6 | `config/autonomous.yaml` directives referencing existing profiles. |
| R7 | `NotificationSink` (Logging default + optional Webhook); delivery failure is non-fatal. |
| R8 | One ongoing conversation per directive + unique per-run audit id; **Cosmos lease** = at-most-once per slot across instances. |
| R9 | Synthetic system identity `autonomous-duty-officer` owns autonomous data. |
| R10 | No new compute/identity; add `autonomous-runs` + `autonomous-leases` containers + one app setting. |
