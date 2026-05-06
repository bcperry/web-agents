# Quickstart: Admin Skills Design Match

## Prerequisites

```bash
uv sync --group dev
cd frontend && npm install
```

Use local auth bypass for manual verification unless testing Azure AD specifically:

```bash
export AUTH_DISABLED=true
export VITE_AUTH_DISABLED=true
```

## Build and Run

```bash
cd frontend
npm run build
cd ..
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000`.

## Manual Verification Flow

1. Open the app and accept the disclaimer if shown.
2. Open Admin.
3. Compare Agents and Skills tabs.
4. Confirm Skills uses the same Admin design language as Agents:
   - Left-side saved-items panel.
   - Right-side create/edit form panel.
   - Matching section title styling.
   - Matching list-card border, spacing, text hierarchy, and actions.
   - Matching form labels, inputs, textarea, and action buttons.
5. Create a new skill and confirm validation and save behavior still work.
6. Edit an existing skill and confirm name is read-only while description/content remain editable.
7. Trigger delete confirmation and confirm the action styling remains consistent.
8. Confirm loading, empty, error, and success states do not visually break the Admin layout.

## Regression Checks

```bash
cd frontend && npm run lint
cd frontend && npm run build
```

Backend tests are optional unless implementation changes Skill API behavior:

```bash
uv run pytest
```

## Visual Verification Requirements

This feature changes visible Admin UI and must follow the constitution's Playwright protocol.

Capture at minimum:

- Skills tab list state at 1440x900.
- Skills create form state at 1440x900.
- Skills edit form state at 1440x900.
- Skills delete confirmation state at 1440x900.
- Skills tab at 768x1024 and 360x640 to verify responsive behavior.

The reusable Admin screenshot script now captures both Agent Builder states and Skills states so future agents can regenerate the same evidence without inline Playwright heredocs.

Example command shape:

```bash
uv run python scripts/capture_admin_agent_screenshots.py --base-url http://localhost:8000
```

## Final Verification Report

Validated on 2026-05-06 against `http://localhost:8001` with auth disabled and built frontend assets served by FastAPI.

Commands run:

```bash
cd frontend && npm run lint && npm run build
AUTH_DISABLED=true VITE_AUTH_DISABLED=true uv run uvicorn main:app --host 0.0.0.0 --port 8001
uv run python scripts/capture_admin_agent_screenshots.py --base-url http://localhost:8001 --output-dir screenshots
```

Generated and reviewed screenshots:

- `screenshots/006-admin-skills-list.png`
- `screenshots/006-admin-skills-create.png`
- `screenshots/006-admin-skills-edit.png`
- `screenshots/006-admin-skills-delete-confirm.png`
- `screenshots/006-admin-skills-tablet.png`
- `screenshots/006-admin-skills-mobile.png`

Review result: Skills now uses the Agent Builder-style left list and right form layout, visible text is readable, no affected Admin emoji remains, controls do not overlap, and desktop/tablet/mobile captures show no horizontal overflow. Browser-level create/edit/delete regression passed using a temporary `visual-regression-skill`, which was deleted after the run.

API/storage check: no changes were made to `main.py`, `frontend/src/api/client.ts`, or persisted `skills/` content.
