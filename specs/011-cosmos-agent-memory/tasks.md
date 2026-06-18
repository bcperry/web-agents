# Tasks: Azure Cosmos DB Agent Memory Layer

**Input**: Design documents from `/specs/011-cosmos-agent-memory/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)

**Tests**: Included, in two tiers. (1) Fast **unit tests** use in-memory Cosmos fakes and always run. (2) **Integration tests run against the local Azure Cosmos DB Emulator** (the durable-path verification — real `CosmosHistoryProvider`, real `/session_id` and `/user_id` partitions, real queries) behind an `emulator` pytest marker that auto-skips when the emulator is unreachable, so the default offline run stays green. This matches the repo's Azure Cosmos DB guidance (use the emulator for local dev/testing).

**Organization**: Tasks are grouped by user story (from spec.md) to enable independent implementation and testing. Four P1 stories, one P2, one P3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US6 (user-story phases only)
- Backend Python is at the repository root; frontend is in `frontend/`; infra is in `infra/`

## Path Conventions (from plan.md Structure Decision)

- Backend: repo-root modules (`main.py`, `agent_factory.py`, `session_orchestration.py`, NEW `cosmos_memory.py`), tests in `tests/`
- Frontend: `frontend/src/` (api, hooks, components, pages, types)
- Infra: `infra/` + `infra/modules/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the dependency and configuration surface the feature needs.

- [ ] T001 Add `agent-framework-azure-cosmos` to `pyproject.toml` dependencies and install with `uv add agent-framework-azure-cosmos --prerelease=allow && uv sync` (never `pip`)
- [ ] T002 [P] Document the Cosmos environment variables (`AZURE_COSMOS_ENDPOINT`, `AZURE_COSMOS_DATABASE_NAME`, `AZURE_COSMOS_CONTAINER_NAME`, `AZURE_COSMOS_CONVERSATIONS_CONTAINER`, `AZURE_COSMOS_KEY` for local) in `README.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared storage/factory layer every story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 Create `cosmos_memory.py` with Cosmos config resolution: read `AZURE_COSMOS_*` env vars and resolve `credential` = `AZURE_COSMOS_KEY` (local) or `DefaultAzureCredential()` configured for Azure US Government; mask secrets in any log line
- [ ] T004 Implement `get_history_provider()` in `cosmos_memory.py`: return a cached `CosmosHistoryProvider` (from `agent_framework.azure`) when `AZURE_COSMOS_ENDPOINT` is set, else `InMemoryHistoryProvider(skip_excluded=True)`; expose `.source_id` for downstream wiring
- [ ] T005 Define `ConversationIndexRepository` interface + `CosmosConversationIndexRepository` in `cosmos_memory.py` (`create`, `list_for_user`, `get_owned`, `touch`, `delete`), all partition-scoped by `/user_id` per [data-model.md](data-model.md)
- [ ] T006 Implement `InMemoryConversationIndexRepository` fallback in `cosmos_memory.py` exposing the same interface (process-local dict keyed by `user_id`)
- [ ] T007 Implement `get_conversation_repository()` selector + client/provider lifecycle (close on shutdown) in `cosmos_memory.py`, choosing Cosmos vs in-memory by config (depends on T003–T006)
- [ ] T008 [P] Update `agent_factory._build_context_providers` to call `get_history_provider()` and pass `history_source_id=history.source_id` to `CompactionProvider` (replace the `InMemoryHistoryProvider(skip_excluded=True)` literal) in `agent_factory.py`
- [ ] T009 Wire the conversation repository singleton into `main.py` (construct on startup, expose via `SessionContext`/FastAPI dependency, close on shutdown) (depends on T007)
- [ ] T010 [P] Add two test harnesses to `tests/conftest.py`: (a) in-memory Cosmos fakes (fake history provider + fake repository) for fast unit tests, and (b) a session-scoped **Azure Cosmos DB Emulator** fixture — async `CosmosClient` to `AZURE_COSMOS_EMULATOR_ENDPOINT` (default `https://localhost:8081`) using the well-known emulator key from env and `connection_verify=False` — exposed behind an `emulator` pytest marker that auto-skips when the endpoint is unreachable

