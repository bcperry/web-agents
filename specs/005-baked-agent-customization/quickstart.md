# Quickstart: Baked Agent Customization

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

## Backend and Frontend Build

```bash
cd frontend
npm run build
cd ..
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000`.

## Manual Test Flow

1. Open the app and go to Admin.
2. Open the Agents tab.
3. In the built-in agents section, choose a standard agent such as `FAA Aviation AI` or `Azure Government Specialist`.
4. Confirm the edit form is pre-populated with the same fields as custom agents:
   - Read-only canonical name
   - Description
   - System prompt
   - Temperature
   - Tools
   - AI Search context
   - Skills
   - MCP servers
   - Starter questions
   - Icon
5. Change the description or add an obvious starter question.
6. Save the built-in customization.
7. Return to chat.
8. Confirm the same built-in agent card remains in place and shows a visible `CUSTOMIZED` indicator.
9. Select the customized built-in agent.
10. Confirm the active chat/capabilities area indicates local override settings are active.
11. Start a conversation and confirm normal message streaming still works.
12. Start a new chat and return to Admin.
13. Use `make standard` for the customized built-in agent.
14. Confirm a complete `agents.yaml` candidate payload/snippet is shown or copied/exported.
15. Use reset/default action for the same built-in agent.
16. Return to profile selection and confirm the `CUSTOMIZED` indicator is gone and defaults are restored.

## Regression Checks

```bash
uv run pytest
cd frontend && npm run lint
cd frontend && npm run build
```

## Visual Verification Requirements

Because this feature changes visible UI, complete the constitution's Playwright screenshot protocol before implementation is considered done.

Capture at minimum:

- Profile selector with no customized built-ins.
- Profile selector with one customized built-in card.
- Admin Agents tab showing built-in and custom agent sections.
- Built-in customization edit form.
- Active chat view using a customized built-in profile.
- Make-standard candidate modal/drawer.

Default viewport: `1440x900`. Also capture responsive views at `768x1024` and `360x640` if the Admin or profile card layout changes.

## Promotion Workflow

The `make standard` UI only creates a candidate. To actually make an override the shared standard agent:

1. Apply the generated candidate to `config/agents.yaml` in source control.
2. Run `uv run pytest` to validate backend/profile behavior.
3. Run frontend lint/build.
4. Run the evaluation pipeline required for prompt/model/parameter changes.
5. Review and merge through the normal PR process.
