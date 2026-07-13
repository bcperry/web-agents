# Quickstart: Agent Creation Tools

## Prerequisites

- Python 3.12.6 managed with `uv` only.
- Existing frontend dependencies managed with `npm` (no new package is planned).
- Cosmos emulator available through the **Start Cosmos Emulator** task or
  `bash scripts/start_cosmos_emulator.sh`.

## Focused Offline Verification

Run the implementation's narrow tests first:

```bash
uv run pytest -q \
  tests/test_creation_tools.py \
  tests/test_definition_creation.py \
  tests/test_user_data.py \
  tests/test_skills_manager.py \
  tests/test_agent_factory.py \
  tests/test_api.py
```

Required assertions:

- neither creation tool is instantiated unless its exact saved name is selected;
- selecting one never selects the other;
- tool schemas contain no owner field and closures write only to the bound user;
- valid definitions persist and return the documented bounded result;
- invalid references produce field issues and no write;
- duplicate calls preserve the original document byte-for-byte;
- storage exceptions produce sanitized retryable errors;
- global plus owner skill resolution excludes every other owner;
- custom-agent management writes use the same strict validator;
- old saved agents still tolerate references deleted after save at session start.

Then run the full offline suite:

```bash
uv run pytest -q
```

Build the frontend and run the focused browser contract for the generic tool
picker and custom/built-in save payloads:

```bash
cd frontend && npm run build && cd ..
uv run pytest -q tests/test_agent_builder_ui.py
```

## Cosmos Emulator Verification

```bash
bash scripts/start_cosmos_emulator.sh
uv run pytest -q -m emulator
```

The emulator slice must prove:

1. two concurrent creates for the same `(user_id, id)` yield one success and one duplicate;
2. the same id can be created in two different user partitions;
3. list/get for user B never returns user A's user skill or custom agent;
4. records remain available through a fresh repository instance; and
5. the user-skill container is partitioned by `/user_id`.

## Manual API and Runtime Check

Start the existing app after building the frontend:

```bash
cd frontend && npm run build
cd ..
AUTH_DISABLED=true uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

1. Confirm `GET /api/tools` lists `create_skill` and `create_agent` separately.
2. Save four test agents: neither tool, skill only, agent only, and both.
3. Start each agent and inspect `tools_loaded`; it must exactly match the saved grants.
4. Invoke each enabled tool with a unique valid definition and verify the structured result.
5. Read the owner's skill/custom-agent catalog and confirm the full definition is present.
6. Restart the backend and repeat the reads.
7. Authenticate as a second user and confirm neither definition can be listed, resolved, or inferred.

No visual change is planned. If implementation changes the existing builder layout rather than only
feeding it new inventory data, run the constitution's Admin Agent Builder screenshot workflow.

## Configuration

| Environment variable | Default | Purpose |
|----------------------|---------|---------|
| `AZURE_COSMOS_ENDPOINT` | required | Existing Cosmos endpoint. |
| `AZURE_COSMOS_DATABASE_NAME` | `agent-memory` | Existing application database. |
| `AZURE_COSMOS_USER_SKILLS_CONTAINER` | `user-skills` | Owner-partitioned skill definitions. |
| `AZURE_COSMOS_CUSTOM_AGENTS_CONTAINER` | `custom-agents` | Existing owner-partitioned custom agents. |

Production uses managed identity and Azure Government endpoints. Keys remain local/emulator-only and
must never appear in tool results, API responses, logs, or committed configuration.