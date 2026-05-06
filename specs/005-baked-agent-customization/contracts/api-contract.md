# API Contract: Baked Agent Customization

## GET /api/profiles/{profile_id}/definition

Return the safe editable definition for a built-in/pre-baked profile.

### Request

```http
GET /api/profiles/faa/definition
Authorization: Bearer <token>
```

### Response: 200

```json
{
  "id": "faa",
  "name": "FAA Aviation AI",
  "description": "Aviation information assistant powered by FAA data tools.",
  "icon": "/icons/hybrid.svg",
  "systemPrompt": "You are an aviation information assistant...",
  "tools": ["get_user_profile", "save_user_profile"],
  "skills": [],
  "mcpServers": [
    {
      "name": "faa-mcp",
      "transport": "http",
      "url": "https://faa-mcp.azurewebsites.us/mcp",
      "authenticated": false
    }
  ],
  "useSearchContext": false,
  "starters": [
    {
      "label": "Look up an aircraft",
      "message": "Can you look up information about a specific aircraft by tail number?"
    }
  ],
  "temperature": 0.2,
  "source": "builtin"
}
```

### Errors

- `401 Unauthorized` if auth fails.
- `404 Not Found` if `profile_id` is unknown or refers to a non-built-in profile.
- `500 Internal Server Error` if profile configuration cannot be loaded.

### Security Rules

- Response must not include secrets, tokens, raw authorization headers, API keys, connection strings, or environment variable values used as credentials.
- Environment placeholders in MCP URLs may be resolved only when they are not secrets; credential-like env values must be omitted or masked.

## POST /api/sessions with profile override

Extend existing session creation endpoint to accept an optional override for a known built-in profile.

### Request

```http
POST /api/sessions
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "profile_id": "faa",
  "profile_override": {
    "description": "Aviation information assistant tuned for local demo.",
    "custom_prompt": "You are an aviation information assistant...",
    "custom_tools": ["get_user_profile", "save_user_profile"],
    "custom_skills": [],
    "custom_search_context": false,
    "custom_temperature": 0.2,
    "mcp_servers": [
      {
        "name": "faa-mcp",
        "transport": "http",
        "url": "https://faa-mcp.azurewebsites.us/mcp",
        "authenticated": false
      }
    ],
    "override_updated_at": "2026-05-06T12:00:00.000Z"
  },
  "user_profile": {
    "name": "Blaine",
    "preferences": "...",
    "notes": "..."
  }
}
```

Field names align with the existing custom-session payload where practical to minimize backend branching. Built-in override requests intentionally omit editable agent name; the backend must derive `profile_name` from the canonical built-in profile.

### Response: 200

```json
{
  "session_id": "uuid",
  "profile_id": "faa",
  "profile_name": "FAA Aviation AI",
  "tools_loaded": ["get_user_profile", "save_user_profile"],
  "skills_loaded": [],
  "search_context": false,
  "mcp_results": [
    {
      "name": "faa-mcp",
      "transport": "http",
      "status": "connected",
      "tool_count": 4
    }
  ],
  "used_profile_override": true,
  "override_updated_at": "2026-05-06T12:00:00.000Z"
}
```

### Behavior

- If `profile_override` is omitted, existing built-in profile session behavior remains unchanged.
- If `profile_override` is present, `profile_id` must still identify a known built-in profile.
- Backend uses override prompt/tools/skills/MCP/search/temperature for runtime creation.
- Backend ignores/rejects any attempted local override display name and derives the session `profile_name` from the canonical built-in profile.
- Backend preserves `profile_id` and trace/log identity as the original built-in profile id.
- Backend must validate user input limits, profile existence, tool names, MCP config shape, and search availability consistently with custom-agent session behavior.

### Errors

- `400 Bad Request` for unknown profile, invalid override shape, invalid temperature, missing prompt, attempted name override, or invalid MCP entry.
- `401 Unauthorized` if auth fails.
- `500 Internal Server Error` for unexpected runtime/session creation failures.

## Frontend-Only Contract: Standard Agent Candidate

The browser generates this object from a local override when the user chooses `make standard`.

```json
{
  "profileId": "faa",
  "generatedAt": "2026-05-06T12:05:00.000Z",
  "sourceOverrideUpdatedAt": "2026-05-06T12:00:00.000Z",
  "profile": {
    "name": "FAA Aviation AI",
    "description": "Aviation information assistant tuned for local demo.",
    "icon": "/icons/hybrid.svg",
    "tools": ["get_user_profile", "save_user_profile"],
    "skills": [],
    "mcp_servers": [
      {
        "name": "faa-mcp",
        "transport": "http",
        "url": "https://faa-mcp.azurewebsites.us/mcp",
        "description": "FAA aviation data tools"
      }
    ],
    "search_context": false,
    "temperature": 0.2,
    "starters": [],
    "system_prompt": "You are an aviation information assistant..."
  },
  "yaml": "faa:\n  name: FAA Aviation AI\n  ..."
}
```

### Behavior

- Candidate generation must not update server files.
- UI should provide copy/download affordance and explain that shared promotion requires source update, tests, and evals.
- Candidate must omit local-only fields such as `createdAt`, `updatedAt`, `source`, and `baseProfileId`.
