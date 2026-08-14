# Contract: SSE Events

**Feature**: 016-agent-ui-pane

Extends the existing `text` / `function_call` / `function_result` / `usage` / `error` / `done`
stream produced by `streaming.stream_agent_response` and dispatched in
`frontend/src/api/client.ts`.

---

## New event: `agent_view`

Emitted when a `function_result` arrives for a `render_agent_view` call whose result reports
`status: "rendered"`. Emitted **after** the corresponding `function_result` so the transcript
marker and the pane update in a consistent order.

```text
event: agent_view
data: {"view_id":"0f1e...","title":"Readiness by unit","call_id":"call_abc","created_at":"2026-08-14T18:04:11.512Z"}
```

| Field | Type | Notes |
|---|---|---|
| `view_id` | string | Fetch key for `GET /api/sessions/{id}/views/{view_id}`. |
| `title` | string | Displayed immediately in the pane header and transcript marker. |
| `call_id` | string | Ties the view to its tool step so `ChatMessage` can render the marker in place. |
| `created_at` | ISO-8601 string | Ordering. |

**Deliberately absent**: `html`. Content is fetched over REST so the live path and the reload
path share one code path, and so SSE frames stay small (research.md D3).

**Client behavior** (`SSECallback.onAgentView`):

1. Append the metadata to the conversation's view list.
2. Fetch the view content; on success set it active and open the pane if it is not collapsed.
3. On fetch failure show a retry-able error in the pane — never break the chat stream (FR-015).

**Failure case**: when the tool returns `status: "rejected"` (oversize or invalid), **no**
`agent_view` event is emitted. The rejection is visible in the normal `function_result` tool step,
and the agent has an actionable result it can retry from.

---

## Unchanged events

`text`, `function_call`, `function_result`, `usage`, `error`, and `done` keep their current shapes.
A client that ignores `agent_view` continues to work exactly as today — the event is purely
additive, and `dispatchSSEEvent`'s `switch` already no-ops on unknown event names.
