# Implementation Plan: Agent Creation Tools

**Branch**: `014-agent-creation-tools` | **Date**: 2026-07-10 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/014-agent-creation-tools/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Expose `create_skill` and `create_agent` as two independently selectable, non-default Agent
Framework function tools. Bind both tools to the authenticated user while resolving session
dependencies, then delegate their work to shared backend creation services rather than invoking
FastAPI routes. Extend the existing Cosmos user-scoped repository with atomic `create`, add a
separate `/user_id`-partitioned user-skill container, and combine global skills with the current
user's skills for catalog and runtime resolution. Converge custom-agent management writes and tool
creation on one strict validator while retaining the existing session-time compatibility behavior
that drops deleted skill references. Return bounded, sanitized creation-result objects and cover
tool grants, validation, atomic duplicates, persistence, and cross-user isolation with focused
unit/API tests plus Cosmos emulator integration.

## Technical Context

**Language/Version**: Python 3.12.6 backend; existing TypeScript/React frontend contracts remain
compatible and require only tool-inventory consumption already supported by the builder.  
**Primary Dependencies**: FastAPI, Pydantic, Agent Framework function tools, async Azure Cosmos DB
SDK through the existing shared client. No new dependencies.  
**Storage**: Existing `agent-memory` Cosmos database. Custom agents remain in `custom-agents`
partitioned by `/user_id`; add `user-skills`, also partitioned by `/user_id`. Global skills remain
in the existing `/id`-partitioned `skills` container.  
**Testing**: `pytest` with existing loop-independent in-memory repository doubles; focused API,
service, runtime-tool wiring, and orchestration tests; `@pytest.mark.emulator` tests for atomic
owner-scoped create and isolation.  
**Target Platform**: Linux Azure App Service in Azure Government; local WSL development with the
Cosmos emulator.  
**Project Type**: Existing two-tier web application (FastAPI backend and React/TypeScript SPA),
deployed as one service.  
**Performance Goals**: Return normal valid creation results within 5 seconds for at least 95% of
calls; use partition-scoped point operations for owner-specific create/get and keep result payloads
bounded.  
**Constraints**: Explicit grants only; immutable authenticated owner binding; validation before
write; atomic no-overwrite create; no cross-user lookup or disclosure; no process-memory/file
fallback; no secrets or full instructions in results/logs; preserve session compatibility for
previously saved stale references; `uv` only.  
**Scale/Scope**: Two new function tools, one user-skill container, one shared strict custom-agent
validation path, and focused changes to backend wiring/catalog behavior. No new service or frontend
screen.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Read-Only Data Access | PASS | No SQL behavior changes. Writes target application-owned Cosmos configuration only; query tools remain read-only. |
| II. Single-File Agent Definitions | PASS | Built-in profiles remain solely in `config/agents.yaml`. Tool names/descriptions live with Python tool implementations and registry metadata; neither tool is added to a default profile. |
| III. Security & Credential Hygiene | PASS | Tool factories bind an authenticated `user_id`; schemas expose no ownership input. Results and logs exclude content, instructions, owner ids, credentials, and raw provider errors. Cosmos continues to use managed identity in production. |
| IV. Evaluation-Driven Quality | PASS | No model, prompt, or parameter default changes. Deterministic tool/service tests cover behavior; no evaluation run is required unless implementation later changes prompts. |
| V. Simplicity & Minimalism | PASS | Reuses `build_tool_instances`, `CosmosUserScopedRepository`, `SkillManager` validation, existing custom-agent validators, and repository doubles. Adds no package or deployable. |
| VI. Infrastructure as Code | PASS | The user-skill Cosmos container and app setting are added through existing Terraform Cosmos/App Service modules, not manually. |
| VII. Two-Tier API-First Architecture | PASS | Creation remains backend-only and management routes delegate to the same services. Existing FastAPI/OpenAPI surfaces remain the frontend boundary. |

**Pre-design gate**: PASS. No constitution violations or unresolved clarifications.

