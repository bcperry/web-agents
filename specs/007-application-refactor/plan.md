# Implementation Plan: Application Refactor And Deduplication

**Branch**: `007-application-refactor` | **Date**: 2026-05-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/007-application-refactor/spec.md`

## Summary

Refactor the existing FastAPI plus React application to remove duplicated backend session orchestration, frontend API/storage/content helpers, oversized admin/chat state, dead or repeated CSS, and brittle test setup while preserving current API routes, SSE event names, local storage keys, user-visible UI behavior, and deployment shape. The plan explicitly excludes edits to `config/agents.yaml`.

## Follow-Up Wrapper Flattening Plan

The first implementation pass successfully moved behavior out of oversized files, but the extraction introduced several layers that now obscure the session story. The follow-up cleanup should reduce wrapper code rather than create more helper surfaces.

### Goals

- Make the session creation path readable in one pass: route request -> validated session intent -> chat runtime -> stored session response.
- Collapse pass-through agent factory functions so there is one obvious place where the SDK agent is built.
- Replace frontend session API variants with one typed session creation request while preserving existing exported API functions during migration.
- Delete compatibility aliases, one-method classes, and setter-bag hooks when they no longer represent a useful domain boundary.
- Keep the completed behavior-preserving contract intact: routes, SSE events, localStorage keys, frontend exports, and `config/agents.yaml` remain unchanged.

### Targeted Cleanup Areas

| Area | Current Smell | Preferred Shape |
|------|---------------|-----------------|
| `agent_factory.py` | `create_chat_runtime()` -> `spawn_agent()` -> `_create_agent()` hides the actual SDK construction | `create_chat_runtime()` calls a single clear `build_agent()`/inline builder and owns runtime construction |
| `session_orchestration.py` | Per-request `SessionCreationService(...)` class wraps procedural session creation | Plain request-oriented functions or a module-level service with fewer constructor dependencies |
| `frontend/src/api/client.ts` | Four wrappers post to `/api/sessions` with body variants | One internal `postSession()`/`createSessionRequest()` plus compatibility exports |
| `frontend/src/hooks/useSessionLifecycle.ts` | `startChatSession()` mirrors backend mode branching and calls many API wrappers | Build one typed session request payload, then call one API function |
| `validators.py` | `ToolRegistry` is a one-method wrapper over known tool validation | Direct `known_tool_names_from_profiles()` + `validate_tool_names()` usage |
| `streaming.py` | Underscore compatibility aliases duplicate exported helper names | Import/use canonical helper names only |
| frontend form hooks | Some hooks mostly expose raw state setters | Keep hooks only where they own workflow decisions; inline or rename setter bags |

### Non-Goals

- Do not edit `config/agents.yaml`.
- Do not change API routes, response field names, status codes, SSE event names, localStorage keys, or generated frontend public exports.
- Do not add backend or frontend dependencies.
- Do not start a backend package-layout migration in this follow-up slice.

## Technical Context

**Language/Version**: Python 3.12.6, TypeScript 5.9, React 19  
**Primary Dependencies**: FastAPI, agent-framework-core/openai/azure-ai-search, Azure SDKs, React, Vite, react-markdown, MSAL  
**Storage**: In-memory backend sessions, file-backed `skills/`, browser localStorage, Terraform-managed Azure App Service resources  
**Testing**: `uv run pytest`, `npm test`, `npm run build`, `npm run lint`, Playwright screenshot verification for visual changes  
**Target Platform**: Linux development environment and Azure App Service single deployment serving FastAPI plus built React SPA  
**Project Type**: Two-tier web application in one repository and one deployment unit  
**Performance Goals**: No user-visible latency regression; preserve streaming behavior and session cleanup while reducing maintainability cost  
**Constraints**: Do not edit `config/agents.yaml`; no new runtime dependencies unless justified; preserve API/SSE/storage contracts; backend package manager is `uv` only; frontend package manager is `npm`; visual verification is mandatory for CSS/UI changes  
**Scale/Scope**: Refactor about 2.9k backend root Python lines, 4.3k frontend TypeScript/TSX lines, 3.0k frontend CSS lines, and 1.4k backend test lines; target at least 1,000 net runtime-line reduction

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Gate Status**: PASS

- **Read-Only Data Access**: PASS. No SQL tool behavior or database write capability is added. Existing read-only guarantees must remain covered by tests.
- **Single-File Agent Definitions**: PASS. `config/agents.yaml` is read-only and out of scope for every refactor task.
- **Security & Credential Hygiene**: PASS. Refactor preserves backend-only access to LLM, search, MCP, auth, and secrets; API responses and logs must not expose credentials or bearer tokens.
- **Evaluation-Driven Quality**: PASS. No prompt, model, agent profile, or parameter behavior changes are planned. Evaluation pipeline is not required unless implementation later changes prompts or model settings.
- **Simplicity & Minimalism**: PASS. New code is limited to focused helper/service modules that remove real duplication. No new dependencies are planned.
- **Infrastructure as Code**: PASS. No infrastructure changes are planned. Existing Terraform deployment remains unchanged.
- **Two-Tier API-First Architecture**: PASS. FastAPI remains the sole backend gateway and React remains presentation/UI. No frontend direct Azure calls are introduced.
- **Visual Verification Protocol**: PASS WITH ACTION. CSS or component markup changes must complete build plus Playwright screenshot verification before implementation is considered done.

## Project Structure

### Documentation (this feature)

```text
specs/007-application-refactor/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
.
├── main.py                         # Keep FastAPI app/routes; reduce orchestration
├── agent_factory.py                # Reuse existing runtime creation machinery
├── mcp_servers.py                  # Reuse existing MCP parsing/connection helpers
├── session_orchestration.py        # New: shared session creation flow
├── validators.py                   # New: tool/skill/input/image/error validation helpers
├── skills_manager.py               # New: file-backed skill CRUD/path safety
├── streaming.py                    # New: SSE event, usage, and content conversion helpers
├── tests/
│   ├── conftest.py                 # Shared env/client/session fixtures
│   ├── test_api.py                 # Existing route contract tests
│   ├── test_session_orchestration.py
│   ├── test_validators.py
│   ├── test_skills_manager.py
│   └── test_streaming.py
└── frontend/
  └── src/
    ├── api/
    │   ├── client.ts           # Preserve exported API functions
    │   └── helpers.ts          # New: authenticated fetch/response handling
    ├── components/             # Extract reusable admin/image subcomponents
    ├── hooks/                  # Extract chat lifecycle/form-state hooks
    ├── pages/                  # Keep page exports stable
    ├── styles/index.css        # Consolidate app styles
    └── utils/
      ├── storage.ts          # New: typed localStorage helpers
      └── content.ts          # New: image/content filtering and formatting
```

**Structure Decision**: Preserve the current root-backend plus `frontend/` layout required by the constitution. Add small backend modules beside `main.py` rather than moving the backend into a new package during this refactor, because that gives the line-reduction and duplication benefits with less import and deployment risk.

## Complexity Tracking

No constitution violations identified.

## Post-Design Constitution Check

**Gate Status**: PASS

- Design preserves read-only SQL posture and does not add data mutation capabilities.
- Design keeps `config/agents.yaml` unchanged and explicitly verifies it remains diff-free.
- Design preserves backend-only access to secrets and Azure services.
- Design avoids new dependencies and uses current `uv`, `npm`, pytest, Vite, and Playwright tooling.
- Design preserves the two-tier FastAPI plus React deployment model.
- Design includes visual verification for CSS/component appearance changes.
