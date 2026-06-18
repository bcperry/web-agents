# Phase 0 Research: Azure Cosmos DB Agent Memory Layer

**Feature**: `011-cosmos-agent-memory` | **Date**: 2026-06-18

This document records the technical decisions that resolve the Technical Context unknowns in [plan.md](plan.md). Each item follows Decision / Rationale / Alternatives considered. Findings are grounded in the installed Agent Framework source and the published `agent-framework-azure-cosmos` provider.

---

## R1. History provider: use the built-in `CosmosHistoryProvider`

**Decision**: Use `CosmosHistoryProvider` from the `agent-framework-azure-cosmos` package, imported as `from agent_framework.azure import CosmosHistoryProvider`. Add `agent-framework-azure-cosmos` to `pyproject.toml` and install with `uv`.

**Rationale**:
- The installed `agent_framework.azure` namespace already lazily re-exports `CosmosHistoryProvider`; attempting to use it without the package raises a clear `ModuleNotFoundError` instructing installation of `agent-framework-azure-cosmos`. So the import path is stable and the only missing piece is the dependency.
- `CosmosHistoryProvider(HistoryProvider)` subclasses the exact same base class as the current `InMemoryHistoryProvider`. It implements `get_messages(session_id, *, state)` / `save_messages(session_id, messages, *, state)` plus `clear(session_id)` and `list_sessions()`. This makes it a near drop-in for the provider already used in `agent_factory._build_context_providers`.
- Using the maintained provider satisfies Principle V (Simplicity): no custom Cosmos provider to write or maintain.

**Alternatives considered**:
- *Custom `ContextProvider` subclass writing to Cosmos*: rejected — duplicates maintained functionality, more code to audit, violates YAGNI.
- *Service-side thread storage (provider-managed conversation ids)*: rejected — the app already controls session ids and needs explicit ownership/index control for the per-user pane; service-side storage would not give the per-user index the left pane requires.

---

## R2. Drop-in into the existing context-provider pipeline

**Decision**: In `_build_context_providers`, construct a `CosmosHistoryProvider` (when Cosmos is configured) in place of `InMemoryHistoryProvider(skip_excluded=True)`, and continue to pass `history_source_id=history.source_id` to the existing `CompactionProvider`.

**Rationale**:
- `CompactionProvider` only needs the history provider's `source_id` string. `CosmosHistoryProvider` exposes `source_id` (default `"azure_cosmos_history"`) via the shared `HistoryProvider`/`ContextProvider` base, so the compaction wiring is unchanged.
- The remaining providers (`CompactionProvider`, `AzureAISearchContextProvider`, `SkillsProvider`) are unaffected; only the history element changes.

**Alternatives considered**:
- *Keep `InMemoryHistoryProvider` and separately mirror messages to Cosmos*: rejected — double bookkeeping, ordering/consistency risk, and the agent would still read volatile memory rather than the durable store.

**Known risk / validation item**: `InMemoryHistoryProvider` is initialized with `skip_excluded=True` so it omits messages the `CompactionProvider` marked `_excluded` when re-loading context. `CosmosHistoryProvider.get_messages` does not implement `skip_excluded` filtering and stores whatever flows through `save_messages`. The compaction-plus-persistence interaction (whether exclusion markers should be persisted and re-applied on load) must be validated during implementation; the provider's `store_outputs`/`store_inputs`/`store_context_messages` flags and `load_messages` flag are the tuning points. This is an implementation validation task, not an open spec question.

---

## R3. session_id is the Cosmos partition key; backend controls it

**Decision**: Treat `conversation_id == AgentSession.session_id` as a server-generated unguessable UUID, and use it directly as the Cosmos messages partition key. On resume, rebuild the `AgentSession` with the same `session_id` so `CosmosHistoryProvider` auto-loads prior messages.

**Rationale**:
- `CosmosHistoryProvider` partitions message documents on `/session_id` and uses the `session_id` argument (sourced from `AgentSession.session_id`) for all reads/writes. The backend already creates sessions and can set/restore `session_id` (current code does `agent_session._session_id = session_id`).
- This eliminates the current client→server "history blob" round-trip: history lives in Cosmos and is loaded by the provider keyed on the session id alone.
- Unguessable UUIDs satisfy FR-009 (non-enumerable keys).

**Alternatives considered**:
- *Composite `user_id:conversation_uuid` session id to bake ownership into the partition key*: rejected as the primary mechanism — the provider hardcodes `/session_id` as the partition path, and ownership is more clearly and flexibly enforced via the per-user index (R4) than by string-parsing partition keys. (A composite id remains a possible defense-in-depth option but is not required.)

---

## R4. Two-container model: messages + per-user conversation index

**Decision**: Use one Cosmos database with two containers:
1. `chat-history` — message documents, partition key `/session_id`, owned/managed by `CosmosHistoryProvider`.
2. `conversations` — one index document per conversation, partition key `/user_id`, owned/managed by new backend code (`cosmos_memory.py`).

