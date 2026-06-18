# Quickstart: Azure Cosmos DB Agent Memory Layer

**Feature**: `011-cosmos-agent-memory` | **Date**: 2026-06-18

How to configure, run, and verify the Cosmos-backed memory layer locally and in Azure (Government). Follow the project's package rules: backend deps via `uv` only; frontend via `npm`.

## Prerequisites

- Python 3.12.6, `uv`, Node toolchain (`npm`) — as today.
- For cloud: an Azure Government subscription and Terraform configured for the `usgovernment` cloud.
- For full-fidelity local Cosmos (optional): the Azure Cosmos DB Emulator (Docker) or a real account key.

## 1. Add the backend dependency (uv)

```bash
# from repo root
uv add agent-framework-azure-cosmos --prerelease=allow
uv sync
```

This makes `from agent_framework.azure import CosmosHistoryProvider` importable (it raises a clear error until the package is present) and pulls in the `azure-cosmos` async SDK.

## 2. Choose a storage mode

The backend selects its memory path from `AZURE_COSMOS_ENDPOINT`:

| Mode | When | Effect |
|------|------|--------|
| Not configured | `AZURE_COSMOS_ENDPOINT` unset | Backend **fails fast at startup** — there is no in-memory fallback. |
| Cosmos emulator (key) | local dev/test | Durable, full-fidelity persistence locally using `AZURE_COSMOS_KEY`. **Required for local runs.** |
| Cosmos + Managed Identity | Azure deployment | Durable persistence via RBAC; no key. |

### 2a. Cosmos is required (no in-memory fallback)

The backend will not start unless Cosmos is configured. Locally, run the emulator (§2b) and set `AZURE_COSMOS_ENDPOINT`; when deployed, Terraform wires the real account. If `AZURE_COSMOS_ENDPOINT` is unset, startup fails fast with a clear error.

### 2b. Local with the Azure Cosmos DB Emulator (durable local + integration tests)

Start the emulator (Docker), then point the app and tests at it. The emulator uses a fixed, publicly documented key and a self-signed TLS cert, so async clients set `connection_verify=False` locally.

```bash
# start the Linux Azure Cosmos DB Emulator (NoSQL API)
docker run -d --name cosmos-emulator -p 8081:8081 -p 10250-10255:10250-10255 \
  mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:latest

# well-known emulator endpoint + key (public; identical for every emulator instance)
export AZURE_COSMOS_ENDPOINT="https://localhost:8081/"
export AZURE_COSMOS_EMULATOR_ENDPOINT="https://localhost:8081/"
export AZURE_COSMOS_KEY="C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
export AZURE_COSMOS_DATABASE_NAME="agent-memory"
export AZURE_COSMOS_CONTAINER_NAME="chat-history"
export AZURE_COSMOS_CONVERSATIONS_CONTAINER="conversations"
AUTH_DISABLED=true uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The provider creates the messages container if missing; the backend ensures the `conversations` container exists. The `AZURE_COSMOS_KEY` above is Microsoft's public well-known emulator key (not a secret) — production never uses a key. For parity with production, prefer provisioning via Terraform (below).

## 3. Provision Azure resources (Terraform)

The `infra/modules/cosmos` module creates the account (NoSQL, serverless, Azure Gov), the database, both containers (partition keys `/session_id` and `/user_id`), and the **Cosmos DB Built-in Data Contributor** data-plane role assignment for the app's user-assigned managed identity. `main.tf` passes the endpoint/db/container names into the `app-service` module as app settings.

```bash
cd infra
terraform init
terraform plan   -var-file=main.tfvars.json
terraform apply  -var-file=main.tfvars.json
```

Expected outputs (added in `outputs.tf`): the Cosmos account endpoint and name. The app service receives `AZURE_COSMOS_ENDPOINT`, `AZURE_COSMOS_DATABASE_NAME`, and `AZURE_COSMOS_CONTAINER_NAME` (no key). Production keeps account-key (local) auth disabled.

> Reminder (terraform + azd): never feed Terraform outputs back as inputs for the same resource; keep user-set inputs (names, throughput mode) as separate variables.

## 4. Build the frontend and run

```bash
cd frontend && npm install && npm run build && cd ..
AUTH_DISABLED=true uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

