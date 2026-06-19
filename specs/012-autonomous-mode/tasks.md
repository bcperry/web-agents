# Tasks: Autonomous Mode

**Input**: Design documents from `/specs/012-autonomous-mode/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included. The user requested a complete implementation and this repository has an
established offline pytest suite with in-memory Cosmos doubles; tests are part of "done".

**Organization**: Tasks are grouped by user story (US1–US5) so each slice is independently
implementable and testable. Priorities: US1 (P1), US2 (P1), US3 (P2), US4 (P2), US5 (P2).

> **Rebuild note:** the design was revised to an **in-process scheduler** (no Azure Function,
> no shared key — see plan.md / research.md). This task list is retargeted to that design. The
> original branch implemented an earlier (Function-App) version that was **reverted to `main`**;
> the **backend was then rebuilt from scratch** against this in-process design (not the reverted
> code). Backend phases 1–8 are complete and verified (266-test offline suite + emulator + a live
> end-to-end cycle). The only remaining box is the frontend nav wiring (T044).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- File paths are repository-root-relative (this repo is flat: backend modules at root,
  `infra/`, `config/`, `tests/`)

## Path Conventions

- Backend (agent host): root-level Python modules (`autonomous.py`, `autonomous_scheduler.py`,
  `notifications.py`, `main.py`, `cosmos_memory.py`)
- Config: `config/autonomous.yaml`
- Infrastructure: `infra/` (Terraform — Cosmos containers + App Service setting; no new compute)
- Tests: `tests/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffolding and dependencies for the feature

- [X] T001 Create `config/autonomous.yaml` with `schema_version: 1`, `enabled: true`,
  `system_user_id: autonomous-duty-officer`, and one default directive
  (`id: duty-officer-watch`, `profile_id: chief-of-staff`, a watch-officer `instruction`,
  `schedule`, `notify` referencing `AUTONOMOUS_NOTIFY_WEBHOOK_URL`) per
  `contracts/autonomous-config.md`.
- [X] T002 [P] Ensure `httpx` (WebhookSink) and `croniter` (scheduler NCRONTAB evaluation) are
  explicit backend dependencies in `pyproject.toml`; run `uv sync` to confirm. (uv only — never pip.)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared data + config layer that every user story depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [US-shared] Add `AutonomousRunRecord` dataclass in `cosmos_memory.py` with
  `to_doc()`/`from_doc()`/`to_wire()` (camelCase wire keys) per `data-model.md`
  (fields: id, directive_id, profile_id, session_id, status, started_at, finished_at,
  response_text, tool_events, usage, error, notify_status, notify_error, trigger,
  doc_type=`autonomous_run`, schema_version=1). No secrets in any field.
- [X] T004 [US-shared] Add `CosmosAutonomousRunRepository` (container `autonomous-runs`,
  partition `/directive_id`) with `create_run()`, `list_runs(limit, directive_id=None)`,
  `get_run(id, directive_id)` and a module-level `get_autonomous_run_repository()` singleton
  in `cosmos_memory.py`; wire it into the existing `close_cosmos_*` / `clear_*` lifecycle
  helpers and `create_container_if_not_exists` startup path.
- [X] T005 [P] [US-shared] Add `InMemoryAutonomousRunRepository` to `tests/_doubles.py`
  mirroring the Cosmos repo's interface (create/list/get, recency-ordered).
- [X] T006 [US-shared] Wire the in-memory autonomous-run repo into the autouse
  `_cosmos_doubles` fixture and `clear_cosmos_singletons` in `tests/conftest.py` so unit
  tests never touch a real Cosmos account.
- [X] T007 [US-shared] Create `autonomous.py` config layer: `Directive` dataclass,
  `AutonomousConfig` dataclass, `load_autonomous_config(path)` /
  `load_directives()` reading `config/autonomous.yaml`, applying env overrides
  (`AUTONOMOUS_ENABLED`, `AUTONOMOUS_USER_ID`), duplicate-id rejection, and treating a
  missing file as a disabled no-op (per `contracts/autonomous-config.md`).

**Checkpoint**: Data + config foundation ready — user stories can now begin.

---

## Phase 3: User Story 1 - Agent Acts on a Standing Directive Without a Human Present (P1) 🎯 MVP

**Goal**: A configured directive causes the agent to take an action and produce a response
with no human in the loop.

**Independent Test**: `POST /api/autonomous/run-now` (or call `run_autonomous_cycle` directly)
with no chat input returns a completed response derived solely from the directive instruction.

### Tests for User Story 1 ⚠️ (write first, ensure they fail)

- [X] T008 [P] [US1] Unit test in `tests/test_autonomous.py`: `run_autonomous_cycle` builds a
  session for the directive's profile, sends the directive instruction, and returns an
  `AutonomousRunResult` with non-empty `response_text`, captured `tool_events`, and `usage`
  (using the fake agent runtime double).
