# Runtime Function Tool Contract

## Availability and Binding

- Registry names are exactly `create_skill` and `create_agent`.
- Each appears independently in `GET /api/tools` with its Python-owned description.
- Neither is present in any profile/custom-agent defaults.
- `build_tool_instances` returns only explicitly requested registered names.
- Session construction binds each returned function to the authenticated user. No tool input schema
  contains `user_id`, owner, tenant, partition key, token, or equivalent authority field.

## `create_skill`

Creates one durable skill owned by the invoking user.

### Input

```json
{
  "name": "incident-summary",
  "description": "Summarize incident notes into an action report.",
  "content": "# Incident Summary\nUse the supplied notes..."
}
```

All fields are required. Validation and normalization match the management skill rules. A global
skill name or an existing skill name in the invoking owner's partition is a duplicate.

## `create_agent`

Creates one durable custom agent owned by the invoking user.

### Input

```json
{
  "id": "incident-planner",
  "name": "Incident Planner",
  "description": "Builds incident action plans.",
  "systemPrompt": "Create concise, evidence-based plans.",
  "tools": ["create_skill"],
  "skills": ["incident-summary"],
  "mcpServers": [],
  "useSearchContext": false,
  "icon": "/favicon.png",
  "starters": [{"label": "Plan", "message": "Create an incident plan."}],
  "temperature": 0.2,
  "agentsAsTools": []
}
```

Optional fields use the existing custom-agent defaults. Creation is strict: every tool, skill,
server, and delegated-agent reference must be valid and resolvable for the invoking user. A target
owned by another user resolves as nonexistent. `source`, owner fields, and timestamps are not tool
inputs.

## Success Result

```json
{
  "status": "created",
  "kind": "skill",
  "id": "incident-summary",
  "name": "incident-summary",
  "message": "Created skill 'incident-summary'."
}
```

Required fields: `status`, `kind`, `id`, `name`, `message`. The result never includes content,
system instructions, owner identity, timestamps, storage metadata, tokens, or server credentials.

## Error Result

```json
{
  "status": "error",
  "kind": "agent",
  "code": "validation_error",
  "message": "The agent definition is invalid.",
  "retryable": false,
  "issues": [
    {"field": "skills[0]", "reason": "Skill could not be resolved."}
  ]
}
```

| Code | Retryable | Meaning |
|------|-----------|---------|
| `validation_error` | `false` | One or more fields failed validation; `issues` is required. |
| `duplicate` | `false` | Requested owner-scoped identity already exists, or skill name is globally reserved. |
| `unauthorized` | `false` | No valid authenticated identity was bound; no owner lookup occurs. |
| `temporarily_unavailable` | `true` | Durable store failed; returned message is sanitized. |

Unexpected exceptions map to `temporarily_unavailable`; raw exception/provider text is not returned.
Duplicate results may name the requested id/name but do not return the existing document.

## Atomicity and Retry

- Validation completes before `create_item`.
- Creation uses a Cosmos atomic create, never upsert.
- Concurrent same-owner/same-id calls produce one `created` and one `duplicate`.
- Different owners may create the same id, except user skill names reserved by a global skill.
- Retrying an interrupted successful call produces `duplicate`, never another record or overwrite.