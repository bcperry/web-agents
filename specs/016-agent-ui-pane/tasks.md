# Tasks: Agent Dynamic UI Pane

**Input**: Design documents from `/specs/016-agent-ui-pane/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)

**Tests**: Included. The spec explicitly requires an "automated security test suite" (SC-002) and an
"isolation test suite" (SC-003), and the constitution requires backend tests to pass before merge.
Test tasks are therefore scoped to the security-critical and contract paths, not blanket coverage.

**Organization**: Tasks are grouped by user story so each story can be implemented, tested, and
demonstrated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete work)
- **[Story]**: The user story this task serves (US1–US4)

## Path Conventions

Two-tier web app per [plan.md](plan.md): Python backend modules at the repository root with routes
in `api_routes/`, React SPA in `frontend/src/`, backend tests in `tests/`, Terraform in `infra/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Storage provisioning, tunable limits, and shared types that everything else builds on.

- [X] T001 [P] Declare the `agent_views` Cosmos container (name `agent-views`, `partition_key_paths = ["/user_id"]`) in infra/modules/cosmos/main.tf, mirroring the existing `user_profiles` resource
- [X] T002 [P] Create agent_views.py with a local `_env_int` helper and the limit constants `MAX_AGENT_VIEW_CHARS` (250000), `MAX_AGENT_VIEWS_PER_CONVERSATION` (50), `MAX_VIEW_DATA_RESPONSE_CHARS` (20000), `MAX_VIEW_DATA_REQUESTS_PER_MINUTE` (60)
- [X] T003 [P] Add `AgentView`, `AgentViewSummary`, `SSEAgentViewEvent`, and the `agentui.*` bridge envelope types to frontend/src/types/api.ts per contracts/view-bridge.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Persistence and tool-registration plumbing that every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Add `CosmosAgentViewRepository` (partition `/user_id`, top-level `conversation_id`, methods `list_for_conversation`, `get`, `create`, `delete_for_conversation`) and the `get_agent_views_repository()` singleton to user_data.py, following the `CosmosUserScopedRepository` pattern
- [X] T005 Add the view record shape, `title`/`html` validation, FIFO eviction at `MAX_AGENT_VIEWS_PER_CONVERSATION`, and the `save_view()` / `list_views()` / `get_view()` helpers to agent_views.py per data-model.md (depends on T002, T004)
- [X] T006 Add a `session_scoped: bool = False` field to `FunctionToolRegistration` and pass `session_id` to session-scoped factories inside `build_tool_instances` in app_context.py, leaving existing user-only factories unchanged
- [X] T007 [P] Add tests/test_agent_views.py covering empty-title rejection, oversize HTML rejection, FIFO eviction at the cap, and partition-scoped repository reads using the in-memory doubles in tests/_doubles.py

**Checkpoint**: Views can be stored and retrieved, and a session-aware tool can be registered.

---

## Phase 3: User Story 1 - An Agent Shows a View Instead of Describing One (Priority: P1) 🎯 MVP

**Goal**: An enabled agent authors a view that appears, rendered and isolated, in a right-hand pane
beside the conversation, with a transcript marker and safe failure behavior.

**Independent Test**: Grant `render_agent_view` to one profile, ask for a visual answer, and confirm
the pane opens with the rendered view while chat keeps streaming. Remove the grant and confirm no
pane appears.

### Implementation for User Story 1

