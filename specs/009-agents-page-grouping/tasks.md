# Tasks: Agents Page Grouping & Pagination

**Input**: Design documents from `/specs/009-agents-page-grouping/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## User Stories (from spec.md)

- **US1** (P1): Group field in agents.yaml and backend API passthrough
- **US2** (P2): Group field in custom agents (frontend form & localStorage)
- **US3** (P3): Grouped display with collapsible sections in ProfileSelector
- **US4** (P4): Pagination ("Show More") within groups

---

## Phase 1: Setup

**Purpose**: No new project setup needed — all changes are additive to existing files.

- [X] T001 Verify existing tests pass before changes with `uv run pytest tests/test_prompt_tools_yaml.py -v`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Type definitions that all user stories depend on.

- [X] T002 [P] Add `group?: string` to `AgentProfile` interface in frontend/src/types/api.ts
- [X] T003 [P] Add `group?: string` to `CustomAgentDefinition` interface in frontend/src/types/api.ts
- [X] T004 [P] Add `group?: string` to `AgentCustomizationOverride` interface in frontend/src/types/api.ts

**Checkpoint**: Type foundations ready — user story implementation can begin.

---

## Phase 3: User Story 1 - Group Field in YAML & Backend (Priority: P1) 🎯 MVP

**Goal**: Add optional `group` field to `agents.yaml` profiles and pass it through the `/api/profiles` API response.

**Independent Test**: Call `GET /api/profiles` and verify each profile object includes a `group` string field.

### Implementation for User Story 1

- [X] T005 [US1] Add `group` field to each profile in config/agents.yaml (e.g., "Command Staff" for chief-of-staff, "General Staff" for G1-G9)
- [X] T006 [US1] Pass `group` field in `GET /api/profiles` response dict in main.py (add `"group": entry.get("group", "")` to the profiles.append block)
- [X] T007 [US1] Update schema validation in tests/test_prompt_tools_yaml.py to accept optional `group` field as string
- [X] T008 [US1] Run `uv run pytest tests/test_prompt_tools_yaml.py -v` to verify YAML validation passes

**Checkpoint**: Backend serves `group` field. Frontend types accept it. API contract fulfilled.

---

## Phase 4: User Story 2 - Group Field in Custom Agents (Priority: P2)

**Goal**: Allow users to assign a group to custom agents via the Agent Builder form.

**Independent Test**: Create a custom agent in the admin page with a group name, save it, reload the page, and verify the group persists.

### Implementation for User Story 2

- [X] T009 [US2] Add `group: string` field to `AgentBuilderFormState` interface and `EMPTY_AGENT_FORM` in frontend/src/hooks/useAgentBuilderForm.ts
- [X] T010 [US2] Include `group` in `prepareCustomAgent()` output in frontend/src/hooks/useAgentBuilderForm.ts
- [X] T011 [US2] Include `group` in `prepareBuiltInOverride()` output in frontend/src/hooks/useAgentBuilderForm.ts
- [X] T012 [US2] Add group text input field to the Agent Builder form in frontend/src/pages/AgentBuilder.tsx (with datalist of existing group names)
- [X] T013 [US2] Populate `form.group` when editing an existing custom agent or built-in override in frontend/src/pages/AgentBuilder.tsx

**Checkpoint**: Custom agents can be assigned to groups; group persists in localStorage.

---

## Phase 5: User Story 3 - Grouped Display in ProfileSelector (Priority: P3)

**Goal**: Replace the flat card grid with collapsible group sections, matching the admin page dropdown pattern.

**Independent Test**: Navigate to the agents page; verify agents are grouped by their `group` field into collapsible sections with +/- toggle buttons; verify "Other" group shows ungrouped agents last.

### Implementation for User Story 3

- [X] T014 [US3] Refactor ProfileSelector in frontend/src/components/ProfileSelector.tsx to compute grouped profiles using `useMemo` (group by `profile.group || profile.customAgent?.group || 'Other'`)
- [X] T015 [US3] Render collapsible sections per group in frontend/src/components/ProfileSelector.tsx (reuse `agent-builder-section-toggle` CSS pattern with +/- icons and `aria-expanded`)
- [X] T016 [US3] Add group section collapse/expand state management (useState for collapsed groups set) in frontend/src/components/ProfileSelector.tsx
- [X] T017 [US3] Add CSS styles for profile-selector group sections in frontend/src/styles/ (reuse existing agent-builder-section-toggle styles or extend)
- [X] T018 [US3] Ensure "Other" group renders last in the sorted group list in frontend/src/components/ProfileSelector.tsx

**Checkpoint**: Agents page shows collapsible grouped sections. All groups expand/collapse correctly.

---

## Phase 6: User Story 4 - Pagination Within Groups (Priority: P4)

**Goal**: Large groups show a limited number of agents (6) with a "Show More" button to reveal the rest.

**Independent Test**: With a group containing >6 agents, verify only 6 are shown initially; clicking "Show More" reveals all; button disappears when all are shown.

### Implementation for User Story 4

- [X] T019 [US4] Add per-group expanded state tracking (useState for expanded groups set) in frontend/src/components/ProfileSelector.tsx
- [X] T020 [US4] Slice displayed profiles to PAGE_SIZE (6) per group unless expanded in frontend/src/components/ProfileSelector.tsx
- [X] T021 [US4] Render "Show More (N remaining)" button at end of truncated groups in frontend/src/components/ProfileSelector.tsx
- [X] T022 [US4] Style the "Show More" button to match existing UI patterns in frontend/src/styles/

**Checkpoint**: Groups with many agents paginate correctly. Show More reveals all.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Visual verification, final validation, cleanup.

- [X] T023 Build frontend with `cd frontend && npm run build` and verify zero errors
- [X] T024 Run full backend test suite with `uv run pytest` and verify all pass
- [X] T025 Visual verification: start server and capture screenshots of grouped agents page per Visual Verification Protocol
- [X] T026 Verify keyboard accessibility (Tab through groups, Enter to expand/collapse, Enter to select agent)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — verify clean baseline
- **Phase 2 (Foundational)**: No dependencies — type additions only
- **Phase 3 (US1)**: Depends on Phase 2 (needs types defined)
- **Phase 4 (US2)**: Depends on Phase 2 (needs types defined); can run in parallel with Phase 3
- **Phase 5 (US3)**: Depends on Phase 3 (needs `group` field in API response) and Phase 4 (needs custom agent groups)
- **Phase 6 (US4)**: Depends on Phase 5 (needs grouped display to paginate)
- **Phase 7 (Polish)**: Depends on all previous phases

### User Story Dependencies

- **US1** (YAML + Backend): Independent after types
- **US2** (Custom Agents): Independent after types; can parallel with US1
- **US3** (Grouped Display): Depends on US1 + US2 (needs group data from both sources)
- **US4** (Pagination): Depends on US3 (needs grouped sections to paginate within)

### Parallel Opportunities

- T002, T003, T004 can all run in parallel (different type definitions)
- US1 and US2 can run in parallel after Phase 2

---

## Implementation Strategy

**MVP**: Phase 1 + Phase 2 + Phase 3 (US1) = backend serves `group`, frontend types ready
**Increment 2**: Phase 4 (US2) = custom agents get group field
**Increment 3**: Phase 5 (US3) = grouped display rendered
**Increment 4**: Phase 6 (US4) = pagination within groups
**Final**: Phase 7 = polish and visual verification

Suggested approach: Implement sequentially P1→P2→P3→P4 since each builds on the previous, but US1 and US2 can be done in parallel if desired.
