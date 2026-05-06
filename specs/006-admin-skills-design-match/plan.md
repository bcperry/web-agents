# Implementation Plan: Admin Skills Design Match

**Branch**: `006-admin-skills-design-match` | **Date**: 2026-05-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/006-admin-skills-design-match/spec.md`

## Summary

Redesign the Admin Skills tab so it visually matches the Agent Builder surface: same left-list/right-form layout, panel framing, section headers, list card treatment, text action buttons, dense form styling, feedback states, and responsive behavior. Keep all existing skill create, edit, delete, AI-generation, validation, and API behavior intact. Extend the reusable Admin screenshot tooling to capture the Skills tab states required by the constitution.

## Technical Context

**Language/Version**: TypeScript 5.9 frontend; React 19; Python 3.12.6 backend unchanged  
**Primary Dependencies**: React, Vite 8, existing frontend API client, existing FastAPI skill endpoints, Playwright for visual verification  
**Storage**: Existing filesystem-backed skills under `skills/<name>/SKILL.md`; no new storage  
**Testing**: `cd frontend && npm run lint`; `cd frontend && npm run build`; Playwright screenshot verification via reusable script; backend tests not expected unless API behavior changes  
**Target Platform**: Single FastAPI App Service serving built React SPA; local Linux/WSL development  
**Project Type**: Two-tier web application: FastAPI backend + React/TypeScript frontend  
**Performance Goals**: Admin Skills render remains synchronous after existing `/api/skills` load; no added network round trips for visual-only layout changes  
**Constraints**: Preserve existing skill CRUD behavior; no new frontend/backend dependencies; UI changes require constitution visual verification with screenshots in `screenshots/`  
**Scale/Scope**: One Admin tab/component (`frontend/src/components/SkillBuilder.tsx`), shared Admin styles (`frontend/src/styles/index.css`), and screenshot script extension (`scripts/capture_admin_agent_screenshots.py` or a sibling reusable Admin script)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Read-Only Data Access**: PASS. Feature does not add SQL operations or data access.
- **II. Single-File Agent Definitions**: PASS. No agent profile definition changes.
- **III. Security & Credential Hygiene**: PASS. No credential or auth flow changes.
- **IV. Evaluation-Driven Quality**: PASS. No prompt/model/parameter behavior changes requiring eval pipeline.
- **V. Simplicity & Minimalism**: PASS. Reuse existing Agent Builder layout/style primitives instead of adding a new design system or dependency.
- **VI. Infrastructure as Code**: PASS. No infrastructure changes.
- **VII. Two-Tier API-First Architecture**: PASS. Existing Skills API remains through FastAPI; frontend does not call backend internals directly.
- **Visual Verification Protocol**: PASS WITH REQUIRED TASKS. This is a visual Admin UI change and must run frontend build plus Playwright screenshot review. Reusable screenshot scripting is required for repeated Admin states.

## Project Structure

### Documentation (this feature)

```text
specs/006-admin-skills-design-match/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── tasks.md                 # Created later by /speckit.tasks
```

### Source Code (repository root)

```text
frontend/src/components/SkillBuilder.tsx       # Redesign Skills list/form structure using Agent Builder layout language
frontend/src/styles/index.css                  # Reuse/consolidate Admin builder styles and responsive behavior
frontend/src/api/client.ts                     # No expected change unless existing skill types need reuse
frontend/src/types/api.ts                      # No expected change unless existing SkillSummary typing is insufficient
scripts/capture_admin_agent_screenshots.py     # Extend or mirror for Skills tab visual verification
screenshots/                                  # Store generated Skills tab screenshots for review
```

**Structure Decision**: Keep the redesign inside the existing frontend/Admin component structure. `SkillBuilder` remains the Skills tab implementation, but its JSX and CSS should reuse Agent Builder layout classes or shared Admin-builder classes where practical. No backend restructuring or API contract change is planned.

## Complexity Tracking

No constitution violations or added complexity exceptions are required.

## Phase 0: Research Summary

See [research.md](research.md).

## Phase 1: Design Summary

See [data-model.md](data-model.md) and [quickstart.md](quickstart.md). No external interface contracts are required because this feature preserves the existing Skills API and only changes Admin presentation.

## Post-Design Constitution Check

- **I. Read-Only Data Access**: PASS. No SQL or data access changes.
- **II. Single-File Agent Definitions**: PASS. No agent YAML changes.
- **III. Security & Credential Hygiene**: PASS. No credentials or auth changes.
- **IV. Evaluation-Driven Quality**: PASS. No agent behavior changes.
- **V. Simplicity & Minimalism**: PASS. Design reuses existing Agent Builder styles and avoids new dependencies.
- **VI. Infrastructure as Code**: PASS. No infrastructure changes.
- **VII. Two-Tier API-First Architecture**: PASS. Existing API-first shape remains unchanged.
- **Visual Verification Protocol**: PASS WITH REQUIRED IMPLEMENTATION TASKS. Implementation tasks must include frontend build, reusable Playwright screenshot script updates, screenshot capture/review for Skills list/create/edit states, and responsive desktop/tablet/mobile coverage.
