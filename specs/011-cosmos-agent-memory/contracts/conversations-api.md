# Contract: Conversations API (REST)

**Feature**: `011-cosmos-agent-memory` | **Date**: 2026-06-18

Backend REST endpoints that let the frontend read the authenticated user's real conversations and messages from Azure Cosmos DB, and that change session create/resume to load history server-side. All endpoints are served by the FastAPI backend (the only gateway to Cosmos — Principle VII) and require authentication via the existing `get_current_user` dependency (except where local-dev `AUTH_DISABLED=true` applies).

**Conventions**:
- Base path: `/api`.
- Auth: `Authorization: Bearer <token>` → `AuthenticatedUser{ user_id, username }`. `user_id` (token `oid`) is the ownership key and is NEVER read from the request body.
- Ownership: every operation on a specific conversation first verifies the `conversations` index document's `user_id` equals the caller's `user_id`. Failures return `404 Not Found` (do not disclose existence to non-owners).
- Errors: JSON `{ "detail": "<message>" }`. Cosmos throttling/transient failures surface as `503` with a retry hint; secrets never appear in messages.

---

## 1. List my conversations

```
GET /api/conversations
```

Returns the authenticated user's conversations for the left chat pane, newest activity first. Single-partition query on `/user_id`.

**Query parameters** (optional):
| Name | Type | Default | Notes |
|------|------|---------|-------|
| `limit` | int | 50 | Max items to return (bounded, e.g. 1–200). |
| `cursor` | string | — | Opaque continuation token for paging (Cosmos continuation), if more than `limit`. |

**Response 200**:
```json
{
  "conversations": [
    {
      "id": "f1e2d3c4-...",
      "profileId": "chief-of-staff",
      "profileName": "Chief of Staff",
      "description": "Help me plan the offsite agenda",
      "createdAt": "2026-06-18T14:03:11Z",
      "lastActivityAt": "2026-06-18T14:25:02Z",
      "customAgentId": null,
      "usedBuiltInOverride": false,
      "baseProfileId": null,
      "overrideUpdatedAt": null
    }
  ],
  "nextCursor": null
}
```

**Status codes**: `200` OK · `401` unauthenticated · `503` Cosmos unavailable/throttled.

**Notes**: Returns only the caller's conversations. Cosmos is required — there is no in-memory fallback (the app fails fast at startup if Cosmos isn't configured; unit tests inject in-memory doubles).

---

## 2. Get one conversation's messages (for resume display)

```
GET /api/conversations/{id}/messages
```

Returns the stored messages of a conversation the caller owns, mapped to the chat view's `ChatMessage[]` shape. Ownership is verified against the index before reading the `chat-history` container.

**Path parameters**: `id` — conversation id (== session id).

**Response 200**:
```json
{
  "id": "f1e2d3c4-...",
  "profileId": "chief-of-staff",
  "profileName": "Chief of Staff",
  "messages": [
    { "role": "user", "content": "Help me plan the offsite agenda", "images": [] },
    {
      "role": "assistant",
      "content": "Here is a draft agenda...",
      "tool_invocations": [
        { "call_id": "call-1", "name": "get_user_profile", "arguments": "{}", "result": "{...}" }
      ],
      "usage": { "input_token_count": 150, "output_token_count": 60, "total_token_count": 210 }
    }
  ]
}
```

**Status codes**: `200` OK · `401` unauthenticated · `404` not found or not owned · `503` Cosmos unavailable.

**Notes**: Message mapping mirrors the streaming event shapes already produced by `streaming.py` (`text`, `function_call`, `function_result`, `usage`), so resumed conversations render identically to live ones. Tool-internal/excluded messages are not surfaced as separate chat bubbles.

---

## 3. Delete a conversation

```
DELETE /api/conversations/{id}
```

Deletes a conversation the caller owns: clears its messages from `chat-history` (provider `clear(session_id)`) and removes its `conversations` index document. Idempotent for the owner.

**Response**: `204 No Content`.

**Status codes**: `204` deleted · `401` unauthenticated · `404` not found or not owned · `503` Cosmos unavailable (partial failure is reported and retryable; see FR-018).

**Behavioral notes**:
- If the conversation being deleted is the active session, the frontend resets to a new/empty chat (edge case).
- Deletion order SHOULD clear messages first, then delete the index doc, so a retry after partial failure still resolves; the implementation must avoid an index entry that points at already-cleared messages without signaling the inconsistency.

---

## 4. Changed: Create / resume a session

The existing `POST /api/sessions` and `POST /api/sessions/{session_id}/messages` endpoints remain, with these contract changes:

### 4a. `POST /api/sessions` — create or resume

**New conversation** (no `conversation_id`): the backend generates a server-side `session_id` (UUID), creates the `conversations` index document bound to the caller's `user_id` and chosen profile, and returns the `session_id`.

**Resume existing** (request includes `conversation_id`): the backend verifies ownership of that id, rebuilds the `AgentSession` with the same `session_id`, and the `CosmosHistoryProvider` loads prior history automatically.

**Request body** (additions/removals relative to today):
| Field | Change | Notes |
|-------|--------|-------|
| `conversation_id` | NEW (optional) | When present → resume that conversation (ownership-checked). When absent → create new. |
| `history` | REMOVED | The client no longer supplies a serialized session/history blob; history lives in Cosmos. |
| `profile_id`, `custom_*`, `profile_override`, `mcp_servers`, `agents_as_tools`, `user_profile` | unchanged | Existing session-creation fields are preserved for new conversations. |

**Response**: existing shape (`session_id`, `profile_id`, `profile_name`, `tools_loaded`, `skills_loaded`, `agents_loaded`, `search_context`, `mcp_results`), where `session_id` is the conversation id usable with the conversations endpoints.

**Status codes**: `200`/`201` created or resumed · `401` unauthenticated · `404` resume id not found or not owned · `400` invalid profile/override · `503` Cosmos unavailable (when Cosmos is the configured store).

### 4b. `POST /api/sessions/{session_id}/messages` — send a message (unchanged transport)

- Transport, SSE event shapes (`text`, `function_call`, `function_result`, `usage`, `done`, `error`), text and multipart/image inputs are **unchanged** (FR-011).
- Side effect change: on stream completion (`done`), the backend (1) ensures the turn's messages are persisted to `chat-history` via the provider, (2) sets `title` from the first user message if not yet set, and (3) bumps `last_activity_at` on the index document.

### 4c. `GET /api/sessions/{session_id}/history` — deprecated for persistence

- This endpoint (previously used by the client to fetch the serializable session blob for localStorage) is no longer the persistence mechanism. It MAY be retained for diagnostics or removed; the frontend stops depending on it for saving conversations. The authoritative read path is `GET /api/conversations/{id}/messages`.

### 4d. `DELETE /api/sessions/{session_id}` — runtime cleanup only

- Continues to tear down the in-process runtime session. It does NOT delete persisted history (use `DELETE /api/conversations/{id}` for durable deletion). Ending a runtime session leaves the durable conversation intact for later resume.

---

## Authorization matrix

| Endpoint | Owner | Non-owner | Unauthenticated |
|----------|-------|-----------|-----------------|
| `GET /api/conversations` | own list only | own list only | `401` |
| `GET /api/conversations/{id}/messages` | `200` | `404` | `401` |
| `DELETE /api/conversations/{id}` | `204` | `404` | `401` |
| `POST /api/sessions` (resume) | `200` | `404` | `401` |

All non-owner access to a specific conversation returns `404` (never `403`) to avoid disclosing existence (FR-008).
