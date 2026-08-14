# Contract: REST API

**Feature**: 016-agent-ui-pane

All endpoints require a valid bearer token via the existing `get_current_user` dependency and are
served by `api_routes/agent_views.py`. `{session_id}` is the conversation id. Every endpoint
re-verifies ownership with `ConversationIndexRepository.get_owned(user_id, session_id)` before
reading anything — a 404 is returned for both "missing" and "not yours" so the endpoint does not
leak the existence of another user's conversation.

---

## `GET /api/sessions/{session_id}/views`

List the views for a conversation, oldest first. Used on conversation open to restore views
(FR-013) and to surface views produced during autonomous runs (FR-018).

**Response `200`**

```json
{
  "views": [
    {
      "viewId": "0f1e...",
      "title": "Readiness by unit",
      "createdAt": "2026-08-14T18:04:11.512Z",
      "chars": 18422,
      "source": "chat"
    }
  ]
}
```

Metadata only — no `html`. Keeps the list response small when a conversation holds many views.

**Errors**: `401` unauthenticated · `404` conversation not found or not owned · `503` store
unavailable.

---

## `GET /api/sessions/{session_id}/views/{view_id}`

Fetch one view including its markup. Called by the pane after an `agent_view` SSE event and when
the user selects a transcript marker.

**Response `200`**

```json
{
  "viewId": "0f1e...",
  "title": "Readiness by unit",
  "createdAt": "2026-08-14T18:04:11.512Z",
  "chars": 18422,
  "source": "chat",
  "html": "<section>...</section>"
}
```

`html` is returned exactly as the agent authored it. Isolation is applied when the client mounts
it in the sandboxed frame — the server never rewrites the markup.

**Errors**: `401` · `404` view not found, not owned, or belongs to another conversation · `503`.

---

## `POST /api/sessions/{session_id}/views/{view_id}/data`

The permission broker. Executes one tool call on behalf of a rendered view.

**Request**

```json
{ "tool": "get_user_profile", "arguments": {} }
```

**Response `200`**

```json
{ "ok": true, "data": "{\"name\":\"Alex\"}", "truncated": false, "durationMs": 142 }
```

**Refusal `403`**

```json
{ "ok": false, "error": { "code": "not_permitted", "message": "That data is not available to this view." } }
```

**Status codes**

| Status | `error.code` | Meaning |
|---|---|---|
| `200` | — | Tool executed; `data` holds the tool's own result, truncated if oversize. |
| `400` | `invalid_arguments` | `arguments` is not a JSON object, or fails argument bounds. |
| `401` | — | Unauthenticated. |
| `403` | `not_permitted` | The tool is not in the rendering agent's live tool set, or is `render_agent_view`. |
| `404` | — | Conversation or view not found / not owned. |
| `409` | `session_inactive` | No live session; the client re-establishes the session and retries once. |
| `429` | `rate_limited` | Per-session broker budget exhausted; `Retry-After` seconds included. |
| `500` | `tool_failed` | The tool raised. The message is sanitized — no stack traces, no connection strings. |

**Invariants**

- The executing identity is always the bearer-token user. Nothing in the request body can change
  the acting user, agent, or session.
- Refusals return **zero bytes** of tool data (SC-002).
- Every outcome — including refusals — is logged and added to the session eval trace (FR-008).

---

## Modified: `DELETE /api/conversations/{conversation_id}`

Existing endpoint gains a step: delete that conversation's views from the user's partition before
deleting the conversation record, so views never outlive their conversation.
