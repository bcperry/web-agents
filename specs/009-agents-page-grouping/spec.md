# Feature Spec: Agents Page Grouping & Pagination

**Branch**: `009-agents-page-grouping` | **Date**: 2026-05-12

## Problem Statement

The agents page (`ProfileSelector`) currently displays all agents in a flat card grid. As the number of agents grows (built-in G-staff sections, custom agents), the page becomes unwieldy. Users need a way to browse agents by logical group and paginate large lists.

## Requirements

### Functional Requirements

1. **Group field in agents.yaml**: Each agent profile in `config/agents.yaml` MUST support an optional `group` field (string) that categorizes the agent into a named group.
2. **Group field in custom agents**: Custom agents created via the admin page MUST also support a `group` field, stored in localStorage alongside other custom agent data.
3. **Grouped display**: The agents page (`ProfileSelector`) MUST display agents organized by group using collapsible dropdown sections — matching the visual pattern used in the Agents and Skills tabs of the admin page (`AgentBuilder`).
4. **Ungrouped agents**: Agents without a `group` field MUST appear in a default "Ungrouped" or "Other" section.
5. **Pagination**: When a group contains many agents, the section SHOULD support pagination (or "show more" behavior).
6. **No behavioral changes**: This feature MUST NOT alter how agents are created, configured, or used in sessions. It is purely a display/organizational enhancement.

### Non-Functional Requirements

- The grouped UI MUST be responsive and accessible (keyboard navigation, ARIA attributes).
- Performance: grouping/pagination is client-side only — no new API endpoints needed (the existing `/api/profiles` already returns all profiles).

## Out of Scope

- Changing agent creation workflows.
- Changing how agents function or are instantiated.
- Backend pagination (all agents loaded client-side).
- Reordering agents within groups.

## Acceptance Criteria

1. `agents.yaml` schema supports optional `group: string` per profile.
2. Custom agent definition includes optional `group` field.
3. ProfileSelector renders agents in collapsible group sections.
4. Groups are collapsed/expanded via click (matching admin page pattern).
5. Pagination within groups works when agent count exceeds threshold.
6. Existing tests continue to pass; no breaking changes to API contract.
