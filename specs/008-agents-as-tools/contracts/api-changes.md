# Contract: API Changes

All existing endpoints. No new routes. All changes are additive.

## `GET /api/profiles/{profile_id}/definition`

Response body gains:

```json
{
  "...existing fields...": "...",
  "agentsAsTools": [
    {
      "agentRef": { "kind": "builtin", "profileId": "azgov" },
      "toolName": "azure_government_specialist",
      "toolDescription": "Specialist for Azure Government cloud questions...",
      "argDescription": "Request for the azure_government_specialist agent."
    }
  ]
}
```

- `agentRef` is the only stored field; `toolName` / `toolDescription` / `argDescription` are derived by the backend (see `agent-schema.md` derivation rules) and included in the response so the UI can display them read-only.
- Field is always present; empty list when none configured.
- Built-in profile responses MUST never emit `kind: "custom"` refs (YAML cannot express them).

## `POST /api/sessions` — custom agent path

Request body for a session created from a custom agent gains:

```json
{
  "...existing fields...": "...",
  "agentsAsTools": [
    { "agentRef": { "kind": "builtin", "profileId": "azgov" } },
    {
      "agentRef": {
        "kind": "custom",
        "customAgentId": "f3a1...",
        "definition": { "id": "f3a1...", "name": "Blaine Bot", "...": "..." }
      }
    }
  ]
}
```

The frontend MUST inline the full `definition` object for every `kind: "custom"` ref before sending. The backend MUST validate `definition.id === customAgentId`. The frontend does not send `toolName` / `toolDescription` / `argDescription`; if it does, the backend ignores them and recomputes from the target agent.

## `POST /api/sessions` — built-in override path

Same additive shape inside the override payload (`AgentCustomizationOverride`).

## Validation Error Response

When any validation rule from `validation-rules.md` fails, the API returns HTTP `400` with:

```json
{
  "error": "validation_failed",
  "details": [
    {
      "field": "agentsAsTools[1].agentRef",
      "code": "direct_cycle",
      "message": "Agent 'Blaine Bot' already references this agent as a tool."
    }
  ]
}
```

The `field` path uses dotted/bracketed notation so the frontend can attach errors to the right row.

## Trace / Observability

Existing trace stream (used by `eval_trace.py` and the chat UI) emits a tool-invocation event for each sub-agent call:

```json
{
  "type": "tool_call",
  "tool_name": "consult_azgov_specialist",
  "tool_kind": "sub_agent",
  "sub_agent": { "kind": "builtin", "profileId": "azgov" },
  "arguments": { "request": "..." },
  "result_preview": "..."
}
```

`tool_kind: "sub_agent"` is the new tag distinguishing these from regular function tools and MCP tools.

## OpenAPI

FastAPI auto-regenerates `/openapi.json`. Frontend types in `frontend/src/types/api.ts` are kept in sync with the schema additions documented in `agent-schema.md`.
