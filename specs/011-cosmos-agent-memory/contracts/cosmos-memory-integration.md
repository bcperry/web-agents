# Contract: Cosmos Memory Backend Integration

**Feature**: `011-cosmos-agent-memory` | **Date**: 2026-06-18

Internal backend contract for wiring Azure Cosmos DB into the agent runtime and the conversation index. This is the integration surface implemented in a new `cosmos_memory.py` module plus edits to `agent_factory.py`, `session_orchestration.py`, and `main.py`. It is not a public HTTP API (that is `conversations-api.md`); it defines the Python-level seams so the integration stays seamless and minimal.

## Configuration (environment)

| Variable | Required (prod) | Purpose |
|----------|-----------------|---------|
| `AZURE_COSMOS_ENDPOINT` | yes | Cosmos account endpoint (`https://<acct>.documents.azure.us:443/`). Presence selects the Cosmos path; absence selects the local in-memory fallback. |
| `AZURE_COSMOS_DATABASE_NAME` | yes | Database name (e.g. `agent-memory`). |
| `AZURE_COSMOS_CONTAINER_NAME` | yes | Messages container name (e.g. `chat-history`). Consumed by `CosmosHistoryProvider`. |
| `AZURE_COSMOS_CONVERSATIONS_CONTAINER` | no (default `conversations`) | Per-user index container name. |
| `AZURE_COSMOS_KEY` | local only | Account key for local/emulator use. MUST be unset in production (Managed Identity + RBAC). |

- Credential resolution mirrors the existing AI Search pattern: if `AZURE_COSMOS_KEY` is set, use it (local/dev); otherwise use `DefaultAzureCredential()` configured for Azure US Government, relying on the app's user-assigned managed identity.
- Secrets MUST never be logged; endpoint values may be logged, keys/credentials must not.

## History provider factory

A single cached factory builds the agent-facing history provider.

```text
get_history_provider() -> HistoryProvider
  if AZURE_COSMOS_ENDPOINT is configured:
      return CosmosHistoryProvider(
          endpoint=<AZURE_COSMOS_ENDPOINT>,
          database_name=<AZURE_COSMOS_DATABASE_NAME>,
          container_name=<AZURE_COSMOS_CONTAINER_NAME>,
          credential=<AZURE_COSMOS_KEY or DefaultAzureCredential()>,
          # source_id defaults to "azure_cosmos_history"
      )
  else:
      return InMemoryHistoryProvider(skip_excluded=True)   # local-dev / test fallback
```

**Contract guarantees**:
- The returned object is a `HistoryProvider` and therefore exposes `.source_id`. Callers MUST use `provider.source_id` for `CompactionProvider(history_source_id=...)` rather than hardcoding a string.
- The Cosmos client owns its own async lifecycle; the provider is reused (not recreated per request) consistent with Azure SDK guidance (single client instance). Provider/client cleanup hooks into the app/runtime shutdown path.
- The factory is import-safe: it does not connect at import time; the Cosmos container is resolved lazily on first use (the provider creates the container if missing as a safety net, though Terraform is the authoritative provisioner).

## `_build_context_providers` change (`agent_factory.py`)

The current pipeline (unchanged except for the history element):

```text
history    = get_history_provider()                      # was: InMemoryHistoryProvider(skip_excluded=True)
compaction = CompactionProvider(
                 before_strategy=pipeline,
                 after_strategy=pipeline,
                 tokenizer=tokenizer,
                 history_source_id=history.source_id,      # works for both providers
             )
providers  = [history, compaction]
# + optional AzureAISearchContextProvider, SkillsProvider (unchanged)
```

**Guarantees**:
- No change to the order or presence of compaction/search/skills providers.
- The swap is transparent to `create_chat_runtime`/`ChatRuntime`; the returned `agent` and `session` behave identically except history is now durable and session-keyed.
- `agent.create_session()` continues to produce an `AgentSession`; the backend assigns/overrides `session_id` to the conversation id so the provider partitions correctly.

## Conversation index repository (`cosmos_memory.py`)

Application-owned repository for the `conversations` container. Interface (async):

```text
class ConversationIndexRepository:
    async def create(user_id, conversation_id, profile_id, profile_name, *, custom_agent_id=None,
                     used_builtin_override=False, base_profile_id=None, override_updated_at=None) -> IndexEntry
    async def list_for_user(user_id, *, limit=50, cursor=None) -> (list[IndexEntry], next_cursor)
    async def get_owned(user_id, conversation_id) -> IndexEntry | None     # ownership check (point-read)
    async def touch(user_id, conversation_id, *, title=None) -> None       # bump last_activity_at; set title if provided/unset
    async def delete(user_id, conversation_id) -> bool                      # delete index doc (after messages cleared)
```

**Guarantees & rules**:
- All methods are partition-scoped by `user_id`; `user_id` always comes from the authenticated principal, never the request body.
- `get_owned` returns `None` for both "missing" and "owned by someone else" (callers translate to `404`).
- `create` generates the conversation id (UUID) server-side; it equals the messages `session_id`.
- `touch` is called on turn completion: sets `title` from the first user message when not yet set, and always updates `last_activity_at`.
- A **fallback implementation** (in-memory dict keyed by `user_id`) is used when Cosmos is not configured, exposing the same interface so route handlers are storage-agnostic. The fallback is process-local and non-durable (documented local-dev behavior).

## Ownership-gated message access

The only sanctioned way route handlers read or clear messages:

```text
entry = await conversations_repo.get_owned(user.user_id, conversation_id)
if entry is None:
    raise HTTPException(404)
messages = await history_provider.get_messages(conversation_id)   # session_id == conversation_id
# or, for delete:
await history_provider.clear(conversation_id)
await conversations_repo.delete(user.user_id, conversation_id)
```

**Guarantee**: message-container access is always preceded by an index ownership check in the same request, giving a single authorization choke point (FR-008).

## Session create/resume wiring (`session_orchestration.py`)

- **Create**: generate `session_id` (UUID) → build runtime via `create_chat_runtime` → set `AgentSession.session_id = session_id` → `conversations_repo.create(user.user_id, session_id, profile_id, profile_name, ...)`.
- **Resume**: require `conversation_id` → `get_owned(user.user_id, conversation_id)` (else `404`) → build runtime → set `AgentSession.session_id = conversation_id`. No client-supplied `history` blob is read; the provider loads messages on first run.
- The previous `_restore_session_history(...from client dict...)` path is removed from the durable-storage flow; in the local fallback, in-memory session state may still be used but is non-authoritative.

## Failure & resilience contract

- Cosmos throttling/transient errors propagate as a retryable error to the route layer, which returns `503` with a retry hint (FR-018). The Azure Cosmos SDK's built-in retry handles most `429`s; the app adds a clear user-facing error rather than a stack trace.
- Diagnostics: on latency over threshold or unexpected status, capture Cosmos diagnostics for troubleshooting (without leaking credentials), consistent with Cosmos SDK best practices.
- Startup MUST NOT hard-fail when Cosmos is unconfigured locally; it selects the fallback. Startup MAY warn (once) that durable memory is disabled.

## Testing contract

- Unit/integration tests construct `ConversationIndexRepository` and the history provider against a **fake** Cosmos data layer (in-memory doubles implementing the same async methods), so `list/get/touch/delete`, ownership/isolation, resume, and the fallback path are covered with no live cloud account.
- A smoke test asserts `get_history_provider()` returns a `CosmosHistoryProvider` when `AZURE_COSMOS_ENDPOINT` is set (without connecting) and `InMemoryHistoryProvider` otherwise.
