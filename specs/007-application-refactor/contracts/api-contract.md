# API Contract: Behavior-Preserving Refactor

This refactor must not introduce breaking backend API changes. Routes may call new helpers/services internally, but external behavior remains stable.

## Contract Rules

- Preserve existing route paths, methods, status codes, and response field names unless a later task explicitly documents a compatibility-preserving migration.
- Preserve SSE event names: `text`, `function_call`, `function_result`, `usage`, `error`, `done`.
- Preserve auth behavior, including `AuthError` handling on the frontend for 401 responses.
- Preserve local development behavior when `AUTH_DISABLED=true`.
- Preserve error-message semantics where tests or UI flows depend on them.
- Do not edit `config/agents.yaml`.

## Routes To Preserve

| Method | Route | Contract Notes |
|--------|-------|----------------|
| GET | `/api/health` | Returns `{ "status": "healthy" }`. |
| GET | `/api/auth/config` | Returns frontend auth/runtime config without secrets. |
| GET | `/api/tools` | Returns available/unavailable tools plus search context availability. |
| GET | `/api/profiles` | Returns healthy profiles and unavailable profile reasons. |
| GET | `/api/profiles/{profile_id}/definition` | Returns built-in profile definition without secret fields. |
| POST | `/api/mcp/test` | Tests inline HTTP MCP servers and returns per-server results. |
| GET | `/api/skills` | Lists skill summaries. |
| POST | `/api/skills/generate` | Generates skill Markdown body from description. |
| GET | `/api/skills/{name}` | Returns `{ name, description, content }`. |
| POST | `/api/skills` | Creates a skill and returns created definition with 201. |
| PUT | `/api/skills/{name}` | Updates skill definition. |
| DELETE | `/api/skills/{name}` | Deletes skill and returns 204. |
| POST | `/api/sessions` | Creates standard, custom, or override sessions. |
| GET | `/api/sessions/{session_id}/history` | Exports backend session state and override metadata. |
| POST | `/api/sessions/{session_id}/messages` | Streams SSE response events for text/multipart messages. |
| DELETE | `/api/sessions/{session_id}` | Cleans up MCP connections and session usage, returns 204. |

## Session Response Shape

Required for all successful session creation responses:

```json
{
  "session_id": "uuid",
  "profile_id": "profile-key-or-custom",
  "profile_name": "Display Name",
  "tools_loaded": [],
  "skills_loaded": [],
  "search_context": false,
  "mcp_results": []
}
```

Built-in override responses also preserve:

```json
{
  "used_profile_override": true,
  "override_updated_at": "2026-05-06T12:00:00.000Z"
}
```

## Verification

- `uv run pytest` must pass.
- Existing route tests must continue to pass without frontend changes.
- New unit tests should cover extracted validators, skill manager, streaming helpers, and session orchestration.
- `git diff -- config/agents.yaml` must be empty.