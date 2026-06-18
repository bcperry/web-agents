# Implementation Plan: Azure Cosmos DB Agent Memory Layer

**Branch**: `011-cosmos-agent-memory` | **Date**: 2026-06-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/011-cosmos-agent-memory/spec.md`

## Summary

Replace browser-stored conversation history with a server-side memory layer backed by Azure Cosmos DB (SQL/NoSQL API), integrated through Microsoft Agent Framework's `CosmosHistoryProvider`. Conversation messages are persisted per conversation (partition key `/session_id`) by the framework provider, giving agents durable per-user/per-agent memory that survives process restarts. A second Cosmos container holds a per-user conversation index (partition key `/user_id`) that powers the left chat pane and enforces ownership. New backend endpoints (`/api/conversations`) let the frontend read the user's real conversations and messages from Cosmos; the frontend stops using `localStorage` as the source of truth for history. Cosmos is provisioned via Terraform with Managed Identity (RBAC) in production and a key/emulator path for local development.

The integration is intentionally "seamless": `CosmosHistoryProvider` subclasses the same `HistoryProvider` base as the current `InMemoryHistoryProvider` (it exposes the same `source_id` contract the existing `CompactionProvider` depends on), so it drops into the existing `agent_factory._build_context_providers` pipeline. The session identifier the backend already controls becomes the Cosmos partition key for messages.

## Technical Context

**Language/Version**: Python 3.12.6 (FastAPI backend); TypeScript 5.9.x + React 19.x (frontend)  
**Primary Dependencies**: `agent-framework-core`/`agent-framework-openai` (existing); NEW `agent-framework-azure-cosmos` (provides `CosmosHistoryProvider`, re-exported as `agent_framework.azure.CosmosHistoryProvider`); `azure-cosmos` (async SDK, pulled in by the provider); `azure-identity` (`DefaultAzureCredential`, already used)  
**Storage**: Azure Cosmos DB for NoSQL — one database, two containers: `chat-history` (messages, partition key `/session_id`, managed by `CosmosHistoryProvider`) and `conversations` (per-user index, partition key `/user_id`, managed by new backend code). Local dev/tests use a Cosmos key/emulator or an in-memory fallback  
**Testing**: `uv run pytest` (backend) in two tiers — fast unit tests with in-memory Cosmos fakes (offline default), plus integration tests against the local Azure Cosmos DB Emulator (`emulator` marker; auto-skips when unreachable) covering the real provider, partition keys, ownership, resume, and delete; `npm run build` + Playwright visual verification (frontend chat pane)  
**Target Platform**: Browser SPA served by FastAPI as a single Azure App Service deployment (Azure Government)  
**Project Type**: Two-tier web application (Python backend at repo root, React frontend in `frontend/`)  
**Performance Goals**: Conversation-list load and per-conversation message read perceptibly immediate (single-partition Cosmos queries); message-send latency dominated by the LLM call, not by history persistence; history persistence is incremental (append per turn), not full-blob rewrites  
**Constraints**: Azure Government endpoints only (`*.documents.azure.us`); Managed Identity/RBAC in production (no keys); frontend never contacts Cosmos directly; no secrets in logs/responses/bundle; `uv` only for backend deps; existing chat/streaming/tool/image behavior must not regress; UI changes require Playwright screenshots at desktop/tablet/mobile  
**Scale/Scope**: Multi-user; per-user conversation lists from a handful up to many dozens of conversations; per-conversation message counts in the typical chat range (well under the 20 GB logical-partition limit per conversation and per user index)

**Resolved unknowns** (see [research.md](research.md) for rationale): throughput mode (serverless), credential strategy (Managed Identity prod / key local), local-dev fallback (in-memory provider when Cosmos unconfigured), title derivation (first user message), pre-existing browser conversation handling (ignored, no auto-migration), and Cosmos compaction interaction. No open `NEEDS CLARIFICATION` items remain.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Read-Only Data Access (SQL) | N/A | The read-only constraint governs the agent's Azure SQL tool access. This feature adds Cosmos as a memory store; it introduces no SQL data mutation and does not relax the SQL read-only rule. Cosmos writes are conversation-memory persistence, scoped to the authenticated user. |
| II. Single-File Agent Definitions | PASS | No agent profiles or tool docs move to YAML; the change is in the history-provider wiring and a new persistence module. `agents.yaml` is unchanged. |
| III. Security & Credential Hygiene | PASS (gated) | Managed Identity/RBAC in prod, key only for local; Azure Gov endpoints; ownership checks on every conversation operation; unguessable conversation ids; no secrets logged or sent to the frontend. Enforced by FR-008/009/013/014/017. |
| IV. Evaluation-Driven Quality | PASS | No prompt/model/parameter changes. Memory persistence can influence multi-turn outputs, so the eval pipeline remains the gate for any subsequent prompt/model change; this feature itself ships no agent-behavior config change. |
| V. Simplicity & Minimalism | PASS | Reuses the built-in `CosmosHistoryProvider` instead of a custom provider; adds the minimum (one dependency, one persistence module, one Terraform module, four endpoints). Two containers are justified by two distinct access patterns (per-session messages vs. per-user index) — see Complexity Tracking. |
| VI. Infrastructure as Code | PASS (gated) | Cosmos account/database/containers and the managed-identity data-plane role assignment are provisioned via a new Terraform module under `infra/`. No portal-created resources. Enforced by FR-015. |
| VII. Two-Tier API-First Architecture | PASS | Frontend reads conversations only through new backend REST endpoints; the backend is the sole gateway to Cosmos. No direct frontend-to-Azure calls. Contracts documented in `contracts/`. |

**Gate result**: PASS — no violations requiring justification. Security and IaC principles are satisfied by explicit requirements and the Terraform module; verification occurs during implementation and visual/security review.

## Project Structure

### Documentation (this feature)

```text
specs/011-cosmos-agent-memory/
├── plan.md              # This file
├── research.md          # Phase 0 output — decisions & rationale
├── data-model.md        # Phase 1 output — Cosmos containers & entities
├── quickstart.md        # Phase 1 output — setup, local dev, verification
├── contracts/
│   ├── conversations-api.md   # New REST endpoints for the conversation index + messages
│   └── cosmos-memory-integration.md  # Backend provider/repository integration contract
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
# Backend (repository root)
cosmos_memory.py            # NEW: CosmosHistoryProvider factory + conversation-index repository
                            #      (list/get/upsert/delete index docs, ownership checks, fallback)
