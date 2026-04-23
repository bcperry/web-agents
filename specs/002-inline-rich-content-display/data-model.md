# Data Model: Inline Rich Content Display

**Feature**: 002-inline-rich-content-display  
**Date**: 2026-04-23

## Entities

### ContentItem (new — shared concept between backend SSE and frontend types)

Represents a single content item within a tool/MCP result. Discriminated union on `type`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"text" \| "image"` | Yes | Content type discriminator |
| `text` | `string` | If type=text | Text content |
| `data` | `string` | If type=image | Base64-encoded image data |
| `mimeType` | `string` | If type=image | MIME type (e.g., `image/png`) |

**Validation rules**:
- `type` must be `"text"` or `"image"` (future types ignored by frontend)
- For `image` items: `mimeType` must be one of `image/jpeg`, `image/png`, `image/gif`, `image/webp`
- For `image` items: `data` must be non-empty base64 string

### SSEFunctionResultEvent (modified)

Existing SSE event payload, extended with optional `content_items`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `call_id` | `string` | Yes | Tool call ID |
| `result` | `string` | Yes | Text-only result (backwards compat) |
| `arguments` | `string` | No | Serialized tool arguments |
| `content_items` | `ContentItem[]` | No | Structured content including images |

**Backwards compatibility**: If `content_items` is absent, clients use `result` string (existing behavior). If present, clients prefer `content_items` for rendering.

### ToolInvocation (modified)

Frontend type representing a completed tool call.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `call_id` | `string` | Yes | Tool call ID |
| `name` | `string` | Yes | Tool function name |
| `arguments` | `string` | No | Serialized arguments |
| `result` | `string` | No | Text-only result string |
| `content_items` | `ContentItem[]` | No | Structured content items |

### ImageData (existing — unchanged)

Used for user-uploaded images. No changes needed.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `filename` | `string` | Yes | Original filename |
| `media_type` | `string` | Yes | MIME type |
| `data` | `string` | Yes | Base64-encoded data |

## Relationships

```
ChatMessage 1 ──→ * ToolInvocation (tool_invocations array)
ToolInvocation 1 ──→ * ContentItem (content_items array, optional)
ContentItem ──discriminated on type──→ TextContent | ImageContent
```

## State Transitions

No stateful entities. Content items are immutable once received via SSE and stored in the conversation state.

## Data Flow

```
MCP Server → agent_framework (mcp_server_tool_result with output[])
  → main.py _stream_agent_response() extracts ContentItem[]
    → SSE function_result event with content_items[]
      → client.ts parses and dispatches
        → useChat.ts stores in ToolInvocation.content_items
          → ToolStep.tsx renders images + text
          → ChatMessage.tsx optionally shows images inline
```
