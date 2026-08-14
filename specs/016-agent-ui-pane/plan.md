# Implementation Plan: Agent Dynamic UI Pane

**Branch**: `016-agent-ui-pane` | **Date**: 2026-08-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/016-agent-ui-pane/spec.md`

## Summary

Add an opt-in agent tool, `render_agent_view`, that lets an enabled agent author an HTML
view and show it in a new right-hand pane beside the chat. The view is rendered in a
**sandboxed, opaque-origin iframe** (`sandbox="allow-scripts"` with no `allow-same-origin`)
carrying a host-injected `default-src 'none'; connect-src 'none'` CSP, so the view can run
its own behavior but can reach neither the host application nor the network. When the view
needs data it calls a host-provided `agentData(tool, args)` bridge; the host forwards the
request to a backend broker that executes **the exact tool callables already instantiated
for that agent's live session**, under the signed-in owner's identity. Permission parity is
therefore structural — the broker has no independent allow-list to drift from.

Views are persisted per-user in Cosmos (`agent-views`, partitioned by `/user_id`) so they
survive reloads and so views produced during autonomous runs are waiting when the user opens
the conversation. The tool returns only a compact acknowledgement to the model, so view HTML
never re-enters the model context; the frontend fetches view content over REST after an
`agent_view` SSE event.

## Technical Context

**Language/Version**: Python 3.12+ (backend), TypeScript 5.9 / React 19 (frontend)  
**Primary Dependencies**: FastAPI, `agent-framework-core`, `azure-cosmos` (async), Vite 8 — **no new runtime dependencies in either tier**  
**Storage**: Azure Cosmos DB — new `agent-views` container partitioned by `/user_id` (mirrors `user-profiles`)  
**Testing**: `uv run pytest` (backend), `npm test` → `tsc -b` (frontend type check), Playwright screenshot capture script (Visual Verification Protocol)  
**Target Platform**: Azure App Service (single unit: FastAPI serving the built SPA), evergreen Chromium/Firefox/Safari  
**Project Type**: Two-tier web application (Python backend at repo root, React SPA in `frontend/`)  
**Performance Goals**: view visible ≤3 s after the render tool completes (SC-001); brokered data request returns in <3 s for 95% of calls (SC-004); chat streaming never blocked by rendering  
**Constraints**: view HTML ≤ `MAX_AGENT_VIEW_CHARS` (default 250,000); ≤ `MAX_AGENT_VIEWS_PER_CONVERSATION` (default 50, FIFO eviction); ≤ 60 broker requests/min per session; broker response ≤ `MAX_VIEW_DATA_RESPONSE_CHARS` (default 20,000); a view has zero network egress and zero host-origin access  
**Scale/Scope**: 1 new backend module, 1 new router, 1 new tool, 1 new repository, 1 new SSE event; 3 new frontend components/hooks + 1 CSS module; 1 new Terraform container resource

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Initial | Post-Design | Notes |
|---|---|---|---|
| I. Read-Only Data Access | PASS | PASS | The feature introduces no data path of its own. A view can only invoke function tools already instantiated for the agent's session, so every existing read-only guard, row limit, and validator applies unchanged. |
| II. Single-File Agent Definitions | PASS | PASS | The capability is granted by adding `render_agent_view` to a profile's `tools:` list in `config/agents.yaml`. All tool documentation and usage rules live in the Python docstring on the tool function — no YAML restatement. |
| III. Security & Credential Hygiene | PASS | PASS | Opaque-origin sandbox + `connect-src 'none'` CSP + server-side broker validation (dual control, neither alone is the control). All endpoints require `get_current_user`; every request re-checks conversation ownership via `get_owned`. Views are user-partitioned in Cosmos. No secrets enter view HTML or broker responses. |
| IV. Evaluation-Driven Quality | PASS (with action) | PASS (with action) | Adding a tool changes agent behavior for the enabled profile, so the eval pipeline must run before promotion. Tracked as a Phase 2 task. |
| V. Simplicity & Minimalism | PASS | PASS | Zero new dependencies. Reuses the existing tool registry, per-user Cosmos repository pattern, SSE channel, and session lifecycle. Deliberately rejects an HTML sanitizer, a widget/templating DSL, and a client-side permission model (see research.md). |
| VI. Infrastructure as Code | PASS | PASS | The new container is declared in `infra/modules/cosmos/main.tf` following the `user_profiles` pattern; runtime `create_container_if_not_exists` keeps the emulator path working. |
| VII. Two-Tier API-First | PASS | PASS | All view storage and brokered execution live behind FastAPI. The SPA holds no business logic and reaches no Azure service directly. The sandboxed view sits strictly downstream of the SPA and cannot originate network calls at all. |
| Visual Verification Protocol | N/A | REQUIRED | This is a UI change. `scripts/capture_agent_view_screenshots.py` must capture the pane open and collapsed, a rendered view, the error state, and the 768×1024 / 360×640 responsive layouts, and every screenshot must be reviewed before the work is called done. |

**Gate result**: PASS — no violations, so the Complexity Tracking table stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/016-agent-ui-pane/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output — decisions and rejected alternatives
├── data-model.md        # Phase 1 output — entities, storage, limits
├── quickstart.md        # Phase 1 output — enable, run, verify
├── contracts/
│   ├── rest-api.md      # Backend HTTP endpoints
│   ├── sse-events.md    # agent_view SSE event
│   ├── view-bridge.md   # host ↔ sandboxed view postMessage protocol
│   └── tool-contract.md # render_agent_view tool signature and behavior
├── checklists/
│   └── requirements.md  # Spec quality checklist (passing)
└── tasks.md             # Phase 2 output — NOT created by /speckit.plan
```

