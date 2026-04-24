# Feature Spec: Admin Page with Agent Builder + Skill Builder

**Branch**: `003-admin-page-agent-skill-builder`  
**Date**: 2026-06-17  
**Status**: Active

## Overview

Move the existing Custom Agent Builder out of the main chat page and into a dedicated Admin page. Add a Skill Builder alongside it on the same Admin page so administrators can create, edit, and delete skill markdown files directly from the UI.

## Goals

1. Declutter the main chat UI — the agent builder is an admin/power-user tool, not a day-to-day feature.
2. Provide a central admin panel reachable from the sidebar.
3. Allow skill management (create, edit, delete `skills/<name>/SKILL.md` files) through a browser UI rather than editing files by hand.

## Scope

### In Scope

- New `AdminPage` React component with two tabs: **Agents** and **Skills**.
- Move `AgentBuilder` usage from `ChatPage` into the Admin page's Agents tab.
- New `SkillBuilder` React component on the Skills tab for CRUD of skill files.
- Backend REST endpoints for skill CRUD: GET all (already exists), GET one, POST, PUT, DELETE.
- Sidebar navigation link to open the Admin page.
- Remove `showAgentBuilder` state and inline `AgentBuilder` rendering from `ChatPage`.

### Out of Scope

- Role-based access control / admin-only gating (no auth changes).
- Multi-file skill bundles (skills remain single-file SKILL.md).
- Skill versioning or audit history.

## User Stories

1. **As a user**, I click "Admin" in the sidebar and land on the Admin page — the main chat is unaffected.
2. **As a user**, on the Agents tab I see the full Agent Builder experience I previously accessed via the sidebar shortcut.
3. **As a user**, on the Skills tab I can see all installed skills, edit their name/description/content, create a new skill, or delete an existing one.
4. **As a user**, changes I make in the Skill Builder persist immediately (server-side file write) and are picked up by the next agent session.

## Functional Requirements

### Admin Page

- Accessible via a sidebar button (replaces existing "CUSTOM AGENT BUILDER" button).
- Contains two tabs: **Agents** and **Skills**.
- Tab state persists during the page session (not persisted across reloads).
- Navigating away from Admin (via sidebar back button or new conversation) returns to `ChatPage`.

### Agent Builder (Agents Tab)

- Identical functionality to current `AgentBuilder` component.
- `onBack` callback navigates back to `ChatPage`.
- No other changes to agent builder logic.

### Skill Builder (Skills Tab)

- **List view**: Shows all skills loaded from `/api/skills`. Each item shows name and description with Edit/Delete actions.
- **Create form**: Name (slug, required), description (required), markdown body (textarea).
- **Edit form**: Pre-populated from `/api/skills/{name}` (returns full SKILL.md content).
- **Delete**: Confirm and call `DELETE /api/skills/{name}`.
- **Validation**: Name must be a valid directory slug (`[a-z0-9-]+`). Name must be unique on create.
- **Feedback**: Show inline success/error messages. No page reload required.

## Backend Requirements

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/skills/{name}` | Returns full SKILL.md content for one skill |
| POST | `/api/skills` | Creates a new skill directory + SKILL.md |
| PUT | `/api/skills/{name}` | Overwrites existing SKILL.md |
| DELETE | `/api/skills/{name}` | Removes the skill directory |

### Skill File Format

```markdown
---
name: {slug}
description: "{description}"
---

{markdown body}
```

### Validation Rules (backend)

- `name`: matches `^[a-z0-9][a-z0-9-]*$`, max 64 chars.
- `description`: non-empty string, max 256 chars.
- `content`: non-empty string, max 64 KB.
- `DELETE` and `PUT` return 404 if the skill doesn't exist.
- `POST` returns 409 if a skill with that name already exists.

## Non-Functional Requirements

- Constitution compliance: all SQL ops remain read-only; no new dependencies required beyond what's already in use.
- Frontend: No React Router required — simple view-state switching in `App.tsx` (consistent with existing pattern).
- Security: All endpoints authenticated (same `get_current_user` dependency pattern). Skills are written server-side; the frontend never constructs file paths.
- Visual: Admin page follows the existing dark tactical UI theme.
