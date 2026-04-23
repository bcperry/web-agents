# Feature Spec: Inline Rich Content Display

**ID**: 002  
**Branch**: `002-inline-rich-content-display`  
**Date**: 2026-04-23  
**Status**: Draft

## Problem Statement

Skills and MCP servers can return rich content types (images, potentially other media) in their responses. Currently, the backend silently drops non-text content items from MCP tool results, and the frontend renders all tool results as plain text/JSON in `<pre>` blocks. Users cannot see images or other rich content that tools produce.

## Requirements

### Functional Requirements

1. **FR-1**: MCP server tool results containing `image` content items MUST be extracted and forwarded to the frontend via the existing SSE stream.
2. **FR-2**: Skill/tool results containing image data (base64-encoded) MUST be forwarded to the frontend.
3. **FR-3**: The frontend MUST render images inline within the tool step result display (expandable accordion in ToolStep component).
4. **FR-4**: Images from tool results MUST also be renderable inline in assistant message text when the LLM references them.
5. **FR-5**: Session history restoration MUST preserve and re-render rich content from tool results.
6. **FR-6**: The system MUST handle missing or malformed image data gracefully — no crashes or blank screens.

### Non-Functional Requirements

1. **NFR-1**: Base64 image payloads in SSE events MUST NOT exceed a reasonable size threshold to avoid browser memory issues. Large images should be served via a backend endpoint.
2. **NFR-2**: Image rendering MUST not block or delay text content streaming.
3. **NFR-3**: No credentials, tokens, or sensitive metadata may be embedded in image data URIs or image-serving endpoints.

## Scope

### In Scope

- Backend: Extract image content from MCP `mcp_server_tool_result` events
- Backend: Forward image data in SSE `function_result` events
- Frontend: Parse image data from `function_result` SSE events
- Frontend: Render images inline in ToolStep component
- Frontend: Render images inline in ChatMessage when referenced
- Frontend: Restore images from session history
- TypeScript types update for rich content in tool results

### Out of Scope

- Video, audio, or other non-image media types (future feature)
- Image editing or manipulation in the UI
- Image caching/CDN infrastructure
- Thumbnail generation or image resizing on the backend

## User Stories

- **US-1**: As a user, when I invoke a skill or MCP tool that generates an image (e.g., a chart, diagram, or screenshot), I want to see that image displayed inline in the chat so I can understand the result without leaving the interface.
- **US-2**: As a user, when I review my chat history, I want previously generated images to still be visible so I don't lose context.
