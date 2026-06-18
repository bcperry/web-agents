# Feature Specification: Azure Cosmos DB Agent Memory Layer

**Feature Branch**: `011-cosmos-agent-memory`  
**Created**: 2026-06-18  
**Status**: Draft  
**Input**: User description: "I need to add cosmosdb to this as the agent's memory layer. take your time reading the docs for Agent Framework. this should be a seamless integration. the agents will need a per-user/per agent chat history. the chat pane on the left side will need to read the ACTUAL chats from Cosmos instead of browser storage."

## Overview

Today, conversation history lives in the browser's `localStorage`: the left chat pane lists at most a handful of conversations stored per-browser, and the agent's "memory" is a serialized session blob that the client round-trips back to the backend on every resume. This is fragile (cleared with browser cache), siloed per device, capped in count, and places conversation state in the client tier.

This feature moves conversation memory to **Azure Cosmos DB** as the server-side source of truth, integrated through Microsoft Agent Framework's `CosmosHistoryProvider`. Each conversation gets **per-user and per-agent** persistent history. The left chat pane reads the user's **actual** conversations from Cosmos through the backend API instead of from browser storage.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent Remembers a Conversation Across Turns and Restarts (Priority: P1)

As a user chatting with an agent, I want the agent to remember everything said earlier in the conversation — even after the server restarts or I return later — so the assistant maintains continuity without me re-supplying context.

**Why this priority**: Persistent agent memory is the core of the feature. Without server-side history, every other capability (listing, resuming, isolation) has nothing durable to read.

**Independent Test**: Start a conversation, tell the agent a fact, restart the backend process, send a follow-up that depends on the earlier fact, and confirm the agent recalls it. History is read back from Cosmos, not from any client-supplied blob.

**Acceptance Scenarios**:

1. **Given** a user has exchanged several turns with an agent, **When** they send another message, **Then** the agent's response reflects awareness of all prior turns in that conversation.
2. **Given** the backend process is restarted after a conversation, **When** the user resumes the same conversation and sends a message, **Then** the agent still has the full prior history available as context.
3. **Given** a message is sent, **When** the turn completes, **Then** the user and assistant messages for that turn are durably stored in Cosmos under that conversation.

---

### User Story 2 - Left Chat Pane Lists My Real Conversations (Priority: P1)

As an authenticated user, I want the left chat pane to show my actual past conversations retrieved from the server, so I see a complete, durable history that follows me across browsers and devices rather than a per-browser cache.

**Why this priority**: The user explicitly requires the chat pane to read real chats from Cosmos instead of browser storage. This is the primary visible behavior change.

**Independent Test**: Sign in, hold conversations, then open the app in a different browser/device (same account) and confirm the same conversation list appears, ordered by most recent activity, sourced from the backend API.

**Acceptance Scenarios**:

1. **Given** a signed-in user with prior conversations, **When** the chat pane loads, **Then** it displays their conversations retrieved from the backend (not from `localStorage`), each showing a title/description, the agent used, and last-activity time.
2. **Given** the same user signs in from a different browser or device, **When** the chat pane loads, **Then** it shows the same conversation list.
3. **Given** a brand-new user with no history, **When** the chat pane loads, **Then** it shows an empty state without errors.
4. **Given** the conversation list is loading or temporarily unavailable, **When** the pane renders, **Then** it shows a clear loading or error state instead of stale browser data.

---

### User Story 3 - Resume a Past Conversation With Full History (Priority: P1)

As a user, I want to click a conversation in the left pane and continue exactly where I left off, with the previous messages displayed and the agent retaining their context.

**Why this priority**: Listing conversations is only useful if they can be reopened. Resume ties the index (US2) to the memory (US1).

**Independent Test**: Select a past conversation, confirm its messages render in the chat view, send a new message that depends on earlier context, and confirm the agent responds with full awareness.

**Acceptance Scenarios**:

1. **Given** a user selects a past conversation, **When** it opens, **Then** the prior messages for that conversation are displayed in order, retrieved from the server.
2. **Given** a resumed conversation, **When** the user sends a new message, **Then** the agent has the prior history as context and the new turn is appended to the same stored conversation.
3. **Given** a resumed conversation that used a particular agent, **When** it reopens, **Then** it continues with that same agent identity.

---

### User Story 4 - My Conversations Are Private to Me (Priority: P1)

As an authenticated user, I want my conversation history to be accessible only to me, so no other user can list, read, resume, or delete my chats.

**Why this priority**: This is a security-sensitive, multi-user, government-context application. Per-user isolation is non-negotiable and must be enforced server-side.

**Independent Test**: As user A, create a conversation and note its identifier. As user B, attempt to fetch, resume, and delete that identifier via the API and confirm every attempt is denied.

**Acceptance Scenarios**:

1. **Given** a conversation owned by user A, **When** user B requests its messages, **Then** the request is denied and no content is returned.
2. **Given** a conversation owned by user A, **When** user B attempts to resume or delete it, **Then** the request is denied and the conversation is unchanged.
3. **Given** the conversation list endpoint, **When** any authenticated user calls it, **Then** only conversations owned by that user are returned.
4. **Given** an unauthenticated caller, **When** they call any conversation endpoint, **Then** access is rejected (outside local development).

