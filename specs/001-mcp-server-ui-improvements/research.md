# Research: MCP Server UI Improvements

**Feature**: 001-mcp-server-ui-improvements | **Date**: 2026-04-22

## R1: MCP Connection Status Reporting

### Decision: Extend session creation API response with per-server connection results

**Rationale**: The backend `connect_mcp_servers()` function already iterates over MCP configs and catches failures per-server. Currently it logs warnings and silently skips failed servers. We extend it to return structured results: `[{name, transport, status: "connected"|"failed", error?: string, tool_count?: int}]`. The session creation endpoint includes this in the response body as `mcp_results`.

**Alternatives considered**:
- **Separate `/api/mcp/status` endpoint**: Rejected — adds complexity and requires the frontend to make a second call. The connection attempt already happens at session creation time.
- **WebSocket push for MCP status**: Rejected — over-engineered for a one-time status check that naturally coincides with session creation.

### Decision: New `McpStatusIndicator` component for visual status

**Rationale**: A small, reusable component that renders a green checkmark or red X per MCP server, with the server name. Used in ChatPage after session creation. Not shown in ProfileSelector (default agents' MCP config is unknown until a session is created).

**Alternatives considered**:
- **Show MCP status in ProfileSelector cards**: Rejected — would require pre-connecting to MCP servers for all profiles at page load, which is wasteful and slow. Status is only meaningful after a session is created.

## R2: Toast Notifications for MCP Failures

### Decision: Emit warning toast in `useChat.ts` after session creation when `mcp_results` contains failures

**Rationale**: The existing `emitToast()` imperative function works outside React context and is already used for error reporting in `client.ts`. After `createSession()` returns, `useChat.ts` checks `mcp_results` for any `status: "failed"` entries and emits a warning toast listing the failed server names.

**Alternatives considered**:
- **Blocking error modal**: Rejected — MCP failures are non-fatal (agent still works with remaining tools). A warning toast is appropriate.
- **Per-server toast**: Rejected — multiple toasts for multiple failures is noisy. One consolidated toast listing all failed servers is cleaner.

## R3: Authenticated MCP Server Connections

### Decision: Two auth modes — passthrough and OBO — selected per-server via config

**Rationale**: Not all authenticated MCP servers share the same Azure AD app registration as the web-agents backend. A user's token has an `aud` claim addressed to the web-agents client ID. MCP servers with their own app registration will reject that token because the audience doesn't match. We need to support both scenarios:

1. **Passthrough** (`auth: true`): Forward the user's token as-is. Works when the MCP server shares the same Azure AD app registration (or is configured to accept the web-agents audience).
2. **OBO (On-Behalf-Of)** (`auth_scope: "api://<mcp-client-id>/.default"`): Exchange the user's token for a new token addressed to the MCP server's app registration using MSAL `ConfidentialClientApplication.acquire_token_on_behalf_of()`. Works for any MCP server with a distinct app registration.

Both modes use the `http_client` parameter on `MCPStreamableHTTPTool` — the only difference is which token ends up in the `Authorization` header.

**Implementation details**:
- `MCPServerConfig` gains `auth: bool = False` and `auth_scope: str | None = None`
- `agents.yaml` MCP entries gain optional `auth: true` and/or `auth_scope: "api://.../.default"`
- `McpServerEntry` frontend type gains optional `authenticated: boolean` and `authScope: string`
- `create_mcp_tool()` accepts an optional `auth_token: str` parameter (already resolved — passthrough or OBO-exchanged)
- New helper `resolve_mcp_auth_token()` in `mcp_servers.py`:
  - If `config.auth_scope` is set: perform OBO exchange via `ConfidentialClientApplication` (requires `AZURE_AD_CLIENT_SECRET` env var) and return the new token
  - Elif `config.auth` is true: return the user's token as-is
  - Else: return `None` (no auth)
- Session creation endpoint extracts the bearer token from the request's `Authorization` header and passes it to the resolve function
- `ConfidentialClientApplication` requires backend env vars: `AZURE_AD_CLIENT_ID` (already available), `AZURE_AD_CLIENT_SECRET` (new, for OBO), `AZURE_AD_AUTHORITY` (already available)

**Security considerations**:
- Token is only forwarded/exchanged server-side; never exposed to frontend
- Neither the user token nor the OBO token is logged (Constitution Principle III)
- Only HTTP MCP servers support auth (stdio is local, no auth needed)
- `AZURE_AD_CLIENT_SECRET` is a backend-only env var, never in frontend bundles
- OBO token has a narrower scope (only what the MCP server's app registration allows)

**Alternatives considered**:
- **Passthrough only**: Rejected — requires all MCP servers to share the same app registration or skip audience validation. Not realistic for third-party or cross-team MCP servers.
- **OBO only**: Rejected — over-engineered for MCP servers that share the same app registration. OBO requires a client secret and an extra network call to the token endpoint.
- **`header_provider` callback**: Rejected — requires threading token through `FunctionInvocationContext.kwargs` which involves changes to the agent runtime invocation layer. `http_client` approach is self-contained.
- **Frontend sends token directly to MCP server**: Rejected — violates Constitution Principle VII (frontend must not communicate with external services directly) and Principle III (no secrets in frontend bundles).

## Technology Decisions Summary

| Decision | Technology | Version |
|----------|-----------|---------|
| MCP auth (passthrough) | `httpx.AsyncClient` with default headers via `MCPStreamableHTTPTool(http_client=...)` | httpx (already installed) |
| MCP auth (OBO) | MSAL `ConfidentialClientApplication.acquire_token_on_behalf_of()` → `httpx.AsyncClient` | msal (new dependency) |
| Status reporting | Extended JSON response on `POST /api/sessions` | FastAPI (existing) |
| UI indicators | New `McpStatusIndicator.tsx` React component | React (existing) |
| Toast notifications | Existing `emitToast()` from `useToast.tsx` | Custom (existing) |
| Frontend auth | MSAL `getToken()` already in `useAuth.ts` | @azure/msal-browser (existing) |
