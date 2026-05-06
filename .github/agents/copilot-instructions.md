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
- 006-admin-skills-design-match: Added TypeScript 5.9 frontend; React 19; Python 3.12.6 backend unchanged + React, Vite 8, existing frontend API client, existing FastAPI skill endpoints, Playwright for visual verification
- 005-baked-agent-customization: Added Python 3.12.6 backend; TypeScript 5.9 frontend; React 19; Vite 8 + FastAPI, agent-framework-core/openai/azure-ai-search, React, MSAL, localStorage APIs
- 004-azd-deploy-frontend: Added Python 3.12 (backend), TypeScript (frontend) + FastAPI, React/Vite, Terraform (azurerm ~> 4.0)