- [X] T008 [US1] Implement `build_render_agent_view_tool(user_id, session_id)` in tools.py returning the `render_agent_view(title, html)` async tool, with the docstring contract from contracts/tool-contract.md (self-contained markup, `window.agentData`, no external URLs, no emoji, still answer in chat)
- [X] T009 [US1] Register `render_agent_view` as a `session_scoped=True` entry in `function_tool_registry()` in app_context.py (depends on T006, T008)
- [X] T010 [US1] Emit the `agent_view` SSE event from `stream_agent_response` in streaming.py when a `function_result` for `render_agent_view` reports `status: "rendered"`, per contracts/sse-events.md
- [X] T011 [US1] Create api_routes/agent_views.py with `GET /api/sessions/{session_id}/views` and `GET /api/sessions/{session_id}/views/{view_id}`, both requiring `get_current_user` and re-checking ownership via `ConversationIndexRepository.get_owned`
- [X] T012 [US1] Register the `agent_views` router in the `include_router` loop in main.py
- [X] T013 [P] [US1] Add `listAgentViews()` and `getAgentView()` plus the `onAgentView` callback and `agent_view` case in `dispatchSSEEvent` to frontend/src/api/client.ts
- [X] T014 [P] [US1] Create frontend/src/components/AgentViewFrame.tsx rendering `<iframe sandbox="allow-scripts">` (no `allow-same-origin`) with the host CSP `<meta>` prepended to `srcdoc` and a descriptive `title`, per contracts/view-bridge.md
- [X] T015 [P] [US1] Create frontend/src/styles/modules/agent-view.css with the pane column, header, frame, and state styles, and import it from frontend/src/styles/index.css
- [X] T016 [US1] Create frontend/src/components/AgentViewPane.tsx with the header, agent-generated provenance label, and loading/empty states (depends on T014)
- [X] T017 [US1] Create frontend/src/hooks/useAgentViews.ts holding the conversation's view list, the active view, and the fetch-on-`agent_view` logic (depends on T013)
- [X] T018 [US1] Mount `AgentViewPane` as the right column in frontend/src/pages/ChatPage.tsx and wire `onAgentView` into the existing send-message flow (depends on T016, T017)
- [X] T019 [US1] Render an "open view" marker in place of the raw tool accordion for `render_agent_view` tool steps in frontend/src/components/ChatMessage.tsx, selecting that view in the pane
- [X] T020 [US1] Add the failure path to frontend/src/components/AgentViewPane.tsx: rejected or unfetchable views show an error state and leave the conversation fully usable (FR-015)
- [X] T021 [US1] Grant `render_agent_view` to the pilot profile's `tools:` list in config/agents.yaml
- [X] T022 [P] [US1] Extend tests/test_streaming.py with `agent_view` emission on a rendered result and no emission on a rejected result

**Checkpoint**: An enabled agent can render a view that appears in an isolated pane; a disabled agent cannot.

---

## Phase 4: User Story 2 - The View Fetches Fresh Data Under the Agent's Permissions (Priority: P1)

**Goal**: Controls inside a view fetch data through the backend broker, which executes only the
tools the rendering agent already has, as the signed-in owner, and refuses everything else.

**Independent Test**: Render a view with a refresh control bound to a permitted tool and confirm the
data updates in place; then request a tool the agent does not have and confirm a visible refusal
that returns zero data and appears in the audit trail.

### Implementation for User Story 2

- [X] T023 [US2] Add `validate_view_data_request(tool, arguments)` to validators.py enforcing a non-empty tool-name shape, a JSON-object `arguments`, and argument count/size bounds
- [X] T024 [US2] Implement the broker in agent_views.py: resolve the tool by name from the live `SessionData.tools`, exclude `render_agent_view`, execute the callable, and truncate the result to `MAX_VIEW_DATA_RESPONSE_CHARS` with a `truncated` flag (depends on T023)
- [X] T025 [US2] Add the per-session request budget (`MAX_VIEW_DATA_REQUESTS_PER_MINUTE`) to agent_views.py and enforce it before any tool executes
- [X] T026 [US2] Add `POST /api/sessions/{session_id}/views/{view_id}/data` to api_routes/agent_views.py implementing the full contracts/rest-api.md status matrix (200 / 400 `invalid_arguments` / 403 `not_permitted` / 404 / 409 `session_inactive` / 429 `rate_limited` / 500 `tool_failed` with sanitized messages)
- [X] T027 [US2] Record every broker outcome — including refusals — with structured `logger.info` fields and an eval-trace entry when the session trace logger is enabled, in api_routes/agent_views.py (FR-008)
- [X] T028 [P] [US2] Add the injected bootstrap script constant defining `window.agentData(tool, args)` to frontend/src/components/AgentViewFrame.tsx, placed after the CSP meta and before the agent markup
- [X] T029 [US2] Handle inbound `agentui.request` messages in frontend/src/components/AgentViewFrame.tsx, validating `event.source === iframe.contentWindow`, envelope version, and `requestId` correlation, and tearing the listener down on unmount (depends on T028)
- [X] T030 [US2] Add `requestAgentViewData()` to frontend/src/api/client.ts returning the structured outcome instead of throwing, so refusals render inside the view. *(Adjusted: a `409 session_inactive` surfaces "reopen this conversation" rather than auto-re-establishing the session — an automatic retry would mask a genuinely dead backend session.)*
- [X] T031 [US2] Post `agentui.response` error envelopes back into the frame for refusal, failure, and rate-limit outcomes so the view can show a retry-able message (depends on T029, T030)
- [X] T032 [P] [US2] Add tests/test_agent_views_api.py covering: non-permitted tool returns 403 with zero data, `render_agent_view` is not broker-callable, another user's view returns 404, a dead session returns 409, the budget returns 429, and oversize results are truncated
- [X] T033 [P] [US2] Add the isolation probe fixture at scripts/agent_view_isolation_probe.html attempting `fetch`, `parent.document`, `localStorage`, and a non-permitted tool call, for use by the visual/security verification run

