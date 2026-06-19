# Implementation Plan: Durable Cosmos-Backed Skills

**Branch**: `013-cosmos-durable-skills` | **Date**: 2026-06-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/013-cosmos-durable-skills/spec.md`

## Summary

Move agent **skills** off the backend's ephemeral local filesystem (`skills/` + `SKILL.md`
files) into **Azure Cosmos DB** as the durable, shared source of truth — reusing the exact pattern
established by the autonomous **directive** store (feature 012): the repository `skills/` directory
**seeds defaults** at startup (idempotent), and **Cosmos is the runtime store** for every create,
edit, and delete made through the admin Skill Builder. Add a `CosmosSkillRepository` (global,
partitioned by `/id`) to `cosmos_memory.py`, a `seed_skills()` startup step that mirrors
`seed_autonomous_directives()`, and a `CosmosSkillsSource` (an Agent Framework `SkillsSource`)
that lets agents load their selected skills from Cosmos lazily at run time while preserving
name-based filtering. The `SkillManager` becomes Cosmos-backed (its validation is retained); the
`/api/skills*` REST surface and the React Skill Builder are **unchanged**. A new `skills` Cosmos
container is declared in Terraform. No non-durable fallback — Cosmos is required, exactly as for
agent memory (011) and autonomous mode (012).

## Technical Context

**Language/Version**: Python 3.12 (backend only). The TypeScript/React frontend is **untouched** —
the `/api/skills*` wire contract is preserved, so no frontend change is required.  
**Primary Dependencies**: FastAPI, `agent-framework` (the existing skills runtime —
`SkillsSource`, `InlineSkill`, `SkillFrontmatter`, `InMemorySkillsSource`, `FilteringSkillsSource`,
`SkillsProvider`), `azure-cosmos` (async). No new dependencies.  
**Storage**: Azure Cosmos DB (NoSQL, serverless) in the existing `agent-memory` database and shared
async `CosmosClient` — one new `skills` container partitioned by `/id` (global operator config,
identical shape choice to `autonomous-directives`).  
**Testing**: `pytest` offline unit suite with the existing in-memory Cosmos doubles via the autouse
`_cosmos_doubles` fixture (add an `InMemorySkillRepository` seeded from the filesystem defaults);
`@pytest.mark.emulator` integration tests against the local Cosmos emulator for the real repository.  
**Target Platform**: Azure Government (`.azure.us` / `.usgovcloudapi.net`). The existing App Service
backend hosts everything. Local dev runs the backend with `AUTH_DISABLED=true` and the Cosmos
emulator.  
**Project Type**: Two-tier web app (FastAPI backend + React frontend). No new deployable unit — a
storage-tier migration inside the existing backend.  
**Performance Goals**: Skill catalog is small (tens of skills). "List all" is a cheap query;
point reads/writes are partition-scoped by id. Agent skill loading is lazy and per-session-cached
by `SkillsProvider`, adding no steady-state latency to the chat path.  
**Constraints**: Reuse the shared Cosmos client; no secrets in logs/records/responses; Azure
Government endpoints; managed identity in production, keys only for local/emulator; `uv` for backend
deps (never pip); offline unit suite must pass with no live cloud; no non-durable runtime fallback.  
**Scale/Scope**: One deployment (possibly multiple instances). Skill volume grows slowly via the
admin builder. Backend-only change; frontend and agent runtime semantics preserved.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Read-Only Data Access | ✅ PASS | Adds no SQL. Skill docs are app-owned config writes to Cosmos, not user-database mutations. Agents' read-only SQL tools are unchanged. |
| II. Single-File Agent Definitions | ✅ PASS | No new agent profiles. Profiles still reference skills by name in `agents.yaml`; skill *content* (the `SKILL.md` body) is operator data in Cosmos, not tool documentation. Tool docs remain Python docstrings. |
| III. Security & Credential Hygiene | ✅ PASS | No new secret. Reuses the shared Cosmos client (MI in prod, emulator key locally). Skill CRUD is behind the existing `get_current_user` auth; no credentials in skill docs, logs, or responses. Azure Government endpoints. |
| IV. Evaluation-Driven Quality | ✅ PASS | No prompt/model/parameter change to existing profiles. Skill-loading behavior (advertise/load/filter) is preserved; only the storage origin changes. |
| V. Simplicity & Minimalism | ✅ PASS | Reuses the directive store pattern verbatim (one repo + getter + seed function + container). One new `SkillsSource` subclass replaces the file source; `SkillManager` swaps its backing store but keeps its validation. No new service, no new dependency. |
| VI. Infrastructure as Code | ✅ PASS | The new `skills` Cosmos container is declared in the existing `infra/modules/cosmos` module (partition `/id`), consistent with the other containers. No portal clicks, no new compute/identity. |
| VII. Two-Tier API-First Architecture | ✅ PASS | No third deployable. Storage migration lives entirely in the backend; the `/api/skills*` API and the frontend are unchanged, preserving the two-tier shape. |

**Result**: PASS — no deviations. No gate blocks Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/013-cosmos-durable-skills/
├── plan.md              # This file (/speckit.plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── skills-api.md            # Backend REST contract (/api/skills*) — unchanged shapes
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
# Backend (repository root — existing FastAPI app; the single agent host)
cosmos_memory.py           # EDIT: add CosmosSkillRepository (container `skills`, partition /id)
                           #       with list_skills/get_skill/create_skill/upsert_skill/delete_skill;
                           #       add get_skill_repository() singleton + close_cosmos() reset.
skills_manager.py          # EDIT: SkillManager becomes Cosmos-backed (async CRUD over the repo),
                           #       keeping name/description/content validation. Add seed_skills()
                           #       reading the filesystem defaults and upserting missing ids.
agent_factory.py           # EDIT: add CosmosSkillsSource(SkillsSource); _build_skills_provider()
                           #       wraps FilteringSkillsSource(CosmosSkillsSource(), predicate)
                           #       instead of FileSkillsSource (lazy async fetch at run time).
validators.py              # EDIT: available_skill_names() reads from the Cosmos repo (async)
                           #       instead of FileSkillsSource(skills_dir).
session_orchestration.py   # EDIT (minimal): available_skill_names() no longer needs skills_dir;
                           #       keep filter_known_skill_names() behavior.
main.py                    # EDIT: skill endpoints await the async SkillManager; call seed_skills()
                           #       in lifespan (like seed_autonomous_directives).
skills/                    # KEEP: now the SEED source of default skills (table-usage, etc.),
                           #       no longer the runtime read/write store.

# Infrastructure as Code (Terraform) — one new container, no new compute
infra/
└── modules/cosmos/        # EDIT: declare a `skills` container (partition /id) + output.

# Tests (repository root tests/)
tests/
├── _doubles.py            # EDIT: add InMemorySkillRepository mirroring the Cosmos repo interface.
├── conftest.py            # EDIT: autouse fixture injects the skill double, seeded from the
                           #       filesystem defaults (so reads return built-ins offline).
├── test_skills.py         # EDIT: update _build_skills_provider tests for the Cosmos-backed source.
├── test_skills_cosmos.py  # NEW: skill repo CRUD + seeding via doubles (offline) and the
                           #      SkillManager Cosmos path; @pytest.mark.emulator real-repo CRUD.
└── test_api.py            # EDIT (if needed): /api/skills* durability assertions via TestClient.
```