### Source Code (repository root)

```text
# Backend (Python, repository root)
agent_views.py                 # NEW — view record, size/count limits, broker execution
api_routes/agent_views.py      # NEW — list views, get view, POST view data broker
tools.py                       # MODIFIED — build_render_agent_view_tool factory
app_context.py                 # MODIFIED — register render_agent_view; session-scoped factories
user_data.py                   # MODIFIED — CosmosAgentViewRepository (partition /user_id)
streaming.py                   # MODIFIED — emit agent_view SSE event on render tool result
validators.py                  # MODIFIED — validate_view_data_request
main.py                        # MODIFIED — include the agent_views router
config/agents.yaml             # MODIFIED — grant render_agent_view to the pilot profile

tests/
├── test_agent_views.py        # NEW — record limits, eviction, repository behavior
├── test_agent_views_api.py    # NEW — ownership, broker permission refusals, rate limits
└── test_streaming.py          # MODIFIED — agent_view event emission

# Frontend (frontend/)
frontend/src/components/AgentViewPane.tsx    # NEW — pane chrome, view switcher, states
frontend/src/components/AgentViewFrame.tsx   # NEW — sandboxed iframe + bridge handler
frontend/src/hooks/useAgentViews.ts          # NEW — view list, active view, pane state
frontend/src/api/client.ts                   # MODIFIED — view endpoints + onAgentView SSE
frontend/src/types/api.ts                    # MODIFIED — AgentView, SSE + bridge types
frontend/src/pages/ChatPage.tsx              # MODIFIED — mount the pane in the layout
frontend/src/components/ChatMessage.tsx      # MODIFIED — transcript "open view" marker
frontend/src/styles/modules/agent-view.css   # NEW — pane layout and responsive behavior

# Infrastructure
infra/modules/cosmos/main.tf   # MODIFIED — agent_views container (/user_id)

# Verification
scripts/capture_agent_view_screenshots.py    # NEW — reusable Playwright capture
```

**Structure Decision**: Two-tier layout per Constitution VII — backend modules stay flat at the
repository root beside `tools.py` and `streaming.py`, routes go under `api_routes/`, and the SPA
follows the existing `components/` + `hooks/` + `api/` + `styles/modules/` split. No new
top-level directories are introduced.

## Design Decisions (summary — full rationale in research.md)

1. **Isolation**: `<iframe sandbox="allow-scripts" srcdoc=...>` without `allow-same-origin`
   yields an opaque origin — no host DOM, no host storage, no cookies, no top-level navigation.
   A host-prepended `<meta http-equiv="Content-Security-Policy">` with
   `default-src 'none'; connect-src 'none'` removes network egress. CSP is additive, so an
   agent-authored policy can only tighten the host policy, never loosen it.
2. **No HTML sanitizer**: sanitizing while still permitting the scripts that make a view dynamic
   is self-defeating and bypass-prone. Browser origin isolation is the stronger, simpler control.
3. **Broker uses live session tools**: `SessionData.tools` holds the already-instantiated,
   user-bound callables. The broker looks the requested tool up in that list — it cannot widen
   the agent's permissions because it has no separate list to widen. Requests against an inactive
   session return `409` and the client re-establishes the session before retrying.
4. **Metadata-only tool result**: the tool persists the HTML and returns
   `{view_id, title, status, chars}`, so view HTML is never echoed back into model context.
5. **Live and restore share one path**: the `agent_view` SSE event carries metadata only; both
   live rendering and conversation reload fetch content from
   `GET /api/sessions/{id}/views/{view_id}`.
6. **MCP tools excluded from the broker (MVP)**: `session_data.mcp_tools` is a separate list, so
   restricting the broker to `session_data.tools` is a natural narrowing that still satisfies
   FR-006 (a subset of the agent's tools).
7. **FR-014 refinement**: oversized single views are rejected; reaching the per-conversation view
   cap evicts the oldest view rather than permanently blocking rendering. The spec text was
   updated to say this explicitly so the artifacts agree.

## Phase Status

- **Phase 0 (Research)**: complete → [research.md](research.md). No `NEEDS CLARIFICATION` items
  remained in Technical Context after research.
- **Phase 1 (Design & Contracts)**: complete → [data-model.md](data-model.md),
  [contracts/](contracts/), [quickstart.md](quickstart.md); agent context file refreshed.
- **Phase 2 (Tasks)**: not started — run `/speckit.tasks`.

## Complexity Tracking

> No Constitution Check violations. Table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
