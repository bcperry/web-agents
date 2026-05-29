# Implementation Plan: Admin Settings Page

**Branch**: `010-admin-settings-page` | **Date**: 2026-05-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/010-admin-settings-page/spec.md`

## Summary

Move app-level settings out of the conversation sidebar and into a stronger Admin page settings hub. Add a top-right settings gear in authenticated chat headers that exposes user identity, Admin navigation, and logout, while Admin gains a default Settings tab containing the existing Light/Dark theme control. Preserve existing Agents and Skills admin workflows.

## Technical Context

**Language/Version**: TypeScript 5.9.x and React 19.x for frontend; Python 3.12.6/FastAPI backend unchanged  
**Primary Dependencies**: React, Vite, existing `useTheme` and `useAuth` hooks; no new dependencies  
**Storage**: Existing localStorage key `webagents_theme`; no backend storage changes  
**Testing**: `npm run build` for frontend type/build validation; screenshot-based visual verification per constitution  
**Target Platform**: Browser SPA served by FastAPI single deployment  
**Project Type**: Two-tier web application; this feature is frontend-only  
**Performance Goals**: No added network calls; settings menu and Admin tab interactions should feel immediate on existing supported browsers  
**Constraints**: Preserve existing Admin browser-history behavior; no API/infra/auth contract changes; no new package dependencies; UI changes require Playwright screenshots at desktop/tablet/mobile widths  
**Scale/Scope**: Affects chat/profile headers, sidebar, Admin page tabs, and existing theme control placement

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Read-Only Data Access | N/A | No SQL or backend data access changes |
| II. Single-File Agent Definitions | N/A | No agent profile or tool definition changes |
| III. Security & Credential Hygiene | PASS | No secrets, endpoints, bundles, or auth token handling changes; user email is already available client auth display data |
| IV. Evaluation-Driven Quality | N/A | No prompt, model, or parameter changes |
| V. Simplicity & Minimalism | PASS | Reuses current hooks and Admin tab structure; no new dependencies or settings backend |
| VI. Infrastructure as Code | N/A | No infrastructure changes |
| VII. Two-Tier API-First Architecture | PASS | Frontend presentation change only; backend API remains unchanged |

**Gate result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/010-admin-settings-page/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── ui-settings-contract.md
└── tasks.md              # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
frontend/src/
├── components/
│   ├── Sidebar.tsx            # Remove theme/admin/user/logout sections and related props
│   └── SettingsMenu.tsx       # New reusable header gear/menu component
├── pages/
│   ├── ChatPage.tsx           # Render SettingsMenu in profile and chat headers
│   └── AdminPage.tsx          # Add Settings tab and theme/account settings section
├── hooks/
│   ├── useAuth.ts             # Existing auth source; no behavior change expected
│   └── useTheme.tsx           # Existing theme source; no behavior change expected
└── styles/
    └── index.css              # Header menu, Admin Settings, responsive, and sidebar cleanup styles

frontend/
└── package.json               # Existing build/test scripts only

screenshots/
└── 010-admin-settings-page/   # Visual verification captures
```

**Structure Decision**: Web application with backend at repository root and React frontend in `frontend/`. Implementation is scoped to frontend UI files and screenshots; no backend, infra, or API files are expected to change.

## Phase 0: Research

Research completed in [research.md](research.md). All technical context values are resolved; no open clarification items remain.

## Phase 1: Design & Contracts

Design artifacts completed:

- [data-model.md](data-model.md)
- [quickstart.md](quickstart.md)
- [contracts/ui-settings-contract.md](contracts/ui-settings-contract.md)

## Constitution Check - Post-Design

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Read-Only Data Access | N/A | No SQL or data access changes introduced by design |
| II. Single-File Agent Definitions | N/A | No agent definition changes introduced by design |
| III. Security & Credential Hygiene | PASS | Design only displays existing authenticated email and does not expose secrets |
| IV. Evaluation-Driven Quality | N/A | No AI behavior changes |
| V. Simplicity & Minimalism | PASS | Design uses one small reusable menu and existing hooks/tabs |
| VI. Infrastructure as Code | N/A | No infra changes |
| VII. Two-Tier API-First Architecture | PASS | No direct Azure/frontend service calls or API contract changes |

**Gate result**: PASS — no violations.

## Complexity Tracking

No constitution violations require justification.