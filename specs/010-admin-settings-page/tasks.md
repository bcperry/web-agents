# Tasks: Admin Settings Page

**Input**: Design documents from `/specs/010-admin-settings-page/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ui-settings-contract.md, quickstart.md

**Tests**: No TDD/unit test tasks are generated because tests were not explicitly requested. Build validation and visual verification are included because the feature specification and constitution require them for UI changes.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: Which user story this task belongs to (`US1`, `US2`, `US3`, `US4`)
- Every task includes exact file paths

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare local context and visual evidence location for the frontend UI change.

- [X] T001 Create visual verification output placeholder in screenshots/010-admin-settings-page/.gitkeep
- [X] T002 [P] Review authenticated header branches in frontend/src/pages/ChatPage.tsx and settings/sidebar ownership in frontend/src/components/Sidebar.tsx
- [X] T003 [P] Review Admin tab structure in frontend/src/pages/AdminPage.tsx and current theme hook behavior in frontend/src/hooks/useTheme.tsx

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish shared UI contracts and style targets that all user stories rely on.

**CRITICAL**: No user story work should begin until this phase is complete.

- [X] T004 Define reusable settings menu props and accessible interaction contract in frontend/src/components/SettingsMenu.tsx
- [X] T005 [P] Add base CSS selectors for header settings controls and Admin Settings layout in frontend/src/styles/index.css
- [X] T006 [P] Prepare reusable visual capture script skeleton for affected screens in scripts/capture_admin_settings_screenshots.py

**Checkpoint**: Foundation ready - user story implementation can begin.

---

## Phase 3: User Story 1 - Open Settings From Chat Header (Priority: P1) MVP

**Goal**: Authenticated users can open a compact top-right settings gear from both profile-selection and active-chat headers, see their email, and navigate to Admin.

**Independent Test**: From profile selection and active chat, open the top-right gear, confirm email/Admin/logout content, and select Admin to verify existing Admin navigation opens.

### Implementation for User Story 1

- [X] T007 [US1] Implement settings gear button, menu open/close state, Admin action, optional Logout action, and long-email rendering in frontend/src/components/SettingsMenu.tsx
- [X] T008 [US1] Import and render SettingsMenu in the profile-selection header branch in frontend/src/pages/ChatPage.tsx
- [X] T009 [US1] Render SettingsMenu beside TokenUsage and New Chat in the active-chat header branch in frontend/src/pages/ChatPage.tsx
- [X] T010 [US1] Wire SettingsMenu to existing useAuth user/logout data and onOpenAdmin callback in frontend/src/pages/ChatPage.tsx
- [X] T011 [US1] Complete responsive, focus, and menu-positioning styles for header settings controls in frontend/src/styles/index.css
- [X] T012 [US1] Extend scripts/capture_admin_settings_screenshots.py to capture profile-selection and active-chat headers with the settings menu open

**Checkpoint**: User Story 1 should be fully functional and independently testable.

---

## Phase 4: User Story 2 - Manage Theme From Admin Settings (Priority: P1)

**Goal**: Theme selection lives in Admin Settings, uses the existing theme hook, updates immediately, and persists after refresh.

**Independent Test**: Open Admin Settings, switch Light/Dark, return to chat, refresh, and confirm the selected theme persists.

### Implementation for User Story 2

- [X] T013 [US2] Add `settings` to the Admin tab state and make it the default active tab in frontend/src/pages/AdminPage.tsx
- [X] T014 [US2] Import useTheme and render Light/Dark theme controls in the Settings section in frontend/src/pages/AdminPage.tsx
- [X] T015 [US2] Add optional user/account summary props for Admin Settings in frontend/src/pages/AdminPage.tsx
- [X] T016 [US2] Pass authenticated user email from AppContent into AdminPage in frontend/src/App.tsx
- [X] T017 [US2] Style Admin Settings theme and account sections in frontend/src/styles/index.css
- [X] T018 [US2] Extend scripts/capture_admin_settings_screenshots.py to capture Admin Settings in light and dark themes

**Checkpoint**: User Story 2 should be fully functional and independently testable.

---

## Phase 5: User Story 3 - Admin Page Becomes Settings Hub (Priority: P2)

**Goal**: Admin reads as a complete settings hub while preserving existing Agents and Skills workflows.

**Independent Test**: Open Admin, verify Settings/Agents/Skills tabs, switch among sections, and confirm AgentBuilder and SkillBuilder still render and operate.

### Implementation for User Story 3

- [X] T019 [US3] Update Admin page title, tab labels, and Settings/Agents/Skills ordering in frontend/src/pages/AdminPage.tsx
- [X] T020 [US3] Preserve existing AgentBuilder props and render path under the Agents tab in frontend/src/pages/AdminPage.tsx
- [X] T021 [US3] Preserve existing SkillBuilder render path under the Skills tab in frontend/src/pages/AdminPage.tsx
- [X] T022 [US3] Refine Admin header, tab, and content spacing for the settings hub layout in frontend/src/styles/index.css
- [X] T023 [US3] Extend scripts/capture_admin_settings_screenshots.py to capture Agents and Skills tabs after the Admin layout update

**Checkpoint**: User Story 3 should be fully functional and independently testable.

---

## Phase 6: User Story 4 - Sidebar Focuses On Conversations (Priority: P3)

**Goal**: Sidebar shows conversation controls only, with theme/admin/user/logout removed and settings reachable from the header gear.

**Independent Test**: Expand and collapse the sidebar at desktop and mobile widths; verify conversation history and New Chat remain while Theme, Admin, email, and Logout are absent.

### Implementation for User Story 4

- [X] T024 [US4] Remove theme option constants, useTheme import, and advanced/theme JSX from frontend/src/components/Sidebar.tsx
- [X] T025 [US4] Remove userEmail, onLogout, and onOpenAdmin props from SidebarProps and Sidebar usage in frontend/src/components/Sidebar.tsx
- [X] T026 [US4] Stop passing userEmail, onLogout, and onOpenAdmin into Sidebar in frontend/src/pages/ChatPage.tsx
- [X] T027 [US4] Remove obsolete sidebar advanced/theme styles from frontend/src/styles/index.css
- [X] T028 [US4] Extend scripts/capture_admin_settings_screenshots.py to capture expanded sidebar on desktop and mobile showing conversation controls only

**Checkpoint**: User Story 4 should be fully functional and independently testable.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validate the complete feature and clean up documentation/visual evidence.

- [X] T029 [P] Update implementation notes in specs/010-admin-settings-page/quickstart.md with final verification command and screenshot names
- [X] T030 Run frontend build validation with `npm run build` from frontend/package.json
- [X] T031 Run visual capture script with `uv run python scripts/capture_admin_settings_screenshots.py --base-url http://localhost:8000 --output-dir screenshots/010-admin-settings-page` from scripts/capture_admin_settings_screenshots.py
- [X] T032 Review captured screenshots in screenshots/010-admin-settings-page/ for clipped text, overlapping header controls, menu viewport overflow, and correct light/dark theme rendering
- [X] T033 Fix any visual verification defects in frontend/src/pages/ChatPage.tsx, frontend/src/pages/AdminPage.tsx, frontend/src/components/SettingsMenu.tsx, frontend/src/components/Sidebar.tsx, or frontend/src/styles/index.css

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - blocks all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational completion - MVP navigation path
- **User Story 2 (Phase 4)**: Depends on Foundational completion; can proceed in parallel with US1 after AdminPage prop needs are coordinated
- **User Story 3 (Phase 5)**: Depends on US2 because it refines the Admin tab structure introduced there
- **User Story 4 (Phase 6)**: Depends on US1 because sidebar settings removal should happen after header gear navigation exists
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Foundational; no dependency on other stories
- **User Story 2 (P1)**: Starts after Foundational; no dependency on other stories, but shares AdminPage with US3
- **User Story 3 (P2)**: Starts after US2 to avoid conflicting edits in AdminPage
- **User Story 4 (P3)**: Starts after US1 so Admin/user/logout access remains available through the header settings gear