**Checkpoint**: Views fetch live data under the agent's permissions, and every escalation attempt is refused and audited.

---

## Phase 5: User Story 3 - Administrators Decide Which Agents Get a UI Pane (Priority: P2)

**Goal**: The capability is granted and revoked through the existing per-agent tool list, is visible
to users, and revocation never destroys existing views.

**Independent Test**: Toggle the tool for an agent, start a new conversation, and confirm the agent
can or cannot render; confirm older conversations still display their views after revocation.

### Implementation for User Story 3

- [X] T034 [US3] Confirm `render_agent_view` is returned by the `/api/tools` inventory in api_routes/profiles.py with a user-facing description, so it appears in the admin tool picker and the capabilities bar without bespoke wiring (FR-019)
- [X] T035 [US3] Ensure a session without the grant exposes no view surface: the pane stays unmounted and the view endpoints reject render attempts, in frontend/src/pages/ChatPage.tsx and api_routes/agent_views.py
- [X] T036 [US3] Keep previously stored views readable after the grant is revoked (read paths must not depend on the tool being present) in api_routes/agent_views.py
- [X] T037 [P] [US3] Add coverage to tests/test_agent_views_api.py for an agent without the grant: no render tool available, and existing views still listable and fetchable

**Checkpoint**: Enablement is fully controlled by the existing agent tool list, with no orphaned data on revocation.

---

## Phase 6: User Story 4 - The Pane Behaves Like a Well-Mannered Part of the App (Priority: P2)

**Goal**: The pane can be collapsed, closed, resized, and switched between views; content survives
reloads and unattended runs; narrow screens and assistive technology are handled.

**Independent Test**: Produce two views, switch between them, collapse and reopen the pane, reload
the page, and reopen the conversation the next day — the newest view is restored and earlier views
remain reachable from their transcript markers.

### Implementation for User Story 4

- [X] T038 [US4] Add collapse, close, and reopen controls to frontend/src/components/AgentViewPane.tsx, ensuring close never discards a stored view (FR-009)
- [X] T039 [US4] Add the drag-to-resize handle with a `[320, 720]` px clamp to frontend/src/components/AgentViewPane.tsx
- [X] T040 [US4] Persist `{open, width, activeViewId}` per conversation under the `agentViewPane:{conversation_id}` localStorage key in frontend/src/hooks/useAgentViews.ts, with a safe fallback for missing or malformed entries
- [X] T041 [US4] Add the view switcher so the newest view opens by default and earlier views are selectable from their transcript markers, in frontend/src/components/AgentViewPane.tsx and frontend/src/hooks/useAgentViews.ts (FR-011, FR-012)
- [X] T042 [US4] Load stored views when a conversation is opened or the page is reloaded, in frontend/src/hooks/useAgentViews.ts, and notify in the transcript when a view arrives while the pane is closed (FR-013)
- [X] T043 [US4] Set `source: "autonomous"` for views rendered outside an interactive turn in agent_views.py and badge them in the pane header so unattended output is recognizable (FR-018)
- [X] T044 [US4] Add the responsive breakpoint below 900 px to frontend/src/styles/modules/agent-view.css so the pane becomes a full-width overlay, with an explicit "Back to chat" control in frontend/src/components/AgentViewPane.tsx (FR-010)
- [X] T045 [US4] Add keyboard and screen-reader support in frontend/src/components/AgentViewPane.tsx: focus moves to the pane heading on open, returns to the triggering transcript marker on close, and focus is never trapped inside the frame (FR-020)
- [X] T046 [P] [US4] Add a stored-views restore test to tests/test_agent_views_api.py covering ordering, the per-conversation cap, and `source` round-tripping

