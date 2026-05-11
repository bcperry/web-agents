# Contract: Validation Rules (single source of truth)

Each rule is enforced **identically** in two places:

- **Frontend**: `frontend/src/utils/agentToolValidation.ts` (consumed by `useAgentBuilderForm` and the new `AgentAsToolPicker` component).
- **Backend**: `validators.py` (consumed by `session_orchestration.py` on session create and by any agent-update path).

All rules return structured errors in the shape defined by `api-changes.md` — `{ field, code, message }`.

| # | Code | Rule | Failing example |
|---|---|---|---|
| V1 | `unresolved_agent_ref` | `agentRef` resolves to a known agent (built-in profile present in `agents.yaml` or inlined custom definition with matching `id`) | `profileId: "ghost"` not in YAML |
| V2 | `self_reference` | `agentRef` does not point at the parent being saved | Editing agent `X`, adding a ref with `customAgentId: X` |
| V3 | `direct_cycle` | If target agent currently has a ref pointing back at parent, reject | Agent `B` already has a ref to `A`; user tries to add `B` as a tool on `A` |
| V4 | `duplicate_target` | Same target agent referenced twice in the same parent | Two refs both with `profileId: azgov` |
| V5 | `definition_id_mismatch` (backend only) | For `kind: "custom"`, `definition.id === customAgentId` | Frontend bug or tampering |

**Removed (now non-issues)**: tool-name format, description-required, and duplicate-tool-name validations. `tool_name` and `tool_description` are derived from the target agent (see `agent-schema.md` derivation rules); the slugifier guarantees format compliance, derivation guarantees a non-empty description (with a fallback), and collisions across distinct targets are deterministically disambiguated rather than rejected.

## Cycle-detection inputs

- **Frontend** has the full custom-agent table (`useCustomAgents`) plus the built-in profile list — it can resolve all `agentRef`s and inspect their own `agentsAsTools` to apply V5.
- **Backend** receives an inlined payload (the parent's full `agentsAsTools` list, with `definition` inlined for each `kind: "custom"` ref). For V5, it inspects each target's own `agents_as_tools` (from YAML for built-in, from the inlined definition for custom) and rejects if any of them point back to the parent's ID.

## Save-blocking semantics

- V2, V3, V4 block save in the UI (the Save button is disabled and inline error messages are shown next to the offending row).
- V1 is a runtime-only condition: configuration is allowed to remain (the orphaned ref is shown in the form with a remove affordance per FR-008), but a warning is logged and the tool is omitted from the runtime tool list.
- V5 is a defense-in-depth check; never expected to trigger from a well-behaved frontend.

## Out-of-scope (per spec)

- Multi-hop cycle detection (A→B→C→A and longer chains). Direct cycle (V5) only.
- Maximum recursion depth / cost ceilings.
