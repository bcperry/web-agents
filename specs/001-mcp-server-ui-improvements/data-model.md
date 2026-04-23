# Data Model: MCP Server UI Improvements

**Feature**: 001-mcp-server-ui-improvements | **Date**: 2026-04-22

## Entity Changes

### 1. MCPServerConfig (Backend — `mcp_servers.py`)

**Modified entity** — existing `@dataclass`, add `auth` and `auth_scope` fields.

```python
@dataclass
class MCPServerConfig:
    name: str
    transport: str          # "http" or "stdio"
    url: str | None = None
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    allowed_tools: list[str] | None = None
    request_timeout: int | None = None
    description: str | None = None
    auth: bool = False               # NEW — passthrough: forward user's bearer token as-is
    auth_scope: str | None = None    # NEW — OBO: exchange token for this scope (e.g. "api://<client-id>/.default")
```

**Validation rules**:
- `auth` and `auth_scope` are only valid when `transport == "http"` (stdio servers are local, no auth)
- If both `auth: true` and `auth_scope` are set, `auth_scope` takes precedence (OBO mode)
- If `auth: true` and no token is available (e.g., AUTH_DISABLED mode), log a warning and connect without auth
- If `auth_scope` is set and `AZURE_AD_CLIENT_SECRET` is missing, log a warning and fall back to passthrough if `auth: true`, otherwise connect without auth
- If OBO token exchange fails (e.g., invalid scope, network error, consent not granted), the MCP connection MUST be reported as `status: "failed"` in `MCPConnectionResult` with an error describing the token exchange failure. No silent fallback to unauthenticated connection for `auth_scope` servers.

---

### 2. MCPConnectionResult (Backend — `mcp_servers.py`)

**New entity** — returned by `connect_mcp_servers()`.

```python
@dataclass
class MCPConnectionResult:
    name: str
    transport: str
    status: str             # "connected" | "failed"
    tool_count: int = 0     # number of tools loaded (0 if failed)
    error: str | None = None  # error message if failed
```

---

### 3. McpServerEntry (Frontend — `types/api.ts`)

**Modified type** — add `authenticated` field.

```typescript
export interface McpServerEntry {
  name: string;
  transport: 'http' | 'stdio';
  url: string;
  authenticated?: boolean;   // NEW — passthrough: forward user's token as-is
  authScope?: string;        // NEW — OBO: exchange token for this scope
}
```

---

### 4. McpConnectionResult (Frontend — `types/api.ts`)

**New type** — parsed from session creation response.

```typescript
export interface McpConnectionResult {
  name: string;
  transport: string;
  status: 'connected' | 'failed';
  tool_count: number;
  error?: string;
}
```

---

### 5. SessionCreateResponse (Frontend — `types/api.ts`)

**Modified type** — add `mcp_results` field.

```typescript
export interface SessionCreateResponse {
  session_id: string;
  profile_id: string;
  profile_name: string;
  mcp_results?: McpConnectionResult[];  // NEW — per-server connection outcomes
}
```

---

### 6. agents.yaml MCP Server Entries

**Modified schema** — optional `auth` field on mcp_servers items.

```yaml
mcp_servers:
  # Passthrough: forward user's token as-is (same app registration)
  - name: same-app-server
    transport: http
    url: "https://same-app.azure.us/mcp"
    auth: true
    description: "MCP server sharing our app registration"

  # OBO: exchange token for MCP server's audience (separate app registration)
  - name: cross-app-server
    transport: http
    url: "https://cross-app.azure.us/mcp"
    auth_scope: "api://mcp-server-client-id/.default"
    description: "MCP server with its own app registration"

  # No auth (default)
  - name: public-server
    transport: http
    url: "https://public.azure.us/mcp"
```

---

## State Transitions

### MCP Connection Lifecycle (per session creation)

```
[Config Parsed] → [Connecting] → [Connected] (status: "connected", tool_count > 0)
                                → [Failed]    (status: "failed", error: "<reason>")
```

- All servers are attempted regardless of individual failures
- Failed servers do not block session creation
- Results are returned in the session creation response

### Frontend MCP Status Display Lifecycle

```
[No Session]           → No MCP status shown
[Session Creating]     → Loading state (optional spinner)
[Session Created]      → Parse mcp_results → show indicators
                         If any failed → emit warning toast
[Session Active]       → MCP status indicators persist in chat header
```

## Relationships

```
agents.yaml profile
  └── mcp_servers[] (0..N)
        └── MCPServerConfig (parsed at session creation)
              └── MCPConnectionResult (returned per server)

SessionCreateResponse
  ├── session_id, profile_id, profile_name (existing)
  └── mcp_results[] (new, 0..N MCPConnectionResult)

McpStatusIndicator component
  └── receives McpConnectionResult[] as prop
```
