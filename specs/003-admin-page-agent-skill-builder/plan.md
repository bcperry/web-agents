# Implementation Plan: Admin Page — Agent Builder + Skill Builder

**Branch**: `003-admin-page-agent-skill-builder` | **Date**: 2026-06-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-admin-page-agent-skill-builder/spec.md`

## Summary

Move the existing Custom Agent Builder from `ChatPage` into a new dedicated `AdminPage` component (two-tab layout: Agents + Skills). Add a Skill Builder tab that provides CRUD for `skills/<name>/SKILL.md` files via new backend REST endpoints. Navigation via the existing sidebar's ADVANCED section replaces the current "CUSTOM AGENT BUILDER" button with an "ADMIN" button. No new dependencies needed; no routing library required — simple view-state switching in `App.tsx`.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript/React 18 (frontend)  
**Primary Dependencies**: FastAPI (backend), React + existing component library (frontend)  
**Storage**: Filesystem (`skills/<name>/SKILL.md`), localStorage (custom agents — unchanged)  
**Testing**: pytest (backend), npm test (frontend)  
**Target Platform**: Linux server + browser SPA  
**Project Type**: Web application (two-tier FastAPI + React)  
**Performance Goals**: Standard CRUD latency (<200ms p95 for skill reads/writes)  
**Constraints**: No new npm or Python packages; constitution-compliant read-only SQL; authenticated endpoints only  
**Scale/Scope**: Small admin feature; ~5-10 skills expected

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Notes |
|-----------|-------|-------|
| I. Read-Only Data Access | PASS | No SQL involved in this feature; skill files are local filesystem only |
| II. Single-File Agent Definitions | PASS | `agents.yaml` unchanged; skill CRUD operates on `skills/` directory |
| III. Security & Credential Hygiene | PASS | All new endpoints use `get_current_user`; no secrets in frontend; file paths constructed server-side only |
| IV. Evaluation-Driven Quality | PASS | No prompt/model changes; agent behavior unchanged |
| V. Simplicity & Minimalism | PASS | No new packages; simple view-state routing (no React Router); CRUD via filesystem |
| VI. Infrastructure as Code | PASS | No new Azure resources |
| VII. Two-Tier API-First Architecture | PASS | All skill file operations proxied through FastAPI backend |

**Visual Verification Protocol**: Required — this feature adds a new Admin page with tabs, forms, and list views. Playwright screenshots required before merge.

## Project Structure

### Documentation (this feature)

```text
specs/003-admin-page-agent-skill-builder/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── pages/
│   │   ├── AdminPage.tsx        # NEW — two-tab admin layout
│   │   ├── AgentBuilder.tsx     # UNCHANGED (moved into AdminPage usage)
│   │   └── ChatPage.tsx         # MODIFIED — remove AgentBuilder state/rendering
│   ├── components/
│   │   ├── SkillBuilder.tsx     # NEW — CRUD UI for skills
│   │   └── Sidebar.tsx          # MODIFIED — replace agent builder btn with admin btn
│   ├── api/
│   │   └── client.ts            # MODIFIED — add skill CRUD API calls
│   ├── types/
│   │   └── api.ts               # MODIFIED — add Skill types
│   └── App.tsx                  # MODIFIED — add adminView state

main.py                          # MODIFIED — add GET/POST/PUT/DELETE /api/skills/* endpoints
tests/
└── test_skills_api.py           # NEW — backend tests for skill CRUD endpoints
```

## Phase 0: Research

> No NEEDS CLARIFICATION items — all technical decisions are determined by existing codebase.

See `research.md`.

## Phase 1: Design & Contracts

See `data-model.md` and `contracts/`.

## Complexity Tracking

No constitution violations.