agent_factory.py            # MODIFY: _build_context_providers swaps InMemoryHistoryProvider ->
                            #         CosmosHistoryProvider when Cosmos is configured (in-memory fallback otherwise)
session_orchestration.py    # MODIFY: on create, generate session_id + write conversation index doc bound to user_id;
                            #         on resume, rebuild AgentSession with existing session_id (ownership-checked);
                            #         drop reliance on client-supplied history blob
main.py                     # MODIFY: add /api/conversations endpoints (list/get-messages/delete);
                            #         update message "done" handling to bump last_activity_at + title
auth.py                     # REUSE: AuthenticatedUser.user_id (oid) is the ownership/partition key (no change expected)

tests/
├── test_cosmos_memory.py            # NEW: provider factory + index repository (faked Cosmos) + fallback
├── test_conversations_api.py        # NEW: list/get/delete endpoints + per-user isolation/ownership
├── test_session_orchestration.py    # MODIFY: resume-by-id, index doc creation, no-blob path
└── conftest.py                      # MODIFY: fixtures/fakes for Cosmos data path

# Frontend (frontend/)
frontend/src/
├── api/
│   └── client.ts                    # MODIFY: add listConversations/getConversation(messages)/deleteConversation;
│                                    #         resume by conversation_id instead of posting a history blob
├── hooks/
│   ├── useConversationStore.ts      # REPLACE: server-backed conversation index/messages (was localStorage)
│   ├── useConversationPersistence.ts# MODIFY: stop writing full conversations to localStorage; server persists
│   ├── useSessionLifecycle.ts       # MODIFY: resume via conversation_id; load messages from API
│   └── useChat.ts                   # MODIFY: align save/resume flow to server-sourced history
├── components/
│   └── Sidebar.tsx                  # MODIFY: render server conversations with loading/empty/error states
├── pages/
│   └── ChatPage.tsx                 # MODIFY: fetch conversation list from API; select -> load from server
└── types/
    └── api.ts                       # MODIFY: conversation/message types aligned to new API responses