**Rationale**:
- `CosmosHistoryProvider` stores only raw messages partitioned by session; it does not store per-user metadata (title, agent name, timestamps) and its `list_sessions()` is a cross-partition scan over all users — unsuitable for a per-user, isolated, efficient left-pane list.
- A `conversations` container partitioned by `/user_id` makes "list my conversations" a single-partition query, gives natural per-user isolation, and is the authoritative ownership record consulted before any message read/resume/delete.
- This directly maps to the existing frontend concepts (`ConversationIndexEntry` for the list, message history for the view), easing the frontend migration.

**Alternatives considered**:
- *Single container for messages and index*: rejected — per-user listing would require cross-partition scans of a session-partitioned container; mixing index metadata into provider-managed message docs would break the provider's schema. (Recorded in plan Complexity Tracking.)
- *Hierarchical Partition Keys (HPK)*: considered per Cosmos guidance for >20 GB partitions. Rejected for now — a single conversation's messages and a single user's index both stay well under the 20 GB logical-partition limit, and the framework provider fixes `/session_id` as a non-hierarchical key. Simple partition keys keep queries single-partition without added complexity. Revisit only if a single user accumulates index volume approaching the limit.

---

## R5. Throughput mode: serverless

**Decision**: Provision the Cosmos account in **serverless** throughput mode.

**Rationale**:
- Chat traffic is spiky and user-driven; serverless bills per-request-unit with no minimum provisioned RU, matching a variable, bursty interactive workload and minimizing idle cost.
- Operationally simpler than autoscale RU planning for an initial rollout (Principle V).

**Alternatives considered**:
- *Provisioned autoscale*: better for sustained high throughput or when multi-region writes are needed; rejected for the initial scope as over-provisioning for an interactive chat memory store. Revisit if sustained load or SLA/throughput guarantees demand it.

---

## R6. Credentials: Managed Identity (prod) / key (local); Azure Government endpoints

