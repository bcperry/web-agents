# SSE API Contract Changes: Inline Rich Content

**Feature**: 002-inline-rich-content-display  
**Date**: 2026-04-23

## Modified SSE Event: `function_result`

### Before (current)

```
event: function_result
data: {"call_id": "call_123", "result": "Query returned 5 rows:\n...", "arguments": "{\"query\": \"SELECT ...\"}"}
```

- `result` is always a plain string (text only)
- Image content from MCP results is silently dropped

### After (proposed)

```
event: function_result
data: {"call_id": "call_123", "result": "Generated chart:", "arguments": "{...}", "content_items": [{"type": "text", "text": "Generated chart:"}, {"type": "image", "data": "iVBORw0KGgo...", "mimeType": "image/png"}]}
```

- `result` remains a string containing only text parts (backwards compatible)
- `content_items` is a new optional array containing all structured content

### Field Changes

| Field | Change | Type | Description |
|-------|--------|------|-------------|
| `call_id` | Unchanged | `string` | Tool invocation identifier |
| `result` | Unchanged semantics | `string` | Text-only rendering of result (for backwards compat) |
| `arguments` | Unchanged | `string?` | Serialized tool arguments |
| `content_items` | **NEW** | `ContentItem[]?` | Structured content items; present when result contains non-text content |

### ContentItem Schema

```typescript
type ContentItem =
  | { type: "text"; text: string }
  | { type: "image"; data: string; mimeType: string };
```

### When `content_items` is included

- **Always** when the tool result is a list of MCP content items (i.e., `mcp_server_tool_result`)
- **Not included** for regular `function_result` (native tool calls) that return plain text, unless the result contains structured content

### Client behavior

1. If `content_items` is present and non-empty → use it for rendering
2. Otherwise → fall back to `result` string (existing behavior)
3. Unknown `type` values in `content_items` → skip silently (forward compatible)

## Modified REST Endpoint: `GET /api/sessions/{session_id}/history`

### No backend changes needed

The history endpoint returns `session_data.agent_session.to_dict()` which already preserves the full MCP `output` list including image content items. The change is purely in the **frontend** parsing of history data.

### Frontend history extraction changes

`extractMessagesFromSessionData()` currently filters MCP output to text-only. It must be updated to:
1. Extract `type: "image"` items alongside `type: "text"` items
2. Store them as `content_items` on the `ToolInvocation` object
3. Use the same rendering path as live SSE `function_result` events

## Allowed Image MIME Types

Frontend must validate `mimeType` before rendering:

```
image/jpeg
image/png
image/gif
image/webp
```

Unknown MIME types → skip the image item (do not render).
