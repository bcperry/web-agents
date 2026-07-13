# Management API and Catalog Contract

## Tool Inventory

### `GET /api/tools`

The response shape remains unchanged:

```json
{
  "tools": [{"name": "create_agent", "description": "Create a durable user-owned custom agent..."}],
  "unavailable": [],
  "search_context_available": true,
  "search_context_reason": null
}
```

Inventory is sourced from the function-tool registry rather than only scanning names currently used
in `agents.yaml`. This allows both creation tools to be selectable without granting either by
default. Existing registered tools remain present with Python-owned descriptions.

## Skill Catalog Reads

Authenticated skill catalog reads resolve:

1. all global/built-in skill summaries from the existing `skills` repository; and
2. only user-owned skill summaries from the caller's `user-skills` partition.

The existing summary/full skill wire shapes remain `{name, description}` and
`{name, description, content}`. A name is unique in the combined owner catalog because user create
rejects global collisions. Cross-user skills are never queried or returned.

Existing global skill administration remains on the established `/api/skills` management surface.
Implementation may add explicit source metadata internally, but must not silently redirect a global
update/delete to a user-owned item. User-owned definitions created by the tool must be observable
through owner catalog/management reads.

## Custom Agent Writes

### `PUT /api/custom-agents/{agent_id}`

The route keeps its existing path and successful bare-definition response, but delegates validation
and normalization to the same custom-agent definition service used by `create_agent`.

- `agent_id` must match body `id`.
- Full create/update payload validation is strict.
- Capability resolution is scoped to the authenticated caller.
- Existing explicit management updates may use repository `upsert` and preserve `createdAt`.
- Runtime `create_agent` always uses atomic `create`, never this HTTP route and never upsert.
- Invalid payloads return an HTTP validation response derived from the shared field issues.
- Storage failures remain sanitized `503` responses.

## Session Compatibility

Starting an already saved custom agent retains current compatibility behavior:

- a skill deleted after save may be dropped with a warning so the agent still starts;
- no creation/update path may use that tolerant policy;
- tool grants are always exact: absent `create_skill`/`create_agent` names produce absent runtime
  functions.

This distinction prevents new invalid records while preserving FR-020 for existing records.

## Authorization

All endpoints continue to require `get_current_user`. Owner identity comes only from that dependency.
Cross-user records behave as not found and no response distinguishes "owned by another user" from
"does not exist".