**Checkpoint**: The pane is a durable, accessible, responsive part of the application.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T047 Delete a conversation's views inside `delete_conversation` in api_routes/sessions.py so views never outlive their conversation
- [X] T048 [P] Create scripts/capture_agent_view_screenshots.py accepting `--base-url`, `--out-dir`, `--viewport`, and `--chrome-path`, capturing the pane with a rendered view, the collapsed pane, the view switcher, the error state, the isolation probe result, and the 768×1024 and 360×640 layouts
- [X] T049 Run the Visual Verification Protocol: `npm run build`, start the server, run scripts/capture_agent_view_screenshots.py, review every screenshot for clipping, contrast, alignment, and missing assets, and fix and re-run until clean. *(Two defects found and fixed: view text used hard-coded dark colors against the light theme, and the responsive captures were contaminated by desktop-mounted sidebar state.)*
- [ ] T050 Run the evaluation pipeline for the profile granted `render_agent_view` in config/agents.yaml and confirm no score regression before promotion (Constitution IV). **BLOCKED**: this repo has `eval_trace.py` and `eval_traces/` but no `eval/` pipeline or datasets to run.
- [ ] T051 [P] Run `terraform plan` against infra/main.tf and review the single `agent_views` container addition in infra/modules/cosmos/main.tf. **PARTIAL**: `terraform fmt -check -recursive` and `terraform validate` both pass; a real `plan` needs the user's Azure session and touches shared state, so it was not run unattended.
- [ ] T052 Execute the specs/016-agent-ui-pane/quickstart.md walkthrough end to end, including the four security probes in section 5. **PARTIAL**: sections 5-7 are verified (isolation probes all blocked in a real browser, tests green, screenshots reviewed); the live-agent walkthrough needs the Cosmos emulator plus Azure OpenAI credentials.
- [X] T053 Run the full gate: `uv run pytest` across tests/ (362 passed) and `npm test` + `npm run lint` in frontend/ (both clean)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately
- **Foundational (Phase 2)**: depends on Setup — **blocks all user stories**
- **US1 (Phase 3)**: depends on Foundational
- **US2 (Phase 4)**: depends on Foundational; T028–T031 extend the frame and client created in US1 (T014, T013)
- **US3 (Phase 5)**: depends on Foundational; verification tasks assume US1's endpoints exist
- **US4 (Phase 6)**: depends on Foundational; extends the pane and hook created in US1
- **Polish (Phase 7)**: depends on all shipped stories; T049 requires every UI change to be complete

### User Story Dependencies

- **US1 (P1)**: independent — the MVP slice
- **US2 (P1)**: independently testable, but shares files with US1 (`AgentViewFrame.tsx`, `client.ts`), so run it after US1 rather than concurrently in the same files
- **US3 (P2)**: independent of US2 and US4
- **US4 (P2)**: independent of US2 and US3

### Critical Path

`T002 → T004 → T005 → T008 → T009 → T010 → T011 → T012 → T017 → T018` delivers a visible rendered view.

### Parallel Opportunities

- Setup: T001, T002, T003 all in parallel (Terraform, backend, frontend types)
- Foundational: T007 in parallel with T004–T006 once the record shape is agreed
- US1: T013, T014, T015, T022 in parallel; then T016/T017 → T018
- US2: T028, T032, T033 in parallel with backend broker work T023–T027
- US3/US4 can be staffed in parallel with each other after US1 lands
- Polish: T048 and T051 in parallel

## Parallel Example: User Story 1

```text
# After T012 (router registered), launch together:
T013  frontend/src/api/client.ts          — view endpoints + SSE callback
T014  frontend/src/components/AgentViewFrame.tsx — sandboxed frame
T015  frontend/src/styles/modules/agent-view.css — pane styles
T022  tests/test_streaming.py             — agent_view emission tests
# Then sequentially: T016 → T017 → T018 → T019 → T020
```

## Implementation Strategy

**MVP scope**: Phases 1–3 (T001–T022). That delivers an enabled agent rendering an isolated,
persisted view in a side pane with a transcript marker and safe failure behavior — demonstrable on
its own, with no broker yet.

**Increment 2**: Phase 4 (T023–T033) turns the view interactive and closes the security contract.
Ship US1 and US2 together if the pane is going in front of real data, since an isolated but static
view is the safer half of the feature.

**Increment 3**: Phases 5 and 6 (T034–T046), staffable in parallel — governance and pane ergonomics.

**Always last**: Phase 7. T049 (visual verification) and T053 (test gate) are non-negotiable
completion criteria per the constitution.

## Summary

| Metric | Value |
|---|---|
| Total tasks | 53 |
| Setup / Foundational | 3 / 4 |
| US1 (P1, MVP) | 15 |
| US2 (P1) | 11 |
| US3 (P2) | 4 |
| US4 (P2) | 9 |
| Polish | 7 |
| Parallelizable tasks | 15 marked `[P]` |
| New files | 10 (4 backend/test, 4 frontend, 2 script/fixture) |
| Modified files | 15 |
| New dependencies | 0 |