- [X] T009 [P] [US1] API test in `tests/test_autonomous_api.py`: `POST /api/autonomous/run-now`
  with `{}` returns `200` and the run wire shape; omitting `directive_id` runs the first enabled
  directive; unknown `directive_id` returns `404`.

### Implementation for User Story 1

- [X] T010 [US1] Implement system identity helper in `autonomous.py`
  (`system_user(config) -> AuthenticatedUser(user_id=system_user_id, username="Autonomous Duty Officer")`).
- [X] T011 [US1] Implement `run_autonomous_cycle(ctx, directive, *, trigger, logger)` in
  `autonomous.py`: create a fresh session via `session_orchestration.create_chat_session`
  for `directive.profile_id` owned by the system identity, drive the agent by consuming
  `streaming.stream_agent_response`, read `stream_agent_response._last_result`
  (text/tool_events/usage), and return an `AutonomousRunResult`. Catch dependency/profile
  errors and return a failure result (never raise to the caller).
- [X] T012 [US1] Add `POST /api/autonomous/run-now` endpoint in `main.py` (request model
  `{directive_id?}`, user-authenticated via `get_current_user`), resolving the directive
  (explicit or first-enabled), calling `run_autonomous_cycle(_session_context, ..., trigger="manual")`,
  and returning the run wire shape; `404` for unknown directive, `409` when disabled.
- [X] T013 [US1] Add structured logging (no secrets) around each cycle in `autonomous.py`
  (start/finish, directive id, status, duration).

**Checkpoint**: The agent acts on a directive end-to-end and returns a response unattended.

---

## Phase 4: User Story 2 - Every Autonomous Action Is Auditable (P1)

**Goal**: Every cycle writes one durable, tamper-evident run record; history is queryable.

**Independent Test**: After a cycle, `GET /api/autonomous/runs` returns the record; it
survives a backend restart (Cosmos durability).

### Tests for User Story 2 ⚠️

- [X] T014 [P] [US2] API test in `tests/test_autonomous_api.py`: after a `run`, `GET
  /api/autonomous/runs` returns the record most-recent-first; `limit` and `directive_id`
  filters honored; response contains no secret fields.
- [X] T015 [P] [US2] Emulator test in `tests/test_autonomous_runs_cosmos.py`
  (`@pytest.mark.emulator`): `CosmosAutonomousRunRepository` create→list→get round-trips a
  record against the Cosmos emulator (partition `/directive_id`).

### Implementation for User Story 2

- [X] T016 [US2] Persist exactly one `AutonomousRunRecord` at the end of every cycle
  (success or caught failure) in `run_autonomous_cycle` via `get_autonomous_run_repository()`
  — single write, never partial (FR-016).
- [X] T017 [US2] Add `GET /api/autonomous/runs` endpoint in `main.py`
  (`limit` default 50/max 200, optional `directive_id`) returning `{runs, count}` using the
  repository; standard user auth.
- [X] T018 [US2] Ensure run records and API responses exclude credentials/secrets and
  truncate `response_text` sanely (full text remains in chat history); verify in `to_wire()`.

**Checkpoint**: Autonomous actions are fully auditable and durable.

---

## Phase 5: User Story 3 - Autonomous Output Is Routed to Humans for Review (P2)

**Goal**: Each completed cycle is delivered to a human-review channel; delivery outcome is
recorded and delivery failure is non-fatal.

**Independent Test**: With a webhook configured, a cycle POSTs its result and records
`notifyStatus: delivered`; with the webhook failing, the run still persists with
`notifyStatus: failed` + `notifyError`.

### Tests for User Story 3 ⚠️

- [X] T019 [P] [US3] Unit tests in `tests/test_autonomous.py`: `LoggingSink` returns
  `logged`; `WebhookSink` success returns `delivered`; `WebhookSink` HTTP error returns
  `failed` with a sanitized error and does NOT raise (cycle still completes).

### Implementation for User Story 3

- [X] T020 [P] [US3] Create `notifications.py`: `NotificationSink` Protocol, `LoggingSink`
  (default), `WebhookSink` (httpx POST, timeout, sanitized errors), and
  `build_notification_sink(directive, config)` resolving env-var-name-or-URL with global
  fallback per `contracts/autonomous-config.md`.
- [X] T021 [US3] Wire notification delivery into `run_autonomous_cycle` after the agent
  completes: build the sink, deliver, and record `notify_status` / `notify_error` on the run
  (delivery failure is caught and non-fatal).

**Checkpoint**: Autonomous output reaches a review channel without losing the audit record.

---

## Phase 6: User Story 4 - Operators Configure and Control Autonomous Behavior (P2)

