# Implementation Plan: Baked Agent Customization

**Branch**: `005-baked-agent-customization` | **Date**: 2026-05-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/005-baked-agent-customization/spec.md`

## Summary

Allow users to customize built-in/pre-baked agents with the same behavior/capability fields as existing custom agents while keeping the canonical built-in name read-only. Store overrides in browser localStorage keyed by built-in profile id, visibly mark overridden agents in the UI, apply overrides when starting sessions while preserving the original profile identity, and provide a fast `make standard` path that exports a canonical `agents.yaml` candidate rather than mutating server configuration from the browser.

## Technical Context

**Language/Version**: Python 3.12.6 backend; TypeScript 5.9 frontend; React 19; Vite 8  
**Primary Dependencies**: FastAPI, agent-framework-core/openai/azure-ai-search, React, MSAL, localStorage APIs  
**Storage**: Browser localStorage for per-user built-in agent overrides; existing `config/agents.yaml` remains canonical shared standard profile source; backend in-memory sessions unchanged  
**Testing**: `uv run pytest`; `cd frontend && npm run build`; `cd frontend && npm run lint`; Playwright visual verification for affected UI screens per constitution  
**Target Platform**: Single FastAPI App Service serving built React SPA; local WSL/Linux development  
**Project Type**: Two-tier web application: FastAPI backend + React/TypeScript frontend  
**Performance Goals**: Profile list hydration and override merge should be synchronous/local and not add network round trips after profile definitions load; session start should remain comparable to current custom-agent session start  
**Constraints**: Do not mutate `config/agents.yaml` from the browser; do not store secrets/tokens in localStorage overrides; all agent functionality still flows through backend API; visual UI changes require screenshot verification  
**Scale/Scope**: Adds one localStorage-backed customization store, profile-definition API, session override request path, Admin/ProfileSelector/Chat UI indicators, and tests for existing custom-agent and built-in profile behavior

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Read-Only Data Access**: PASS. Feature does not add SQL operations or data mutation tools.
- **II. Single-File Agent Definitions**: PASS. `config/agents.yaml` remains the canonical standard profile source. Local browser overrides are user-specific runtime customizations, not alternate shared profile definition files. `make standard` produces a candidate payload for explicit source review.
- **III. Security & Credential Hygiene**: PASS. Overrides must not store credentials, tokens, connection strings, or secrets. MCP auth settings may store booleans/scopes only, matching existing custom-agent behavior.
- **IV. Evaluation-Driven Quality**: PASS WITH REQUIRED FOLLOW-UP. Local overrides do not change shared prompt behavior. If a promoted candidate is actually committed to `config/agents.yaml`, prompt/model/parameter eval pipeline must run before shared deployment.
- **V. Simplicity & Minimalism**: PASS. Reuses existing custom-agent field shape, localStorage pattern, and agent runtime path. Adds targeted backend endpoints rather than a new persistence tier.
- **VI. Infrastructure as Code**: PASS. No infrastructure changes planned.
- **VII. Two-Tier API-First Architecture**: PASS. Frontend continues to call only backend API for agent sessions and profile data.
- **Visual Verification Protocol**: PASS WITH REQUIRED IMPLEMENTATION TASKS. UI changes affect Admin, profile selector, and active chat indicators; Playwright screenshots are required before completion.

## Project Structure

### Documentation (this feature)

```text
specs/005-baked-agent-customization/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api-contract.md
└── tasks.md                 # Created later by /speckit.tasks
```

### Source Code (repository root)

```text
main.py                      # Add safe profile definition endpoint and session override handling
prompt_config.py             # Reuse/extend profile loading helpers if needed
frontend/src/types/api.ts    # Add built-in override, profile definition, and session override types
frontend/src/api/client.ts   # Add profile definition client + session override payload support
frontend/src/hooks/          # Add/use built-in customization localStorage hook
frontend/src/pages/          # Update AdminPage, AgentBuilder, ChatPage flows
frontend/src/components/     # Update ProfileSelector and capabilities/indicator UI
tests/                       # Add backend contract/session tests
frontend/src/**/*.tsx        # Frontend build/lint coverage; visual verification via Playwright screenshots
```

**Structure Decision**: Use the existing two-tier repo layout. Backend files remain at repository root; frontend React source remains under `frontend/src`; feature artifacts remain under `specs/005-baked-agent-customization`.

## Complexity Tracking

No constitution violations or additional complexity exceptions are required.

## Phase 0: Research Summary

See [research.md](research.md).

## Phase 1: Design Summary

See [data-model.md](data-model.md), [contracts/api-contract.md](contracts/api-contract.md), and [quickstart.md](quickstart.md).

## Post-Design Constitution Check

- **I. Read-Only Data Access**: PASS. No SQL write path introduced.
- **II. Single-File Agent Definitions**: PASS. Standard shared definitions remain in `config/agents.yaml`; local overrides are explicit per-user runtime state; promotion is export/candidate only.
- **III. Security & Credential Hygiene**: PASS. API contract excludes secrets from definitions/overrides and continues to route all sensitive operations through backend.
- **IV. Evaluation-Driven Quality**: PASS. Shared standard promotion requires follow-up PR/edit to YAML and eval pipeline; local-only customizations are user-specific runtime changes.
- **V. Simplicity & Minimalism**: PASS. Reuses current custom-agent schema and storage pattern, with one focused additional hook and API extension.
- **VI. Infrastructure as Code**: PASS. No infra changes.
- **VII. Two-Tier API-First Architecture**: PASS. Frontend consumes backend profile/session APIs only.
- **Visual Verification Protocol**: PASS WITH REQUIRED TASKS. The tasks phase must include build, local server, Playwright screenshots for Admin/ProfileSelector/chat customized states, and image review.