**Post-design gate**: PASS. The Phase 1 model and contracts retain the same boundaries: Python
owns tool documentation and validation, Cosmos owns durable data, FastAPI owns management access,
and no SQL, prompt, dependency, or third-tier change is introduced.

## Project Structure

### Documentation (this feature)

```text
specs/014-agent-creation-tools/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── management-api.md
│   └── runtime-tools.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
# Backend (existing FastAPI app at repository root)
tools.py                    # Add owner-bound create_skill/create_agent tool factories and docs.
app_context.py              # Register independent tool metadata/factories; instantiate exact grants.
definition_creation.py      # New shared request models, strict validation orchestration, services,
                            # and sanitized ToolCreationResult mapping.
skills_manager.py           # Expose shared skill field validation and combined global/user catalog.
user_data.py                # Add atomic create and a user-skills repository singleton.
validators.py               # Make capability lookup owner-aware and provide strict creation mode.
agent_factory.py            # Load selected skills from global + owner catalog for parent/sub-agents.
session_orchestration.py    # Pass immutable user identity to skill loading and tool factories;
                            # retain compatibility dropping only when starting old definitions.
api_routes/profiles.py      # Inventory tools from the registry, including ungranted optional tools.
api_routes/skills.py        # Read combined owner catalog while retaining established global CRUD.
api_routes/user_data.py     # Validate custom-agent management writes through shared service rules.
infra/                      # Declare user-skills container and configuration using existing modules.

frontend/src/               # No new screen; existing API-driven tool selector consumes inventory.

tests/
├── _doubles.py             # Add atomic create to user-scoped double and user-skill injection.
├── conftest.py             # Reset/inject the new repository singleton.
├── test_creation_tools.py  # Tool contract, binding, failures, no-secret output, independent grants.
├── test_definition_creation.py # Strict validation and persistence service tests.
├── test_user_data.py       # Management convergence, create atomicity, and user isolation.
├── test_skills_manager.py  # Combined catalog, collision, and owner-aware resolution tests.
├── test_agent_factory.py   # Owner-scoped selected-skill loading tests.
├── test_api.py             # Inventory and exact runtime tool availability tests.
└── test_*_cosmos.py        # Emulator coverage for owner partitioning and concurrent duplicate create.
```

**Structure Decision**: Keep the existing root-level FastAPI architecture. Add one narrow
`definition_creation.py` business layer because tool calls and HTTP routes need the same strict
validation/persistence behavior without calling each other. Keep storage mechanics in
`user_data.py`, skill-specific field/catalog behavior in `skills_manager.py`, and runtime grant
assembly in `app_context.py`. The frontend already renders `/api/tools`; no new UI component is
needed once inventory is registry-backed.

## Complexity Tracking

No constitution deviations. No complexity exceptions are required.

## Phase 0 - Research

See [research.md](research.md). All technical context is resolved. The controlling decisions are:
an explicit tool registry independent of profile defaults; owner-bound closure factories; shared
strict creation services; atomic `create_item` within `/user_id`; a separate user-skill container;
and owner-aware global-plus-user skill resolution.

## Phase 1 - Design & Contracts

- [data-model.md](data-model.md) defines grants, user-owned skill documents, custom-agent payloads,
  validation issues, and bounded results.
- [contracts/runtime-tools.md](contracts/runtime-tools.md) defines the model-visible tool schemas and
  stable result envelope.
- [contracts/management-api.md](contracts/management-api.md) defines catalog and custom-agent write
  convergence while preserving existing session compatibility.
- [quickstart.md](quickstart.md) defines focused implementation verification and emulator checks.

## Phase 2 - Implementation Planning

Implementation should proceed in dependency order: repository atomic create and user-skill store;
shared models/validators/services; owner-aware skill catalogs; tool registry/factories; session and
sub-agent identity threading; management route convergence; Terraform; then focused unit/API and
emulator tests. Detailed executable tasks are intentionally deferred to `/speckit.tasks`.