**Checkpoint**: Storage/factory layer ready — user stories can begin.

---

## Phase 3: User Story 1 - Agent Remembers Across Turns and Restarts (Priority: P1) 🎯 MVP

**Goal**: Durable per-conversation memory. Messages persist to Cosmos keyed by `session_id`; recreating a session with the same id reloads full history so the agent stays context-aware across turns and process restarts.

**Independent Test**: Tell the agent a fact, restart the backend, resume the same conversation id, ask a dependent question → correct, context-aware answer; turn messages are present in the messages store.

### Tests for User Story 1

- [ ] T011 [P] [US1] Unit test provider selection + repository `create`/`get_owned` (Cosmos-vs-fallback, no connect) in `tests/test_cosmos_memory.py`
- [ ] T012 [P] [US1] Emulator integration test (`@pytest.mark.emulator`): against the local Cosmos emulator, persist a turn via the real `CosmosHistoryProvider`, re-instantiate the provider (simulated restart), and assert prior history reloads by `conversation_id`, verifying the real `/session_id` partition round-trip, in `tests/test_session_orchestration.py`

### Implementation for User Story 1

- [ ] T013 [US1] In `session_orchestration.py` create flow: generate a UUID `session_id`, set `AgentSession.session_id`, and call `repo.create(user.user_id, session_id, profile_id, profile_name, ...)` to write the index doc
- [ ] T014 [US1] In `session_orchestration.py` add resume: accept `conversation_id`, verify ownership via `repo.get_owned` (404 when `None`), rebuild `AgentSession` with that `session_id`, and remove the client `history`-blob restore from the durable path (depends on T013)
- [ ] T015 [US1] Update `POST /api/sessions` in `main.py` to accept optional `conversation_id` (resume) and stop requiring the `history` blob; return `session_id` as the conversation id (depends on T014)
- [ ] T016 [US1] On message stream completion (`done`) in `main.py`, call `repo.touch(user_id, conversation_id, title=<first user message if unset>)` to set the title and bump `last_activity_at`
- [ ] T017 [US1] Add Cosmos failure handling to session create/resume/turn in `main.py`/`session_orchestration.py`: surface a retryable `503`, never leave a turn partially persisted, never leak credentials (FR-018)

**Checkpoint**: Agent memory is durable and survives restarts — MVP is functional and independently testable.

---

## Phase 4: User Story 2 - Left Chat Pane Lists My Real Conversations (Priority: P1)

**Goal**: The left pane shows the authenticated user's actual conversations from the backend (newest first), not browser storage.

**Independent Test**: Hold conversations, open the app in a second browser/device as the same user → identical list sourced from `GET /api/conversations`; new user sees an empty state.

### Tests for User Story 2

- [ ] T018 [P] [US2] API test (`emulator`-backed repository — real `/user_id` partition query): `GET /api/conversations` returns only the caller's conversations, ordered by `last_activity_at` desc, with paging, in `tests/test_conversations_api.py`

### Implementation for User Story 2

- [ ] T019 [US2] Add `GET /api/conversations` in `main.py` (auth-scoped `repo.list_for_user`, `limit`/`cursor`) returning the wire shape from [contracts/conversations-api.md](contracts/conversations-api.md)
- [ ] T020 [P] [US2] Align `ConversationIndexEntry` to the API response and drop reliance on `StoredConversation.sessionData` in `frontend/src/types/api.ts`
- [ ] T021 [US2] Add `listConversations()` to `frontend/src/api/client.ts` calling `GET /api/conversations` (depends on T020)
- [ ] T022 [US2] Replace localStorage `loadIndex` with server `listConversations` (with loading/error state) in `frontend/src/hooks/useConversationStore.ts` (depends on T021)
- [ ] T023 [US2] Render server conversations with loading/empty/error states (handle empty title) in `frontend/src/components/Sidebar.tsx` and `frontend/src/pages/ChatPage.tsx` (depends on T022)