The left chat pane now loads conversations from `GET /api/conversations` instead of `localStorage`.

## 5. End-to-end verification (maps to user stories)

Run these against `http://localhost:8000` (use the cloud URL for a deployed check). With `AUTH_DISABLED=true`, a dev user identity is used; for isolation tests, run with auth enabled and two accounts.

1. **Agent memory across restarts (US1, SC-001)**
   - Start a chat; tell the agent a fact ("My project is codenamed Falcon").
   - Restart the backend process.
   - Resume the same conversation; ask "What's my project codename?" → agent answers "Falcon".
2. **Left pane lists real chats (US2, SC-002)**
   - Hold two or three conversations.
   - Open the app in a second browser/profile signed in as the same user → the same list appears, newest first.
   - Confirm via dev tools that the list comes from `/api/conversations` (network), not `localStorage`.
3. **Resume with full history (US3)**
   - Click a past conversation → prior messages render; send a context-dependent follow-up → correct, context-aware reply; the new turn is appended.
4. **Per-user isolation (US4, SC-003)** — auth enabled, users A and B
   - As A, create a conversation; note its `id`.
   - As B, call `GET /api/conversations/{id}/messages`, `POST /api/sessions` (resume that id), and `DELETE /api/conversations/{id}` → each returns `404`; A's conversation is unchanged.
   - `GET /api/conversations` as B never includes A's conversation.
5. **Delete (US5, SC-005)**
   - Delete a conversation from the pane → it disappears from the list; `GET /api/conversations/{id}/messages` returns `404`.
6. **Cosmos required locally (US6, SC-006)**
   - With no `AZURE_COSMOS_ENDPOINT`, the backend **fails fast** (no fallback). With the emulator configured it persists durably. `uv run pytest` passes using injected in-memory doubles.
7. **No secret leakage (SC-007)**
   - Grep logs and the built bundle for any key/connection string → none present.

## 6. Tests

Two tiers — fast unit tests (in-memory fakes, always run) and integration tests against the local Cosmos emulator (real provider/containers):

```bash
# unit tier — no emulator needed (emulator tests deselected by default)
uv run pytest -q

# integration tier — requires the running Cosmos emulator (see 2b)
uv run pytest -m emulator -q
```

The unit tier covers provider selection (Cosmos required, else raises), conversation create/list/get/touch/delete, ownership/isolation, resume-by-id, and turn-completion metadata updates with injected in-memory doubles. The `emulator` tier re-runs the durable paths against the real emulator — verifying `/session_id` and `/user_id` partition behavior, real queries (list ordering, ownership reads), resume reload, and delete — and skips when the emulator data plane is unreachable.

## 7. Visual verification (constitution — required for UI changes)

The chat pane changes are UI-affecting, so capture and review screenshots after `npm run build`:

```bash
# the API is mocked by the script, but the app requires Cosmos config to start
AUTH_DISABLED=true AZURE_COSMOS_ENDPOINT=https://localhost:8081/ AZURE_COSMOS_KEY=dummy uv run uvicorn main:app --host 0.0.0.0 --port 8000 &
# capture chat-pane states with Playwright (system Chrome at /usr/bin/google-chrome)
uv run python scripts/capture_cosmos_chat_pane_screenshots.py --base-url http://localhost:8000
```

Capture and visually review: conversation list populated, empty state (new user), loading/error state, and a resumed conversation with prior messages. Save under `screenshots/011-cosmos-agent-memory/`. Re-run after any fix. Use text indicators (no emoji) in any new UI labels.

## 8. Rollback / disable

- There is no non-durable fallback: if Cosmos is unreachable the app surfaces retryable `503`s; if `AZURE_COSMOS_ENDPOINT` is unset the app fails to start. "Disabling" memory is not a supported mode — fix Cosmos instead.
- Cosmos data is unaffected by app restarts; deletion is only via `DELETE /api/conversations/{id}` or Terraform-managed teardown.
