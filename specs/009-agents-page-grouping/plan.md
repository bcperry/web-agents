# Implementation Plan: Agents Page Grouping & Pagination

**Branch**: `009-agents-page-grouping` | **Date**: 2026-05-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/009-agents-page-grouping/spec.md`

## Summary

Add an optional `group` field to agent profiles (both in `agents.yaml` and custom agents) and render the agents page (`ProfileSelector`) with collapsible group sections and pagination. Uses the same dropdown/toggle pattern as the admin page `AgentBuilder`. No changes to agent behavior, session creation, or backend logic beyond passing the `group` field through.

## Technical Context

**Language/Version**: Python 3.12+ (backend), TypeScript (frontend)  
**Primary Dependencies**: FastAPI (backend), React (frontend), Vite (bundler)  
**Storage**: `config/agents.yaml` (built-in), localStorage (custom agents)  
**Testing**: pytest (backend), manual + visual verification (frontend)  
**Target Platform**: Web (Linux server + browser SPA)  
**Project Type**: Web service (two-tier: FastAPI backend + React frontend)  
**Performance Goals**: N/A (client-side grouping, no new API calls)  
**Constraints**: Must not break existing API contract; purely additive  
**Scale/Scope**: ~10-20 agents currently, designed to handle 50+

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Read-Only Data Access | N/A | No SQL changes |
| II. Single-File Agent Definitions | PASS | `group` added to existing `agents.yaml` schema |
| III. Security & Credential Hygiene | PASS | No secrets, no new endpoints |
| IV. Evaluation-Driven Quality | N/A | No prompt/model changes |
| V. Simplicity & Minimalism | PASS | Minimal additive change, reuses existing UI pattern |
| VI. Infrastructure as Code | N/A | No infra changes |
| VII. Two-Tier API-First Architecture | PASS | Backend passes `group` through `/api/profiles`; frontend handles display |

**Gate result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/009-agents-page-grouping/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
config/
└── agents.yaml              # Add optional `group` field per profile

main.py                      # Pass `group` field in GET /api/profiles response

frontend/src/
├── types/
│   └── api.ts               # Add `group?: string` to AgentProfile & CustomAgentDefinition
├── components/
│   └── ProfileSelector.tsx  # Refactor: group agents into collapsible sections with pagination
├── pages/
│   └── AgentBuilder.tsx     # Add `group` field input to custom agent form
├── hooks/
│   └── useAgentBuilderForm.ts  # Include `group` in form state
└── styles/
    └── (existing CSS)       # Extend with group section styles

tests/
└── test_prompt_tools_yaml.py  # Update schema validation if needed
```

**Structure Decision**: Web application (Option 2). Backend at repo root, frontend in `frontend/`. All changes are additive to existing files — no new files except possibly a small CSS addition.

## Complexity Tracking

> No constitution violations — section not required.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
