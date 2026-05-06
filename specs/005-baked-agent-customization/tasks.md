# Tasks: Baked Agent Customization

**Input**: Design documents from `/specs/005-baked-agent-customization/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-contract.md, quickstart.md

**Tests**: Included where the repository already has test infrastructure: backend pytest tests, frontend lint/build, and constitution-required Playwright visual verification for UI changes.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task includes exact file paths

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm current branch, baseline behavior, and affected source files before implementation.

- [X] T001 Confirm branch `005-baked-agent-customization` and working tree status in /home/bcperry/git_wsl/web-agents
- [X] T002 [P] Review existing custom agent localStorage behavior in frontend/src/hooks/useCustomAgents.ts
- [X] T003 [P] Review existing agent builder form behavior in frontend/src/pages/AgentBuilder.tsx
- [X] T004 [P] Review existing session creation endpoints in main.py
- [X] T005 [P] Review existing API and type contracts in frontend/src/api/client.ts and frontend/src/types/api.ts

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add shared types, client contracts, and backend API support required before any story can apply built-in overrides.

**CRITICAL**: No user story implementation can start until this phase is complete.

- [X] T006 [P] Add BuiltInAgentDefinition, AgentCustomizationOverride, StandardAgentCandidate, and override session response fields in frontend/src/types/api.ts
- [X] T007 [P] Add profile definition and profile override Pydantic request/response models in main.py
- [X] T008 Implement safe built-in profile definition serialization from config/agents.yaml in main.py
- [X] T009 Add GET /api/profiles/{profile_id}/definition endpoint in main.py
- [X] T010 Extend POST /api/sessions to accept profile_override for known built-in profiles in main.py
- [X] T011 Reject attempted built-in profile name overrides and derive profile_name from canonical profile in main.py
- [X] T012 [P] Add fetchBuiltInProfileDefinition and createSessionWithProfileOverride client functions in frontend/src/api/client.ts
- [X] T013 [P] Add backend tests for profile definition endpoint success, unknown profile, and secret-safe response in tests/test_api.py
- [X] T014 [P] Add backend tests for override session creation, canonical profile_name preservation, and attempted name override rejection in tests/test_api.py

**Checkpoint**: Backend/API foundation is ready; user-story work can now consume full built-in definitions and create overridden sessions.

---

## Phase 3: User Story 1 - Customize a Built-In Agent Locally (Priority: P1) MVP

**Goal**: Users can save local behavior/capability overrides for built-in agents, keep the canonical name read-only, and launch the built-in profile with the override applied.

**Independent Test**: Open Admin, customize a built-in agent without changing its name, save, return to chat, select that built-in profile, and verify the session starts with overridden behavior/capabilities while retaining the built-in profile identity.

### Tests for User Story 1

- [X] T015 [P] [US1] Add backend regression test for built-in override metadata in session history response in tests/test_api.py

### Implementation for User Story 1

- [X] T016 [P] [US1] Create useBuiltInAgentCustomizations hook with localStorage validation and corrupted JSON recovery in frontend/src/hooks/useBuiltInAgentCustomizations.ts
- [X] T017 [P] [US1] Add override metadata fields to StoredConversation and ConversationIndexEntry in frontend/src/types/api.ts
- [X] T018 [US1] Update AppContent to load, save, and reset built-in override state in frontend/src/App.tsx
- [X] T019 [US1] Refactor AgentBuilder to support built-in definitions with read-only canonical name in frontend/src/pages/AgentBuilder.tsx
- [X] T020 [US1] Add built-in agent section and edit flow that fetches profile definitions in frontend/src/pages/AgentBuilder.tsx
- [X] T021 [US1] Update ChatPage profile merge logic to keep customized built-ins in original selector positions in frontend/src/pages/ChatPage.tsx
- [X] T022 [US1] Update ChatPage profile selection to call createSessionWithProfileOverride for customized built-ins in frontend/src/pages/ChatPage.tsx
- [X] T023 [US1] Preserve usedBuiltInOverride, baseProfileId, and overrideUpdatedAt when saving conversations in frontend/src/hooks/useChat.ts
- [X] T024 [US1] Ensure delete/reset of custom agents does not delete built-in override conversations in frontend/src/hooks/useConversationStore.ts

**Checkpoint**: User Story 1 is independently functional and delivers the MVP.

---

## Phase 4: User Story 2 - Notice Customized Built-In Agents (Priority: P2)

**Goal**: Users can easily see when a built-in agent has a local override in selection, Admin, and active chat/capabilities UI.

**Independent Test**: Save a local override for one built-in agent and verify clear `CUSTOMIZED` indicators appear in profile selection, Admin built-in list, and active chat/capabilities while unmodified built-ins remain visually standard.

### Implementation for User Story 2

- [X] T025 [US2] Add isCustomized and override metadata display support to AgentProfile in frontend/src/types/api.ts
- [X] T026 [US2] Render `CUSTOMIZED` badge for overridden built-in cards in frontend/src/components/ProfileSelector.tsx
- [X] T027 [US2] Render built-in override indicator in active chat header/capabilities area in frontend/src/components/AgentCapabilitiesBar.tsx
- [X] T028 [US2] Style customized built-in badges and indicators in frontend/src/styles/index.css
- [X] T029 [US2] Render distinct built-in, customized built-in, and custom-agent rows in Admin agents list in frontend/src/pages/AgentBuilder.tsx

**Checkpoint**: User Stories 1 and 2 work independently; users can identify local overrides before and during use.

---

## Phase 5: User Story 3 - Reset or Promote a Customization (Priority: P3)

**Goal**: Users can reset a built-in override back to defaults or generate a canonical `agents.yaml` candidate without mutating server configuration from the browser.

**Independent Test**: For a customized built-in, reset removes the override and badge; make-standard opens/copies a complete YAML/profile candidate while leaving the local override customized.

### Implementation for User Story 3

- [X] T030 [P] [US3] Create standard agent candidate generator with YAML and structured payload output in frontend/src/utils/standardAgentCandidate.ts
- [X] T031 [US3] Add reset-to-default action for customized built-ins in frontend/src/pages/AgentBuilder.tsx
- [X] T032 [US3] Add make-standard candidate modal or drawer with copy/download affordance in frontend/src/pages/AgentBuilder.tsx
- [X] T033 [US3] Ensure make-standard leaves local override state unchanged in frontend/src/pages/AgentBuilder.tsx
- [X] T034 [US3] Add user-facing promotion workflow notice for tests/evals/source review in frontend/src/pages/AgentBuilder.tsx

**Checkpoint**: All user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validate, visually verify, and clean up behavior across all stories.

- [X] T035 [P] Update quickstart verification notes if implementation details changed in specs/005-baked-agent-customization/quickstart.md
- [X] T036 Run backend regression tests with `uv run pytest` from /home/bcperry/git_wsl/web-agents
- [X] T037 Run frontend lint with `npm run lint` from /home/bcperry/git_wsl/web-agents/frontend
- [X] T038 Run frontend production build with `npm run build` from /home/bcperry/git_wsl/web-agents/frontend
- [X] T039 Start backend serving built frontend with AUTH_DISABLED=true using main.py from /home/bcperry/git_wsl/web-agents
- [X] T040 Capture Playwright screenshot of profile selector without customized built-ins in screenshots/005-profile-selector-default.png
- [X] T041 Capture Playwright screenshot of profile selector with one customized built-in in screenshots/005-profile-selector-customized.png
- [X] T042 Capture Playwright screenshot of Admin Agents tab with built-in and custom sections in screenshots/005-admin-agents.png
- [X] T043 Capture Playwright screenshot of built-in customization edit form in screenshots/005-built-in-edit-form.png
- [X] T044 Capture Playwright screenshot of active chat using a customized built-in in screenshots/005-chat-customized-active.png
- [X] T045 Capture Playwright screenshot of make-standard candidate modal/drawer in screenshots/005-make-standard-candidate.png
- [X] T046 Review screenshots for clipping, overlap, contrast, missing assets, and responsive layout in screenshots/
- [X] T047 Fix visual defects found during screenshot review in frontend/src/styles/index.css
- [X] T048 Fix visual defects found during screenshot review in frontend/src/pages/AgentBuilder.tsx
- [X] T049 Fix visual defects found during screenshot review in frontend/src/components/ProfileSelector.tsx
- [X] T050 Fix visual defects found during screenshot review in frontend/src/components/AgentCapabilitiesBar.tsx

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; can start immediately.
- **Foundational (Phase 2)**: Depends on Setup; blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational; MVP delivery.
- **User Story 2 (Phase 4)**: Depends on Foundational and uses US1 override state, but its UI indicators can be developed mostly independently.
- **User Story 3 (Phase 5)**: Depends on Foundational and US1 storage/edit flow.
- **Polish (Phase 6)**: Depends on completed desired user stories.

### User Story Dependencies

- **US1 (P1)**: Required MVP; no dependency on US2 or US3.
- **US2 (P2)**: Depends on the override state created for US1 but can be tested with seeded localStorage.
- **US3 (P3)**: Depends on override records from US1 but can be tested with seeded localStorage.

### Within Each User Story

- Backend pytest tasks should be written before implementation where applicable.
- Types and storage models before UI flow changes.
- API clients before session integration.
- Core story behavior before visual styling.
- Each story should be validated independently at its checkpoint.

---

## Parallel Opportunities

- T002-T005 can run in parallel during setup.
- T006, T007, T012, T013, and T014 can run in parallel after setup because they touch different files/concerns.
- T015-T017 can run in parallel after foundational API/type work.
- T030 can run in parallel with T031 after US1 is complete because it writes frontend/src/utils/standardAgentCandidate.ts while reset UI work stays in frontend/src/pages/AgentBuilder.tsx.
- Screenshot capture tasks T040-T045 can run sequentially in one Playwright session, but preparation for each affected screen can be assigned independently.

## Parallel Example: User Story 1

```bash
# Parallelizable US1 tasks after foundational work:
Task: "T015 [P] [US1] Add backend regression test for built-in override metadata in session history response in tests/test_api.py"
Task: "T016 [P] [US1] Create useBuiltInAgentCustomizations hook with localStorage validation and corrupted JSON recovery in frontend/src/hooks/useBuiltInAgentCustomizations.ts"
Task: "T017 [P] [US1] Add override metadata fields to StoredConversation and ConversationIndexEntry in frontend/src/types/api.ts"
```

## Parallel Example: User Story 2

```bash
# US2 tasks mostly share UI files, so implement sequentially to avoid conflicts:
Task: "T025 [US2] Add isCustomized and override metadata display support to AgentProfile in frontend/src/types/api.ts"
Task: "T026 [US2] Render CUSTOMIZED badge for overridden built-in cards in frontend/src/components/ProfileSelector.tsx"
Task: "T027 [US2] Render built-in override indicator in active chat header/capabilities area in frontend/src/components/AgentCapabilitiesBar.tsx"
```

## Parallel Example: User Story 3

```bash
# Parallelizable US3 task after US1 is complete:
Task: "T030 [P] [US3] Create standard agent candidate generator with YAML and structured payload output in frontend/src/utils/standardAgentCandidate.ts"

# Then complete AgentBuilder UI tasks sequentially:
Task: "T031 [US3] Add reset-to-default action for customized built-ins in frontend/src/pages/AgentBuilder.tsx"
Task: "T032 [US3] Add make-standard candidate modal or drawer with copy/download affordance in frontend/src/pages/AgentBuilder.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 setup.
2. Complete Phase 2 foundational API/types/client work.
3. Complete Phase 3 US1 local customization and overridden session start.
4. Stop and validate US1 independently through Admin -> Chat flow.
5. Demo or deploy MVP if needed.

### Incremental Delivery

1. Setup + Foundational -> built-in definition endpoint and override session path ready.
2. US1 -> users can customize and use baked-agent overrides.
3. US2 -> users can clearly notice customized baked agents.
4. US3 -> users can reset overrides and export standard-agent candidates.
5. Polish -> tests, build, lint, visual verification.

### Notes

- Built-in customization must never allow editing the canonical profile name.
- Browser UI must not mutate config/agents.yaml directly.
- Shared promotion from make-standard output requires source review, tests, and eval pipeline before deployment.
- Follow the Visual Verification Protocol for every UI change in this feature.