**Checkpoint**: The pane lists real per-user conversations from Cosmos.

---

## Phase 5: User Story 3 - Resume a Past Conversation With Full History (Priority: P1)

**Goal**: Selecting a conversation renders its prior messages and continues with the agent's full context.

**Independent Test**: Select a past conversation → prior messages render; send a context-dependent follow-up → correct reply; new turn appends to the same conversation.

### Tests for User Story 3

- [ ] T024 [P] [US3] API test (`emulator`-backed — real message read from `chat-history`): `GET /api/conversations/{id}/messages` returns the owner's messages mapped to `ChatMessage[]`, and `404` for missing/non-owner, in `tests/test_conversations_api.py`

### Implementation for User Story 3

- [ ] T025 [US3] Add a stored-`Message` → `ChatMessage` wire-shape mapping helper (role, content, `tool_invocations`, `usage`, `images`) reusing existing event shapes in `streaming.py`
- [ ] T026 [US3] Add `GET /api/conversations/{id}/messages` in `main.py`: ownership check, then `history_provider.get_messages(id)` mapped via T025 (depends on T025)
- [ ] T027 [P] [US3] Add `getConversationMessages(id)` to `frontend/src/api/client.ts` calling `GET /api/conversations/{id}/messages`
- [ ] T028 [US3] Resume via `conversation_id` and load messages from the API (replace localStorage `loadConversation` + `extractMessagesFromSessionData`) in `frontend/src/hooks/useSessionLifecycle.ts` and `frontend/src/hooks/useConversationPersistence.ts` (depends on T027)
- [ ] T029 [US3] Render resumed messages from the server and post `conversation_id` (no history blob) when resuming in `frontend/src/pages/ChatPage.tsx` and `frontend/src/hooks/useChat.ts` (depends on T028)

**Checkpoint**: Conversations reopen with full history and continue seamlessly.

---

## Phase 6: User Story 4 - My Conversations Are Private to Me (Priority: P1)

**Goal**: Ownership is enforced on every conversation read/resume/delete; cross-user access is impossible.

**Independent Test**: As user B, attempt to list/read/resume/delete user A's conversation id → every attempt denied (`404`); B's list never includes A's conversations.

### Tests for User Story 4

- [ ] T030 [P] [US4] Cross-user isolation tests (`emulator`-backed — real per-`user_id` partition isolation): non-owner `GET messages`/resume/`DELETE` → `404`; `list` excludes other users, in `tests/test_conversations_api.py`

### Implementation for User Story 4

- [ ] T031 [US4] Ensure `get_owned` returns `None` for both missing and foreign-owned docs and is the single ownership choke point used by all conversation paths in `cosmos_memory.py`
- [ ] T032 [US4] Verify every conversation/session-resume handler returns `404` (not `403`) on ownership failure, never discloses existence, and sources `user_id` only from the validated token in `main.py`
- [ ] T033 [US4] Confirm conversation ids are server-generated UUIDs (non-enumerable) on all create paths in `session_orchestration.py`

**Checkpoint**: Per-user isolation verified end to end.

---

## Phase 7: User Story 5 - Delete a Conversation (Priority: P2)

**Goal**: A user can delete a conversation, removing its index entry and its stored messages.

**Independent Test**: Delete from the pane → it disappears from the list and `GET /api/conversations/{id}/messages` returns `404`.

### Tests for User Story 5

- [ ] T034 [P] [US5] API test (`emulator`-backed — assert messages are actually gone from `chat-history` after delete): `DELETE /api/conversations/{id}` clears messages + removes the index doc, returns `404` for non-owner, and is idempotent, in `tests/test_conversations_api.py`

### Implementation for User Story 5

