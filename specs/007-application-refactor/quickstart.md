# Quickstart: Application Refactor And Deduplication

## Scope Guard

Before starting implementation, confirm the branch and the protected config file:

```bash
git branch --show-current
git diff -- config/agents.yaml
```

Expected branch: `007-application-refactor`.

Expected `config/agents.yaml` diff: empty.

## Recommended Implementation Order

1. Extract backend validators and unit tests.
2. Extract backend streaming/usage/error helpers and unit tests.
3. Extract backend skill manager and unit tests.
4. Extract backend session orchestration and keep route contracts stable.
5. Add frontend storage/content/API helpers while preserving exports.
6. Split `useChat`, `AgentBuilder`, and `SkillBuilder` internals by responsibility.
7. Clean CSS last and run visual verification.
8. Replace brittle source-inspection tests where behavior can be asserted.
9. Flatten wrapper layers introduced or exposed by the first pass: agent factory construction, session orchestration, frontend session API variants, compatibility aliases, and state-only hooks.

## Wrapper Flattening Follow-Up

Focus this cleanup on deleting or collapsing indirection. Prefer a direct function with a precise name over a class or wrapper whose only job is to forward arguments.

Recommended order:

1. Collapse `spawn_agent()` and `_create_agent()` in `agent_factory.py` into one clear agent builder used by `create_chat_runtime()`.
2. Replace per-request `SessionCreationService(...)` construction with clearer session creation functions or a module-level service boundary in `session_orchestration.py` and `main.py`.
3. Centralize frontend `/api/sessions` request posting in `frontend/src/api/client.ts`, keeping current exported functions as compatibility shims if needed.
4. Simplify `startChatSession()` in `frontend/src/hooks/useSessionLifecycle.ts` so it builds one session intent/request instead of mirroring every backend branch through separate client functions.
5. Remove `ToolRegistry` in `validators.py` and use direct tool-name validation helpers.
6. Remove underscore compatibility exports in `streaming.py` after `main.py` and tests import canonical helper names.
7. Revisit frontend hooks that mostly return setters, especially `useSkillForm`, `useAgentBuilderForm`, and `useAgentMcpEditor`, and either give them workflow ownership or inline the state back into the owning component.

### Phase 7 Starting Call Chains - 2026-05-07

Current backend standard session path before wrapper flattening:

```text
main.create_session
-> SessionCreationService(...).create
-> SessionCreationService._create_profile_session
-> create_chat_runtime
-> spawn_agent
-> _create_agent
-> OpenAIChatClient.as_agent
-> agent.create_session
```

Current backend custom session path before wrapper flattening:

```text
main.create_session
-> SessionCreationService(...).create
-> SessionCreationService._create_custom_session
-> create_chat_runtime
-> spawn_agent
-> _create_agent
-> OpenAIChatClient.as_agent
-> agent.create_session
```

Current backend built-in override path before wrapper flattening:

```text
main.create_session
-> SessionCreationService(...).create
-> SessionCreationService._create_profile_session
-> ProfileOverrideRequest parsing
-> create_chat_runtime(custom_name=profile_name, custom_instructions=override prompt)
-> spawn_agent
-> _create_agent
-> OpenAIChatClient.as_agent
-> agent.create_session
```

Current frontend session start path before wrapper flattening:

```text
useChat.startSession
-> startChatSession
-> createCustomSession | createSessionWithProfileOverride | createSessionWithHistory | createSession
-> fetch POST /api/sessions
```

### Phase 7 Wrapper Flattening Results - 2026-05-07

Backend standard/custom session creation now follows a shorter path:

```text
main.create_session
-> create_chat_session
-> _create_profile_chat_session | _create_custom_chat_session
-> create_chat_runtime
-> OpenAIChatClient.as_agent
-> agent.create_session
```

Built-in override session creation follows the same profile branch, with `ProfileOverrideRequest` parsing inside `_create_profile_chat_session` before `create_chat_runtime(custom_name=profile_name, custom_instructions=override prompt)`.

