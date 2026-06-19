# Quickstart: Durable Cosmos-Backed Skills

## Prerequisites

- `uv` (the only package manager used here — never pip).
- The Azure Cosmos DB Emulator running locally (the backend requires Cosmos; there is no
  non-durable fallback). Start it via the VS Code task **Start Cosmos Emulator** or
  `bash scripts/start_cosmos_emulator.sh`.

## Run the backend locally

```bash
# Cosmos emulator endpoint + local auth (well-known emulator key handled in code)
export AZURE_COSMOS_ENDPOINT="https://localhost:8081/"
export AUTH_DISABLED=true

uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

On startup the backend logs the skill seed count, e.g.:

```
Skills — seeded N default skill(s) from ./skills into Cosmos
```

## Verify durability (the core of the feature)

```bash
# 1. Create a skill through the builder API.
curl -s -X POST localhost:8000/api/skills \
  -H 'content-type: application/json' \
  -d '{"name":"demo-skill","description":"A demo.","content":"# Demo\nDo the thing."}' | jq

# 2. Confirm it lists and reads back.
curl -s localhost:8000/api/skills | jq '.skills[] | select(.name=="demo-skill")'
curl -s localhost:8000/api/skills/demo-skill | jq

# 3. Restart the backend (Ctrl-C, re-run uvicorn). Because the local skills/ directory does NOT
#    contain demo-skill, a filesystem store would lose it — Cosmos does not.
curl -s localhost:8000/api/skills/demo-skill | jq   # still present → durable
```

## Verify an agent loads a Cosmos skill

1. Ensure a profile or custom agent references a skill name (e.g. the `sql` profile references
   `table-usage`).
2. Start a chat session with that agent; the agent advertises the skill and can load its body.
   The content is fetched from Cosmos lazily at run time. Editing the skill via `PUT /api/skills/
   table-usage` is reflected in the **next** session.

## Seeding semantics

- Empty container → each default under `skills/` is created once.
- Edit a default at runtime, restart → the edit is preserved (seeding never overwrites existing
  ids).
- Add a new default under `skills/`, restart → it is seeded; nothing is duplicated.
- Delete a default at runtime → it returns on next startup (it is a repo default). Remove it from
  `skills/` to retire it permanently.

## Tests

```bash
# Offline unit suite (in-memory Cosmos doubles seeded from the filesystem defaults; no live cloud).
uv run pytest -q

# Skill-focused tests.
uv run pytest -q tests/test_skills.py tests/test_skills_cosmos.py

# Emulator-backed integration (real skills container). Skipped automatically if the emulator
# is not reachable on localhost:8081.
uv run pytest -q -m emulator
```

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `AZURE_COSMOS_ENDPOINT` | — (required) | Cosmos endpoint (emulator or real account). |
| `AZURE_COSMOS_DATABASE_NAME` | `agent-memory` | Database holding the `skills` container. |
| `AZURE_COSMOS_SKILLS_CONTAINER` | `skills` | The skills container name. |
