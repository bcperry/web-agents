# Phase 1 Data Model: Azure Cosmos DB Agent Memory Layer

**Feature**: `011-cosmos-agent-memory` | **Date**: 2026-06-18 | **Plan**: [plan.md](plan.md)

This document defines the Azure Cosmos DB storage model, the document schemas, partition strategy, and the lifecycle/validation rules that satisfy the spec's functional requirements. Cosmos DB for NoSQL (SQL API) is used.

## Storage topology

```text
Cosmos DB account (NoSQL API, serverless, Azure Government: *.documents.azure.us)
└── database: agent-memory                # AZURE_COSMOS_DATABASE_NAME
    ├── container: chat-history           # AZURE_COSMOS_CONTAINER_NAME — messages
    │     partition key: /session_id
    │     owner: agent_framework CosmosHistoryProvider
    └── container: conversations          # per-user conversation index
          partition key: /user_id
          owner: backend cosmos_memory.py (ConversationIndexRepository)
```

- **One database, two containers.** Each container has a single, distinct access pattern (see [research.md](research.md) R4).
- The `chat-history` container schema is owned by the Agent Framework provider; the application treats it as managed storage and never writes message documents by hand. The application reads it only through the provider (e.g., `get_messages`, `clear`).
- The `conversations` container is owned and shaped entirely by application code.

---

## Entity 1 — Conversation Message (`chat-history` container)

Represents a single persisted message in a conversation. **Managed by `CosmosHistoryProvider`** — schema shown for reference only; the application does not author these documents.

| Field | Type | Notes |
|-------|------|-------|
| `id` | string (UUID) | Document id, generated per message by the provider. |
| `session_id` | string | **Partition key** (`/session_id`). Equals the conversation id. |
| `sort_key` | number | Monotonic ordering key (`time_ns()` base + index). Messages are returned `ORDER BY sort_key ASC`. |
| `source_id` | string | Provider source id (default `"azure_cosmos_history"`); used to scope queries. |
| `message` | object | Serialized Agent Framework `Message` (`Message.to_dict()`), including role and content (text, tool calls/results, etc.). |

**Access patterns** (all single-partition by `session_id`):
- Load history for a turn: `SELECT c.message ... WHERE c.session_id=@sid AND c.source_id=@src ORDER BY c.sort_key ASC` (provider `get_messages`).
- Append turn messages: batched upsert (provider `save_messages`).
- Clear on delete: query ids then batched delete (provider `clear`).

**Rules**:
- The application MUST NOT read this container except through the provider, and MUST verify conversation ownership (Entity 2) before invoking provider reads/clears for a given `session_id`.
- Message documents are append-only per turn; ordering relies on `sort_key`.

---

## Entity 2 — Conversation Index Entry (`conversations` container)

Represents one chat thread owned by a user. **Authored and managed by the backend** (`cosmos_memory.py`). This is the authoritative ownership record and the source for the left chat pane.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string (UUID) | yes | Document id == conversation id == `session_id` (messages partition key). Unguessable (FR-009). |
| `user_id` | string | yes | **Partition key** (`/user_id`). The owner's stable identifier (auth token `oid`). |
| `profile_id` | string | yes | Agent/profile identifier used by this conversation (e.g., `chief-of-staff`, or `custom`). |
| `profile_name` | string | yes | Display name of the agent, for the list. |
| `title` | string | yes | Human-readable description derived from the first user message (truncated, e.g. ≤60 chars). Empty until the first message (see lifecycle). |
| `created_at` | string (ISO-8601 UTC) | yes | Creation timestamp. |
| `last_activity_at` | string (ISO-8601 UTC) | yes | Updated on each completed turn; the list orders by this descending. |
| `custom_agent_id` | string | no | Set when a custom agent was used, to reopen with the same agent. |
| `used_builtin_override` | boolean | no | True when a built-in agent was customized for this conversation. |
| `base_profile_id` | string | no | Original profile id when an override was applied. |
| `override_updated_at` | string (ISO-8601 UTC) | no | Timestamp of the applied override, mirrors existing session metadata. |
| `doc_type` | string | no | Constant marker (e.g. `"conversation"`) for forward-compatibility if the container is ever shared. |
| `schema_version` | number | no | Document schema version for future migrations (initially `1`). |

**Access patterns** (all single-partition by `user_id`):
- List my conversations: `SELECT * FROM c WHERE c.user_id=@uid ORDER BY c.last_activity_at DESC` (optionally `OFFSET/LIMIT` for paging).
- Ownership check / fetch one: point-read by (`id`, partition `user_id`).
- Upsert on create and on activity: replace/upsert the document.
- Delete: point-delete by (`id`, partition `user_id`).

