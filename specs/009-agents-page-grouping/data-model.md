# Data Model: Agents Page Grouping & Pagination

**Feature**: 009-agents-page-grouping | **Date**: 2026-05-12

## Entities

### 1. Agent Profile (Backend — `agents.yaml`)

```yaml
# config/agents.yaml — per profile entry
profiles:
  <profile-id>:
    name: string           # required
    description: string    # required
    icon: string           # required
    group: string          # NEW — optional, free-form group name
    tools: string[]        # required (may be empty)
    skills: string[]       # required (may be empty)
    mcp_servers: list      # required (may be empty)
    agents_as_tools: list  # optional
    starters: list         # optional
    system_prompt: string  # required
```

**New field**: `group` (optional string)
- If omitted or empty, agent belongs to the "Other" group.
- No validation beyond type check (string).

### 2. Agent Profile (API Response — `GET /api/profiles`)

```json
{
  "profiles": [
    {
      "id": "chief-of-staff",
      "name": "Chief of Staff",
      "description": "...",
      "icon": "/icons/hybrid.svg",
      "group": "Command Staff",       // NEW field
      "starters": [...],
      "skills": [...],
      "mcp_server_count": 0
    }
  ],
  "unavailable": [...]
}
```

**New field**: `group` (string, defaults to `""` if not set in YAML)

### 3. AgentProfile (Frontend TypeScript)

```typescript
export interface AgentProfile {
  id: string;
  name: string;
  description: string;
  icon: string;
  group?: string;              // NEW — optional group name
  starters: StarterQuestion[];
  isCustom?: boolean;
  isCustomized?: boolean;
  customAgent?: CustomAgentDefinition;
  builtInOverride?: AgentCustomizationOverride;
  baseProfileId?: string;
  usedBuiltInOverride?: boolean;
  overrideUpdatedAt?: string;
  mcp_server_count?: number;
}
```

### 4. CustomAgentDefinition (Frontend TypeScript)

```typescript
export interface CustomAgentDefinition {
  id: string;
  name: string;
  description: string;
  group?: string;              // NEW — optional group name
  systemPrompt: string;
  tools: string[];
  skills: string[];
  mcpServers: McpServerEntry[];
  useSearchContext: boolean;
  icon: string;
  starters: StarterQuestion[];
  temperature?: number;
  agentsAsTools?: SubAgentToolRef[];
  createdAt: string;
  updatedAt: string;
}
```

### 5. ProfileSelector Grouped State

```typescript
// Computed from profiles array — no persistence needed
interface GroupedProfiles {
  [groupName: string]: AgentProfile[];
}

// Derived at render time:
// 1. Group profiles by `profile.group || profile.customAgent?.group || "Other"`
// 2. Sort group names alphabetically, "Other" last
// 3. Each group shows up to PAGE_SIZE (6) agents initially
// 4. "Show More" expands to show all
```

## Relationships

```
agents.yaml  ─────────>  GET /api/profiles  ─────────>  AgentProfile[]
  (group field)            (passes group)                 (displays in groups)

localStorage ─────────>  useCustomAgents()  ─────────>  AgentProfile[]
  (group field)            (merges into list)             (same grouping logic)
```

## Validation Rules

| Field | Rule |
|-------|------|
| `group` in YAML | Optional. Must be a string if present. |
| `group` in custom agent | Optional. Must be a string if present. |
| `group` in API response | Always present as string (empty string if not set). |

## State Transitions

N/A — No state machine. Grouping is a pure display concern.
