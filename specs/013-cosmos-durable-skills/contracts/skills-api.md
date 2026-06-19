# Contract: Skills REST API (`/api/skills*`)

> **Unchanged from the current implementation.** This feature migrates only the storage tier
> (filesystem → Cosmos). Request/response shapes, status codes, and auth are preserved so the
> React Skill Builder requires no change. This document records the contract the Cosmos-backed
> implementation must continue to honor.

All endpoints require an authenticated user (`get_current_user`); outside local dev,
unauthenticated callers are rejected.

## GET `/api/skills`

List skill summaries (for the custom-agent builder and the Skill Builder list).

**200 Response**
```json
{ "skills": [ { "name": "table-usage", "description": "..." } ] }
```
- Ordered by creation time then name. No `content` in the summary list.

## GET `/api/skills/{name}`

Fetch a single skill in full.

**200 Response**
```json
{ "name": "table-usage", "description": "...", "content": "# Table Usage\n..." }
```
**404** — skill not found.

## POST `/api/skills`

Create a new skill.

**Request**
```json
{ "name": "my-skill", "description": "...", "content": "# ...\n" }
```
**201 Response** — the created skill `{ name, description, content }`.
**422** — invalid name/description/content.
**409** — a skill with that name already exists.

## PUT `/api/skills/{name}`

Update an existing skill's description/content (name is the path key).

**Request**
```json
{ "description": "...", "content": "# ...\n" }
```
**200 Response** — the updated skill `{ name, description, content }`.
**404** — skill not found.
**422** — invalid description/content.

## DELETE `/api/skills/{name}`

Remove a skill.

**204** — deleted.
**404** — skill not found.

## POST `/api/skills/generate`

Generate `SKILL.md` body content from a short description using the LLM (unchanged; does not touch
storage).

**Request**
```json
{ "name": "my-skill", "description": "what the skill should do" }
```
**200 Response**
```json
{ "content": "# Generated markdown body..." }
```
**422** — missing/oversized description.
**502** — LLM generation failed or returned empty.

## Durability guarantees (new — same observable contract, durable backing)

- Every successful `POST`/`PUT`/`DELETE` is persisted to Cosmos and is visible to all backend
  instances and after restart/redeploy.
- `created_at` is preserved across updates; `updated_at` refreshes on each write.
- With Cosmos unconfigured the backend fails fast at startup (no non-durable fallback).