**Goal**: Operators enable/disable autonomy and inspect configured directives without code
changes or secret exposure.

**Independent Test**: `enabled: false` (or `AUTONOMOUS_ENABLED=false`) makes `run` a no-op
(`409`); `GET /api/autonomous/directives` lists directives without secrets.

### Tests for User Story 4 ⚠️

- [X] T022 [P] [US4] Tests in `tests/test_autonomous_api.py`: when disabled, `POST
  /api/autonomous/run-now` returns `409` and writes no record; `GET /api/autonomous/directives`
  returns `{enabled, systemUserId, directives[]}` with truncated `instructionSummary` and a
  non-secret `notify` descriptor.

### Implementation for User Story 4

- [X] T023 [US4] Enforce the master/per-directive enable gate in `run_autonomous_cycle` and
  the `run-now` endpoint (disabled → `409`, no cycle, no record).
- [X] T024 [US4] Add `GET /api/autonomous/directives` endpoint in `main.py` returning the
  sanitized directive listing (no secrets; `notify` as `"webhook"`/`"log"`).
- [X] T025 [US4] Add an "Autonomous mode" startup summary log line in `main.py` (enabled,
  directive count, system identity) — no secrets.

**Checkpoint**: Autonomy is intentional, inspectable, and controllable.

---

## Phase 7: User Story 5 - The Scheduler Is Gated and the Manual Trigger Is Authenticated (P2)

**Goal**: An in-process scheduler runs due directives unattended (gated by a flag, at-most-once
across instances via a Cosmos lease); the only HTTP entry point is the user-authenticated
`run-now`.

**Independent Test**: With the scheduler flag off, no cycles run; with it on, a due directive
fires once per slot (even with two scheduler instances sharing the lease store). `run-now`
requires a normal user session.

### Tests for User Story 5 ⚠️

- [X] T026 [P] [US5] Scheduler tests in `tests/test_autonomous_scheduler.py`: a due directive
  fires once per slot and again on the next slot; baseline-seeding skips the current slot on
  start; a disabled config never fires; two scheduler instances sharing the (in-memory) lease
  store fire the slot exactly once.
- [X] T027 [P] [US5] Lease emulator test in `tests/test_autonomous_runs_cosmos.py`
  (`@pytest.mark.emulator`): `CosmosAutonomousLeaseRepository.try_acquire` returns True for the
  first claim of `{directive}:{slot}` and False for a duplicate.

### Implementation for User Story 5

- [X] T028 [US5] Add `CosmosAutonomousLeaseRepository` (container `autonomous-leases`, partition
  `/directive_id`, `default_ttl = -1`) with `try_acquire(directive_id, slot, ttl)` (atomic
  `create_item`; `CosmosResourceExistsError` → False) + `get_autonomous_lease_repository()`
  singleton + close/clear wiring in `cosmos_memory.py`; add `InMemoryAutonomousLeaseRepository`
  to `tests/_doubles.py` and inject it in the autouse fixture.
- [X] T029 [US5] Create `autonomous_scheduler.py`: `scheduler_enabled()` gate
  (`AUTONOMOUS_SCHEDULER_ENABLED`), `_current_slot(schedule, now)` via `croniter`, and
  `AutonomousScheduler` (poll loop, baseline-seed on start, per-(directive, slot) lease claim,
  then `run_autonomous_cycle(..., trigger="timer")`).
- [X] T030 [US5] Start/stop the scheduler from the FastAPI lifespan in `main.py` when
  `scheduler_enabled()` (create on startup, cancel/await on shutdown); never block startup.
- [X] T031 [US5] Keep `run-now` user-authenticated: `POST /api/autonomous/run-now` depends on
  `get_current_user` only (no service key, no `require_autonomous_caller`, no `X-Autonomous-Key`).
- [X] T032 [US5] Declare the `autonomous-runs` and `autonomous-leases` containers in
  `infra/modules/cosmos` (`main.tf` + `variables.tf` + `outputs.tf`); the leases container sets
  `default_ttl = -1` so per-item TTL applies. Wire the container names through the app-service
  module env (`AZURE_COSMOS_AUTONOMOUS_CONTAINER`, `AZURE_COSMOS_LEASES_CONTAINER`).
- [X] T033 [US5] Add the `AUTONOMOUS_SCHEDULER_ENABLED` app setting to
  `infra/modules/app-service` (empty ⇒ `"true"`) and the `autonomous_scheduler_enabled` variable
  through `infra/variables.tf`, `infra/main.tf`, `infra/main.tfvars.json`, and `azure.yaml`
  parameters. No function-app module, no `autonomous` azd service, no trigger key.

**Checkpoint**: The schedule runs in-process, single-fire across instances, with no external
trigger and no shared secret.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T036 [P] Update `README.md` with an Autonomous Mode section (in-process scheduler,
  config, endpoints, local run) linking to `specs/012-autonomous-mode/quickstart.md`.