---

### User Story 5 - Delete a Conversation (Priority: P2)

As a user, I want to delete a conversation so it is removed from my history and its stored messages no longer persist.

**Why this priority**: Users need control over their own data; deletion is a standard expectation and a data-hygiene requirement, but it depends on listing/ownership existing first.

**Independent Test**: Delete a conversation from the left pane, confirm it disappears from the list, and confirm a subsequent attempt to fetch its messages returns nothing.

**Acceptance Scenarios**:

1. **Given** a user deletes one of their conversations, **When** the chat pane refreshes, **Then** the conversation no longer appears in the list.
2. **Given** a deleted conversation, **When** anyone attempts to retrieve its messages, **Then** no messages are returned.
3. **Given** a user attempts to delete a conversation they do not own, **When** the request is processed, **Then** it is denied.

---

### User Story 6 - Works Locally With the Cosmos Emulator (Priority: P3)

As a developer, I want local development and tests to use the Azure Cosmos DB Emulator (not a cloud account), so iteration stays fast and cost-free while behaving exactly like production — with no silent non-durable fallback.

**Why this priority**: Developer experience and testability matter, but the production behavior (P1) is what delivers user value.

**Independent Test**: Run the Cosmos emulator locally and confirm the backend starts and persists durably; with no Cosmos configured at all, confirm the backend FAILS to start (no in-memory fallback). Run the unit suite and confirm conversation/memory behavior is validated with in-memory doubles, and the emulator integration suite passes against the running emulator.

**Acceptance Scenarios**:

1. **Given** the Cosmos emulator is running and `AZURE_COSMOS_ENDPOINT` points at it, **When** the backend starts, **Then** it starts successfully and chat history persists durably (same behavior as production).
2. **Given** no Cosmos is configured (`AZURE_COSMOS_ENDPOINT` unset), **When** the backend starts, **Then** it FAILS fast with a clear error — there is no non-durable in-memory fallback.
3. **Given** the automated unit suite, **When** it runs, **Then** conversation listing, resume, isolation, and deletion behaviors are covered using in-memory Cosmos doubles, with no live cloud dependency.
4. **Given** the local Azure Cosmos DB Emulator is running, **When** the `emulator`-marked integration suite runs against it, **Then** persistence, ownership, resume, and deletion are verified against the real provider and containers; **When** the emulator is not running, **Then** those tests are deselected/skipped and the default unit suite still passes.

### Edge Cases

- A conversation has no messages yet (created but the first message failed or was abandoned): the index entry must not show a broken title and must not error the list view.
- A very long first message: the derived conversation title must be truncated/wrapped without layout overflow in the chat pane.
- Cosmos is temporarily unavailable or rate-limited (429): message send and list operations must surface a clear, retryable error and must not corrupt or partially persist a turn.
- The authenticated user identifier is missing from the token: conversation endpoints must reject the request rather than fall back to a shared or empty partition.
- A conversation identifier that does not exist or is not owned by the caller: requests must be denied/return not-found without revealing whether the identifier exists for another user.
- Concurrent sends in the same conversation: stored message ordering must remain consistent and readable.
- Existing browser-stored conversations from before this feature: the system must not crash on their presence; their handling (ignored vs. one-time import) is a defined, documented behavior.
- Deleting a conversation while it is the active session: the active view must handle the removal gracefully (e.g., return to a new/empty chat).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST persist agent conversation messages (user and assistant turns, including tool interactions that are part of history) to Azure Cosmos DB as the server-side source of truth, via Agent Framework's Cosmos history provider.
- **FR-002**: Each conversation MUST be associated with the authenticated user who owns it and with the agent/profile used, enabling per-user and per-agent history.
- **FR-003**: The agent MUST load a conversation's prior history from Cosmos when continuing or resuming that conversation, so responses reflect full prior context without the client supplying the history.
- **FR-004**: The system MUST expose a backend API for the left chat pane to list the authenticated user's conversations, returning at minimum a conversation identifier, title/description, agent/profile name, and last-activity timestamp, ordered by most recent activity.
- **FR-005**: The system MUST expose a backend API to retrieve the messages of a single conversation owned by the authenticated user, for display when resuming.
- **FR-006**: The system MUST expose a backend API to delete a conversation owned by the authenticated user, removing both its index entry and its stored messages.
- **FR-007**: The frontend left chat pane MUST source its conversation list and message history from the backend API and MUST NOT rely on browser storage as the source of truth for conversation history.
- **FR-008**: The system MUST enforce ownership on every conversation read, resume, and delete operation, so a user can only access conversations they own; cross-user access MUST be denied.
- **FR-009**: Conversation identifiers used as storage keys MUST be unguessable (e.g., random identifiers) so they cannot be enumerated by other users.
- **FR-010**: The system MUST derive and store a human-readable conversation title/description (e.g., from the first user message) and MUST update the conversation's last-activity timestamp as the conversation progresses.
- **FR-011**: The system MUST continue to support sending messages, streaming responses, tool invocations, and image inputs exactly as today; adding Cosmos memory MUST NOT regress existing chat behavior.
- **FR-012**: The frontend MUST NOT communicate with Azure Cosmos DB directly; all Cosmos access MUST be proxied through the backend.
- **FR-013**: In production, backend access to Cosmos DB MUST authenticate via Azure Managed Identity (RBAC data-plane role); account keys MUST be permitted only for local development.
- **FR-014**: All Cosmos DB endpoints MUST target the Azure Government cloud in production deployments.
- **FR-015**: The Cosmos DB account, database, and containers MUST be provisioned through the project's Terraform infrastructure as code, including the data-plane role assignment for the application's managed identity.
- **FR-016**: The system MUST require Azure Cosmos DB and MUST NOT provide a non-durable in-memory fallback: locally it runs against the Cosmos emulator, when deployed it uses the real account, and if Cosmos is not configured the backend MUST fail fast at startup. Automated unit tests MAY substitute in-memory test doubles for the Cosmos data path so they run without a live account.
- **FR-017**: Cosmos credentials, connection strings, and keys MUST never appear in logs, API responses, or the frontend bundle.
- **FR-018**: When Cosmos operations fail (e.g., throttling or transient errors), the system MUST surface a clear, retryable error to the user and MUST avoid leaving a conversation turn partially persisted in an inconsistent state.
- **FR-019**: The behavior for conversations previously stored only in the browser MUST be explicitly defined (ignored or one-time imported) and MUST NOT cause errors when present.
- **FR-020**: New backend dependencies MUST be added via `uv` (the Cosmos history provider package), consistent with project package-management rules.

