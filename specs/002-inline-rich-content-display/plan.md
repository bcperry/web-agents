# Implementation Plan: Inline Rich Content Display

**Branch**: `002-inline-rich-content-display` | **Date**: 2026-04-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-inline-rich-content-display/spec.md`

## Summary

MCP servers and skills can return rich content (images) in tool results, but the current pipeline silently drops non-text content items at two levels: (1) the agent framework's `OpenAIChatCompletionClient` strips rich content before sending to the LLM, and (2) the SSE stream handler in `main.py` only extracts text. This feature switches to the `OpenAIChatClient` (Responses API) so the LLM can see images in tool results, threads image data through the SSE stream via a new `content_items` array on `function_result` events, and renders images inline in the frontend — both within tool step accordions and in assistant message bodies.

## Technical Context

**Language/Version**: Python 3.12+ (backend), TypeScript (frontend)  
**Primary Dependencies**: FastAPI, React, agent-framework-core, agent-framework-azure-ai-search  
**Storage**: N/A (images are transient, passed through SSE stream)  
**Testing**: pytest (backend), npm test (frontend)  
**Target Platform**: Linux server (Azure App Service), modern browsers  
**Project Type**: Web application (two-tier: FastAPI backend + React SPA frontend)  
**Performance Goals**: SSE stream latency unaffected; images render within 1s of receipt  
**Constraints**: Base64 images in SSE events should be capped (~5MB encoded) to avoid browser memory issues; no credentials in data URIs  
**Scale/Scope**: Existing user base; touches ~6 files across backend and frontend

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Read-Only Data Access | **PASS** | No database changes. Feature is entirely in the message transport layer. |
| II. Single-File Agent Definitions | **PASS** | No changes to `agents.yaml` or agent definitions. |
| III. Security & Credential Hygiene | **PASS** | No credentials in image data URIs. Images are base64-encoded content from tool results, not user secrets. Backend validates content before forwarding. |
| IV. Evaluation-Driven Quality | **PASS** | No prompt or model changes. This is a transport/rendering feature. |
| V. Simplicity & Minimalism | **PASS** | Minimal changes: extend existing SSE event format, add image rendering to existing components. No new abstractions or services. |
| VI. Infrastructure as Code | **PASS** | No infrastructure changes. |
| VII. Two-Tier API-First Architecture | **PASS** | Backend extracts and forwards image data via existing SSE API. Frontend renders it. No direct Azure service calls from frontend. |
| Visual Verification Protocol | **APPLIES** | Frontend rendering changes require Playwright screenshots. |

**Gate result: PASS** — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/002-inline-rich-content-display/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── session-api.md   # SSE event contract changes
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
# Backend (repository root)
agent_factory.py                  # Switch OpenAIChatCompletionClient → OpenAIChatClient (Responses API)
main.py                           # SSE stream — extract image content from MCP results
mcp_servers.py                    # (read-only reference, no changes expected)

# Frontend
frontend/src/
├── types/
│   └── api.ts                    # Add rich content types to ToolInvocation & SSE events
├── api/
│   └── client.ts                 # Parse structured content in function_result events
├── hooks/
│   └── useChat.ts                # Handle rich content in onFunctionResult + history restore
├── components/
│   ├── ChatMessage.tsx           # Render inline images in assistant messages
│   └── ToolStep.tsx              # Render images in tool result accordion
└── styles/
    └── index.css                 # Image display styles (if needed)

# Tests
tests/
└── test_api.py                   # Test SSE image content forwarding
```

**Structure Decision**: Existing two-tier web application structure. Backend changes are in `agent_factory.py` (client swap) and `main.py` (SSE streaming logic). Frontend changes span types, API client, hooks, and two rendering components. No new files or directories needed beyond spec artifacts.

## Complexity Tracking

No constitution violations — this section is not applicable.
