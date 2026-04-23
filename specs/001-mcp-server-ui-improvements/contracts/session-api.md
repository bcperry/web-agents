# API Contract: Session Creation — MCP Server Results

**Feature**: 001-mcp-server-ui-improvements | **Date**: 2026-04-22

## Endpoint: `POST /api/sessions`

### Changes

The session creation response is extended with an optional `mcp_results` array reporting per-MCP-server connection outcomes.

### Request Body Changes

#### Standard profile session (existing + new)

```json
{
  "profile_id": "faa",
  "user_profile": { ... }
}
```

No request body changes for standard profiles. The backend reads MCP configs from `agents.yaml` and the user's auth token from the `Authorization` header.

#### Custom agent session (existing + new)

```json
{
  "profile_id": "custom",
  "custom_name": "My Agent",
  "custom_prompt": "You are...",
  "custom_tools": ["get_user_profile"],
  "mcp_servers": [
    {
      "name": "same-app-mcp",
      "transport": "http",
      "url": "https://same-app.azure.us/mcp",
      "authenticated": true
    },
    {
      "name": "cross-app-mcp",
      "transport": "http",
      "url": "https://cross-app.azure.us/mcp",
      "auth_scope": "api://mcp-server-client-id/.default"
    }
  ]
}
```

**New fields on mcp_servers entries:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `authenticated` | boolean | No (default: false) | Passthrough mode: forward the caller's bearer token as-is to this MCP server |
| `auth_scope` | string | No | OBO mode: exchange the caller's token for one scoped to this value (e.g. `"api://<client-id>/.default"`) |

**Field name mapping (frontend ↔ backend):**
| Concept | Frontend (TypeScript) | Backend (Python/YAML) | API Request Body |
|---------|----------------------|----------------------|------------------|
| Passthrough auth | `authenticated` | `auth` | `authenticated` |
| OBO scope | `authScope` | `auth_scope` | `auth_scope` |

### Response Body Changes

#### Success (201 Created)

```json
{
  "session_id": "uuid-string",
  "profile_id": "faa",
  "profile_name": "FAA Aviation AI",
  "mcp_results": [
    {
      "name": "faa-mcp",
      "transport": "http",
      "status": "connected",
      "tool_count": 5,
      "error": null
    },
    {
      "name": "Aircraft-Database",
      "transport": "http",
      "status": "failed",
      "tool_count": 0,
      "error": "Connection refused"
    }
  ]
}
```

**New field:**
| Field | Type | Description |
|-------|------|-------------|
| `mcp_results` | `McpConnectionResult[]` | Per-server connection outcomes. Empty array if the profile has no MCP servers. |

**McpConnectionResult:**
| Field | Type | Description |
|-------|------|-------------|
| `name` | string | MCP server name from config |
| `transport` | string | `"http"` or `"stdio"` |
| `status` | string | `"connected"` or `"failed"` |
| `tool_count` | integer | Number of tools loaded (0 if failed) |
| `error` | string \| null | Error message if failed, null if connected |

### Backward Compatibility

- `mcp_results` is a new additive field. Existing clients that do not read it are unaffected.
- Profiles with no MCP servers return `"mcp_results": []`.
- The session is still created successfully even if all MCP servers fail — this is non-blocking.

---

## Endpoint: `GET /api/profiles`

### Changes

Profile entries are extended with an `mcp_server_count` field so the frontend can show which profiles have MCP servers (without revealing server URLs/details).

#### Response Body Changes

```json
{
  "profiles": [
    {
      "id": "faa",
      "name": "FAA Aviation AI",
      "description": "...",
      "icon": "/icons/hybrid.svg",
      "starters": [...],
      "skills": [],
      "mcp_server_count": 2
    }
  ],
  "unavailable": [...]
}
```

**New field on profile entries:**
| Field | Type | Description |
|-------|------|-------------|
| `mcp_server_count` | integer | Number of MCP servers configured for this profile (0 if none) |

---

## Authentication Flow for MCP Servers

### Mode 1: Passthrough (`auth: true`)

```
Frontend                     Backend                        MCP Server
   |                            |                         (same app reg)
   |-- POST /api/sessions ----->|                              |
   |   Authorization: Bearer T  |                              |
   |                            |-- Extract token T            |
   |                            |-- auth: true                 |
   |                            |   httpx.AsyncClient(         |
   |                            |     headers={"Auth": T})     |
   |                            |-- tool.connect() ----------->|
   |                            |   (requests carry Bearer T)  |
   |                            |<-- tools loaded -------------|  
   |<-- 201 {mcp_results} -----|                              |
```

### Mode 2: OBO (`auth_scope: "api://.../.default"`)

```
Frontend                     Backend                     Azure AD         MCP Server
   |                            |                           |            (own app reg)
   |-- POST /api/sessions ----->|                           |                |
   |   Authorization: Bearer T  |                           |                |
   |                            |-- Extract token T         |                |
   |                            |-- auth_scope set          |                |
   |                            |-- OBO exchange T -------->|                |
   |                            |   (scope=auth_scope)      |                |
   |                            |<-- Bearer T2 -------------|                |
   |                            |   httpx.AsyncClient(      |                |
   |                            |     headers={"Auth": T2}) |                |
   |                            |-- tool.connect() -------->|--------------->|
   |                            |   (requests carry T2)     |                |
   |                            |<-- tools loaded --------------------------------|
   |<-- 201 {mcp_results} -----|                           |                |
```

The backend acts as a trusted intermediary. Neither the user's token nor the OBO-exchanged token is logged or stored beyond the session's MCP tool instance lifetime. OBO requires `AZURE_AD_CLIENT_SECRET` as a backend env var (never in frontend).