- [ ] T035 [US5] Add `DELETE /api/conversations/{id}` in `main.py`: ownership check → `history_provider.clear(id)` → `repo.delete(user_id, id)`, with retryable `503` on partial failure (FR-018)
- [ ] T036 [US5] Clarify that `DELETE /api/sessions/{id}` performs runtime cleanup only (does not delete durable history) in `main.py`
- [ ] T037 [US5] Add `deleteConversation(id)` to `frontend/src/api/client.ts` and wire the Sidebar delete control to call it, refresh the list, and reset to a new chat when the active conversation is deleted, in `frontend/src/api/client.ts` and `frontend/src/components/Sidebar.tsx`

**Checkpoint**: Deletion works and is owner-scoped.

---

## Phase 8: User Story 6 - Works Locally Without Cloud Cosmos (Priority: P3)

**Goal**: The app runs locally and tests pass with no provisioned cloud Cosmos account.

**Independent Test**: With no `AZURE_COSMOS_ENDPOINT`, the backend starts and chat works; `uv run pytest` passes offline.

### Tests for User Story 6

- [ ] T038 [P] [US6] Test: full conversation flow (create/list/resume/delete) works against the in-memory fallback with no `AZURE_COSMOS_ENDPOINT`, in `tests/test_cosmos_memory.py`

### Implementation for User Story 6

- [ ] T039 [US6] Emit a single startup warning when Cosmos is unconfigured (durable memory disabled) without hard-failing, in `cosmos_memory.py`/`main.py`
- [ ] T040 [US6] Confirm the default `uv run pytest` run passes fully offline (the `emulator` marker is deselected when the emulator is unreachable) with the fallback path exercised by CI-safe fakes, adjusting fixtures/markers in `tests/conftest.py` and `pyproject.toml` if needed

**Checkpoint**: Local/dev/test workflow is cloud-free.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Production infrastructure, cleanup, security, and verification spanning stories.

