# Research: Inline Rich Content Display

**Feature**: 002-inline-rich-content-display  
**Date**: 2026-04-23

## Research Tasks & Findings

### RT-1: MCP Image Content Format

**Question**: What format do MCP servers use to return image content?

**Finding**: MCP tool results arrive as `mcp_server_tool_result` content items. The `output` field is a list of content dicts, each with a `type` discriminator:

```json
{
  "type": "mcp_server_tool_result",
  "call_id": "call_123",
  "output": [
    {"type": "text", "text": "Generated chart:"},
    {"type": "image", "data": "iVBOR...base64...", "mimeType": "image/png"}
  ]
}
```

Image content items have: `type: "image"`, `data` (base64 string), `mimeType` (e.g., `"image/png"`).

**Decision**: Use the MCP protocol's native `image` content type as the source format. No transformation needed at the MCP layer.

### RT-2: Current Content Extraction Gap

**Question**: Where exactly are images being dropped?

**Finding**: Two locations silently discard non-text content:

1. **Backend** (`main.py` ~L414-425): When processing `mcp_server_tool_result`, only items with `type == "text"` are extracted. Image items are filtered out. The SSE `function_result` event only sends a plain string `result` field.

2. **Frontend history** (`useChat.ts` ~L406-478): `extractMessagesFromSessionData()` applies the same text-only filter when restoring from session history.

**Decision**: Both locations must be updated to preserve and forward image content items.

### RT-3: SSE Transport for Image Data

**Question**: Should images be embedded inline in SSE events (base64) or served via a separate endpoint?

**Alternatives considered**:
- **Option A: Inline base64 in SSE events** — Simple, no new endpoints, works with existing streaming infrastructure. Adds payload size to SSE stream.
- **Option B: Backend image endpoint** — Images served via `/api/sessions/{id}/images/{image_id}`. Requires storage, URL management, cleanup. More complex.
- **Option C: Hybrid** — Small images inline, large images via endpoint.

**Decision**: **Option A (inline base64)**. Rationale:
- SSE serialization uses `json.dumps` with no chunking — base64 is JSON-safe.
- MCP images are typically small (charts, diagrams, screenshots) — base64 is < 5MB.
- No new endpoints, no storage, no cleanup — aligns with Constitution Principle V (Simplicity).
- The frontend SSE parser has no size limits on individual events.
- If future needs require large images, Option C can be added later (YAGNI).

### RT-4: SSE Event Payload Design

**Question**: How should the `function_result` SSE event carry image data?

**Alternatives considered**:
- **Option A: Add `images` array alongside `result` string** — Backwards compatible, existing clients ignore unknown fields.
- **Option B: Replace `result` with a structured `content` array** — Breaking change to the SSE contract, but more expressive.
- **Option C: Separate `function_image` SSE event type** — New event type for image content only.

**Decision**: **Option A (add `content_items` array)**. Rationale:
- `result` string remains for text content — existing behavior unchanged.
- New `content_items` array carries structured content (text + image items).
- Frontend can check for `content_items` first, fall back to `result` string for backwards compatibility.
- No breaking changes to the SSE protocol.

### RT-5: Frontend Rendering Strategy

**Question**: How should images be rendered in the ToolStep and ChatMessage components?

**Finding**: 
- `ToolStep.tsx` currently renders result as `<pre>` JSON. Images should render as `<img>` tags with base64 data URIs below the text content.
- `ChatMessage.tsx` renders assistant text via `<ReactMarkdown>`. When the LLM outputs markdown image references, standard markdown `![alt](data:...)` can work, but it's more reliable to detect tool invocations with images and display them alongside the tool step.

**Decision**: 
- Primary image display: In `ToolStep.tsx` within the expandable accordion, images render as `<img>` elements with `data:{mimeType};base64,{data}` URIs.
- Secondary: Images from the most recent tool result also shown inline in the chat message flow (outside the collapsed accordion) so they're immediately visible.
- Use `ALLOWED_IMAGE_MIMES` validation on the frontend to prevent rendering non-image content.

### RT-6: Session History Image Preservation

**Question**: Are images already persisted in session history?

**Finding**: Yes. The `agent_session.to_dict()` call preserves the full MCP `output` list including image content items. The data is already available — the frontend's `extractMessagesFromSessionData()` just needs to extract it instead of filtering it out.

**Decision**: Update `extractMessagesFromSessionData()` to extract image items alongside text. No backend history changes needed.

### RT-7: Size/Security Considerations

**Question**: What validation is needed for image content from tool results?

**Finding**: User-uploaded images go through extensive validation (magic bytes, MIME type, size limits). Tool/MCP result images come from the agent framework, which is a trusted source (the backend controls which MCP servers and tools are available).

**Decision**: 
- Frontend: Validate `mimeType` against allowed types before rendering (defense in depth).
- Frontend: Set `max-width`/`max-height` CSS to prevent layout blowout from large images.
- Backend: No additional validation beyond what the agent framework provides — the MCP servers are configured by the admin in `agents.yaml`.
- No credential/token leakage risk: images are raw pixel data, not URLs requiring auth.

### RT-8: Responses API Client for Rich Tool Results

**Question**: The agent framework logs `WARNING:agent_framework.openai:OpenAI Chat Completions API does not support rich content (images, audio) in tool results. Rich content items will be omitted. Use the Responses API client for rich tool results.` — what is the Responses API client and can we use it?

**Finding**: The `agent_framework_openai` package (v1.0.1) exports two client families:

| Chat Completions API | Responses API |
|---|---|
| `OpenAIChatCompletionClient` (current) | `OpenAIChatClient` |

Key differences:
- `OpenAIChatClient` sets `SUPPORTS_RICH_FUNCTION_OUTPUT = True` — images/audio in tool results are **passed through** to the LLM, not dropped.
- Uses the Responses API endpoint (`/responses`) instead of Chat Completions (`/chat/completions`).
- Constructor is **signature-compatible** — same env-var auto-detection, same parameters.
- `as_agent()` method works identically (inherited from shared `BaseChatClient`).
- Default Azure API version is `"preview"` (maps to latest) instead of `"2024-12-01-preview"`.

The swap is a drop-in replacement in `agent_factory.py`:
1. Change import: `OpenAIChatCompletionClient` → `OpenAIChatClient`
2. Change all type annotations (6 occurrences)
3. Change constructor calls (2 occurrences)

**Risk**: Azure OpenAI deployment must support the Responses API (requires `2025-03-01-preview` or later API version). This should be verified before deploying.

**Decision**: **Switch to `OpenAIChatClient`**. Rationale:
- Eliminates the warning about dropped rich content.
- Enables the LLM to actually see and reason about image tool results (not just the text parts).
- Drop-in replacement with no structural code changes.
- Required for the feature to work end-to-end — without this, the LLM never sees the images even if we forward them to the frontend.
