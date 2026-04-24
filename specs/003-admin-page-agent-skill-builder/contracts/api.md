# API Contracts: Skills CRUD

**Branch**: `003-admin-page-agent-skill-builder`  
**Base path**: `/api/skills`  
**Auth**: All endpoints require `Authorization: Bearer <Azure AD token>` (same pattern as all existing endpoints)

---

## GET /api/skills

List all available skills.

**Response 200**:
```json
{
  "skills": [
    { "name": "table-usage", "description": "Database table and view reference..." },
    { "name": "my-skill", "description": "Custom skill description" }
  ]
}
```

*Unchanged from existing endpoint.*

---

## GET /api/skills/{name}

Get full content of a single skill.

**Path parameter**: `name` — skill directory name (e.g., `table-usage`)

**Response 200**:
```json
{
  "name": "table-usage",
  "description": "Database table and view reference...",
  "content": "# Table Usage Reference\n\nUse this reference BEFORE writing SQL...\n"
}
```

**Response 404**:
```json
{ "detail": "Skill 'xyz' not found" }
```

---

## POST /api/skills

Create a new skill.

**Request body**:
```json
{
  "name": "my-new-skill",
  "description": "A brief description of what this skill does",
  "content": "# My New Skill\n\nThis skill helps the agent with..."
}
```

**Validation**:
- `name`: matches `^[a-z0-9][a-z0-9-]*$`, max 64 chars, must not already exist
- `description`: non-empty, max 256 chars
- `content`: non-empty, max 65,536 chars

**Response 201**:
```json
{
  "name": "my-new-skill",
  "description": "A brief description of what this skill does",
  "content": "# My New Skill\n\nThis skill helps the agent with..."
}
```

**Response 409** (skill already exists):
```json
{ "detail": "Skill 'my-new-skill' already exists" }
```

**Response 422** (validation error):
```json
{ "detail": "Invalid skill name: must match ^[a-z0-9][a-z0-9-]*$" }
```

---

## PUT /api/skills/{name}

Update an existing skill's description and/or content. Name cannot be changed.

**Path parameter**: `name` — skill directory name

**Request body**:
```json
{
  "description": "Updated description",
  "content": "# Updated Content\n\nNew markdown body..."
}
```

**Response 200**:
```json
{
  "name": "my-new-skill",
  "description": "Updated description",
  "content": "# Updated Content\n\nNew markdown body..."
}
```

**Response 404** (skill not found):
```json
{ "detail": "Skill 'xyz' not found" }
```

---

## DELETE /api/skills/{name}

Delete a skill and its directory.

**Path parameter**: `name` — skill directory name

**Response 204**: No body.

**Response 404** (skill not found):
```json
{ "detail": "Skill 'xyz' not found" }
```

---

## UI Contracts

### AdminPage component

```typescript
// No props — top-level page component, accesses global state via hooks
function AdminPage(props: { onBack: () => void }): JSX.Element
```

### SkillBuilder component

```typescript
// Self-contained; fetches skills list internally
function SkillBuilder(): JSX.Element
```

### AgentBuilder (unchanged API)

```typescript
function AgentBuilder(props: AgentBuilderProps): JSX.Element
// AgentBuilderProps unchanged
```

### App.tsx view state

```typescript
type AppView = 'chat' | 'admin';
// currentView replaces showAgentBuilder in ChatPage
```

### Sidebar change

```typescript
// Replace: onOpenAgentBuilder?: () => void
// With:    onOpenAdmin?: () => void
```
