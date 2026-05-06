# Tasks: Admin Skills Design Match

**Input**: Design documents from `/specs/006-admin-skills-design-match/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: No automated unit/contract tests are requested because this is a presentation-only redesign preserving existing APIs. Visual verification, lint, and production build tasks are included because they are required by the specification and constitution.

**Organization**: Tasks are grouped by user story so each story can be implemented and verified independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files or has no dependency on incomplete tasks
- **[Story]**: User story label for story-specific tasks only
- All task descriptions include exact file paths

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the implementation baseline and reusable verification surface.

- [X] T001 Inspect the existing Admin Agents layout references in frontend/src/pages/AgentBuilder.tsx and frontend/src/styles/index.css
- [X] T002 Inspect the existing Skills render modes and handlers in frontend/src/components/SkillBuilder.tsx
- [X] T003 [P] Confirm screenshots/ exists for Admin Skills visual verification artifacts
- [X] T004 [P] Inspect the existing reusable Admin screenshot workflow in scripts/capture_admin_agent_screenshots.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define the shared visual target before changing story-specific behavior.

**CRITICAL**: No user story work should begin until this phase is complete.

- [X] T005 Map Skills UI states to Agent Builder layout regions in frontend/src/components/SkillBuilder.tsx
- [X] T006 Map reusable Agent Builder style classes and any Skills-specific gaps in frontend/src/styles/index.css
- [X] T007 Decide whether to extend scripts/capture_admin_agent_screenshots.py or create scripts/capture_admin_screenshots.py for Skills screenshots

**Checkpoint**: Foundation ready - user story implementation can now begin.

---

## Phase 3: User Story 1 - Match Skills To Agent Builder Layout (Priority: P1) MVP

**Goal**: Admin users can switch from Agents to Skills without a jarring design-language shift.

**Independent Test**: Open Admin, switch from Agents to Skills, and verify Skills uses the same left-list/right-form layout, panel framing, section headers, list card treatment, form density, and action styling as Agents.

### Implementation for User Story 1

- [X] T008 [US1] Replace the separate list/create/edit page structure with a persistent Agent Builder-style layout in frontend/src/components/SkillBuilder.tsx
- [X] T009 [US1] Render saved skills in a left-side panel using Agent Builder-compatible section header, row, name, description, and action treatment in frontend/src/components/SkillBuilder.tsx
- [X] T010 [US1] Render the create/edit skill form in a right-side Agent Builder-compatible form panel in frontend/src/components/SkillBuilder.tsx
- [X] T011 [US1] Convert loading, empty, error, and success messages to Admin-consistent panel states in frontend/src/components/SkillBuilder.tsx
- [X] T012 [US1] Reuse or align SkillBuilder layout, list, form, input, textarea, and button styling with Agent Builder rules in frontend/src/styles/index.css
- [X] T013 [US1] Remove or neutralize obsolete isolated Skill Builder visual rules that conflict with the Agent Builder design language in frontend/src/styles/index.css

**Checkpoint**: User Story 1 should be visually functional and independently reviewable as the MVP.

---

## Phase 4: User Story 2 - Keep Skill Editing Workflows Intact (Priority: P2)

**Goal**: Create, edit, delete, cancel, save, validation, and AI-generation workflows continue to work after the layout redesign.

**Independent Test**: Create a skill, edit an existing skill, cancel an edit, generate skill content with AI, and delete a skill while confirming the same behavior and validation remain available.

### Implementation for User Story 2

- [X] T014 [US2] Preserve create-mode name, description, content, save, cancel, validation, and reset behavior in frontend/src/components/SkillBuilder.tsx
- [X] T015 [US2] Preserve edit-mode skill loading, read-only name display, description/content editing, save, and cancel behavior in frontend/src/components/SkillBuilder.tsx
- [X] T016 [US2] Preserve delete confirmation, delete execution, loading state, and list refresh behavior in frontend/src/components/SkillBuilder.tsx
- [X] T017 [US2] Preserve AI content generation controls, loading state, and generated content insertion in frontend/src/components/SkillBuilder.tsx
- [X] T018 [US2] Ensure SkillBuilder still uses the existing Skills API functions without new endpoint or contract changes in frontend/src/components/SkillBuilder.tsx
- [X] T019 [US2] Run a manual create/edit/delete regression pass using the flow documented in specs/006-admin-skills-design-match/quickstart.md

**Checkpoint**: User Stories 1 and 2 should both work independently, with no Skill Builder behavior regression.

---

## Phase 5: User Story 3 - Verify Responsive Admin Consistency (Priority: P3)

**Goal**: Skills remains consistent with Agents across desktop, tablet, and mobile viewports without overflow, clipping, or awkward spacing.

**Independent Test**: Capture and review desktop, tablet, and mobile screenshots of the Skills tab and confirm no horizontal overflow, overlapping controls, clipped labels, or isolated floating panels.

### Implementation for User Story 3

- [X] T020 [US3] Add Skills tab navigation and screenshot capture states to scripts/capture_admin_agent_screenshots.py or scripts/capture_admin_screenshots.py
- [X] T021 [US3] Seed or select representative saved skill data for screenshot states in scripts/capture_admin_agent_screenshots.py or scripts/capture_admin_screenshots.py
- [X] T022 [US3] Capture Skills list, create form, edit form, and delete confirmation screenshots at 1440x900 into screenshots/
- [X] T023 [US3] Capture Skills responsive screenshots at 768x1024 and 360x640 into screenshots/
- [X] T024 [US3] Review generated Skills screenshots for overflow, overlap, clipped text, and layout mismatch against Agents in screenshots/
- [X] T025 [US3] Fix any responsive spacing, wrapping, or overflow issues discovered during screenshot review in frontend/src/styles/index.css

**Checkpoint**: All user stories should now be independently functional and visually verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup across the redesigned Admin Skills surface.

- [X] T026 [P] Run frontend lint and fix any issues in frontend/src/components/SkillBuilder.tsx and frontend/src/styles/index.css
- [X] T027 [P] Run frontend production build and fix any issues in frontend/src/components/SkillBuilder.tsx and frontend/src/styles/index.css
- [X] T028 [P] Update screenshot workflow notes if a new Admin screenshot script is introduced in specs/006-admin-skills-design-match/quickstart.md
- [X] T029 Confirm no backend API, storage, or Skill file format changes were introduced by reviewing main.py, frontend/src/api/client.ts, and skills/
- [X] T030 Summarize final verification results and screenshot artifact paths in specs/006-admin-skills-design-match/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion - blocks user story implementation.
- **User Story 1 (Phase 3)**: Depends on Foundational completion - MVP.
- **User Story 2 (Phase 4)**: Depends on User Story 1 layout being present so behavior can be verified in the redesigned UI.
- **User Story 3 (Phase 5)**: Depends on User Stories 1 and 2 being complete enough to capture meaningful visual states.
- **Polish (Phase 6)**: Depends on all desired user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - no dependency on other stories.
- **User Story 2 (P2)**: Starts after US1 because it verifies workflows inside the redesigned layout.
- **User Story 3 (P3)**: Starts after US1 and US2 because screenshots must cover final layout and functional states.

### Within Each User Story

- For US1, update structure in SkillBuilder before refining CSS details.
- For US2, preserve existing handlers before manual workflow verification.
- For US3, update screenshot automation before capturing and reviewing artifacts.
- Complete each story checkpoint before moving to the next priority.

### Parallel Opportunities

- T003 and T004 can run in parallel during Setup.
- T026, T027, and T028 can run in parallel after implementation, assuming fixes are coordinated if failures occur.
- Within US3, T022 and T023 can be captured in the same script run after T020 and T021 are complete.

---

## Parallel Example: User Story 1

```bash
# Parallelizable preparation after foundational mapping:
Task: "T008 [US1] Replace the separate list/create/edit page structure with a persistent Agent Builder-style layout in frontend/src/components/SkillBuilder.tsx"
Task: "T012 [US1] Reuse or align SkillBuilder layout, list, form, input, textarea, and button styling with Agent Builder rules in frontend/src/styles/index.css"
```

---

## Parallel Example: User Story 3

```bash
# After screenshot automation is updated and representative state data exists:
Task: "T022 [US3] Capture Skills list, create form, edit form, and delete confirmation screenshots at 1440x900 into screenshots/"
Task: "T023 [US3] Capture Skills responsive screenshots at 768x1024 and 360x640 into screenshots/"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational.
3. Complete Phase 3: User Story 1.
4. Stop and validate that Skills visually matches Agents at desktop size.
5. Demo the matched Admin Skills layout before continuing behavior and responsive verification.

### Incremental Delivery

1. Setup + Foundational: establish the visual target and screenshot approach.
2. US1: redesign Skills into the Agent Builder layout language.
3. US2: confirm create/edit/delete/AI workflows still behave exactly as before.
4. US3: capture and review desktop/tablet/mobile screenshots.
5. Polish: run lint/build and record final verification.

### Parallel Team Strategy

With multiple developers:

1. One developer maps and updates SkillBuilder structure in frontend/src/components/SkillBuilder.tsx.
2. Another developer aligns styles in frontend/src/styles/index.css after the shared mapping is agreed.
3. A third developer updates screenshot automation in scripts/capture_admin_agent_screenshots.py or scripts/capture_admin_screenshots.py.
4. Everyone reconvenes for screenshot review, lint, and build validation.
