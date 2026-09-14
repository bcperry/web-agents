# Web-Agents Development Guidelines

## Active Technologies
- Python 3.12 (pinned to 3.12.6 in `pyproject.toml`)
- agent-framework-core, agent-framework-openai, agent-framework-azure-ai-search
- FastAPI + uvicorn (backend)
- TypeScript 5.x, React 19, Vite 8 (frontend)
- Azure SQL / Azure Synapse Analytics (read-only via pyodbc)
- Azure AI Search (RAG context provider)
- Browser localStorage (conversations, custom agents, user profile, theme)
- Python 3.12+ (backend), TypeScript (frontend) + FastAPI, React, MSAL (Azure AD auth), agent-framework (MCPStdioTool, MCPStreamableHTTPTool) (001-mcp-server-ui-improvements)
- In-memory session store (backend), localStorage (frontend custom agents) (001-mcp-server-ui-improvements)
- Python 3.12+ (backend), TypeScript (frontend) + FastAPI, React, agent-framework-core, agent-framework-azure-ai-search (002-inline-rich-content-display)
- N/A (images are transient, passed through SSE stream) (002-inline-rich-content-display)
- Python 3.12 (backend), TypeScript/React 18 (frontend) + FastAPI (backend), React + existing component library (frontend) (003-admin-page-agent-skill-builder)
- Filesystem (`skills/<name>/SKILL.md`), localStorage (custom agents — unchanged) (003-admin-page-agent-skill-builder)
- Python 3.12 (backend), TypeScript (frontend) + FastAPI, React/Vite, Terraform (azurerm ~> 4.0) (004-azd-deploy-frontend)
- Azure SQL (read-only, connection string passed via env var) (004-azd-deploy-frontend)
- Python 3.12.6 backend; TypeScript 5.9 frontend; React 19; Vite 8 + FastAPI, agent-framework-core/openai/azure-ai-search, React, MSAL, localStorage APIs (005-baked-agent-customization)
- Browser localStorage for per-user built-in agent overrides; existing `config/agents.yaml` remains canonical shared standard profile source; backend in-memory sessions unchanged (005-baked-agent-customization)
- TypeScript 5.9 frontend; React 19; Python 3.12.6 backend unchanged + React, Vite 8, existing frontend API client, existing FastAPI skill endpoints, Playwright for visual verification (006-admin-skills-design-match)
- Existing filesystem-backed skills under `skills/<name>/SKILL.md`; no new storage (006-admin-skills-design-match)
- Python 3.12.6, TypeScript 5.9, React 19 + FastAPI, agent-framework-core/openai/azure-ai-search, Azure SDKs, React, Vite, react-markdown, MSAL (007-application-refactor)
- In-memory backend sessions, file-backed `skills/`, browser localStorage, Terraform-managed Azure App Service resources (007-application-refactor)
- Python 3.12+ (backend), TypeScript / React 18 (frontend) + FastAPI, `agent-framework-core` (`Agent.as_tool()`), `agent-framework-azure-ai-search`, OpenAIChatClient (Azure OpenAI Government endpoint), React, Vite (008-agents-as-tools)
- Built-in agents → `config/agents.yaml`. Custom agents → frontend `localStorage` (key `webagents_custom_agents`). No backend custom-agent store today; the new field is purely additive to the existing in-memory / localStorage shapes. (008-agents-as-tools)
- Python 3.12+ (backend), TypeScript (frontend) + FastAPI (backend), React (frontend), Vite (bundler) (009-agents-page-grouping)
- `config/agents.yaml` (built-in), localStorage (custom agents) (009-agents-page-grouping)
- TypeScript 5.9.x and React 19.x for frontend; Python 3.12.6/FastAPI backend unchanged + React, Vite, existing `useTheme` and `useAuth` hooks; no new dependencies (010-admin-settings-page)
- Existing localStorage key `webagents_theme`; no backend storage changes (010-admin-settings-page)
- Python 3.12.6 (FastAPI backend); TypeScript 5.9.x + React 19.x (frontend) + `agent-framework-core`/`agent-framework-openai` (existing); NEW `agent-framework-azure-cosmos` (provides `CosmosHistoryProvider`, re-exported as `agent_framework.azure.CosmosHistoryProvider`); `azure-cosmos` (async SDK, pulled in by the provider); `azure-identity` (`DefaultAzureCredential`, already used) (011-cosmos-agent-memory)
- Azure Cosmos DB for NoSQL — one database, two containers: `chat-history` (messages, partition key `/session_id`, managed by `CosmosHistoryProvider`) and `conversations` (per-user index, partition key `/user_id`, managed by new backend code). Local dev/tests use a Cosmos key/emulator or an in-memory fallback (011-cosmos-agent-memory)
- Python 3.12.6 backend; existing TypeScript/React frontend contracts remain + FastAPI, Pydantic, Agent Framework function tools, async Azure Cosmos DB (014-agent-creation-tools)
- Existing `agent-memory` Cosmos database. Custom agents remain in `custom-agents` (014-agent-creation-tools)
- Python 3.12+ (backend), TypeScript 5.9 / React 19 (frontend) + FastAPI, `agent-framework-core`, `azure-cosmos` (async), Vite 8 — **no new runtime dependencies in either tier** (016-agent-ui-pane)
- Azure Cosmos DB — new `agent-views` container partitioned by `/user_id` (mirrors `user-profiles`) (016-agent-ui-pane)
- Python 3.12.6; Terraform with AzureRM ~> 4.0; Google Cloud IaC language/repository to be confirmed with its network owner. + Existing FastAPI and Agent Framework runtime; one SAP HANA client selected by the driver spike (`hdbcli` or SAP HANA Client ODBC + existing `pyodbc`); no frontend dependency. (015-sap-hana-private-connectivity)

