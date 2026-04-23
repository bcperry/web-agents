# Quickstart: MCP Server UI Improvements

**Feature**: 001-mcp-server-ui-improvements

## What This Feature Does

1. **MCP Status Indicators** — After creating a session, the chat UI shows a compact status bar with green checkmarks (connected) or red X's (failed) for each MCP server.
2. **Failure Toasts** — When any agent's MCP server fails to connect, a warning toast notification appears listing the failed servers.
3. **Authenticated MCP Servers** — Two per-server auth modes:
   - **Passthrough** (`auth: true` in agents.yaml / `authenticated: true` in custom builder): Forward the user's Azure AD token as-is. For MCP servers sharing the same app registration.
   - **OBO** (`auth_scope` in agents.yaml / `authScope` in custom builder): Exchange the user's token via MSAL OBO flow for a token scoped to the MCP server's own app registration.

## Backend Changes

### `mcp_servers.py`
- `MCPServerConfig` gains `auth: bool = False` and `auth_scope: str | None = None`
- New `MCPConnectionResult` dataclass
- New `resolve_mcp_auth_token()` helper — passthrough returns user token; OBO exchanges via `ConfidentialClientApplication`
- `connect_mcp_servers()` returns `tuple[list[Any], list[MCPConnectionResult]]` instead of `list[Any]`
- `create_mcp_tool()` accepts optional `auth_token` and creates `httpx.AsyncClient` with auth header when needed

### `main.py`
- Session creation response includes `mcp_results` array
- Extracts bearer token from request `Authorization` header for authenticated MCP servers
- `GET /api/profiles` includes `mcp_server_count` per profile

### `config/agents.yaml`
- MCP server entries support optional `auth: true` (passthrough) and/or `auth_scope: "api://.../.default"` (OBO)

### New dependency
- `msal` Python package (for OBO token exchange) — install via `uv add msal`

### New environment variables (OBO only)
- `AZURE_AD_CLIENT_SECRET` — required for OBO token exchange

## Frontend Changes

### `types/api.ts`
- `McpServerEntry` gains optional `authenticated?: boolean` and `authScope?: string`
- New `McpConnectionResult` interface
- `SessionCreateResponse` extended with `mcp_results`

### `components/McpStatusIndicator.tsx`
- New component: renders per-server status with checkmark/X icons

### `hooks/useChat.ts`
- Stores `mcpResults` from session creation
- Emits warning toast when failures detected

### `pages/ChatPage.tsx`
- Renders `McpStatusIndicator` in chat header area

### `pages/AgentBuilder.tsx`
- Add "Authenticated" toggle (passthrough) and "Auth Scope" text field (OBO) to MCP server configuration form

## Field Name Mapping

| Concept | Backend (Python/YAML) | Frontend (TypeScript) | API Request Body |
|---------|----------------------|----------------------|------------------|
| Passthrough auth | `auth` | `authenticated` | `authenticated` |
| OBO scope | `auth_scope` | `authScope` | `auth_scope` |

## Testing

```bash
# Backend tests
uv run pytest tests/test_api.py -v

# Frontend build
cd frontend && npm run build

# Visual verification (required per constitution)
AUTH_DISABLED=true uv run uvicorn main:app --host 0.0.0.0 --port 8000
# Then run Playwright screenshots per Visual Verification Protocol
```