**Validation rules**:
- `id` MUST be a server-generated UUID; never client-supplied (prevents enumeration and cross-user collisions).
- `user_id` MUST come from the validated auth token, never from the request body.
- `title` MUST be bounded in length and sanitized of control characters; derived from the first user message content only.
- `profile_id`/`profile_name` MUST reference a resolvable agent at resume time; if unresolved, resume surfaces a clear error rather than silently changing agents.
- All timestamps are UTC ISO-8601.

---

## Relationships

```text
AuthenticatedUser (user_id = oid)
        │ owns 1..*
        ▼
Conversation Index Entry  (conversations, partition /user_id)
        │ id == session_id  (1:1)
        ▼
Conversation Messages     (chat-history, partition /session_id)  0..*
```

- **User → Conversation**: one-to-many; isolation is physical (per-user partition) and enforced logically (ownership check).
- **Conversation → Messages**: one-to-many; the conversation `id` is the messages' `session_id`. The index entry is the gatekeeper; messages are only accessed after the entry's `user_id` matches the caller.
- No cross-references are stored inside message documents back to the user; ownership is resolved exclusively through the index.

---

## Conversation lifecycle (state transitions)

```text
            create session (new)
   ─────────────────────────────────►  CREATED
                                          │  index doc written: id=session_id, user_id,
                                          │  profile_*, created_at=last_activity_at=now, title=""
                                          │
            first user message completes  ▼
   ─────────────────────────────────►  ACTIVE
                                          │  title set from first user message;
                                          │  messages persisted to chat-history;
                                          │  last_activity_at bumped each turn
                                          │
            resume (by conversation_id)   │  ownership verified; AgentSession rebuilt with
   ◄─────────────────────────────────────┘  same session_id; provider loads prior messages
                                          │
            delete (by conversation_id)   ▼
   ─────────────────────────────────►  DELETED
                                             ownership verified; provider.clear(session_id)
                                             removes messages; index doc deleted
```

**Transition rules**:
- **CREATED → ACTIVE**: occurs when the first turn completes. If a conversation is created but never receives a message, it remains titleless; the list view MUST render it without error (edge case) or such empty entries MAY be pruned (implementation choice, must be consistent).
- **ACTIVE (resume)**: requires a successful ownership check; a failed check returns not-found/denied without revealing existence to non-owners.
- **→ DELETED**: requires ownership check; both containers are updated. Deletion of messages uses the provider's `clear(session_id)`; the index document is point-deleted. Partial failure MUST be surfaced and retryable (FR-018) and MUST NOT leave the index claiming a conversation whose messages were already cleared without signaling the inconsistency.

---

## Consistency, throughput, and limits

- **Throughput**: serverless (per-request RU). No provisioned floor.
- **Partition sizing**: each `session_id` partition (one conversation's messages) and each `user_id` partition (one user's index) is expected to stay far below the 20 GB logical-partition limit. Hierarchical partition keys are not required (see research.md R4).
- **Indexing**: default Cosmos indexing suffices for the point-reads and single-partition `ORDER BY last_activity_at` / `ORDER BY sort_key` queries used here; no composite-index tuning is required initially. If the conversations list query is flagged for an `ORDER BY` index, add a composite index `(user_id, last_activity_at DESC)` as a follow-up.
- **Throttling (429)**: the SDK's retry behavior plus an application-level clear error path (FR-018) handle transient throttling; turns must not be left partially persisted in an inconsistent way visible to the user.

---

## Mapping to existing frontend types

The new API responses map onto (revised) frontend types in `frontend/src/types/api.ts`:

| Cosmos index field | Frontend `ConversationIndexEntry` field |
|--------------------|-----------------------------------------|
| `id` | `id` |
| `profile_id` | `profileId` |
| `profile_name` | `profileName` |
| `title` | `description` |
| `created_at` | `createdAt` |
| `last_activity_at` | `lastActivityAt` |
| `custom_agent_id` | `customAgentId` |
| `used_builtin_override` | `usedBuiltInOverride` |
| `base_profile_id` | `baseProfileId` |
| `override_updated_at` | `overrideUpdatedAt` |

Per-conversation messages returned by `GET /api/conversations/{id}/messages` map to the existing `ChatMessage[]` shape (`role`, `content`, optional `tool_invocations`, `usage`, `images`) so the chat view renders resumed conversations unchanged. The previously client-stored `StoredConversation.sessionData` blob is **removed** from the client contract — history now lives in Cosmos and is loaded server-side.
