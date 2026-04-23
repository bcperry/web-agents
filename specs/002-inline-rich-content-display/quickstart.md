# Quickstart: Inline Rich Content Display

**Feature**: 002-inline-rich-content-display  
**Branch**: `002-inline-rich-content-display`

## Overview

This feature enables images from MCP server and skill tool results to display inline in the chat UI. Currently, only text content from tool results is shown — images are silently dropped.

## Architecture Summary

The change touches 6 files across the backend and frontend:

1. **Backend** (`main.py`): Extract image content items from MCP tool results and include them in the SSE `function_result` event as a new `content_items` array.
2. **Frontend types** (`api.ts`): Add `ContentItem` type and `content_items` field to `ToolInvocation` and `SSEFunctionResultEvent`.
3. **Frontend API** (`client.ts`): No changes needed (SSE parser already handles arbitrary JSON fields).
4. **Frontend hook** (`useChat.ts`): Store `content_items` from SSE events; extract them from session history.
5. **Frontend rendering** (`ToolStep.tsx`): Render images as `<img>` tags with data URIs in tool result accordion.
6. **Frontend rendering** (`ChatMessage.tsx`): Show tool result images inline in the chat flow.

## Key Decisions

- **Inline base64**: Images embedded directly in SSE events as base64 data URIs. No separate image endpoint.
- **Backwards compatible**: `result` string field unchanged. New `content_items` array is optional.
- **Frontend validation**: MIME type checked against allowlist before rendering.

## Testing Strategy

- **Backend**: Add test for SSE `function_result` event with image content items.
- **Frontend**: Visual verification via Playwright screenshots per Constitution.
- **Manual**: Use an MCP server that returns images to verify end-to-end.

## Dependencies

No new dependencies. Uses existing React, base64, and SSE infrastructure.