## Project Structure

```text
main.py                   # FastAPI app entry point
agent_factory.py          # Agent creation and runtime configuration
tools.py                  # Backend tool implementations (SQL, user profile, table usage)
prompt_config.py          # Agent profile loading from agents.yaml
mcp_servers.py            # MCP server and Azure AI Search configuration
auth.py                   # Azure AD authentication
config/agents.yaml        # Agent profile definitions
frontend/                 # React/TypeScript SPA
tests/                    # pytest test suite
infra/                    # Terraform infrastructure
```

## Commands

```bash
uv sync                           # Install backend dependencies
cd frontend && npm install         # Install frontend dependencies
cd frontend && npm run build       # Build frontend
uv run uvicorn main:app --reload   # Run backend
uv run pytest                      # Run tests
```

## Code Style
- Python: standard conventions, type hints
- TypeScript: strict mode, functional React components
- Package manager: uv only (never pip)

## Recent Changes
- 016-agent-ui-pane: Added Python 3.12+ (backend), TypeScript 5.9 / React 19 (frontend) + FastAPI, `agent-framework-core`, `azure-cosmos` (async), Vite 8 — **no new runtime dependencies in either tier**
- 015-sap-hana-private-connectivity: Added Python 3.12.6; Terraform with AzureRM ~> 4.0; Google Cloud IaC language/repository to be confirmed with its network owner. + Existing FastAPI and Agent Framework runtime; one SAP HANA client selected by the driver spike (`hdbcli` or SAP HANA Client ODBC + existing `pyodbc`); no frontend dependency.
- 014-agent-creation-tools: Added Python 3.12.6 backend; existing TypeScript/React frontend contracts remain + FastAPI, Pydantic, Agent Framework function tools, async Azure Cosmos DB
- 011-cosmos-agent-memory: Added Python 3.12.6 (FastAPI backend); TypeScript 5.9.x + React 19.x (frontend) + `agent-framework-core`/`agent-framework-openai` (existing); NEW `agent-framework-azure-cosmos` (provides `CosmosHistoryProvider`, re-exported as `agent_framework.azure.CosmosHistoryProvider`); `azure-cosmos` (async SDK, pulled in by the provider); `azure-identity` (`DefaultAzureCredential`, already used)