### Within Each User Story

- Component contracts before usage wiring
- JSX behavior before CSS refinement
- Core screen behavior before visual capture expansion
- Story checkpoint validation before moving to dependent stories

### Parallel Opportunities

- T002 and T003 can run in parallel during setup
- T005 and T006 can run in parallel after T004 is understood
- US1 and US2 can proceed in parallel after Phase 2 if developers coordinate AdminPage prop changes
- T029 can run in parallel with final implementation cleanup after screenshot names are known
- Visual defect fixes in T033 can be split by file if screenshots identify independent issues

---

## Parallel Example: User Story 1

```bash
# After T007 defines SettingsMenu behavior, these can be split by file:
Task: "Render SettingsMenu in the profile-selection header branch in frontend/src/pages/ChatPage.tsx"
Task: "Complete responsive/focus/menu positioning styles for header settings controls in frontend/src/styles/index.css"
Task: "Extend scripts/capture_admin_settings_screenshots.py to capture profile-selection and active-chat headers with the settings menu open"
```

## Parallel Example: User Story 2

```bash
# After T013 establishes the Settings tab, these can be coordinated by file:
Task: "Render Light/Dark theme controls in frontend/src/pages/AdminPage.tsx"
Task: "Style Admin Settings theme and account sections in frontend/src/styles/index.css"
Task: "Extend scripts/capture_admin_settings_screenshots.py to capture Admin Settings in light and dark themes"
```

## Parallel Example: User Story 4

```bash
# Sidebar component cleanup and final ChatPage prop cleanup can be split carefully:
Task: "Remove theme option constants and advanced/theme JSX from frontend/src/components/Sidebar.tsx"
Task: "Stop passing userEmail, onLogout, and onOpenAdmin into Sidebar in frontend/src/pages/ChatPage.tsx"
Task: "Remove obsolete sidebar advanced/theme styles from frontend/src/styles/index.css"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Validate: settings gear appears in both header states, shows user/Admin/logout, and opens Admin
5. Demo MVP navigation before moving theme/sidebar controls

### Incremental Delivery

1. Complete Setup + Foundational -> shared component/style/script skeleton ready
2. Add User Story 1 -> header settings gear and Admin navigation
3. Add User Story 2 -> Admin Settings theme management
4. Add User Story 3 -> Admin as complete settings hub with Agents/Skills preserved
5. Add User Story 4 -> sidebar cleanup
6. Complete build and visual verification

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Developer A: User Story 1 SettingsMenu and ChatPage wiring
3. Developer B: User Story 2 Admin Settings theme controls
4. Developer C: Screenshot script and CSS refinements after component contracts stabilize
5. Team completes sidebar cleanup and visual verification together

---

## Notes

- [P] tasks use different files or can proceed without incomplete upstream work.
- Each user story has a standalone manual verification checkpoint.
- No backend/API tasks are included because the plan explicitly scopes this feature to frontend UI.
- Visual verification is required before the UI change is considered complete.