### Key Entities *(include if feature involves data)*

- **Conversation (Index Entry)**: Represents one chat thread owned by a user. Key attributes: conversation identifier (also the session identifier), owning user identifier, agent/profile identifier and display name, derived title/description, creation time, last-activity time, and any custom-agent/override descriptors needed to reopen with the same agent. Partitioned per user for efficient per-user listing and isolation.
- **Conversation Message**: Represents a single stored message within a conversation (role, content, and associated tool/usage metadata that constitutes history). Partitioned per conversation/session for efficient in-conversation reads and ordered by a sort key. Managed by the Agent Framework history provider.
- **Authenticated User**: The identity (stable user identifier from the auth token) that owns conversations and scopes all reads/writes. Already established by the existing authentication layer.
- **Session**: The runtime conversation context bound to a conversation identifier; on resume it is reconstructed with the same identifier so history loads from Cosmos.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a backend restart, resuming a conversation and asking about an earlier detail yields a correct, context-aware answer in 100% of manual verification attempts (memory survives process restarts).
- **SC-002**: The same signed-in user sees an identical conversation list across at least two different browsers/devices, confirming server-sourced history (0% reliance on per-browser storage for the list).
- **SC-003**: In cross-user access tests, 100% of attempts by a non-owner to list, read, resume, or delete another user's conversation are denied.
- **SC-004**: Conversation count per user is no longer capped at the previous browser limit; a user can accumulate and retrieve well beyond the prior cap (e.g., dozens of conversations) and still see them all listed.
- **SC-005**: Deleting a conversation removes it from the list and makes its messages unretrievable in 100% of attempts.
- **SC-006**: The application starts and supports chat locally with no cloud Cosmos account configured; the offline unit suite passes without any Cosmos dependency, and the integration suite passes against the local Azure Cosmos DB Emulator (covering list, resume, isolation, delete) — both without a live cloud dependency.
- **SC-007**: No Cosmos key, connection string, or credential appears in any log line, API response, or the built frontend bundle (verified by inspection).
- **SC-008**: Frontend build/type-check completes successfully, and visual verification screenshots of the chat pane (loading, populated list, empty state, resumed conversation) show no clipping or overflow at desktop, tablet, and mobile widths.

## Assumptions

- The existing authentication layer provides a stable per-user identifier (object id) suitable for use as the ownership/partition key; multi-user isolation relies on it.
- One conversation maps to exactly one agent/profile; switching agents starts a new conversation (consistent with current behavior).
- The conversation title is derived from the first user message (consistent with current behavior), not separately user-edited, unless a rename capability is later prioritized.
- Cosmos DB SQL (NoSQL) API is used, matching the Agent Framework Cosmos history provider.
- Auth token storage (`auth_token`) and UI preferences (theme) may remain in browser storage; only conversation history is migrated to the server.

## Out of Scope

- Full-text or semantic search across conversation history (no vector/search index in this feature).
- Cross-agent shared memory or a global long-term memory store beyond per-conversation history.
- User-initiated conversation renaming, tagging, pinning, or folders (potential future enhancement).
- Workflow checkpoint storage (the Cosmos checkpoint storage capability is a separate concern, not required here).
- Bulk migration of large volumes of pre-existing browser conversations beyond the defined handling in FR-019.
