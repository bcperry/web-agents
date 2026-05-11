# Web-Agents

AI agent framework using [agent-framework](https://pypi.org/project/agent-framework/) with Azure OpenAI. Two-tier architecture: **FastAPI** backend + **React/TypeScript** frontend served as static files from the same origin.

## Overview

- AI agent with multiple configurable profiles: SQL queries, Azure AI Search, Hybrid
- Custom agent builder for creating new profiles on the fly
- Agents-as-tools: any agent can declare other agents (built-in or custom) as tools it can delegate to (see [specs/008-agents-as-tools/](specs/008-agents-as-tools/spec.md))
- SSE-streamed chat responses with tool invocation visibility
- Image upload support (JPEG, PNG, GIF, WebP)
- Azure AD authentication with local dev bypass
- Token usage tracking per turn and per session
- User profile persistence across sessions
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
AZURE_OPENAI_API_KEY=your-api-key
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
```

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

## License

See [LICENSE](LICENSE).
