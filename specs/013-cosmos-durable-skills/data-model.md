# Phase 1 Data Model: Durable Cosmos-Backed Skills

## Entity: Skill (Cosmos document)

Global, operator-authored capability. Stored in the `skills` container (database `agent-memory`),
partitioned by `/id`. The id **is** the skill name. Not scoped to any user.

### Document shape (storage)

```json
{
  "id": "table-usage",
  "description": "How to discover and use database tables effectively.",
  "content": "# Table Usage\n\n... SKILL.md body ...",
  "created_at": "2026-06-19T12:00:00+00:00",
  "updated_at": "2026-06-19T12:00:00+00:00",
  "doc_type": "skill",
  "schema_version": 1
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Partition key. **Is** the validated skill name (single source of truth — the wire `name` is derived from it). |
| `description` | string | Short summary advertised to agents (L1 discovery). |
| `content` | string | The `SKILL.md` body / instructions (L2 load). |
| `created_at` | string (ISO-8601) | Set on first create; **preserved** across updates. |
| `updated_at` | string (ISO-8601) | Refreshed on every write. |
| `doc_type` | string | Constant `"skill"` (consistency with other app-owned docs). |
| `schema_version` | int | Constant `1`. |

### Wire shape (REST — unchanged)

The repository returns/accepts the bare wire payload the frontend already uses; the bookkeeping
fields (`created_at`, `updated_at`, `doc_type`, `schema_version`) are storage-only.

```json
{ "name": "table-usage", "description": "...", "content": "..." }
```

- `GET /api/skills` returns `{ "skills": [ { "name", "description" }, ... ] }` (summaries — no
  content, mirroring the current list shape).
- `GET /api/skills/{name}`, `POST /api/skills`, `PUT /api/skills/{name}` return the full
  `{ name, description, content }`.

## Validation rules (enforced at the boundary before any write)

| Field | Rule | On violation |
|-------|------|--------------|
| `name` | Matches `^[a-z0-9][a-z0-9-]*$`, length ≤ 64. Equals the spec skill-name rule. | 422 (create) / 400 (path) |
| `description` | Non-empty, length ≤ 256. | 422 |
| `content` | Non-empty, length ≤ 65536. | 422 |
| create with existing `id` | Must not overwrite. | 409 Conflict |
| get/update/delete missing `id` | Not found. | 404 |

## Lifecycle

- **Create** (`POST /api/skills`): validate → conflict-check by id → write doc with
  `created_at = updated_at = now`.
- **Read** (`GET /api/skills/{name}`): point read by id → 404 if absent.
- **List** (`GET /api/skills`): query all → return name/description summaries, ordered by
  `created_at` then `name`.
- **Update** (`PUT /api/skills/{name}`): validate → require existing → write doc preserving
  original `created_at`, refresh `updated_at`.
- **Delete** (`DELETE /api/skills/{name}`): delete by id → 404 if absent.
- **Seed** (startup, idempotent): for each filesystem default whose id is **not** present in
  Cosmos, create it (`created_at = updated_at = now`). Never overwrites existing ids.

## Relationship to agents

Agents reference skills by **name** only (in `agents.yaml` profile `skills:` and in custom-agent
`custom_skills`). At run time the `CosmosSkillsSource` materializes each Cosmos skill doc as an
Agent Framework `InlineSkill` (`SkillFrontmatter(name, description)` + `instructions=content`);
`FilteringSkillsSource` keeps only the names the agent selected. Unknown names are silently
omitted (no error). No foreign-key enforcement — a referenced skill that does not exist is simply
not advertised.
