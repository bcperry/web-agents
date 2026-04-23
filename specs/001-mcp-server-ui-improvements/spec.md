# Feature Specification: MCP Server UI Improvements

**Branch**: `001-mcp-server-ui-improvements` | **Date**: 2026-04-22

## Problem Statement

MCP server connections are invisible to users. When a default agent's MCP server fails to connect, the session is created silently with missing tools — no feedback is provided. Custom agents similarly have no connection status visibility. Additionally, authenticated MCP servers (requiring the user's Azure AD token) are not supported.

## Requirements

### R1: MCP Connection Status Indicators
- Default and custom agent profiles that use MCP servers MUST display connection status indicators (checkmark for connected, X for failed) in the active session view (chat header area).
- The backend session creation response MUST include per-server connection results (name, status, error reason).
- Status indicators are shown after session creation, not in the ProfileSelector (MCP connections only occur during session creation).
- `GET /api/profiles` MUST include `mcp_server_count` per profile so the frontend knows which profiles use MCP servers.

### R2: Toast Notifications for MCP Failures
- When any agent session (default or custom) is created and one or more MCP servers fail to connect, the frontend MUST display a warning toast notification listing the failed servers.
- Toast type should be `warning` (not blocking) so the user can still use the agent with remaining tools.
- Toast should include the server name(s) that failed.
- A single consolidated toast is emitted per session creation (not one per failed server).

### R3: Authenticated MCP Server Support
- Users must be able to connect to MCP servers that require authentication using their logged-in Azure AD credentials.
- Two authentication modes are supported per-server:
  - **Passthrough** (`auth: true` in agents.yaml / `authenticated: true` in custom agent builder): Forward the user's bearer token as-is. For MCP servers sharing the same Azure AD app registration.
  - **OBO (On-Behalf-Of)** (`auth_scope: "api://<client-id>/.default"` in agents.yaml / `authScope` in custom agent builder): Exchange the user's token for a new token scoped to the MCP server's app registration via MSAL `ConfidentialClientApplication.acquire_token_on_behalf_of()`. For MCP servers with their own app registration.
- If both `auth: true` and `auth_scope` are set on the same server, `auth_scope` takes precedence (OBO mode).
- If OBO token exchange fails, the MCP connection is reported as failed in `mcp_results` — no silent fallback to unauthenticated.
- This applies to both custom agents (user-configured) and default agents (YAML-configured).
- OBO mode requires `AZURE_AD_CLIENT_SECRET` as a backend environment variable.

## Out of Scope
- MCP server discovery/browsing
- Retry logic for failed MCP connections (future enhancement)
- stdio MCP server authentication