Frontend session startup now follows one request-building path:

```text
useChat.startSession
-> startChatSession
-> buildSessionRequest
-> createSessionRequest
-> fetch POST /api/sessions
```

Wrapper reduction:

| Path | Before | After | Result |
|------|--------|-------|--------|
| Backend standard/custom | 8 steps, including `SessionCreationService(...).create`, `spawn_agent`, and `_create_agent` | 6 steps, with direct `create_chat_session` and `OpenAIChatClient.as_agent` construction | SC-007 passed: 2 fewer internal wrapper layers |
| Backend built-in override | 9 steps, including service, spawn, and `_create_agent` wrappers | 7 steps, with override parsing inside the profile branch and direct SDK agent construction | SC-007 passed: 2 fewer internal wrapper layers |
| Frontend session startup | `startChatSession` selected one of four `/api/sessions` wrapper exports | `startChatSession` builds one `SessionRequestPayload` and calls `createSessionRequest` | One network helper owns session POST behavior |

Line-count/accounting snapshot after Phase 7:

| Metric | Phase 6 Current | Phase 7 Current | Result |
|--------|-----------------|-----------------|--------|
| Runtime app code, same inclusion rules as Phase 6 | 10528 | 10524 | -4 net lines |
| `main.py` | 833 | 832 | -1 |
| `agent_factory.py` | 376 before wrapper flattening | 262 | -114 |
| `validators.py` | 167 | 155 | -12 |
| `streaming.py` | 275 | 258 | -17 |
| `frontend/src/api/client.ts` | 399 | 422 | +23; central helper added while preserving compatibility exports |
| `frontend/src/hooks/useSessionLifecycle.ts` | 211 before wrapper flattening | 250 | +39; one request builder replaces branch-specific API calls |

Hook reassessment: `useSkillForm`, `useAgentBuilderForm`, and `useAgentMcpEditor` each still own validation, reset, save-preparation, MCP mutation, or test-result workflow state, so they were left in place rather than inlined.

Validation:

- Behavior pinning: `uv run pytest tests/test_api.py tests/test_provider_routing.py` -> 20 passed, 1 warning
- Focused backend wrapper validation: `uv run pytest tests/test_api.py tests/test_session_orchestration.py tests/test_provider_routing.py tests/test_retry_logic.py tests/test_streaming.py tests/test_validators.py` -> 67 passed, 1 warning
- Frontend wrapper validation: `cd frontend && npm test && npm run build && npm run lint` -> passed; Vite reported the existing chunk-size warning
- Final backend gate: `uv run pytest` -> 149 passed, 1 warning
- Final frontend gate: `cd frontend && npm test && npm run build && npm run lint` -> passed; Vite reported the existing chunk-size warning
- Protected config check: `git diff -- config/agents.yaml` produced no output

## Backend Verification

Use `uv` only for Python commands:

```bash
uv run pytest
```

Recommended focused runs during implementation:

```bash
uv run pytest tests/test_api.py
uv run pytest tests/test_image_input.py tests/test_retry_logic.py
uv run pytest tests/test_skills_api.py tests/test_skills.py
```

## Frontend Verification

```bash
cd frontend
npm test
npm run build
npm run lint
```

If lint currently reports pre-existing issues, document them in the implementation report and ensure refactored files do not add new issues.

## Visual Verification For UI/CSS Changes

1. Build the frontend:

   ```bash
   cd frontend
   npm run build
   ```

2. Start the backend serving built assets:

   ```bash
   AUTH_DISABLED=true uv run uvicorn main:app --host 0.0.0.0 --port 8000
   ```

3. Capture affected screens with Playwright. At minimum, capture the disclaimer or warning overlay scrolled to top and bottom, profile or mission selection, empty chat with starter questions, chat with one user message and one assistant response, and every screen specifically affected by the current change. Reuse the existing admin capture helper where applicable:

   ```bash
   uv run python scripts/capture_admin_agent_screenshots.py --base-url http://localhost:8000
   ```

