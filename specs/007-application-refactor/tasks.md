# Tasks: Application Refactor And Deduplication

**Input**: Design documents from `/specs/007-application-refactor/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Test and verification tasks are included because the specification explicitly requires backend pytest, frontend test/build/lint, contract preservation, and visual verification for UI/CSS changes.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing. `config/agents.yaml` is intentionally excluded from implementation tasks and must remain unchanged.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on an incomplete task.
- **[Story]**: User story label for story-phase tasks only.
- Every task includes at least one exact file path.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish branch, scope, baseline, and protected-file guardrails before refactoring.

- [X] T001 Verify branch `007-application-refactor` and record the empty `git diff -- config/agents.yaml` guard in specs/007-application-refactor/quickstart.md
- [X] T002 [P] Capture baseline backend test status with `uv run pytest` and record failures or pass result in specs/007-application-refactor/quickstart.md
- [X] T003 [P] Add or confirm a no-new-dependency `test` script in frontend/package.json, then capture baseline frontend test/build/lint status with `npm test`, `npm run build`, and `npm run lint` from frontend/package.json and record results in specs/007-application-refactor/quickstart.md
- [X] T004 [P] Capture current runtime line-count baseline for main.py, frontend/src/api/client.ts, frontend/src/hooks/useChat.ts, frontend/src/pages/AgentBuilder.tsx, frontend/src/components/SkillBuilder.tsx, frontend/src/styles/index.css, frontend/src/index.css, and frontend/src/App.css in specs/007-application-refactor/quickstart.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add shared test and helper foundations that all stories depend on.

**CRITICAL**: No user story work should begin until this phase is complete.

- [X] T005 Move duplicated TestClient and `_sessions.clear()` setup into shared fixtures in tests/conftest.py
- [X] T006 [P] Update tests/test_api.py to use the shared client fixture from tests/conftest.py without changing route assertions
- [X] T007 [P] Update tests/test_skills_api.py to use the shared client and temporary skills fixtures from tests/conftest.py
- [X] T008 [P] Create protected-file verification helper or documented check in specs/007-application-refactor/quickstart.md for `git diff -- config/agents.yaml`
- [X] T009 [P] Add backend module skeleton and exports for validators.py with no behavior wired into main.py yet
- [X] T010 [P] Add backend module skeleton and exports for streaming.py with no behavior wired into main.py yet
- [X] T011 [P] Add backend module skeleton and exports for skills_manager.py with no behavior wired into main.py yet
- [X] T012 [P] Add backend module skeleton and exports for session_orchestration.py with no behavior wired into main.py yet

**Checkpoint**: Shared fixtures and empty module targets exist; user story implementation can begin.

---

## Phase 3: User Story 1 - Preserve Chat Behavior While Simplifying Backend Sessions (Priority: P1) MVP

**Goal**: Preserve all backend API/session/SSE behavior while extracting duplicated validation, streaming, skills, and session orchestration code out of main.py.

**Independent Test**: Run `uv run pytest tests/test_api.py tests/test_image_input.py tests/test_retry_logic.py tests/test_skills_api.py tests/test_skills.py tests/test_session_orchestration.py tests/test_validators.py tests/test_skills_manager.py tests/test_streaming.py` and verify `git diff -- config/agents.yaml` remains empty.

### Tests for User Story 1

- [X] T013 [P] [US1] Add tool, skill, temperature, prompt, image, and error-classifier unit tests in tests/test_validators.py
- [X] T014 [P] [US1] Add token usage, SSE event formatting, tool-result content conversion, and error event tests in tests/test_streaming.py
- [X] T015 [P] [US1] Add file-backed skill list/get/create/update/delete/path-safety tests in tests/test_skills_manager.py
- [X] T016 [P] [US1] Add standard profile, custom agent, built-in override, history restore, invalid input, response-shape, and MCP failure redaction tests in tests/test_session_orchestration.py
- [X] T017 [P] [US1] Add or update backend API contract assertions for preserved session and SSE response fields in tests/test_api.py

### Implementation for User Story 1

- [X] T018 [P] [US1] Move usage aggregation helpers, SSE event formatting, retry/context error classification, and content-item conversion from main.py into streaming.py
- [X] T019 [P] [US1] Move image validation constants and upload validation from main.py into validators.py while preserving ALLOWED_IMAGE_MIMES, MAX_IMAGE_SIZE_BYTES, and MAX_IMAGES_PER_MESSAGE compatibility exports
- [X] T020 [P] [US1] Implement ToolRegistry, skill discovery validation, prompt validation, temperature validation, and MCP request validation helpers in validators.py
- [X] T021 [P] [US1] Implement SkillManager for SKILL.md parsing, validation, path traversal prevention, create, update, delete, and list behavior in skills_manager.py
- [X] T022 [US1] Refactor main.py imports to use streaming.py for `_create_usage`, `_usage_value`, `_merge_usage`, `_extract_usage_from_payload`, `_sse_event`, `_is_retryable_error`, and `_is_context_length_error`
- [X] T023 [US1] Refactor main.py imports to use validators.py for image validation and shared tool/skill/temperature validation while preserving public constants used by tests
- [X] T024 [US1] Refactor skill endpoints in main.py to delegate list/get/create/update/delete path operations to SkillManager in skills_manager.py
- [X] T025 [US1] Implement SessionCreationService in session_orchestration.py for standard profile, custom agent, built-in override, user profile injection, sanitized MCP connection failure reporting, history restoration, and response shaping
- [X] T026 [US1] Refactor create_session in main.py to delegate session creation to SessionCreationService while preserving `_sessions` ownership in main.py
- [X] T027 [US1] Update delete_session and lifespan behavior in main.py only as needed to preserve MCP cleanup and final usage logging after session extraction
- [X] T028 [US1] Remove obsolete duplicated validation, skills CRUD, usage, and session response code from main.py after extracted modules are wired in
- [X] T029 [US1] Run focused backend tests and fix regressions in main.py, validators.py, streaming.py, skills_manager.py, session_orchestration.py, and tests/conftest.py

**Checkpoint**: User Story 1 is complete when backend route contracts and session behavior are preserved and `main.py` is reduced below 1,200 lines without changing config/agents.yaml.

---

## Phase 4: User Story 2 - Reduce Frontend Duplication Without Changing Workflows (Priority: P2)

**Goal**: Preserve frontend exported API, hook, storage, and workflow behavior while consolidating repeated request, storage, content, and form-state code.

**Independent Test**: Run `cd frontend && npm run build && npm run lint`, manually exercise profile selection/chat/admin builder/skill builder flows, and verify localStorage keys and API exports remain compatible.

### Tests and Verification for User Story 2

- [X] T030 [P] [US2] Add TypeScript compile coverage for API export compatibility by adding or documenting a compile-only import matrix for all public exports from frontend/src/api/client.ts
- [X] T031 [P] [US2] Add storage compatibility checks or documented manual verification for existing localStorage keys in specs/007-application-refactor/quickstart.md
- [X] T032 [P] [US2] Add frontend workflow verification notes for chat send, saved conversation resume/delete, agent builder save/delete, and skill builder CRUD in specs/007-application-refactor/quickstart.md

### Implementation for User Story 2

- [X] T033 [P] [US2] Create authenticated fetch, JSON body, empty response, unauthorized, and toast-aware response helpers in frontend/src/api/helpers.ts
- [X] T034 [US2] Refactor frontend/src/api/client.ts to use frontend/src/api/helpers.ts while preserving all existing exported functions and SSE handling
- [X] T035 [P] [US2] Create typed localStorage read/write/remove JSON helpers with corruption handling in frontend/src/utils/storage.ts
- [X] T036 [US2] Refactor frontend/src/hooks/useCustomAgents.ts to use frontend/src/utils/storage.ts without changing `webagents_custom_agents`
- [X] T037 [US2] Refactor frontend/src/hooks/useBuiltInAgentCustomizations.ts to use frontend/src/utils/storage.ts without changing `webagents_builtin_agent_customizations`
- [X] T038 [US2] Refactor frontend/src/hooks/useUserProfile.ts to use frontend/src/utils/storage.ts without changing `webagents_user_profile`
- [X] T039 [US2] Refactor frontend/src/hooks/useConversationStore.ts to use frontend/src/utils/storage.ts without changing conversation index and per-conversation keys
- [X] T040 [P] [US2] Create image MIME, tool image filtering, tool result formatting, and session content conversion helpers in frontend/src/utils/content.ts
- [X] T041 [US2] Refactor frontend/src/components/ChatMessage.tsx and frontend/src/components/ToolStep.tsx to use shared image/content helpers from frontend/src/utils/content.ts
- [X] T042 [US2] Extract conversation persistence and session lifecycle helpers from frontend/src/hooks/useChat.ts into frontend/src/hooks/useSessionLifecycle.ts and frontend/src/hooks/useConversationPersistence.ts
- [X] T043 [US2] Refactor frontend/src/hooks/useChat.ts to use useSessionLifecycle and useConversationPersistence while preserving the ChatState return shape
- [X] T044 [P] [US2] Extract MCP server editor state and operations from frontend/src/pages/AgentBuilder.tsx into frontend/src/hooks/useAgentMcpEditor.ts
- [X] T045 [P] [US2] Extract agent form state, validation, reset, edit, and save preparation from frontend/src/pages/AgentBuilder.tsx into frontend/src/hooks/useAgentBuilderForm.ts
- [X] T046 [P] [US2] Extract tool and skill picker logic from frontend/src/pages/AgentBuilder.tsx into frontend/src/components/AgentCapabilityPicker.tsx
- [X] T047 [P] [US2] Extract starter question editor UI from frontend/src/pages/AgentBuilder.tsx into frontend/src/components/StarterQuestionEditor.tsx
- [X] T048 [US2] Refactor frontend/src/pages/AgentBuilder.tsx to compose the extracted hooks/components while preserving exported AgentBuilder props
- [X] T049 [P] [US2] Extract reusable skill form state from frontend/src/components/SkillBuilder.tsx into frontend/src/hooks/useSkillForm.ts
- [X] T050 [US2] Refactor frontend/src/components/SkillBuilder.tsx to use useSkillForm while preserving create/edit/delete/generate behavior
- [X] T051 [US2] Run frontend build/lint and fix regressions in frontend/src/api/client.ts, frontend/src/hooks/useChat.ts, frontend/src/pages/AgentBuilder.tsx, frontend/src/components/SkillBuilder.tsx, and new frontend helpers

**Checkpoint**: User Story 2 is complete when frontend workflows still work, exported API/hook contracts are stable, and duplicated request/storage/content/form code is reduced.

---

## Phase 5: User Story 3 - Clean Styling And Tests Safely (Priority: P3)

**Goal**: Remove dead/repeated CSS and brittle tests while preserving visual design and behavioral coverage.

**Independent Test**: Run `uv run pytest`, `cd frontend && npm run build`, start the backend, capture screenshots for affected screens, inspect screenshots, and verify `git diff -- config/agents.yaml` remains empty.

### Tests and Verification for User Story 3

- [X] T052 [P] [US3] Replace source-inspection assertions with behavioral assertions where feasible in tests/test_image_input.py
- [X] T053 [P] [US3] Replace source-inspection assertions with behavioral assertions where feasible in tests/test_retry_logic.py
- [X] T054 [P] [US3] Add or update reusable Playwright screenshot capture coverage in scripts/capture_admin_agent_screenshots.py, or a companion script if needed, for disclaimer top/bottom, profile selection, empty chat with starter questions, chat with one user message and one assistant response, admin agent builder, and skill builder screens
- [X] T055 [US3] Run visual baseline capture at required viewports where affected, save screenshots under screenshots/, view every generated image, and record pass/fail notes in specs/007-application-refactor/quickstart.md

### Implementation for User Story 3

- [X] T056 [P] [US3] Remove unused demo styles from frontend/src/App.css and remove any stale import references if present in frontend/src/App.tsx
- [X] T057 [P] [US3] Trim frontend/src/index.css to root/global styles actually used by frontend/src/main.tsx and frontend/src/App.tsx
- [X] T058 [US3] Consolidate repeated button, input, textarea, admin panel, saved entry, and action styles in frontend/src/styles/index.css
- [X] T059 [US3] Consolidate repeated message markdown, tool image, and result image styles in frontend/src/styles/index.css
- [X] T060 [US3] Update affected class usage in frontend/src/components/ChatMessage.tsx, frontend/src/components/ToolStep.tsx, frontend/src/pages/AgentBuilder.tsx, and frontend/src/components/SkillBuilder.tsx only if required by CSS consolidation
- [X] T061 [US3] Run frontend build plus full screenshot verification, inspect every generated screenshot for clipping, overflow, overlap, broken assets, missing content, unreadable text, and responsive issues, then fix and re-run until visual review passes in frontend/src/styles/index.css, frontend/src/index.css, frontend/src/App.css, and scripts/capture_admin_agent_screenshots.py

**Checkpoint**: User Story 3 is complete when CSS line count is reduced by at least 400 net lines, visual verification passes, and backend tests remain behavior-focused.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final contract, quality, documentation, and line-count validation across the completed refactor.

- [X] T062 [P] Run complete backend test suite with `uv run pytest` and record result in specs/007-application-refactor/quickstart.md
- [X] T063 [P] Run complete frontend test/build/lint with `cd frontend && npm test && npm run build && npm run lint` and record result in specs/007-application-refactor/quickstart.md
- [X] T064 Verify protected file diff remains empty with `git diff -- config/agents.yaml`, verify dependency files have no unplanned dependency additions, and record results in specs/007-application-refactor/quickstart.md
- [X] T065 Recalculate line-count reductions across all runtime app code while excluding specs, generated output, node_modules, dist, screenshots, traces, and test artifacts, then record against SC-001 through SC-004 in specs/007-application-refactor/quickstart.md
- [X] T066 [P] Review API contract preservation against specs/007-application-refactor/contracts/api-contract.md and update any missing backend tests in tests/test_api.py
- [X] T067 [P] Review frontend contract preservation against specs/007-application-refactor/contracts/frontend-contract.md and update verification notes in specs/007-application-refactor/quickstart.md
- [X] T068 Final cleanup of obsolete imports, comments, and dead helper code in main.py, validators.py, streaming.py, skills_manager.py, session_orchestration.py, and frontend/src

---

## Phase 7: Follow-Up Wrapper Flattening

**Purpose**: Clean up wrapper code exposed by the first refactor pass so session and agent creation read as direct domain flows instead of chains of service/create/spawn helpers.

**Independent Test**: Run `uv run pytest tests/test_api.py tests/test_session_orchestration.py tests/test_provider_routing.py tests/test_retry_logic.py tests/test_streaming.py tests/test_validators.py`, then `cd frontend && npm test && npm run build && npm run lint`, and verify `git diff -- config/agents.yaml` remains empty.

### Backend Wrapper Flattening

- [X] T069 [US4] Document the current standard, custom, and built-in override session call chains in specs/007-application-refactor/quickstart.md before editing agent_factory.py, session_orchestration.py, or frontend/src/hooks/useSessionLifecycle.ts
- [X] T070 [P] [US4] Add or update tests in tests/test_provider_routing.py and tests/test_api.py to pin custom, standard, and built-in override runtime/session behavior before flattening agent_factory.py and session_orchestration.py
- [X] T071 [US4] Collapse `spawn_agent()` and `_create_agent()` in agent_factory.py into one clearly named builder used by `create_chat_runtime()` while preserving `AgentBase` only if an existing caller still requires it
- [X] T072 [US4] Rename or simplify `create_chat_runtime()` in agent_factory.py only if the new name improves domain intent, and update imports in session_orchestration.py and tests without changing runtime behavior
- [X] T073 [US4] Replace per-request `SessionCreationService(...)` construction in main.py with direct session creation functions or a module-level boundary in session_orchestration.py that reduces constructor dependency plumbing
- [X] T074 [US4] Split duplicated session response persistence in session_orchestration.py into a small shared helper only if it removes repeated response/session-data assembly without adding another wrapper layer
- [X] T075 [US4] Remove `ToolRegistry` from validators.py and update session_orchestration.py and tests to use `known_tool_names_from_profiles()` plus `validate_tool_names()` directly
- [X] T076 [US4] Remove underscore compatibility aliases and exports from streaming.py after updating main.py and tests to import canonical helper names
- [X] T077 [US4] Run focused backend validation and fix regressions in agent_factory.py, session_orchestration.py, validators.py, streaming.py, main.py, and related tests

### Frontend Session And Hook Flattening

- [X] T078 [P] [US4] Add or update compile-only API contract coverage in frontend/src/api/client.contract.ts for any new internal session request helper while preserving existing public exports from frontend/src/api/client.ts
- [X] T079 [US4] Centralize `/api/sessions` POST behavior in frontend/src/api/client.ts behind one internal typed request helper while keeping `createSession`, `createSessionWithHistory`, `createCustomSession`, and `createSessionWithProfileOverride` as compatibility exports
- [X] T080 [US4] Simplify `startChatSession()` in frontend/src/hooks/useSessionLifecycle.ts to build one session request intent before calling the centralized frontend API helper
- [X] T081 [US4] Reassess frontend/src/hooks/useSkillForm.ts, frontend/src/hooks/useAgentBuilderForm.ts, and frontend/src/hooks/useAgentMcpEditor.ts; inline state-only hooks or rename/reshape them so each remaining hook owns a workflow rather than only returning setters
- [X] T082 [US4] Run frontend validation and fix regressions in frontend/src/api/client.ts, frontend/src/hooks/useSessionLifecycle.ts, frontend/src/hooks/useChat.ts, frontend/src/pages/AgentBuilder.tsx, and frontend/src/components/SkillBuilder.tsx

### Final Wrapper Cleanup Validation

- [X] T083 [US4] Recalculate the session creation call-chain length and runtime line counts, then record the before/after wrapper reduction and SC-007 result in specs/007-application-refactor/quickstart.md
- [X] T084 [US4] Run complete backend and frontend gates with `uv run pytest` and `cd frontend && npm test && npm run build && npm run lint`, verify `git diff -- config/agents.yaml` remains empty, and record final results in specs/007-application-refactor/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies; can start immediately.
- **Phase 2 Foundational**: Depends on Phase 1; blocks all user stories.
- **Phase 3 US1 Backend MVP**: Depends on Phase 2; should complete before broad frontend and CSS work because it preserves API contracts.
- **Phase 4 US2 Frontend Dedupe**: Depends on Phase 2 and should be validated against US1 route contracts when US1 is available.
- **Phase 5 US3 Styling/Test Cleanup**: Depends on Phase 4 for component structure stability and should run after most UI class usage settles.
- **Phase 6 Polish**: Depends on all desired user stories.
- **Phase 7 Wrapper Flattening**: Depends on Phase 6 baseline completion and should preserve all completed behavior while reducing wrapper layers.

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational; no dependency on US2 or US3.
- **US2 (P2)**: Can start after Foundational, but final verification depends on stable backend contracts from US1.
- **US3 (P3)**: Best after US2 because CSS cleanup should follow component extraction; test cleanup can begin after Foundational.
- **US4 (P1 Follow-Up)**: Starts after the first refactor pass is validated; can be delivered independently as a maintainability cleanup with no user-visible behavior changes.

### Within Each User Story

- Write/update tests and verification notes before implementation tasks in the same story.
- Extract helper modules before wiring routes or components into them.
- Preserve exports and route contracts before deleting old code.
- Run focused verification at every checkpoint.

---

## Parallel Opportunities

- T002, T003, and T004 can run in parallel after T001.
- T006 through T012 can run in parallel after T005 where they touch separate files.
- US1 test tasks T013 through T017 can run in parallel.
- US1 helper implementation tasks T018 through T021 can run in parallel before main.py wiring begins.
- US2 helper/component extraction tasks T033, T035, T040, T044, T045, T046, T047, and T049 can run in parallel before integration tasks.
- US3 source-inspection test tasks T052 and T053 can run in parallel with screenshot script task T054.
- Final verification tasks T062, T063, T066, and T067 can run in parallel after implementation completes.
- T070 and T078 can run in parallel after T069 because backend behavior pinning and frontend export coverage touch separate files.
- T071, T075, and T076 can be worked independently after T070, but T073 should wait until agent factory flattening settles.
- T079 can proceed after T078; T080 should wait until T079 provides the centralized session request helper.

---

## Parallel Example: User Story 1

```bash
# Backend helper tests can be drafted together:
Task: "T013 [P] [US1] Add tool, skill, temperature, prompt, image, and error-classifier unit tests in tests/test_validators.py"
Task: "T014 [P] [US1] Add token usage, SSE event formatting, tool-result content conversion, and error event tests in tests/test_streaming.py"
Task: "T015 [P] [US1] Add file-backed skill list/get/create/update/delete/path-safety tests in tests/test_skills_manager.py"
Task: "T016 [P] [US1] Add standard profile, custom agent, built-in override, history restore, invalid input, and response-shape tests in tests/test_session_orchestration.py"