- [ ] T041 [P] Create `infra/modules/cosmos/{main.tf,variables.tf,outputs.tf}`: Cosmos DB for NoSQL account (Azure Government, serverless), database, and two containers (partition keys `/session_id` and `/user_id`), with local (key) auth disabled in production
- [ ] T042 Add the **Cosmos DB Built-in Data Contributor** data-plane SQL role assignment for the app's user-assigned managed identity in `infra/modules/cosmos/main.tf` (depends on T041)
- [ ] T043 Instantiate the cosmos module, pass endpoint/db/container into the app-service module, and expose account outputs in `infra/main.tf`, `infra/variables.tf`, `infra/outputs.tf` (depends on T041)
- [ ] T044 Accept and set `AZURE_COSMOS_ENDPOINT`/`AZURE_COSMOS_DATABASE_NAME`/`AZURE_COSMOS_CONTAINER_NAME` app settings (no key in production) in `infra/modules/app-service` (depends on T043)
- [ ] T045 [P] Remove dead localStorage conversation code (`webagents_conversation_*` keys, blob save) from `frontend/src/hooks/useConversationStore.ts` and `frontend/src/hooks/useConversationPersistence.ts`
- [ ] T046 [P] Create `scripts/capture_cosmos_chat_pane_screenshots.py` (Playwright, system Chrome, `--base-url` arg) for chat-pane visual verification
- [ ] T047 Run the Visual Verification Protocol: `cd frontend && npm run build`, capture chat-pane states (populated list, empty, loading/error, resumed) to `screenshots/011-cosmos-agent-memory/`, and review each (depends on T046 and the frontend stories)
- [ ] T048 [P] Security check: grep the built bundle (`frontend/dist/`) and runtime logs and confirm no Cosmos key/connection string appears there, in API responses, or in `cosmos_memory.py` log statements (SC-007)
- [ ] T049 Run [quickstart.md](quickstart.md) end-to-end validation (US1–US6 verification steps), including the Cosmos emulator integration suite (`uv run pytest -m emulator`)
- [ ] T050 [P] Register the `emulator` pytest marker in `pyproject.toml` and add `scripts/run_emulator_tests.sh` (starts/uses the Azure Cosmos DB Emulator container, exports `AZURE_COSMOS_EMULATOR_ENDPOINT`/`AZURE_COSMOS_KEY`, then runs `uv run pytest -m emulator`); document the emulator test workflow in `quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: depends on Setup — **blocks all user stories**.
- **User Stories (Phases 3–8)**: all depend on Foundational. The P1 stories are layered (US2/US3/US4/US5 read or gate the index/messages that US1 establishes), so the recommended order is US1 → US2 → US3 → US4 → US5 → US6.
- **Polish (Phase 9)**: depends on the targeted user stories being complete (infra can be built in parallel earlier, but verification tasks T047/T049 need the stories done).

### User Story Dependencies

- **US1 (P1)**: needs only Foundational. Establishes session-id control + index doc creation + resume + turn persistence (the memory engine).
- **US2 (P1)**: needs Foundational; reads the index US1 writes (list endpoint + pane).
- **US3 (P1)**: needs Foundational; resumes/reads messages (uses US1's session-id/ownership; adds the messages endpoint + frontend resume).
- **US4 (P1)**: hardens/verifies the ownership checks used by US1/US2/US3/US5.
- **US5 (P2)**: needs Foundational; deletes index + messages (uses ownership helper).
- **US6 (P3)**: validates the fallback path baked into Foundational.

### Within Each User Story

- Tests are written first and should fail before implementation.
- Backend storage/services before endpoints; types before API client before hooks before components.
- Story complete and independently testable before moving to the next priority.

### Parallel Opportunities

- Setup: T002 [P] alongside T001.
- Foundational: T010 [P] and T008 [P] can proceed alongside the `cosmos_memory.py` work (T003–T007 are sequential — same file).
- Tests (T011/T012, plus each story's [P] test) can be authored in parallel with each other where they are in different files.
- Frontend type task T020 [P] and API task T027 [P] can start before their dependent hook/component tasks.
- Polish: T041/T045/T046/T048/T050 [P] are independent files.

---

## Parallel Example: User Story 1

```text
# Author the US1 tests together (different files):
Task: "Unit test provider selection + repo create/get in tests/test_cosmos_memory.py"   # T011
Task: "Emulator integration test memory-across-restart in tests/test_session_orchestration.py"  # T012

# Then implement sequentially within session_orchestration.py / main.py (shared files):
T013 → T014 → T015 → T016 → T017
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (critical) → 3. Phase 3 US1.
4. **STOP and VALIDATE**: durable memory across restarts (SC-001). Demo the MVP.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 (memory) → US2 (list) → US3 (resume) → US4 (isolation) → US5 (delete) → US6 (local).
3. Each story is an independently testable increment; Polish (infra + visual + security + quickstart) finalizes for deployment.

### Parallel Team Strategy

After Foundational: one developer can carry US1→US3 (backend memory/endpoints) while another builds the frontend pane (US2/US3 frontend) and a third prepares the Terraform `cosmos` module (T041–T044) in parallel; converge on US4 isolation verification and Phase 9 validation.

---

## Summary

- **Total tasks**: 50 (Setup 2, Foundational 8, US1 7, US2 6, US3 6, US4 4, US5 4, US6 3, Polish 10)
- **MVP scope**: Phase 1 + Phase 2 + Phase 3 (US1) — durable agent memory across restarts
- **Tests**: included in two tiers — unit tests with in-memory fakes (offline) + integration tests against the local Azure Cosmos DB Emulator (`emulator` marker; auto-skips when unavailable)
- **Independent test criteria**: stated per story (Goal + Independent Test)
- **Key parallel opportunities**: cross-file foundational tasks (T008/T010), per-story test files, frontend types/client ahead of hooks/components, and the Terraform module alongside backend work
