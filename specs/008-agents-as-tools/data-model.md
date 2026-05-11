# Phase 1 — Data Model: Agents as Tools

## Entities

### `SubAgentToolRef` (new)

A reference from a parent Agent to another Agent that is exposed as an LLM-callable tool on the parent. Only the target identifier is stored; the LLM-visible surface is derived from the target agent on every read.

| Field | Type | Required | Stored? | Notes |
|---|---|---|---|---|
| `agent_ref` | `AgentRef` (tagged union, see below) | yes | yes | Identifies the target agent (built-in or custom). |
| `tool_name` | string | derived | no | Slugified from the target agent's `name` to match `^[a-zA-Z][a-zA-Z0-9_]{0,63}$`. Recomputed on read. Disambiguated with a numeric suffix if two derived names collide on the same parent. |
| `tool_description` | string | derived | no | Copied from the target agent's `description` field. Recomputed on read. Truncated to 500 chars if longer. |
| `arg_description` | string | derived | no | Constant: `"Request for the {tool_name} agent."` |

**Why derived, not stored**: keeps a single source of truth (the target agent's own metadata), eliminates admin data-entry, and lets renames/redescriptions of a sub-agent automatically propagate to every parent that references it (no stale duplication).

### `AgentRef` (tagged union)

```text
AgentRef =
  | { kind: "builtin", profile_id: string }
  | { kind: "custom",  custom_agent_id: string, definition: CustomAgentDefinition }
```

- `profile_id` matches a key in `config/agents.yaml` (e.g., `"sql"`, `"search"`).
- `custom_agent_id` is the stable `id` field already used by `CustomAgentDefinition` (UUID generated on creation).
- `definition` is inlined by the frontend at request time so the backend can build the sub-agent without knowing about frontend `localStorage`. The backend MUST validate that `definition.id === custom_agent_id`.

### Extended: `AgentProfile` (backend, `prompt_config.py`)

Adds one optional field; everything else unchanged. Cardinality is `0..N` where `N` ≤ (total registered agents − 1, i.e. all available agents excluding the parent itself). The empty list, a single ref, a partial subset, and the full set of other agents are all valid configurations.

```python
@dataclass(frozen=True)
class AgentProfile:
    name: str
    logical_profile: str
    system_prompt: str
    description: str
    tool_names: list[str]
    temperature: Optional[float] = None
    skills: list[str] = field(default_factory=list)
    search_context: bool = False
    agents_as_tools: list[SubAgentToolRef] = field(default_factory=list)  # NEW
```

### Extended: `CustomAgentDefinition` (frontend, `frontend/src/types/api.ts`)

```ts
export interface CustomAgentDefinition {
  id: string;
  name: string;
  description: string;
  systemPrompt: string;
  tools: string[];
  skills: string[];
  mcpServers: McpServerEntry[];
  useSearchContext: boolean;
  icon: string;
  starters: StarterQuestion[];
  temperature?: number;
  agentsAsTools: SubAgentToolRef[];   // NEW — defaults to [] when absent
  createdAt: string;
  updatedAt: string;
}
```

`AgentCustomizationOverride` gets the same field with the same semantics.

## Identifier Strategy

- **Built-in agents**: identified by their YAML profile key (`profile_id`). Stable across renames of the human-readable `name` field.
- **Custom agents**: identified by `id` (existing UUID). Stable across renames of `name`.
- A `SubAgentToolRef` MUST always reference by these stable IDs, never by display name. This satisfies the "renamed" edge case in the spec.

## Lifecycle & State Transitions

| Transition | Behavior |
|---|---|
| Create parent w/ refs | Validate (see validation contract). Persist refs as part of agent definition. |
| Edit parent, add ref | Same validation, including new direct-cycle check against current state. |
| Edit parent, remove ref | Allowed unconditionally. |
| Sub-agent renamed | Refs unaffected (ID-based). UI re-resolves display name on render. |
| Sub-agent deleted | Refs become **orphaned**. UI surfaces them with a clear error indicator and a "remove" affordance. Runtime omits orphaned refs from the tool list with a logged warning (FR-008). Parent agent continues to function. |
| Sub-agent invocation succeeds | Result returned to parent LLM as the tool-call result. |
| Sub-agent invocation fails / times out | Structured error returned as the tool-call result (FR-009). Parent run continues. |

## Validation Rules (summary — see `contracts/validation-rules.md` for full normative list)

1. `agent_ref` resolves to an existing agent (or is flagged orphan at runtime).
2. Self-reference rejected: `agent_ref` cannot point at the parent being saved.
3. Direct A↔B cycle rejected: if target agent currently has a ref pointing back at the parent, save fails.
4. The picker prevents adding the same target twice in the same parent.
5. Derived `tool_name` collisions across distinct targets are auto-disambiguated (numeric suffix); never a save-blocking error.

All rules 1–4 are enforced both client-side (form, before save) and server-side (on session create / profile update). Rule 5 is a deterministic post-processing step applied identically on both tiers.

## Backward Compatibility

- The new field is optional and defaults to an empty list.
- Loading existing `config/agents.yaml` without an `agents_as_tools` block produces `agents_as_tools=[]` (no behavior change).
- Loading existing custom agents from `localStorage` without `agentsAsTools` populates it as `[]` on read.
- Existing API payloads without the field are accepted; responses always include the field (possibly as `[]`).