4. View each generated screenshot and verify no clipping, overflow, overlap, broken assets, missing content, unreadable text, or unintended design changes. For responsive changes, repeat captures at 1440x900, 768x1024, and 360x640.

## Contract Checks

After each major refactor step:

```bash
git diff -- config/agents.yaml
uv run pytest
cd frontend && npm test && npm run build
```

`config/agents.yaml` must remain empty in the diff for the entire feature.

## Implementation Log

### T001 Scope Guard - 2026-05-06

- Branch check: `007-application-refactor`
- Protected config check: `git diff -- config/agents.yaml` produced no output
- Reusable protected-file guard: run `git diff -- config/agents.yaml` after every phase and before final delivery; expected output is empty

### T002 Backend Baseline - 2026-05-06

- Command: `uv run pytest`
- Result: 128 passed, 1 warning in 3.39s
- Warning: existing `SkillsProvider` experimental warning from `agent_factory.py`

### T003 Frontend Baseline - 2026-05-06

- Added no-new-dependency frontend test script: `tsc -b --pretty false`
- Command: `cd frontend && npm test && npm run build && npm run lint`
- Result: passed
- Note: Vite reported an existing chunk-size warning for the production bundle

### T004 Line-Count Baseline - 2026-05-06

| File | Lines |
|------|-------|
| `main.py` | 1643 |
| `frontend/src/api/client.ts` | 477 |
| `frontend/src/hooks/useChat.ts` | 569 |
| `frontend/src/pages/AgentBuilder.tsx` | 735 |
| `frontend/src/components/SkillBuilder.tsx` | 369 |
| `frontend/src/styles/index.css` | 2707 |
| `frontend/src/index.css` | 107 |
| `frontend/src/App.css` | 184 |
| **Total** | **6791** |

### Phase 2 Fixture Validation - 2026-05-06

- Command: `uv run pytest tests/test_api.py tests/test_skills_api.py`
- Result: 31 passed, 1 warning in 0.96s
- Warning: existing `SkillsProvider` experimental warning from `main.py`

### US1 Helper Test Baseline - 2026-05-06

- Command: `uv run pytest tests/test_validators.py tests/test_streaming.py tests/test_skills_manager.py tests/test_session_orchestration.py`
- Result: 18 passed, 1 warning in 0.72s
- Warning: existing `SkillsProvider` experimental warning from `validators.py`

### US1 Helper Wiring Validation - 2026-05-06

- Command: `uv run pytest tests/test_api.py tests/test_image_input.py tests/test_retry_logic.py tests/test_skills_api.py tests/test_skills.py tests/test_validators.py tests/test_streaming.py tests/test_skills_manager.py tests/test_session_orchestration.py`
- Result: 126 passed, 1 warning in 3.21s
- Warning: existing `SkillsProvider` experimental warning from `skills_manager.py`

### US1 Session Extraction Validation - 2026-05-06

- Command: `uv run pytest tests/test_api.py tests/test_image_input.py tests/test_retry_logic.py tests/test_skills_api.py tests/test_skills.py tests/test_validators.py tests/test_streaming.py tests/test_skills_manager.py tests/test_session_orchestration.py`
- Result: 126 passed, 1 warning in 3.19s
- `main.py` line count: 833
- Extracted backend module total: validators.py 167, streaming.py 275, skills_manager.py 111, session_orchestration.py 341
- Protected config check: `git diff -- config/agents.yaml` produced no output
- Delete-session and lifespan cleanup behavior required no code changes after session creation extraction

### US2 API/Storage/Content Helper Validation - 2026-05-06