# Infrastructure (infra/)
infra/
├── main.tf                          # MODIFY: instantiate cosmos module; pass endpoint/db/container env to app-service
├── variables.tf                     # MODIFY: cosmos-related variables (name, throughput mode, db/container names)
├── outputs.tf                       # MODIFY: expose cosmos endpoint/account name as outputs
└── modules/
    ├── cosmos/                      # NEW: Cosmos DB account (Gov), database, 2 containers, RBAC role assignment
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    └── app-service/                 # MODIFY: accept + set AZURE_COSMOS_ENDPOINT/DATABASE_NAME/CONTAINER_NAME app settings

screenshots/
└── 011-cosmos-agent-memory/         # Visual verification captures (chat pane states)
```

**Structure Decision**: Two-tier web application. The backend gains one new module (`cosmos_memory.py`) plus targeted edits to agent/session/route wiring; the frontend replaces its localStorage persistence hooks with server-backed equivalents; infrastructure gains a Cosmos module and app-settings wiring. The Agent Framework `CosmosHistoryProvider` is used directly (no custom provider), keeping the surface minimal per Principle V.

## Phase 0: Research

Research completed in [research.md](research.md). All Technical Context unknowns are resolved with decisions and rationale (throughput mode, credential strategy, local fallback, two-container model, title derivation, ordering/partitioning, Azure Government configuration, compaction interaction, and pre-existing browser data handling). No open clarification items remain.

## Phase 1: Design & Contracts

Design artifacts completed:

- [data-model.md](data-model.md) — Cosmos database/containers, document schemas, partition keys, ownership/indexing model, and how framework-managed message docs relate to the conversation index.
- [contracts/conversations-api.md](contracts/conversations-api.md) — new REST endpoints (`GET /api/conversations`, `GET /api/conversations/{id}/messages`, `DELETE /api/conversations/{id}`) and the changed session create/resume contract.
- [contracts/cosmos-memory-integration.md](contracts/cosmos-memory-integration.md) — backend provider/repository integration contract: how `CosmosHistoryProvider` is constructed and wired into `_build_context_providers`, the conversation-index repository interface, and the local-dev fallback.
- [quickstart.md](quickstart.md) — provisioning, environment variables, local-dev (key/emulator/fallback), and end-to-end verification steps including the Visual Verification Protocol.

The agent context file is refreshed via `.specify/scripts/bash/update-agent-context.sh copilot` to record the new Cosmos technology in the active technologies list.

## Constitution Check - Post-Design

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Read-Only Data Access (SQL) | N/A | Design adds Cosmos memory persistence only; SQL tool access remains read-only and unchanged. |
| II. Single-File Agent Definitions | PASS | Design keeps agent/tool definitions in code/`agents.yaml`; persistence lives in `cosmos_memory.py`. |
| III. Security & Credential Hygiene | PASS | Data model and contracts mandate ownership-scoped queries (partition by `user_id`, ownership check before message reads), Managed Identity in prod, Gov endpoints, and no secret exposure. |
| IV. Evaluation-Driven Quality | PASS | No prompt/model/parameter changes in the design. |
| V. Simplicity & Minimalism | PASS | Built-in provider reused; two containers justified by distinct access patterns; no speculative abstractions. |
| VI. Infrastructure as Code | PASS | Cosmos module + RBAC assignment + app settings all in Terraform; no manual provisioning. |
| VII. Two-Tier API-First Architecture | PASS | All Cosmos access is backend-only via documented REST contracts; frontend consumes the API. |

**Gate result**: PASS — no violations.

## Complexity Tracking

No constitution violations require justification. One design choice merits a brief note:

| Choice | Why Needed | Simpler Alternative Rejected Because |
|--------|------------|--------------------------------------|
| Two Cosmos containers (`chat-history` partitioned by `/session_id`, `conversations` partitioned by `/user_id`) | The framework provider owns message storage partitioned by session, but the left pane needs an ownership-scoped, per-user list with titles/timestamps that the provider does not maintain | A single container cannot serve both access patterns efficiently: per-user listing would require cross-partition scans of a session-partitioned container, and shoe-horning index metadata into message docs breaks the provider's managed schema. Two purpose-built containers keep each query single-partition and isolation simple. |