**Structure Decision**: Keep the existing two-tier app and perform a **storage-tier migration
inside the backend**, mirroring features 011/012. Skills become global Cosmos documents
(partition `/id`) in a new `skills` container in the existing `agent-memory` database, reusing the
shared async `CosmosClient`. The Agent Framework integration is preserved by swapping the file
`SkillsSource` for a `CosmosSkillsSource` that builds `InlineSkill` objects from Cosmos docs and is
fetched lazily during agent runs; `FilteringSkillsSource` continues to enforce per-agent skill
selection. The `skills/` directory is retained purely as the seed source of defaults.

## Complexity Tracking

> No constitution deviations. This feature *reduces* operational complexity (one durable store
> instead of ephemeral disk) and reuses an existing, proven pattern. No table required.

## Phase 0 — Research

See [research.md](research.md). Key decisions: (R1) global `/id` partition mirroring directives;
(R2) `CosmosSkillsSource` + lazy async `get_skills()` so `_build_skills_provider` stays sync; (R3)
filesystem `skills/` as idempotent seed source; (R4) retain `SkillManager` validation, swap store;
(R5) no non-durable fallback; (R6) test doubles seeded from filesystem defaults.

## Phase 1 — Design & Contracts

- [data-model.md](data-model.md) — the `Skill` document shape, partition key, and validation rules.
- [contracts/skills-api.md](contracts/skills-api.md) — the (unchanged) `/api/skills*` REST contract,
  now backed by Cosmos.
- [quickstart.md](quickstart.md) — how to run, seed, and verify skill durability locally and against
  the emulator.

## Phase 2 — Tasks

See [tasks.md](tasks.md) (generated by `/speckit.tasks`). Tasks are grouped by user story (US1–US5)
so each slice is independently implementable and testable.