- Added compile-only API export matrix in `frontend/src/api/client.contract.ts` for all public exports from `frontend/src/api/client.ts`
- Preserved localStorage keys: `auth_token`, `webagents_user_profile`, `webagents_custom_agents`, `webagents_builtin_agent_customizations`, `webagents_conversation_index`, and `webagents_conversation_{id}`
- Storage compatibility notes: custom agents keep array persistence; built-in overrides continue filtering invalid entries; conversation index and per-conversation entries still fail safely on corrupt data and remove invalid stored entries where existing behavior did so
- Frontend workflow verification scope for the full US2 checkpoint: chat send, saved conversation resume/delete, agent builder save/delete, and skill builder create/edit/delete/generate should be manually exercised after the pending `useChat`, `AgentBuilder`, and `SkillBuilder` splits
- Command: `cd frontend && npm test && npm run build && npm run lint`
- Result: passed
- Note: Vite reported the existing production bundle chunk-size warning

### US2 useChat Split Validation - 2026-05-06

- Extracted session startup, cleanup, restored-message parsing, and framework content conversion into `frontend/src/hooks/useSessionLifecycle.ts`
- Extracted saved-conversation persistence into `frontend/src/hooks/useConversationPersistence.ts`
- Preserved `useChat` return shape: messages, streaming state, session details, loaded capabilities, errors, conversation id, save counter, and action callbacks
- Command: `cd frontend && npm test && npm run build && npm run lint`
- Result: passed
- Note: Vite reported the existing production bundle chunk-size warning

### US2 AgentBuilder Split Validation - 2026-05-06

- Extracted MCP editor state and connection testing into `frontend/src/hooks/useAgentMcpEditor.ts`
- Extracted agent form state, validation, reset state, and save preparation helpers into `frontend/src/hooks/useAgentBuilderForm.ts`
- Extracted tools/skills picker UI into `frontend/src/components/AgentCapabilityPicker.tsx`
- Extracted starter question editor UI into `frontend/src/components/StarterQuestionEditor.tsx`
- Command: `cd frontend && npm test && npm run build && npm run lint`
- Result: passed
- Note: Vite reported the existing production bundle chunk-size warning

### US2 SkillBuilder Split Validation - 2026-05-06

- Extracted reusable Skill Builder form state, validation, feedback state, delete confirmation state, AI generation state, and create payload preparation into `frontend/src/hooks/useSkillForm.ts`
- Preserved Skill Builder create/edit/delete/generate handlers in `frontend/src/components/SkillBuilder.tsx`
- Command: `cd frontend && npm test && npm run build && npm run lint`
- Result: passed
- Note: Vite reported the existing production bundle chunk-size warning

### US3 Behavioral Test Cleanup - 2026-05-06

- Replaced retry/session source-inspection assertions with behavior-level checks for session deletion, final usage logging, usage accumulation, and long input rejection
- Reviewed image input tests; existing coverage already exercises validators behaviorally, so no source-inspection replacement was needed there
- Command: `uv run pytest tests/test_image_input.py tests/test_retry_logic.py`
- Result: 71 passed

### US3 Visual Baseline Capture - 2026-05-06

- Expanded `scripts/capture_admin_agent_screenshots.py` to capture disclaimer top/bottom, profile selection, empty chat with starter questions, one-turn chat, admin agent builder, and skill builder states
- Added `--mock-api` for deterministic screenshot captures without live LLM or backend data dependencies
- Command: `uv run python scripts/capture_admin_agent_screenshots.py --base-url http://localhost:8000 --output-dir screenshots/007-application-refactor --mock-api`
- Result: passed; screenshots saved under `screenshots/007-application-refactor/`
- Reviewed generated screenshots: disclaimer top/bottom, profile selection, empty chat, one-turn chat, admin agent builder expanded/collapsed states, and skill builder desktop/tablet/mobile showed no obvious clipping, overlap, broken assets, or missing required content

### US3 CSS Cleanup Validation - 2026-05-06

