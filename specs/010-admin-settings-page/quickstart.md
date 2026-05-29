# Quickstart: Admin Settings Page

## Prerequisites

- Use Node/npm for frontend commands.
- Use `uv` for backend/server commands if running the full app.
- Work from repository root `/home/bcperry/git_wsl/web-agents`.

## Implementation Outline

1. Remove theme and advanced/account controls from `frontend/src/components/Sidebar.tsx` and its sidebar-specific CSS.
2. Add a reusable settings gear/menu component under `frontend/src/components/`.
3. Render the settings gear in both authenticated `ChatPage` headers: profile selection and active chat.
4. Extend `AdminPage` tabs to include `Settings` as the default section.
5. Add an Admin Settings section that uses `useTheme` to render Light/Dark controls and shows account context when available.
6. Keep `AgentBuilder` and `SkillBuilder` under the existing Agents and Skills tabs without changing builder behavior.
7. Update CSS for header settings menu, Admin Settings, responsive behavior, and removal of obsolete sidebar settings styles.

## Validation

```bash
cd frontend
npm run build
```

For full visual verification, build the frontend and run the backend serving static assets:

```bash
AUTH_DISABLED=true uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

Capture affected screens with Playwright at desktop, tablet, and mobile widths. Required screenshots:

- Profile selection header with settings gear/menu.
- Active chat header with settings gear/menu.
- Admin Settings tab in light theme.
- Admin Settings tab in dark theme.
- Expanded sidebar showing conversation controls only.

Review screenshots for clipped text, overlapping controls, missing focus/menu affordances, and theme consistency.

Final reusable capture command:

```bash
uv run python scripts/capture_admin_settings_screenshots.py --base-url http://localhost:8000 --output-dir screenshots/010-admin-settings-page --mock-api
```

The script captures 21 PNG files: profile settings menu, chat settings menu, sidebar conversation view, Admin Settings light/dark, Admin Agents, and Admin Skills for desktop, tablet, and mobile viewports.