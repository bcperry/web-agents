# Research: Application Refactor And Deduplication

## Decision: Keep `config/agents.yaml` Read-Only

**Rationale**: The user explicitly excluded `agents.yaml`, and the constitution requires a single file for agent profiles. Refactor value can be achieved in code, CSS, tests, and planning artifacts without changing prompt/profile configuration.

**Alternatives considered**: YAML anchors or prompt fragment extraction could reduce configuration duplication, but those options modify `config/agents.yaml` and are out of scope.

## Decision: Preserve Route Contracts And Extract Backend Services Around Them

**Rationale**: `main.py` contains route definitions plus session creation, validation, skills CRUD, streaming conversion, token usage, and error classification. The safest refactor is to keep FastAPI routes and response shapes stable while moving repeated behavior into focused modules: `session_orchestration.py`, `validators.py`, `skills_manager.py`, and `streaming.py`.

**Alternatives considered**: Moving the backend into a package or creating a larger service framework would create unnecessary import/deployment churn for this feature. Keeping everything in `main.py` would preserve behavior but fail the simplification goal.

## Decision: Consolidate Tool, Skill, Input, Image, And Error Validation

**Rationale**: Tool and skill discovery/validation is repeated across discovery endpoints and session creation branches. Image validation and retry/context error classification are also currently embedded in `main.py`. Extracting these helpers makes behavior testable and reduces duplicated loops and constants.

**Alternatives considered**: A generic validation framework was rejected as overbuilt. Small typed helper functions/classes are enough.

## Decision: Extract Session Creation Last Among Backend Changes

**Rationale**: Session creation is the highest-risk area because it handles custom agents, built-in overrides, MCP connection results, history restoration, user profile injection, and runtime creation. Validators, skills manager, and streaming helpers should be extracted first so the final session extraction is smaller and easier to verify.

**Alternatives considered**: Extracting session orchestration first would produce a large behavior-preserving diff and make failures harder to localize.

## Decision: Preserve Frontend API Exports And Add Internal Request Helpers

**Rationale**: `frontend/src/api/client.ts` repeats authenticated fetch, unauthorized handling, HTTP error handling, JSON body setup, and toast emission. A new internal `frontend/src/api/helpers.ts` can reduce boilerplate while preserving existing exported functions and return types.

**Alternatives considered**: Generating a full API client from OpenAPI is constitutionally preferred long term, but this refactor should avoid new tooling and keep scope focused.

## Decision: Centralize localStorage Helpers Without Changing Keys Or Shapes

**Rationale**: Custom agents, built-in overrides, user profile, conversations, auth token, and theme state all rely on localStorage with repeated parse/stringify/corruption handling. A `frontend/src/utils/storage.ts` helper can standardize failure handling while preserving storage keys and data shapes.

**Alternatives considered**: Migrating to IndexedDB or a state management library was rejected because it adds dependencies and changes persistence behavior.

## Decision: Extract Content/Image Helpers And Reusable Image UI

**Rationale**: Allowed image MIME handling, tool-result image filtering, and content-item conversion appear in multiple frontend paths. A `frontend/src/utils/content.ts` helper and optional shared image component reduce duplication and protect image behavior during stream and history restore flows.

**Alternatives considered**: Keeping logic inside components is simple but repeats validation details and increases drift risk.

## Decision: Split Stateful Frontend Modules By Existing Responsibilities

**Rationale**: `AgentBuilder.tsx`, `SkillBuilder.tsx`, `ChatPage.tsx`, and `useChat.ts` mix state orchestration and rendering. Extracting hooks/components for session lifecycle, conversation persistence, MCP editing, starter editing, capability picking, and form state reduces large files without changing page exports.

**Alternatives considered**: Replacing the current state model with a new global store was rejected as unnecessary and dependency-heavy.

## Decision: Do CSS Cleanup Last And Verify Visually

**Rationale**: `App.css` is unused, `index.css` contains demo/global remnants, and `styles/index.css` repeats button/input/panel/message patterns. CSS deletion is high line-savings but visually risky, so it should follow component extraction and must use the constitution's Playwright screenshot protocol.

**Alternatives considered**: Rewriting CSS into modules or a utility framework was rejected because it would be a broad styling migration rather than a focused refactor.

## Decision: Replace Brittle Source-Inspection Tests Where Feasible

**Rationale**: Several tests use `inspect.getsource` or signature checks, which can block behavior-preserving refactors. Shared fixtures in `tests/conftest.py` and behavioral endpoint/unit tests should replace source-text assertions when possible.

**Alternatives considered**: Keeping source-inspection tests avoids writing new assertions, but it creates false failures during exactly this refactor.

## Decision: No New Dependencies

**Rationale**: Existing tooling is sufficient: pytest, FastAPI TestClient, Vite/TypeScript build, ESLint, and Playwright for screenshots. New dependencies would violate the simplicity principle unless a later task proves a concrete need.

**Alternatives considered**: Adding frontend test libraries or a CSS tooling package could help, but the current request is simplification and deduplication, not test stack expansion.

## Decision: Flatten Wrapper Layers Rather Than Extract More Services

**Rationale**: The first implementation pass separated responsibilities from oversized files, but session creation now reads through too many implementation-shaped names: `SessionCreationService`, `_create_custom_session`, `_create_profile_session`, `create_chat_runtime`, `spawn_agent`, and `_create_agent`. The next cleanup should shorten call chains, rename helpers toward domain intent, and delete compatibility layers that are no longer needed.

**Alternatives considered**: Creating additional builder/service classes was rejected because it would make the session path more abstract. Leaving the wrappers in place was rejected because the primary maintainer experience problem is now navigation and comprehension, not lack of extraction.