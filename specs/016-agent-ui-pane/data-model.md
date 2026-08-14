# Phase 1 Data Model: Agent Dynamic UI Pane

**Feature**: 016-agent-ui-pane | **Date**: 2026-08-14

## Entity: Agent View

One agent-authored rendered unit, produced by a single `render_agent_view` tool call.

**Storage**: Cosmos container `agent-views`, partition key `/user_id`, document id = `view_id`.

| Field | Type | Notes |
|---|---|---|
| `id` (`view_id`) | string (uuid4) | Document id. Generated server-side; the agent never chooses it. |
| `user_id` | string | Partition key. The owning signed-in user (`AuthenticatedUser.user_id`). |
| `conversation_id` | string | Top-level (not nested in `data`) so listing is a partition-scoped query. Equals the session id. |
| `title` | string | Agent-supplied, trimmed, ≤ 120 chars. Shown in pane header and transcript marker. |
| `html` | string | Agent-authored markup. ≤ `MAX_AGENT_VIEW_CHARS` (default 250,000). Stored verbatim — never rewritten or sanitized. |
| `profile_id` | string | Rendering agent profile, recorded for audit. |
| `created_at` | ISO-8601 string | Sort key for ordering and FIFO eviction. |
| `chars` | int | Byte/char count at write time, for limit reporting and telemetry. |
| `source` | `"chat"` \| `"autonomous"` | Distinguishes interactive renders from unattended runs (FR-018). |

**Validation rules**:

- `title` MUST be non-empty after trimming; reject with a message the agent can act on.
- `html` MUST be non-empty and MUST NOT exceed `MAX_AGENT_VIEW_CHARS`; oversize is rejected
  (FR-014) and the tool returns `{"status": "rejected", "reason": "too_large", "limit": N}`.
- The document is immutable once written. A "revision" is a new view, which keeps the transcript
  markers honest about what was shown when.

**Lifecycle / state transitions**:

```text
(tool invoked) → validated → persisted → announced via SSE → rendered in pane
                     │
                     └── rejected (too_large | empty_title | empty_html) → no document written,
                         agent receives an actionable failure result
```

**Retention**: views are deleted with their conversation. `DELETE /api/conversations/{id}` must
also delete that conversation's views in the user's partition. When a conversation exceeds
`MAX_AGENT_VIEWS_PER_CONVERSATION` (default 50), the oldest view is evicted FIFO.

---

## Entity: View Data Request

A single brokered data request that originated inside a rendered view. **Not persisted as its own
document** — it is an audit event on the existing tool-trace surfaces (see research.md D7).

| Field | Type | Notes |
|---|---|---|
| `request_id` | string | Client-generated correlation id for the postMessage round trip. |
| `view_id` | string | The view that issued the request. |
| `conversation_id` | string | Session/conversation scope. |
| `user_id` | string | Always the authenticated caller — never taken from the request body. |
| `tool` | string | Requested tool name. |
| `arguments` | object | JSON object; non-object payloads are rejected. |
| `outcome` | `fulfilled` \| `refused` \| `failed` | `refused` covers permission and validation denials. |
| `refusal_reason` | string \| null | `not_permitted`, `invalid_arguments`, `session_inactive`, `rate_limited`, `not_owner`. |
| `duration_ms` | int | Recorded for the SC-004 latency target. |

**Validation rules** (all server-side, before any tool executes):

1. Caller is authenticated; `user_id` comes from the bearer token only.
2. Caller owns `conversation_id` (`ConversationIndexRepository.get_owned`).
3. `view_id` exists in the caller's partition and belongs to `conversation_id`.
4. The session is live in `_sessions`; otherwise `409 session_inactive`.
5. `tool` resolves to a callable in `SessionData.tools`; otherwise `403 not_permitted`.
6. `tool` is not `render_agent_view` (no recursive self-render).
7. `arguments` is a JSON object within the argument-count and size bounds.
8. The session's broker budget is not exhausted; otherwise `429 rate_limited`.
9. The response is truncated to `MAX_VIEW_DATA_RESPONSE_CHARS` with a `truncated: true` flag.

---

## Entity: UI Capability Grant

Not a stored entity — it is the presence of `render_agent_view` in a profile's `tools:` list in
`config/agents.yaml`, or in a user's custom agent definition. This reuses the existing per-agent
tool allow-list, so no new permission model, schema, or admin surface is introduced (FR-001,
Constitution II).

**Derived behavior**:

- Absent from the list → the tool is never instantiated → the agent cannot render (FR-001), and
  the broker rejects every request for that session because the render tool was never granted.
- Present → the tool appears in the existing tool inventory, so the capabilities bar reflects it
  with no bespoke wiring (FR-019).

---

## Entity: Pane State

Client-side presentation state. **Deliberately not stored server-side** (research.md D8).

| Field | Type | Notes |
|---|---|---|
| `open` | boolean | Pane visible vs collapsed. |
| `width` | number (px) | Clamped to `[320, 720]` on wide viewports; ignored below 900 px. |
| `activeViewId` | string \| null | Defaults to the newest view for the conversation (FR-012). |

**Storage**: `localStorage`, keyed `agentViewPane:{conversation_id}`. Missing or malformed entries
fall back to `{open: true, width: 480, activeViewId: newest}`.

---

## Relationships

```text
User (1) ──< AgentView (many)          partition boundary; enforces FR-017
Conversation (1) ──< AgentView (many)  capped at MAX_AGENT_VIEWS_PER_CONVERSATION, FIFO
AgentView (1) ──< ViewDataRequest (many, transient audit events)
AgentProfile (1) ──> UICapabilityGrant (0..1, expressed as a tools[] entry)
Conversation (1) ──> PaneState (1, client-only)
```

## Configuration Surface

| Variable | Default | Purpose |
|---|---|---|
| `MAX_AGENT_VIEW_CHARS` | `250000` | Largest single view accepted. |
| `MAX_AGENT_VIEWS_PER_CONVERSATION` | `50` | Retention cap; oldest evicted beyond it. |
| `MAX_VIEW_DATA_RESPONSE_CHARS` | `20000` | Backstop truncation for brokered responses. |
| `MAX_VIEW_DATA_REQUESTS_PER_MINUTE` | `60` | Per-session broker budget. |
| `AZURE_COSMOS_AGENT_VIEWS_CONTAINER` | `agent-views` | Container name override. |

All are read with the existing `_env_int` helper pattern so invalid values fall back to defaults
with a warning rather than failing startup.
