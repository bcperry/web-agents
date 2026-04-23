# Tasks: MCP Server UI Improvements

**Input**: Design documents from `/specs/001-mcp-server-ui-improvements/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/session-api.md, quickstart.md

**Tests**: Not explicitly requested in feature specification. Omitted per task generation rules.

**Organization**: Tasks are grouped by user story (R1, R2, R3 from spec.md) to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths included in descriptions

## Phase 1: Setup

**Purpose**: Shared type and data model changes that multiple stories depend on

- [X] T001 Add `MCPConnectionResult` dataclass to mcp_servers.py
- [X] T002 [P] Add `McpConnectionResult` interface and extend `McpServerEntry` type in frontend/src/types/api.ts

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Backend plumbing that MUST be complete before any user story UI work can begin

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Refactor `connect_mcp_servers()` in mcp_servers.py to return `tuple[list[Any], list[MCPConnectionResult]]` with per-server results
- [X] T004 Update `create_session` endpoint in main.py to unpack new `connect_mcp_servers()` return value and include `mcp_results` in both custom and standard session creation responses
- [X] T005 Extend `GET /api/profiles` in main.py to include `mcp_server_count` per profile entry

**Checkpoint**: Backend now returns MCP connection results — frontend story work can begin

---

## Phase 3: User Story 1 — MCP Connection Status Indicators (Priority: P1) MVP

**Goal**: After creating a session, the chat UI shows per-MCP-server connection status with checkmarks (connected) or X's (failed).

**Independent Test**: Create a session with a profile that has MCP servers (e.g., `faa`). Verify the session creation response includes `mcp_results[]`. Verify the chat UI renders status indicators for each server.

### Implementation for User Story 1

- [X] T006 [US1] Create `McpStatusIndicator` component in frontend/src/components/McpStatusIndicator.tsx — accepts `McpConnectionResult[]` prop, renders green checkmark per connected server and red X per failed server with server names
- [X] T007 [US1] Add `mcpResults` state to `useChat` hook in frontend/src/hooks/useChat.ts — parse `mcp_results` from session creation response and store in state, expose via hook return value
- [X] T008 [US1] Render `McpStatusIndicator` in chat header area of frontend/src/pages/ChatPage.tsx — display when `mcpResults` is non-empty, position below agent name/header
- [X] T009 [US1] Update `createSession` and `createCustomSession` in frontend/src/api/client.ts to type the response as `SessionCreateResponse` and return the full response (including `mcp_results`)

**Checkpoint**: User Story 1 complete — selecting an agent with MCP servers shows connection status in chat UI

---

## Phase 4: User Story 2 — Toast Notifications for MCP Failures (Priority: P2)

**Goal**: When a default agent's MCP servers fail to connect during session creation, a warning toast notification lists the failed servers.

**Independent Test**: Start a session with the `faa` profile when MCP servers are unreachable. Verify a warning toast appears listing the failed server names. Verify the session is still created and usable.

**Dependencies**: Requires US1 (T007) for `mcpResults` state in `useChat`.

### Implementation for User Story 2

- [X] T010 [US2] Add MCP failure toast logic in frontend/src/hooks/useChat.ts — after session creation, check `mcpResults` for any `status: "failed"` entries, call `emitToast()` with a warning listing failed server names
- [X] T011 [US2] Ensure toast displays correctly for both standard and custom agent sessions in frontend/src/pages/ChatPage.tsx — verify `emitToast` import and toast container are wired up for the MCP failure path

**Checkpoint**: User Story 2 complete — MCP connection failures produce a non-blocking warning toast

---

## Phase 5: User Story 3 — Authenticated MCP Server Support (Priority: P2)

**Goal**: MCP servers configured with `auth: true` (passthrough) or `auth_scope` (OBO) receive the appropriate bearer token during connection. Both modes are per-server.

**Independent Test**: Configure one MCP server with `auth: true` and another with `auth_scope: "api://test/.default"` in agents.yaml. Create a session while authenticated. Verify passthrough server receives the user's token. Verify OBO server receives an exchanged token with the correct audience. Verify non-auth servers receive no token.

### Implementation for User Story 3

- [X] T012 [P] [US3] Add `auth: bool = False` and `auth_scope: str | None = None` fields to `MCPServerConfig` dataclass and parse both in `parse_mcp_server_configs()` in mcp_servers.py — warn if auth fields used with stdio transport
- [X] T013 [P] [US3] Add `resolve_mcp_auth_token()` helper in mcp_servers.py — if `config.auth_scope` is set, use MSAL `ConfidentialClientApplication.acquire_token_on_behalf_of()` to exchange the user token; elif `config.auth` is true, return the user token as-is; else return None. Requires `AZURE_AD_CLIENT_ID`, `AZURE_AD_CLIENT_SECRET`, `AZURE_AD_AUTHORITY` env vars for OBO
- [X] T014 [P] [US3] Add `auth_token` parameter to `create_mcp_tool()` in mcp_servers.py — when token is provided, create `httpx.AsyncClient` with `Authorization` header and pass as `http_client` to `MCPStreamableHTTPTool`
- [X] T015 [US3] Update `connect_mcp_servers()` in mcp_servers.py to accept optional `user_token` parameter, call `resolve_mcp_auth_token()` per-server, and pass resolved token to `create_mcp_tool()`
- [X] T016 [US3] Extract bearer token from `Authorization` header in `create_session` endpoint in main.py and pass to `connect_mcp_servers()` for both standard and custom session creation paths
- [X] T017 [P] [US3] Add `authenticated` toggle and `authScope` text field to MCP server configuration form in frontend/src/pages/AgentBuilder.tsx — checkbox for passthrough, optional scope input for OBO, maps to `authenticated` and `authScope` fields on `McpServerEntry`
- [X] T018 [US3] Pass `authenticated` and `auth_scope` fields through `createCustomSession()` in frontend/src/api/client.ts so they reach the backend `mcp_servers` request body
- [X] T019 [P] [US3] Add `msal` Python package to pyproject.toml dependencies for OBO token exchange — run `uv add msal`

**Checkpoint**: User Story 3 complete — passthrough servers receive user's token, OBO servers receive exchanged token

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validation, visual verification, and cleanup

- [X] T020 [P] Validate agents.yaml schema still passes existing tests after `auth`/`auth_scope` field additions — run `uv run pytest tests/test_prompt_tools_yaml.py -v`
- [X] T021 [P] Run full backend test suite — `uv run pytest tests/ -v` — fix any regressions from `connect_mcp_servers()` signature change
- [X] T022 Build frontend and verify zero errors — `cd frontend && npm run build`
- [X] T023 Visual Verification Protocol — start server with `AUTH_DISABLED=true uv run uvicorn main:app --host 0.0.0.0 --port 8000`, capture Playwright screenshots of: chat view with MCP status indicators, AgentBuilder with authenticated toggle and auth scope field, toast notification appearance
- [X] T024 Run quickstart.md validation — confirm all documented commands and flows work end-to-end

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on T001 (MCPConnectionResult dataclass)
- **User Story 1 (Phase 3)**: Depends on Foundational (T003-T005) + Setup (T002)
- **User Story 2 (Phase 4)**: Depends on US1 T007 (mcpResults state in useChat)
- **User Story 3 (Phase 5)**: Depends on Foundational (T003) for connect_mcp_servers signature; frontend tasks (T016-T017) can start after T002
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational — no dependencies on other stories
- **User Story 2 (P2)**: Depends on US1 T007 for mcpResults state — lightweight addition
- **User Story 3 (P2)**: Backend tasks (T012-T016) independent of US1/US2; frontend tasks (T017-T018) independent of US1/US2

### Within Each User Story

- Backend changes before frontend changes (data flows backend → frontend)
- Types/models before services/hooks
- Hooks before page components

### Parallel Opportunities

**Setup (Phase 1):**
- T001 and T002 can run in parallel (different files: Python vs TypeScript)

**User Story 3 (Phase 5):**
- T012, T013, and T014 can run in parallel (independent functions in mcp_servers.py)
- T017 and T019 can run in parallel with T012-T016 (different tier / dependency install)

**Polish (Phase 6):**
- T020 and T021 can run in parallel (different test files)

---

## Parallel Example: User Story 3

```bash
# Backend tasks in parallel:
Task T012: "Add auth + auth_scope fields to MCPServerConfig in mcp_servers.py"
Task T013: "Add resolve_mcp_auth_token() helper in mcp_servers.py"
Task T014: "Add auth_token to create_mcp_tool() in mcp_servers.py"