# Backend helper modules can be implemented together:
Task: "T018 [P] [US1] Move usage aggregation helpers, SSE event formatting, retry/context error classification, and content-item conversion from main.py into streaming.py"
Task: "T019 [P] [US1] Move image validation constants and upload validation from main.py into validators.py while preserving ALLOWED_IMAGE_MIMES, MAX_IMAGE_SIZE_BYTES, and MAX_IMAGES_PER_MESSAGE compatibility exports"
Task: "T020 [P] [US1] Implement ToolRegistry, skill discovery validation, prompt validation, temperature validation, and MCP request validation helpers in validators.py"
Task: "T021 [P] [US1] Implement SkillManager for SKILL.md parsing, validation, path traversal prevention, create, update, delete, and list behavior in skills_manager.py"
```

## Parallel Example: User Story 2

```bash
# Frontend helpers and extraction targets can be implemented together:
Task: "T033 [P] [US2] Create authenticated fetch, JSON body, empty response, unauthorized, and toast-aware response helpers in frontend/src/api/helpers.ts"
Task: "T035 [P] [US2] Create typed localStorage read/write/remove JSON helpers with corruption handling in frontend/src/utils/storage.ts"
Task: "T040 [P] [US2] Create image MIME, tool image filtering, tool result formatting, and session content conversion helpers in frontend/src/utils/content.ts"
Task: "T044 [P] [US2] Extract MCP server editor state and operations from frontend/src/pages/AgentBuilder.tsx into frontend/src/hooks/useAgentMcpEditor.ts"
Task: "T045 [P] [US2] Extract agent form state, validation, reset, edit, and save preparation from frontend/src/pages/AgentBuilder.tsx into frontend/src/hooks/useAgentBuilderForm.ts"
Task: "T049 [P] [US2] Extract reusable skill form state from frontend/src/components/SkillBuilder.tsx into frontend/src/hooks/useSkillForm.ts"
```

## Parallel Example: User Story 3

```bash
Task: "T052 [P] [US3] Replace source-inspection assertions with behavioral assertions where feasible in tests/test_image_input.py"
Task: "T053 [P] [US3] Replace source-inspection assertions with behavioral assertions where feasible in tests/test_retry_logic.py"
Task: "T054 [P] [US3] Add or update Playwright screenshot capture coverage for affected admin/chat screens in scripts/capture_admin_agent_screenshots.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 setup and Phase 2 foundational fixtures/module shells.
2. Complete Phase 3 backend extraction in this order: validators, streaming, skills manager, session orchestration.
3. Stop and validate with backend focused tests and `git diff -- config/agents.yaml`.
4. Confirm main.py is below 1,200 lines before proceeding.

### Incremental Delivery

1. Deliver US1 backend simplification and route-contract preservation.
2. Deliver US2 frontend helper/component dedupe while preserving workflows.
3. Deliver US3 CSS/test cleanup with visual verification.
4. Complete Phase 6 final line-count, contract, build, and protected-file checks.
5. Complete Phase 7 wrapper flattening only after the first refactor pass is green, with behavior-pinning tests before collapsing layers.

### Parallel Team Strategy

1. One developer completes shared fixtures and module shells.
2. Backend developer handles US1 helper modules and session orchestration.
3. Frontend developer handles US2 helper and component extraction after API contracts are stable.
4. UI/test developer handles US3 behavioral tests and screenshot verification after component class usage settles.

---

## Notes

- Do not edit config/agents.yaml in any task.
- Use `uv` for Python commands; never use `pip`.
- Use `npm` for frontend commands.
- Keep route paths, response field names, SSE event names, localStorage keys, and exported frontend API functions stable.
- Add no runtime dependencies unless a task updates the plan with a concrete constitution-compliant justification.
- Run visual verification for any CSS or component markup changes before closing US3.
- For Phase 7, prefer deleting a wrapper over renaming it. Add a new helper only when it removes repeated domain logic and shortens the reader's path through session creation.