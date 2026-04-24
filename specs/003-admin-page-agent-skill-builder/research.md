# Research: Admin Page — Agent Builder + Skill Builder

**Branch**: `003-admin-page-agent-skill-builder`

## Decision 1: View Routing Strategy

**Decision**: Use simple view-state variable in `App.tsx` (e.g., `currentView: 'chat' | 'admin'`), not React Router.

**Rationale**: The existing codebase already uses view-state toggling (`showAgentBuilder` in `ChatPage`). Adding React Router for two views would be over-engineering — consistent with Constitution Principle V (Simplicity). The SPA serves a single functional area with only two top-level views.

**Alternatives considered**:
- React Router v6 — rejected; no existing routing infrastructure, adds a new npm dependency, overkill for two views.
- Hash-based URL routing manually — rejected; adds complexity with no user-facing benefit.

## Decision 2: Skill File Storage

**Decision**: Store skills as `skills/{name}/SKILL.md` files (existing convention). Backend CRUD writes/reads these files directly.

**Rationale**: This matches the existing `table-usage` skill structure exactly. The `SkillsProvider` from `agent-framework` already reads this layout. No schema migration or database needed.

**Alternatives considered**:
- Database storage (e.g., new SQLite table) — rejected; adds dependency and breaks existing `SkillsProvider` conventions.
- Single flat YAML/JSON config file — rejected; inconsistent with the established per-skill-directory format.

## Decision 3: Admin Page Tab Layout

**Decision**: Two tabs inside `AdminPage.tsx` — "AGENTS" and "SKILLS" — using the same dark tactical CSS theme. Tab state in local `useState`, not URL params.

**Rationale**: Simple, consistent with existing component patterns. Both tabs are admin-only power-user tools that belong together.

**Alternatives considered**:
- Separate pages/routes for each builder — rejected; adds navigation complexity and routing library dependency.
- Single combined scrollable page — rejected; agent builder and skill builder are distinct tools and would create a very long page.

## Decision 4: Skill Name Validation

**Decision**: Backend enforces `^[a-z0-9][a-z0-9-]*$` (max 64 chars) for skill names. Frontend mirrors this with a client-side validation for immediate feedback.

**Rationale**: Skill name becomes a directory name on the filesystem. Limiting to lowercase alphanumeric + hyphen prevents path traversal, spaces, or OS-reserved characters.

**Alternatives considered**:
- Allow any string and sanitize — rejected; lossy sanitization could silently rename skills in unexpected ways.
- UUID-based filenames with a separate name field — rejected; breaks the existing convention where directory name = skill name.

## Decision 5: Skill Content Format

**Decision**: SKILL.md uses YAML frontmatter (`name`, `description`) followed by markdown body. The `POST`/`PUT` API accepts `{name, description, content}` JSON; the backend assembles the SKILL.md file.

**Rationale**: Existing `table-usage/SKILL.md` uses this format. The `SkillsProvider` parses frontmatter to populate `name`/`description` fields. Keeping the format stable avoids breaking the provider.

**Alternatives considered**:
- Store name/description separately from content — rejected; would require changes to SkillsProvider or dual storage.

## Decision 6: Delete Behavior

**Decision**: `DELETE /api/skills/{name}` removes the entire `skills/{name}/` directory and all its contents.

**Rationale**: Skills only ever contain `SKILL.md` (per current convention). A full directory removal is clean and prevents orphaned directories.

**Alternatives considered**:
- Soft-delete (rename to `.disabled`) — rejected; adds complexity, not needed for this use case.
- Only delete the SKILL.md and leave directory — rejected; leaves empty directories that confuse the SkillsProvider.

## Decision 7: No Role-Based Access Control

**Decision**: The Admin page is accessible to all authenticated users. No additional authorization layer.

**Rationale**: The spec explicitly excludes RBAC from scope. The existing auth model authenticates all users equally. Adding admin-role gating would require Azure AD group changes and is out of scope.

**Alternatives considered**:
- Check for admin group claim in Azure AD token — deferred; out of scope for this feature.