# Then sequential:
Task T015: "Update connect_mcp_servers() in mcp_servers.py"
Task T016: "Extract bearer token in create_session in main.py"

# Frontend tasks (can start in parallel with backend):
Task T017: "Add authenticated toggle + authScope field in AgentBuilder.tsx"
Task T018: "Pass auth fields in client.ts"

# Dependency install (can start in parallel with everything):
Task T019: "Add msal to pyproject.toml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T005)
3. Complete Phase 3: User Story 1 (T006-T009)
4. **STOP and VALIDATE**: Session creation returns `mcp_results`, chat UI shows indicators
5. Deploy/demo if ready — users now see MCP connection status

### Incremental Delivery

1. Setup + Foundational → Backend returns MCP results
2. Add User Story 1 → Status indicators visible → Deploy/Demo (MVP!)
3. Add User Story 2 → Toast warnings for failures → Deploy/Demo
4. Add User Story 3 → Authenticated MCP servers → Deploy/Demo
5. Polish → Tests pass, visual verification, cleanup

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable after foundational phase
- Commit after each task or logical group
- Visual Verification Protocol is NON-NEGOTIABLE per constitution — Phase 6 T023 must not be skipped
- OBO flow (T013) requires `AZURE_AD_CLIENT_SECRET` env var — passthrough works without it
