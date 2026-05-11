# Contract: Agent Schema Additions

## Backend — `config/agents.yaml`

Per-profile block gains an optional `agents_as_tools` list. Entries store **only** the target reference — tool name and description are derived from the target agent at load time.

```yaml
profiles:
  research_coordinator:
    name: Research Coordinator
    description: Coordinates research across specialized agents.
    icon: /icons/coordinator.svg
    tools: []
    skills: []
    mcp_servers: []
    temperature: 0.2
    starters: []
    system_prompt: |
      You coordinate specialized agents...
    agents_as_tools:                 # NEW (optional, defaults to [])
      - agent_ref:
          kind: builtin
          profile_id: azgov
      # tool_name ("azure_government_specialist") and tool_description
      # are derived from the azgov profile at load time — do NOT specify them here.
```

Custom-agent refs are not expressible in `agents.yaml` (built-in YAML cannot reference frontend-localStorage entities). YAML supports `kind: builtin` only.

## Backend — `prompt_config.py`

```python
@dataclass(frozen=True)
class SubAgentToolRef:
    agent_ref: AgentRef          # see below — the only stored field

@dataclass(frozen=True)
class BuiltinAgentRef:
    kind: Literal["builtin"]
    profile_id: str

@dataclass(frozen=True)
class CustomAgentRef:
    kind: Literal["custom"]
    custom_agent_id: str
    definition: dict[str, Any]   # raw custom-agent payload, validated separately

AgentRef = Union[BuiltinAgentRef, CustomAgentRef]
```

`tool_name`, `tool_description`, and `arg_description` are computed by a helper (e.g., `derive_sub_agent_tool_surface(ref, target_agent)`) at the point where `agent_factory` builds the parent's tool list. They are not fields on the dataclass.

`AgentProfile` gains `agents_as_tools: list[SubAgentToolRef] = field(default_factory=list)`.

## Frontend — `frontend/src/types/api.ts`

```ts
export type AgentRef =
  | { kind: 'builtin'; profileId: string }
  | { kind: 'custom'; customAgentId: string; definition: CustomAgentDefinition };

export interface SubAgentToolRef {
  agentRef: AgentRef;          // only stored field
  // Derived fields supplied by the backend on read; treat as read-only on the client:
  toolName?: string;           // server-derived; never set by the form
  toolDescription?: string;    // server-derived; never set by the form
  argDescription?: string;     // server-derived; never set by the form
}
```

The form never writes `toolName` / `toolDescription` / `argDescription`; it only collects `agentRef`. The backend echoes the derived strings back on responses so the UI can display them read-only next to each picked agent.

export interface CustomAgentDefinition {
  // ...existing fields...
  agentsAsTools: SubAgentToolRef[];   // NEW
}

export interface AgentCustomizationOverride {
  // ...existing fields...
  agentsAsTools: SubAgentToolRef[];   // NEW
}

export interface ProfileDefinition {
  // ...existing fields returned by GET /api/profiles/{id}/definition...
  agentsAsTools: SubAgentToolRef[];   // NEW (always present, may be empty)
}
```

## Wire-format Naming Convention

- YAML / Python use `snake_case` (`agents_as_tools`, `agent_ref`, `profile_id`, `custom_agent_id`). Derived fields when echoed back: `tool_name`, `tool_description`, `arg_description`.
- TypeScript uses `camelCase` (`agentsAsTools`, `agentRef`, `profileId`, `customAgentId`, `toolName`, `toolDescription`, `argDescription`).
- The existing `main.py` payload helpers already perform snake↔camel translation for other fields (e.g., `mcpServers` ↔ `mcp_servers`, `useSearchContext` ↔ `use_search_context`); the new field follows the same convention.

## Derivation Rules (normative)

- `tool_name` = `slugify(target_agent.name)` where `slugify` lowercases, replaces any run of non-`[a-zA-Z0-9]` with `_`, trims leading/trailing `_`, prepends `a_` if the result starts with a digit, and truncates to 64 chars. Fallback: target agent's stable identifier if slug is empty.
- `tool_description` = `target_agent.description` (truncated to 500 chars). Fallback: `"Delegate to the {target_agent.name} agent."` if description is empty.
- `arg_description` = `"Request for the {tool_name} agent."`
- Collision handling: if two derived `tool_name`s on the same parent collide, append `_2`, `_3`, … in the order the refs appear.