- [X] T037 Run the full offline suite `uv run pytest -q` and fix any failures; confirm the
  new autonomous unit tests pass without a real Cosmos account.
- [X] T038 [P] Validate `terraform fmt`/`validate` in `infra/` for the Cosmos container +
  app-setting changes (no apply).
- [X] T039 Execute the `quickstart.md` manual steps (backend up, trigger a cycle, list runs)
  and reconcile any drift between docs and behavior.

---

## Phase 9: User Story 6 - All Users See and Ask the Autonomous Agent (P2)

**Goal**: Every authenticated user can view the autonomous agent (status, standing orders,
activity audit trail) and ask it questions from the web app — no admin role required.

**Independent Test**: A normal (non-admin) user opens the **Duty Officer** page, sees the
enabled status + directives + recent runs (expandable), and exchanges a chat message with the
duty officer agent.

### Implementation for User Story 6

- [X] T040 [US6] Add `AutonomousDirective`, `AutonomousDirectivesResponse`, `AutonomousRun`,
  and `AutonomousRunsResponse` types to `frontend/src/types/api.ts` (camelCase mirror of the
  backend `to_wire()` shapes, no secrets).
- [X] T041 [US6] Add `fetchAutonomousDirectives()` and `fetchAutonomousRuns(limit, directiveId)`
  to `frontend/src/api/client.ts` following the existing fetch + `getAuthHeaders` pattern
  (normal-user auth; both endpoints already exist on the backend).
- [X] T042 [US6] Create `frontend/src/pages/AutonomousPage.tsx`: enabled banner, standing
  orders list, recent-activity audit list (expandable: response, tool count, token usage,
  notify status), and an **Ask the Duty Officer** chat panel reusing `useChat` auto-started
  with the directive's profile (`chief-of-staff`). Includes refresh + "Ask about this".
- [X] T043 [US6] Add Duty Officer page styling to `frontend/src/styles/index.css` (reusing
  the existing design tokens; responsive stacked layout under 900px).
- [ ] T044 [US6] Wire navigation for all users: new `'autonomous'` view + history handlers in
  `frontend/src/App.tsx`, and a **Duty Officer** sentinel agent card in the **Automations**
  group on the agents page (`frontend/src/pages/ChatPage.tsx`) that routes to the autonomous
  console via `onOpenAutonomous`. (No settings-menu item.)
- [X] T045 [P] [US6] Add `scripts/capture_autonomous_page_screenshots.py` (mock-driven, no
  live backend) and capture visual references to `screenshots/012-autonomous-mode/`.
- [X] T046 [US6] Verify the frontend: `npm run test` (tsc), `npm run lint`, and `npm run build`
  all pass.

**Checkpoint**: The autonomous agent is discoverable, observable, and conversational for every
authenticated user.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**.
- **User Stories (Phase 3–7)**: All depend on Foundational. US1→US2 share the cycle
  (US2 adds persistence + listing to the cycle US1 creates), so do US1 then US2. US3, US4,
  US5 build on the US1/US2 cycle but are otherwise independent and could be parallelized.
- **Polish (Phase 8)**: After the desired stories are complete.

### User Story Dependencies

- **US1 (P1)**: After Foundational. The MVP — agent acts on a directive.
- **US2 (P1)**: Builds directly on US1's cycle (adds the single-write persistence + `/runs`).
- **US3 (P2)**: After US1 (delivers the cycle's result); independent of US2/US4/US5.
- **US4 (P2)**: After Foundational (config) + US1 endpoint; independent of US3/US5.
- **US5 (P2)**: After US1 (the cycle it schedules) + Foundational (run/lease repos); the
  scheduler, lease, gating, and infra tasks are otherwise self-contained.

### Within Each User Story

- Tests first (and failing) → implementation.
- Models/config before services; services before endpoints; core before integration.

### Parallel Opportunities

- T002 (deps) ∥ T001 (config) in Setup.
- T005 (doubles) is [P] within Foundational.
- Each story's `[P]` test tasks can be written together; `notifications.py` (T020) and the
  scheduler/lease work (T028/T029) touch distinct files.
- US3, US4, US5 can be staffed in parallel once US1/US2 land.

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Phase 1 Setup → Phase 2 Foundational.
2. Phase 3 US1 → **STOP & VALIDATE**: agent acts on a directive unattended.
3. Phase 4 US2 → durable audit + `/runs`. This is the demoable MVP that "snaps into" the
   diagram (Schedule→Agent→Cosmos audit), with the in-process scheduler added next.

### Incremental Delivery

US3 (notify humans) → US4 (configure/control) → US5 (in-process scheduler + lease + infra),
each independently testable, then Phase 8 polish and full-suite validation.
