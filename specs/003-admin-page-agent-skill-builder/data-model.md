# Data Model: Admin Page — Agent Builder + Skill Builder

**Branch**: `003-admin-page-agent-skill-builder`

## Entities

### SkillDefinition (new)

Represents a skill file on the server filesystem.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `name` | string | `^[a-z0-9][a-z0-9-]*$`, max 64 chars, unique | Directory name and frontmatter key |
| `description` | string | non-empty, max 256 chars | Frontmatter `description` value |
| `content` | string | non-empty, max 65,536 chars | Markdown body (everything after frontmatter) |

**Filesystem representation**:
```
skills/
└── {name}/
    └── SKILL.md    ← assembled from frontmatter + content
```

**SKILL.md file format**:
```markdown
---
name: {name}
description: "{description}"
---

{content}
```

### SkillSummary (existing, extended)

Used in the list response. Currently `{name, description}` (from `ToolInfo`). No changes needed — same shape.

### CustomAgentDefinition (existing, unchanged)

Moved to Admin page usage only; data model unchanged. Stored in localStorage.

## State Transitions

### SkillDefinition lifecycle

```
NOT_EXISTS → [POST /api/skills] → EXISTS
EXISTS → [PUT /api/skills/{name}] → EXISTS (updated)
EXISTS → [DELETE /api/skills/{name}] → NOT_EXISTS
```

## Validation Rules

### Backend (enforced on every mutating request)

| Rule | Endpoint | Error |
|------|----------|-------|
| `name` matches `^[a-z0-9][a-z0-9-]*$` | POST, PUT | 422 |
| `name` length ≤ 64 | POST, PUT | 422 |
| `description` non-empty, ≤ 256 chars | POST, PUT | 422 |
| `content` non-empty, ≤ 65536 chars | POST, PUT | 422 |
| skill must not already exist | POST | 409 |
| skill must exist | PUT, DELETE, GET one | 404 |
| no `..` or `/` path components in name | POST, PUT | 422 |

### Frontend (client-side, mirrors backend)

- Name field: live validation against `^[a-z0-9][a-z0-9-]*$`
- Description: required, non-empty
- Content: required, non-empty
- Submit button disabled until all fields valid

## View State Model

```
App.tsx
└── currentView: 'chat' | 'admin'
    ├── 'chat' → <ChatPage />
    └── 'admin' → <AdminPage />
                    └── activeTab: 'agents' | 'skills'
                        ├── 'agents' → <AgentBuilder ... />
                        └── 'skills' → <SkillBuilder />
                                        └── editingSkill: SkillDefinition | null
```

## API Response Shapes

### GET /api/skills (existing, unchanged)
```json
{ "skills": [{ "name": "table-usage", "description": "..." }] }
```

### GET /api/skills/{name} (new)
```json
{ "name": "table-usage", "description": "...", "content": "# Table Usage...\n\n..." }
```

### POST /api/skills (new)
Request: `{ "name": "my-skill", "description": "...", "content": "# My Skill..." }`  
Response (201): `{ "name": "my-skill", "description": "...", "content": "..." }`

### PUT /api/skills/{name} (new)
Request: `{ "description": "...", "content": "..." }`  
Response (200): `{ "name": "my-skill", "description": "...", "content": "..." }`

### DELETE /api/skills/{name} (new)
Response (204): no body
