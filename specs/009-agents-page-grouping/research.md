# Research: Agents Page Grouping & Pagination

**Feature**: 009-agents-page-grouping | **Date**: 2026-05-12

## Research Tasks

### 1. UI Pattern for Collapsible Group Sections

**Decision**: Reuse the exact collapsible section pattern from `AgentBuilder.tsx`.

**Rationale**:
- The admin page already has a working, accessible collapsible section pattern (toggle button with +/- icon, `aria-expanded`, CSS class toggling).
- Reusing the same CSS classes (`agent-builder-section-toggle`, `agent-builder-section-title`, `agent-builder-section-toggle-icon`) ensures visual consistency.
- Alternatively, extract a shared `CollapsibleSection` component — but YAGNI per constitution Principle V. Reusing CSS classes with inline logic is simpler.

**Alternatives considered**:
- Third-party accordion library (rejected: unnecessary dependency per Principle V).
- Custom `<details>`/`<summary>` HTML elements (rejected: harder to style consistently, doesn't match admin page aesthetic).

### 2. Pagination Strategy

**Decision**: Client-side "Show More" button within each group, defaulting to 6 visible agents per group.

**Rationale**:
- All agents are already loaded client-side (from `/api/profiles` + localStorage). No server-side pagination needed.
- A "Show More" button is simpler than numbered pagination for a small-to-medium list.
- 6 agents per group = 2 rows of 3 cards (standard card grid).

**Alternatives considered**:
- Numbered pagination (rejected: over-engineered for ~10-20 agents per group).
- Infinite scroll (rejected: unnecessary complexity for static lists).
- No pagination (rejected: defeats purpose if groups grow large).

### 3. `group` Field Schema Design

**Decision**: Optional string field `group` on agent profiles. No enum restriction — free-form text.

**Rationale**:
- Allows maximum flexibility for users naming their own groups.
- Built-in agents get groups defined in `agents.yaml`.
- Custom agents get a group field in the form (text input or dropdown of existing groups).
- Agents without a `group` are placed in an "Other" section shown last.

**Alternatives considered**:
- Enum/predefined group list (rejected: too rigid, doesn't scale for custom agents).
- Array of groups / multi-group membership (rejected: adds complexity for marginal benefit).
- Separate `groups.yaml` config file (rejected: violates Principle II, over-engineering).

### 4. Backend Changes Required

**Decision**: Minimal — pass `group` field through in `GET /api/profiles` response.

**Rationale**:
- The backend already reads `agents.yaml` and constructs the profile response dict.
- Adding `"group": entry.get("group", "")` is a one-line change in `main.py`.
- No new endpoints, no new models, no schema migrations.

**Alternatives considered**:
- Backend-side grouping/sorting (rejected: grouping is a UI concern, keep in frontend).
- New `/api/groups` endpoint (rejected: over-engineering, violates YAGNI).

### 5. Existing Schema Validation

**Decision**: Update `test_prompt_tools_yaml.py` to accept the optional `group` field.

**Rationale**:
- The test validates `agents.yaml` structure. Adding `group` as an optional string field keeps it passing.
- No breaking change — field is optional.

## Summary of Resolved Items

| Item | Resolution |
|------|-----------|
| UI pattern | Reuse collapsible section pattern from AgentBuilder |
| Pagination | Client-side "Show More" (6 per group default) |
| Group field type | Optional string, free-form |
| Backend change | Pass `group` in profiles response |
| Default group | "Other" for ungrouped agents |
| Validation | Update existing YAML schema test |