- Removed unused Vite demo stylesheet content from `frontend/src/App.css` and trimmed `frontend/src/index.css` to root/body rendering concerns
- Consolidated repeated frontend button, input, textarea, saved action, message image, and tool image styles in `frontend/src/styles/index.css`; no component class-name changes were required
- Removed unused CSS selectors and stale section comments after source usage scanning
- CSS line count: baseline 2998 lines (`App.css` 184, `index.css` 107, `styles/index.css` 2707) to 2575 lines (`index.css` 18, `styles/index.css` 2557), net -423 lines
- Command: `cd frontend && npm test && npm run build && npm run lint`
- Result: passed
- Screenshot command: `uv run python scripts/capture_admin_agent_screenshots.py --base-url http://localhost:8000 --output-dir screenshots/007-application-refactor --mock-api`
- Screenshot result: passed; reviewed final disclaimer, profile selection, one-turn chat, admin builder, and skill builder mobile captures with no obvious clipping, overflow, overlap, broken assets, or missing content

### Phase 6 Final Backend Gate - 2026-05-06

- Command: `uv run pytest`
- Result: 146 passed, 1 warning in 6.64s
- Warning: existing `SkillsProvider` experimental warning from `validators.py`

### Phase 6 Final Frontend Gate - 2026-05-06

- Command: `cd frontend && npm test && npm run build && npm run lint`
- Result: passed
- Build output included `dist/assets/index-BE5OHoTD.css` at 39.59 kB and `dist/assets/index-vlPAe1QI.js` at 633.82 kB
- Note: Vite reported the existing production bundle chunk-size warning

### Phase 6 Protected File And Dependency Check - 2026-05-06

- Protected config check: `git diff -- config/agents.yaml` produced no output
- Dependency manifest check: only `frontend/package.json` changed, for the intentional no-new-dependency `test` script; no package dependency additions were made
- Ignore-file verification: `.gitignore`, `.terraformignore`, and `frontend/eslint.config.js` cover detected Python, Node/TypeScript, Terraform, and ESLint artifacts; no Docker, Prettier, Helm, or publishing npm ignore file was required by the detected project setup

### Phase 6 Line-Count And Success Criteria Check - 2026-05-06

| Metric | Baseline | Current | Result |
|--------|----------|---------|--------|
| Runtime app code, same inclusion rules as `main` comparison | 10534 | 10528 | -6 net lines; SC-001 not met as a strict all-runtime net metric because extracted helper modules intentionally offset large-file reductions |
| Targeted original refactor files | 6791 | 5052 | -1739 lines before counting extracted helper modules |
| `main.py` | 1643 | 833 | -810 lines; SC-002 passed |
| Frontend CSS (`App.css`, `index.css`, `styles/index.css`) | 2998 | 2575 | -423 lines; SC-003 passed |
| Frontend API client | 477 | 399 | -78 lines; SC-004 passed |

- Current extracted helper/module total: 1767 lines across `validators.py`, `streaming.py`, `skills_manager.py`, `session_orchestration.py`, `frontend/src/api/helpers.ts`, `frontend/src/utils/storage.ts`, `frontend/src/utils/content.ts`, `frontend/src/hooks/useSessionLifecycle.ts`, `frontend/src/hooks/useConversationPersistence.ts`, `frontend/src/hooks/useAgentMcpEditor.ts`, `frontend/src/hooks/useAgentBuilderForm.ts`, `frontend/src/hooks/useSkillForm.ts`, `frontend/src/components/AgentCapabilityPicker.tsx`, and `frontend/src/components/StarterQuestionEditor.tsx`
- Targeted original plus extracted helper/module total: 6819 lines before final dead-helper cleanup, compared with the 6791-line targeted baseline

### Phase 6 Contract Review - 2026-05-06

- API contract review: preserved route paths, response fields, auth behavior, SSE event names (`text`, `function_call`, `function_result`, `usage`, `error`, `done`), session response shape, history export behavior, and empty `config/agents.yaml` diff
- Frontend contract review: preserved public `frontend/src/api/client.ts` exports, `useChat()` return shape, localStorage keys/data shapes, admin builder and skill builder exports/workflows, and visual verification coverage for changed chat/admin/skill screens
- Final cleanup: removed an unused frontend API helper and added missing critical ignore patterns without changing runtime behavior