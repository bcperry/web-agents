# API Contract Change: GET /api/profiles

**Feature**: 009-agents-page-grouping | **Date**: 2026-05-12

## Endpoint

`GET /api/profiles`

## Change Type

**Additive** — new optional field in response. Non-breaking.

## Response Schema (updated)

```json
{
  "profiles": [
    {
      "id": "string",
      "name": "string",
      "description": "string",
      "icon": "string",
      "group": "string",           // NEW — group name (empty string if unset)
      "starters": [
        { "label": "string", "message": "string" }
      ],
      "skills": ["string"],
      "mcp_server_count": 0
    }
  ],
  "unavailable": [
    { "id": "string", "name": "string", "reason": "string" }
  ]
}
```

## Backward Compatibility

- The `group` field is additive. Existing frontend code that doesn't use `group` will continue to work.
- Frontend must handle `group` being an empty string (ungrouped agent).
- No request format changes.
- No new endpoints.

## Example

```json
{
  "profiles": [
    {
      "id": "chief-of-staff",
      "name": "Chief of Staff",
      "description": "Senior leader that coordinates the Army general staff.",
      "icon": "/icons/hybrid.svg",
      "group": "Command Staff",
      "starters": [
        { "label": "Who is on staff?", "message": "Which staff sections do you have available?" }
      ],
      "skills": [],
      "mcp_server_count": 0
    },
    {
      "id": "g1-personnel",
      "name": "G-1 Personnel",
      "description": "Assistant Chief of Staff for Personnel.",
      "icon": "/icons/hybrid.svg",
      "group": "General Staff",
      "starters": [...],
      "skills": [],
      "mcp_server_count": 0
    }
  ],
  "unavailable": []
}
```
