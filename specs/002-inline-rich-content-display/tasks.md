# Tasks: Inline Rich Content Display

**Input**: Design documents from `/specs/002-inline-rich-content-display/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/session-api.md, quickstart.md

**Tests**: Not explicitly requested in the feature spec. Omitted per template rules.

**Organization**: Tasks grouped by user story (US1: live image display, US2: history restoration).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Exact file paths included in descriptions

---

## Phase 1: Setup

**Purpose**: Switch to the Responses API client so the agent framework passes rich content through to the LLM instead of dropping it.

- [x] T001 Switch `OpenAIChatCompletionClient` to `OpenAIChatClient` import in agent_factory.py
- [x] T002 Update all type annotations and constructor calls from `OpenAIChatCompletionClient` to `OpenAIChatClient` in agent_factory.py
- [x] T003 Verify the app starts without errors and the warning `OpenAI Chat Completions API does not support rich content` no longer appears in logs

**Checkpoint**: Backend uses Responses API. Rich content in tool results flows to the LLM. No frontend changes yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define shared types and update the SSE transport layer so both user stories can use the same content pipeline.

**CRITICAL**: Both US1 and US2 depend on these types and the backend SSE change.

- [x] T004 [P] Add `ContentItem` type and update `SSEFunctionResultEvent` and `ToolInvocation` interfaces with optional `content_items` field in frontend/src/types/api.ts
- [x] T005 [P] Update `_stream_agent_response()` in main.py to extract image content items from `mcp_server_tool_result` output and include `content_items` array in the SSE `function_result` event payload
- [x] T006 [P] Add CSS styles for inline tool result images (max-width, border-radius, cursor) in frontend/src/styles/index.css

**Checkpoint**: Backend emits `content_items` in SSE events. Frontend types are ready. No rendering yet.

---

## Phase 3: User Story 1 - Live Image Display (Priority: P1) MVP

**Goal**: When a skill or MCP tool returns an image, display it inline in the chat immediately.

**Independent Test**: Invoke an MCP tool that returns an image; verify the image appears in the ToolStep accordion and inline in the chat message flow.

### Implementation for User Story 1

- [x] T007 [US1] Update `onFunctionResult` handler in frontend/src/hooks/useChat.ts to store `content_items` from SSE `function_result` events on the `ToolInvocation` object
- [x] T008 [US1] Update `ToolStep.tsx` to render images from `content_items` as `<img>` elements with base64 data URIs in the tool result accordion in frontend/src/components/ToolStep.tsx
- [x] T009 [US1] Update `ChatMessage.tsx` to display tool result images inline in the chat message flow (outside collapsed accordions) in frontend/src/components/ChatMessage.tsx

**Checkpoint**: Live image display works end-to-end. Images from MCP tool results appear in both the ToolStep accordion and inline in the chat.

---

## Phase 4: User Story 2 - History Image Restoration (Priority: P2)

**Goal**: When reviewing chat history, previously generated images are still visible.

**Independent Test**: Invoke a tool that returns an image, reload the page or switch conversations and back, verify the image is still displayed.

### Implementation for User Story 2

- [x] T010 [US2] Update `extractMessagesFromSessionData()` in frontend/src/hooks/useChat.ts to extract `type: "image"` content items from MCP `output` arrays and store them as `content_items` on restored `ToolInvocation` objects

**Checkpoint**: History restoration preserves images. Both US1 and US2 are complete.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Validation, error handling, and visual verification.

- [x] T011 [P] Add frontend MIME type validation — only render images with allowed types (`image/jpeg`, `image/png`, `image/gif`, `image/webp`) in frontend/src/components/ToolStep.tsx
- [x] T012 [P] Add graceful error handling for malformed image data (broken base64, missing fields) in frontend/src/components/ToolStep.tsx and frontend/src/components/ChatMessage.tsx
- [x] T013 Build frontend and run Visual Verification Protocol per Constitution — capture screenshots of chat with tool result images via Playwright

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (client swap must be done before testing SSE changes)
- **US1 (Phase 3)**: Depends on Phase 2 (types and SSE event format must exist)
- **US2 (Phase 4)**: Depends on Phase 2 (types must exist); independent of US1
- **Polish (Phase 5)**: Depends on US1 and US2 completion

### User Story Dependencies

- **US1 (P1)**: Depends on Foundational (Phase 2). No dependency on US2.
- **US2 (P2)**: Depends on Foundational (Phase 2). No dependency on US1. Can run in parallel with US1.

### Within Each Phase

- T001 → T002 → T003 (sequential — import before annotations before verify)
- T004, T005, T006 can all run in parallel (different files)
- T007 → T008 → T009 (hook must store data before components can render it)
- T010 standalone (different code path from US1)
- T011, T012 can run in parallel; T013 depends on all prior tasks

### Parallel Opportunities

```text
# Phase 2 — all three tasks touch different files:
T004 (api.ts) || T005 (main.py) || T006 (index.css)

# Phase 3 + Phase 4 — US1 and US2 can proceed in parallel after Phase 2:
US1: T007 → T008 → T009
US2: T010

# Phase 5 — validation tasks in parallel:
T011 (ToolStep.tsx) || T012 (ToolStep.tsx + ChatMessage.tsx)
T013 after all above
```

---

## Implementation Strategy

### MVP First (Phase 1 + 2 + 3)

1. Complete Phase 1: Swap to Responses API client
2. Complete Phase 2: Types + SSE + CSS
3. Complete Phase 3: US1 — Live image display
4. **STOP and VALIDATE**: Test with an MCP server that returns images
5. Deploy/demo if ready — users can see tool result images

### Incremental Delivery

1. Phase 1 + 2 → Backend and types ready
2. Add US1 → Live images work → Deploy (MVP!)
3. Add US2 → History images work → Deploy
4. Polish → Validation, error handling, visual verification → Deploy

---

## Notes

- `agent_factory.py` change is the critical enabler — without Responses API, the framework drops images before the LLM sees them
- `main.py` SSE change is the second critical piece — without `content_items`, the frontend never receives image data
- Frontend changes (T007-T010) are rendering-only — no new API calls
- No new dependencies needed — `OpenAIChatClient` is already in the installed `agent_framework_openai` package
- Azure OpenAI deployment must support the Responses API (`2025-03-01-preview` or later API version)
