# Tasks: Admin Page — Agent Builder + Skill Builder

**Branch**: `003-admin-page-agent-skill-builder`  
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

---

## Task 1 — Backend: Skills CRUD endpoints [X]

**File**: `main.py`  
**Dependencies**: None

Add four new FastAPI endpoints for skill CRUD operations. The existing `GET /api/skills` endpoint remains unchanged.

### Subtasks

1. **GET /api/skills/{name}**: Read `skills/{name}/SKILL.md`, parse frontmatter, return `{name, description, content}`. Return 404 if directory or file doesn't exist.

2. **POST /api/skills**: Accept `{name, description, content}`, validate name regex `^[a-z0-9][a-z0-9-]*$` (max 64), description non-empty (max 256), content non-empty (max 65536). Create `skills/{name}/` directory and write `SKILL.md` with frontmatter. Return 409 if already exists.

3. **PUT /api/skills/{name}**: Accept `{description, content}`, overwrite `skills/{name}/SKILL.md`. Return 404 if skill doesn't exist.

4. **DELETE /api/skills/{name}**: Remove `skills/{name}/` directory tree. Return 404 if not found; 204 on success.

### Implementation Notes
- Use `shutil.rmtree` for DELETE.
- Use Pydantic models (`SkillCreateRequest`, `SkillUpdateRequest`, `SkillResponse`) for request/response validation.
- Path traversal prevention: validate that resolved skill path is inside `skills/` directory.
- All endpoints use `Depends(get_current_user)`.

---

## Task 2 — Backend: Tests for Skills CRUD [X]

**File**: `tests/test_skills_api.py`  
**Dependencies**: Task 1

Write pytest tests for all five skill endpoints (including existing GET list). Use `tmp_path` fixture to create a temporary skills directory; patch `Path(__file__).resolve().parent / "skills"` in main.py to point to the temp directory.

### Test cases
- GET list: empty dir returns `[]`; populated dir returns skills
- GET one: valid skill returns 200; missing skill returns 404
- POST: creates files and returns 201; duplicate returns 409; invalid name returns 422
- PUT: updates file and returns 200; missing skill returns 404
- DELETE: removes directory and returns 204; missing skill returns 404

---

## Task 3 — Frontend: API client skill CRUD functions [X]

**File**: `frontend/src/api/client.ts`  
**Dependencies**: None (can run in parallel with Task 1)

Add functions:
- `fetchSkill(name: string): Promise<SkillDefinition>` — calls `GET /api/skills/{name}`
- `createSkill(skill: SkillCreatePayload): Promise<SkillDefinition>` — calls `POST /api/skills`
- `updateSkill(name: string, payload: SkillUpdatePayload): Promise<SkillDefinition>` — calls `PUT /api/skills/{name}`
- `deleteSkill(name: string): Promise<void>` — calls `DELETE /api/skills/{name}`

---

## Task 4 — Frontend: Add Skill types to api.ts [X]

**File**: `frontend/src/types/api.ts`  
**Dependencies**: None (can run in parallel)

Add:
```typescript
export interface SkillDefinition {
  name: string;
  description: string;
  content: string;
}

export interface SkillSummary {
  name: string;
  description: string;
}

export interface SkillCreatePayload {
  name: string;
  description: string;
  content: string;
}

export interface SkillUpdatePayload {
  description: string;
  content: string;
}
```

---

## Task 5 — Frontend: SkillBuilder component [X]

**File**: `frontend/src/components/SkillBuilder.tsx`  
**Dependencies**: Tasks 3, 4

Create `SkillBuilder` component with:
- **List view**: fetch skills on mount via `fetchSkills()`; render each as card with name, description, and Edit/Delete buttons.
- **Create form**: shown when "NEW SKILL" button clicked; fields for name (slug), description, content (textarea); client-side validation; calls `createSkill`; on success refreshes list and resets form.
- **Edit form**: shown when Edit clicked; pre-populated via `fetchSkill(name)`; fields for description and content (name read-only); calls `updateSkill`; on success refreshes list.
- **Delete**: inline confirm dialog; calls `deleteSkill`; on success refreshes list.
- Inline success/error messages (no toast needed, keep it simple).
- Form submit button disabled until all required fields valid.

