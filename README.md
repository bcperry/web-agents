# Web-Agents

AI agent framework using [agent-framework](https://pypi.org/project/agent-framework/) with Azure OpenAI. Two-tier architecture: **FastAPI** backend + **React/TypeScript** frontend served as static files from the same origin.

## Portfolio summary

- **Ownership:** Sole architect and accountable engineer for the application, orchestration, security model, persistence, scheduler, tests, and cloud deployment.
- **Agent platform:** Configurable SQL, Azure AI Search, and hybrid agents; agents-as-tools delegation; visible tool calls; and SSE-streamed responses.
- **Enterprise design:** Microsoft Entra ID, per-user Cosmos DB persistence, ownership validation, audit trails, managed cloud configuration, and Azure Government deployment validation.
- **Autonomous operation:** Durable user-defined automations with schedules, notification sinks, and Cosmos lease-based at-most-once execution.
- **Engineering:** Python, FastAPI, React, TypeScript, Microsoft Agent Framework, pytest, Playwright, Azure App Service, and infrastructure automation.

## Overview

- AI agent with multiple configurable profiles: SQL queries, Azure AI Search, Hybrid
- Custom agent builder for creating new profiles on the fly
- Agents-as-tools: any agent can declare other agents (built-in or custom) as tools it can delegate to (see [specs/008-agents-as-tools/](specs/008-agents-as-tools/spec.md))
- SSE-streamed chat responses with tool invocation visibility
- Image upload support (JPEG, PNG, GIF, WebP)
- Azure AD authentication with local dev bypass
- Token usage tracking per turn and per session
- User profile persistence across sessions
- Optional create/edit tools for durable, user-owned skills and agents
- Profile-specific starter questions

## Architecture

```
┌──────────────────────────────────────────┐
│             Azure App Service            │
│                                          │
│  FastAPI (uvicorn)                       │
│  ├── /api/*          REST + SSE API      │
│  ├── /assets/*       Vite build output   │
│  └── /*              React SPA (static)  │
│                                          │
│  frontend/dist/      Built by Vite       │
└──────────────────────────────────────────┘
```

## Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- ODBC Driver 18 for SQL Server (if using SQL profiles)
- Azure OpenAI account with deployed model

## Installation

```bash
# Backend
uv sync

# Backend + dev tools (pytest, playwright)
uv sync --group dev

# Frontend
cd frontend
npm install
npm run build
cd ..
```

## Configuration

Create a `.env` file at the repository root:

```env
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_MODEL=gpt-4o
# Leave empty to authenticate with Entra ID (managed identity in Azure, `az login` locally).
# Requires the "Cognitive Services OpenAI User" role on the account.
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=2025-01-01-preview

# Azure SQL Database (optional — needed for SQL profiles)
# AZURE_SQL_CONNECTIONSTRING=Driver={ODBC Driver 18 for SQL Server};Server=tcp:your-server.database.net,1433;Database=your-database;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30

# Azure AI Search (optional — needed for search-enabled profiles)
# SEARCH_SERVICE_ENDPOINT=https://your-search-service.search.windows.net
# SEARCH_INDEX_NAME=your-index-name
# SEARCH_API_KEY=your-search-api-key

# Auth (set AUTH_DISABLED=true for local development without Azure AD)
AUTH_DISABLED=true
# AZURE_AD_TENANT_ID=your-tenant-id
# AZURE_AD_CLIENT_ID=your-client-id

# App branding (runtime config served by the backend)
APP_NAME=Web-Agents
APP_TAGLINE=AI Agent Framework

# Cosmos user-owned skills container (partition key /user_id)
AZURE_COSMOS_USER_SKILLS_CONTAINER=user-skills
```

The feature 015 SAP force-equipment emulator can provision a real Azure SQL database and load the
workbook-derived schema with synthetic records. It is reached over the public endpoint restricted to
the App Service outbound IPs and an optional developer IP range — private endpoints are reserved for
the real HANA target described in
[specs/015-sap-hana-private-connectivity/contracts/network-security-handoff.md](specs/015-sap-hana-private-connectivity/contracts/network-security-handoff.md).
See [database_emulator/README.md](database_emulator/README.md) for its data assumptions, opt-in
Terraform settings, migration commands, and verification query.

Frontend environment variables (for Azure AD auth in the browser) go in `frontend/.env`:

```env
VITE_AUTH_DISABLED=true
# VITE_AZURE_AD_TENANT_ID=your-tenant-id
# VITE_AZURE_AD_CLIENT_ID=your-client-id
```

## Running

```bash
# Build frontend + start backend
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000` in your browser.

## Testing

```bash
uv run pytest
```

## Agent Definition Tools

`create_skill`, `edit_skill`, `create_agent`, and `edit_agent` are independent
optional capabilities in the Admin Agent Builder. None is granted to existing or
new agents by default. Each runtime function is bound to the authenticated user
and validates the complete definition before writing. Creation uses atomic Cosmos
semantics so retries or concurrent calls never overwrite existing work; editing
requires an existing definition owned by the same user.

User-created skills appear alongside global skills only for their owner. Global
skill names remain reserved, and another user's skills or custom agents resolve
as nonexistent. The user skill store is configured with
`AZURE_COSMOS_USER_SKILLS_CONTAINER` (default `user-skills`) and is partitioned by
`/user_id`.

After building the frontend, run the focused Agent Builder browser contract with:

```bash
uv run pytest -q tests/test_agent_builder_ui.py
```

## Autonomous Mode (Duty Officer)

An **in-process scheduler** in the backend runs a pre-defined **standing directive**
(an agent profile + an instruction) on a cadence — or on demand — with no human in
the loop. It reuses the existing agent runtime and Cosmos memory (no fork of agent
logic), writes one durable **audit record** per cycle, and delivers the result to a
pluggable **notification sink**. A Cosmos **lease** keyed by `(directive, slot)`
guarantees at-most-once execution even when the backend scales out. There is **no
external trigger and no shared secret**: the schedule runs in-process and the only
HTTP entry point is the user-authenticated `POST /api/autonomous/run-now`.

- **Config**: `config/autonomous.yaml` — a master `enabled` flag, a `system_user_id`,
  and one or more `directives` (`id`, `profile_id`, `instruction`, optional `schedule`
  and `notify`). A missing file is a safe disabled no-op. Contains **no secrets**
  (webhooks are referenced by env-var name). `AUTONOMOUS_ENABLED` /
  `AUTONOMOUS_USER_ID` override the file.
- **Scheduler gate**: `AUTONOMOUS_SCHEDULER_ENABLED` (off by default locally; empty ⇒
  enabled in the deployed App Service). `run-now` works regardless of this flag.
- **Endpoints** (all normal-user auth): `POST /api/autonomous/run-now`,
  `GET /api/autonomous/runs`, `GET /api/autonomous/directives`.
- **Manage automations**: directives are durable in Cosmos (seeded from the YAML the
  first time). Enable/disable, change the schedule, and create/delete automations from
  the **Duty Officer** page, or via `POST` / `PATCH` / `DELETE /api/autonomous/directives`.
  (A YAML-default automation reappears on the next startup unless removed from the YAML.)

```bash
# Trigger one cycle on demand (first enabled directive), then inspect the audit trail:
export AUTH_DISABLED=true AUTONOMOUS_ENABLED=true
curl -s -X POST http://localhost:8000/api/autonomous/run-now -H 'Content-Type: application/json' -d '{}'
curl -s "http://localhost:8000/api/autonomous/runs?limit=10"

# Run the unattended in-process scheduler locally:
AUTONOMOUS_SCHEDULER_ENABLED=true uv run uvicorn main:app --port 8000 --reload
```

See [specs/012-autonomous-mode/quickstart.md](specs/012-autonomous-mode/quickstart.md)
for the full walkthrough (notifications, scheduler, the Duty Officer UI, and tests).

## License

See [LICENSE](LICENSE).
