# Quickstart: Agents Page Grouping & Pagination

**Feature**: 009-agents-page-grouping | **Date**: 2026-05-12

## Overview

This feature adds grouping and pagination to the agents selection page. Agents are organized into collapsible sections by group name, matching the admin page dropdown pattern.

## Quick Implementation Steps

### 1. Add `group` to agents.yaml

```yaml
# config/agents.yaml
profiles:
  chief-of-staff:
    name: Chief of Staff
    group: Command Staff        # <-- add this
    description: ...
    
  g1-personnel:
    name: G-1 Personnel
    group: General Staff        # <-- add this
    description: ...
```

### 2. Pass `group` in backend response

```python
# main.py — in get_profiles()
profiles.append({
    "id": profile_id,
    "name": name,
    "description": entry.get("description", ""),
    "icon": entry.get("icon", _DEFAULT_PROFILE_ICON),
    "group": entry.get("group", ""),    # <-- add this line
    "starters": starters,
    "skills": [...],
    "mcp_server_count": ...,
})
```

### 3. Add `group` to frontend types

```typescript
// frontend/src/types/api.ts
export interface AgentProfile {
  // ... existing fields ...
  group?: string;              // <-- add this
}

export interface CustomAgentDefinition {
  // ... existing fields ...
  group?: string;              // <-- add this
}
```

### 4. Update ProfileSelector with grouping

```typescript
// frontend/src/components/ProfileSelector.tsx
// Group profiles by group name, render collapsible sections
const grouped = useMemo(() => {
  const groups: Record<string, AgentProfile[]> = {};
  for (const p of profiles) {
    const g = p.group || p.customAgent?.group || 'Other';
    (groups[g] ??= []).push(p);
  }
  return groups;
}, [profiles]);
```

### 5. Add `group` field to Agent Builder form

Add a text input for `group` in the custom agent creation form, with a datalist suggesting existing group names.

## Testing

```bash
# Backend tests
uv run pytest tests/test_prompt_tools_yaml.py -v

# Frontend build
cd frontend && npm run build

# Visual verification
AUTH_DISABLED=true uv run uvicorn main:app --host 0.0.0.0 --port 8000
# Then screenshot and verify grouped layout
```

## Key Decisions

- Group name is free-form string (not enum)
- "Other" group for ungrouped agents, displayed last
- 6 agents visible per group by default, "Show More" to expand
- Collapsible sections match admin page toggle pattern
- No backend pagination — all client-side
