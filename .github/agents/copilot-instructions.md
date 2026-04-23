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
- 001-mcp-server-ui-improvements: Added Python 3.12+ (backend), TypeScript (frontend) + FastAPI, React, MSAL (Azure AD auth), agent-framework (MCPStdioTool, MCPStreamableHTTPTool)