### CSS
- Follow existing dark tactical theme.
- Re-use `.agent-builder-*` CSS patterns where applicable; add `.skill-builder-*` classes for new styles.

---

## Task 6 — Frontend: AdminPage component [X]

**File**: `frontend/src/pages/AdminPage.tsx`  
**Dependencies**: Tasks 4, 5 (SkillBuilder); AgentBuilder already exists

Create `AdminPage` component:
- Props: `{ onBack: () => void; agents: CustomAgentDefinition[]; onSaveAgent: ...; onDeleteAgent: ...; }`
- Two tabs: "AGENTS" and "SKILLS" (tab state in `useState`).
- "AGENTS" tab renders `<AgentBuilder agents={...} onSave={...} onDelete={...} onBack={onBack} />`.
- "SKILLS" tab renders `<SkillBuilder />`.
- Tab bar at the top with active tab highlight (same dark theme).
- Back button / breadcrumb in header.

---

## Task 7 — Frontend: Sidebar — replace agent builder btn with admin btn [X]

**File**: `frontend/src/components/Sidebar.tsx`  
**Dependencies**: None (interface change)

- Rename prop `onOpenAgentBuilder` → `onOpenAdmin`.
- Change button label from "⚙ CUSTOM AGENT BUILDER" to "⚙ ADMIN".

---

## Task 8 — Frontend: ChatPage — remove inline AgentBuilder [X]

**File**: `frontend/src/pages/ChatPage.tsx`  
**Dependencies**: Task 7

- Remove `showAgentBuilder` state variable.
- Remove `import { AgentBuilder }` and the `AgentBuilder` JSX block.
- Remove `handleSaveCustomAgent` and `handleDeleteCustomAgent` patterns that were specific to the AgentBuilder rendering inside ChatPage — move them as props to App.tsx level (see Task 9).
- Change `onOpenAgentBuilder={() => setShowAgentBuilder(true)}` → `onOpenAdmin={props.onOpenAdmin}` (receive as prop from App).

---

## Task 9 — Frontend: App.tsx — add admin view state [X]

**File**: `frontend/src/App.tsx`  
**Dependencies**: Tasks 6, 7, 8

- Add `currentView: 'chat' | 'admin'` state (default `'chat'`).
- Pass `onOpenAdmin={() => setCurrentView('admin')}` down to `ChatPage` → `Sidebar`.
- Render `<AdminPage onBack={() => setCurrentView('chat')} agents={customAgents} ... />` when `currentView === 'admin'`.
- Move `useCustomAgents` hook up to `App.tsx` (currently in `ChatPage`), passing agents and CRUD handlers as props to both `ChatPage` and `AdminPage`.

---

## Task 10 — Frontend: CSS updates [X]

**File**: `frontend/src/styles/index.css` (or existing component CSS)  
**Dependencies**: Tasks 5, 6

- Add `.admin-page`, `.admin-tabs`, `.admin-tab`, `.admin-tab.active` styles.
- Add `.skill-builder-*` styles for SkillBuilder list, cards, form, and buttons.
- Ensure consistent dark tactical theme (match `.agent-builder-*` patterns).

---

## Task 11 — Visual Verification (required by constitution) [X]

**Dependencies**: Tasks 1-10 complete, frontend built and server running

Follow the Visual Verification Protocol:
1. `cd frontend && npm run build`
2. `AUTH_DISABLED=true uv run uvicorn main:app --host 0.0.0.0 --port 8000`
3. Playwright screenshots:
   - Chat page (baseline — unchanged)
   - Sidebar with new ADMIN button
   - Admin page — Agents tab
   - Admin page — Skills tab (list view)
   - Admin page — Skills tab (create form)
   - Admin page — Skills tab (edit form)
4. Agentic visual review of each screenshot.
5. Fix any visual defects and re-verify.

---

## Dependency Graph

```
Tasks 3, 4, 7   → parallel (no deps)
Task 1          → parallel (backend, no dep on frontend)
Task 2          → after Task 1
Task 5          → after Tasks 3, 4
Task 6          → after Task 5
Task 8          → after Task 7
Task 9          → after Tasks 6, 8
Task 10         → after Tasks 5, 6
Task 11         → after Tasks 1-10
```