**Decision**: In production, authenticate to Cosmos with `DefaultAzureCredential` (the app's user-assigned Managed Identity) and a data-plane RBAC role; permit an account key via `AZURE_COSMOS_KEY` only for local development. All Cosmos endpoints target Azure Government (`*.documents.azure.us`).

**Rationale**:
- Constitution Principle III mandates Managed Identity in production and keys only for local dev, and requires Azure Government endpoints. `CosmosHistoryProvider` accepts either a credential object or a key string and reads `AZURE_COSMOS_*` env vars, supporting both paths cleanly.
- `DefaultAzureCredential` is already the project's pattern (used for AI Search).

**Configuration notes for Azure Government**:
- The provider/SDK must resolve the Government login authority and Cosmos resource scope. The deployment configures `DefaultAzureCredential` for the US Government cloud (consistent with the existing `login.microsoftonline.us` authority usage) and uses the `.documents.azure.us` account endpoint.
- The data-plane role assignment uses the **Cosmos DB Built-in Data Contributor** SQL role (data-plane), not just control-plane RBAC, because message read/write are data-plane operations.

**Alternatives considered**:
- *Account key in production*: rejected — violates Principle III.
- *Connection string env var*: rejected — keys/connection strings must not be the production path; managed identity avoids storing a secret at all.

---

## R7. Local development & test strategy (no fallback)

**Decision**: Azure Cosmos DB is **required** — there is **no non-durable in-memory fallback** in the app. Locally the app runs against the **Cosmos emulator** (`AZURE_COSMOS_ENDPOINT` points at it); when deployed it uses the real account; if `AZURE_COSMOS_ENDPOINT` is unset the backend **fails fast at startup**. Testing is two-tier: fast **unit tests** inject in-memory Cosmos doubles (always run, no dependency); **integration tests** run against the local emulator behind an `emulator` pytest marker (deselected by default; run with `-m emulator`), exercising the real `CosmosHistoryProvider`, real `/session_id` and `/user_id` partitions, and real queries.

**Rationale**:
- Satisfies User Story 6 and the requirement that memory is always durable: a silent in-memory fallback could mask data loss, so it is removed.
- Aligns with the repo's Azure Cosmos DB guidance, which recommends the emulator for local development and testing.
- A single switch (presence of `AZURE_COSMOS_ENDPOINT`) selects emulator-vs-real; absence is a hard error, keeping behavior predictable.

**Alternatives considered**:
- *In-memory app fallback when unconfigured*: rejected — hides the fact that chat history isn't durable; the app must fail fast instead.
- *Fakes only, no emulator*: rejected — fakes can't validate real partition-key behavior, query ordering, ownership reads, or batch delete; the emulator catches integration defects fakes would miss.
- *Mock the whole provider in app code*: rejected — fakes belong in tests (injected); app code always uses the real Cosmos provider.

---

## R8. Conversation title and activity metadata

**Decision**: Derive the conversation title/description from the first user message (truncated, consistent with current behavior). Update the index document's `last_activity_at` (and set the title on first message) as part of completing each turn.

**Rationale**:
- Matches today's UX (the frontend currently derives a 60-char description from the first user message), so the visible behavior is unchanged while the storage moves server-side.
- Keeping title derivation server-side ensures the list is correct regardless of client.

**Alternatives considered**:
- *LLM-generated titles*: rejected for scope — extra model calls and cost; out of scope (can be a later enhancement).
- *User-edited titles/rename*: out of scope (listed in spec Out of Scope).

---

## R9. Handling pre-existing browser-stored conversations

**Decision**: Do not auto-migrate existing `localStorage` conversations. The frontend stops using the localStorage conversation keys as the source of truth; their presence is ignored and must not cause errors. Auth token and theme remain in browser storage.

**Rationale**:
- The prior store was capped (≈5) and per-browser; a clean cut to server-sourced history is simpler and avoids fragile migration logic (Principle V, FR-019).
- Ignoring legacy keys is safe and side-effect-free; a one-time import is explicitly out of scope.

**Alternatives considered**:
- *One-time import of localStorage conversations into Cosmos*: rejected for scope/complexity; the limited, per-browser nature of the old data makes migration low value.

---

## R10. Infrastructure as Code (Terraform)

**Decision**: Add `infra/modules/cosmos` provisioning the Cosmos DB for NoSQL account (Azure Gov), the database, and the two containers with the correct partition keys, plus a data-plane SQL role assignment granting the app's user-assigned managed identity the **Cosmos DB Built-in Data Contributor** role. Wire `AZURE_COSMOS_ENDPOINT`, `AZURE_COSMOS_DATABASE_NAME`, and `AZURE_COSMOS_CONTAINER_NAME` into the `app-service` module app settings. Disable local (key) auth on the account in production.

**Rationale**:
- Constitution Principle VI requires all Azure resources via Terraform with module groupings; the existing `infra/` already follows this pattern (managed-identity, app-service modules).
- Provisioning the containers in IaC (rather than relying on the provider's `create_container_if_not_exists`) makes partition keys and throughput explicit, reviewable, and reproducible. The provider's auto-create remains a safety net but is not the source of truth.

**Alternatives considered**:
- *Let the provider auto-create database/containers at runtime*: rejected as the authoritative mechanism — partition-key/throughput choices belong in reviewable IaC; runtime auto-create also requires broader control-plane permissions for the app identity.
- *Account key in app settings*: rejected — managed identity + RBAC avoids storing a secret (Principle III).

---

## R11. API surface and ownership enforcement

**Decision**: Add `GET /api/conversations`, `GET /api/conversations/{id}/messages`, and `DELETE /api/conversations/{id}`, each scoped to the authenticated `user_id`. Session create/resume moves to a `conversation_id`-based contract (no client history blob). Every message read, resume, and delete verifies that the index document's `user_id` equals the caller's `user_id` before touching the messages container.

**Rationale**:
- Centralizing ownership checks at the index (partitioned by `user_id`) gives a single, auditable authorization point (FR-008) and keeps the messages container access strictly gated.
- Reusing the existing `get_current_user` dependency keeps auth consistent with the rest of the API (Principle VII).

**Alternatives considered**:
- *Trust the session/conversation id alone*: rejected — ids must be treated as capabilities only after ownership verification to prevent cross-user access even if an id leaks.

---

## R12. Frontend migration approach

**Decision**: Replace the localStorage-backed `useConversationStore` with a server-backed implementation calling the new endpoints; update `useConversationPersistence`/`useSessionLifecycle`/`useChat` so resume loads messages from the API and the client no longer persists full conversations or posts a history blob. `Sidebar`/`ChatPage` render the server list with loading/empty/error states.

**Rationale**:
- Keeps the change surface localized to the persistence hooks and the components that consume them, preserving the existing chat/streaming UI (FR-011) while satisfying FR-007 (server-sourced history).

**Alternatives considered**:
- *Dual-write to localStorage and server*: rejected — reintroduces the client as a source of truth, risks divergence, and contradicts the feature's goal.

---

## Summary of resolved unknowns

| Unknown (from Technical Context) | Resolution |
|----------------------------------|------------|
| History provider choice/import | Built-in `CosmosHistoryProvider` via `agent_framework.azure`; add `agent-framework-azure-cosmos` (R1) |
| Pipeline compatibility | Drop-in with unchanged `CompactionProvider` wiring; validate exclusion interaction (R2) |
| Partition key / id strategy | `session_id` (UUID) as messages partition key; backend-controlled (R3) |
| Per-user listing & isolation | Second `conversations` container partitioned by `/user_id` (R4) |
| Throughput mode | Serverless (R5) |
| Credentials & cloud | Managed Identity prod / key local; Azure Gov endpoints; Data Contributor role (R6) |
| Local/test execution | No app fallback (fail fast if unconfigured); unit tests inject in-memory doubles; emulator for integration, deselected by default (R7) |
| Title & activity metadata | Derived from first user message; server-updated `last_activity_at` (R8) |
| Legacy browser data | Ignored, no auto-migration (R9) |
| Infrastructure | Terraform `cosmos` module + RBAC + app settings (R10) |
| API & authorization | `/api/conversations` endpoints + ownership checks at the index (R11) |
| Frontend persistence | Server-backed hooks replace localStorage (R12) |

No `NEEDS CLARIFICATION` items remain. Proceed to Phase 1 design.
