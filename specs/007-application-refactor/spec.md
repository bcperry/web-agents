# Feature Specification: Application Refactor And Deduplication

**Feature Branch**: `007-application-refactor`  
**Created**: 2026-05-06  
**Status**: Draft  
**Input**: User description: "lets plan for this application refactor as discussed. the only thing i dont want to do is mess with the agents.yaml."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preserve Chat Behavior While Simplifying Backend Sessions (Priority: P1)

As a user of the chat application, I need existing standard agents, customized built-in agents, and custom agents to create sessions, stream responses, call tools, restore history, report usage, and clean up resources exactly as they do today while the backend implementation is split into smaller, easier-to-maintain units.

**Why this priority**: Backend session orchestration is the largest behavioral risk and the largest concentration of duplicated code. Preserving chat behavior is the minimum viable value for the refactor.

**Independent Test**: Can be tested by running backend API tests for profile listing, session creation, message streaming, history export, retry/context-limit handling, image validation, and session deletion without changing user-visible responses.

**Acceptance Scenarios**:

1. **Given** an existing standard profile, **When** a user creates a session and sends a message, **Then** the API returns the same session fields, streams the same event types, logs token usage, and cleans up the session on deletion.
2. **Given** a customized built-in profile override, **When** a user creates a session, **Then** the canonical profile name is preserved, override metadata is returned in the session response and history response, and selected tools, skills, search context, and MCP servers are honored.
3. **Given** a custom agent with selected tools, skills, optional MCP servers, optional search context, and optional temperature, **When** a user creates a session, **Then** validation and runtime creation behave as before and invalid tools, skills, temperatures, or MCP entries are rejected with equivalent errors.

---

### User Story 2 - Reduce Frontend Duplication Without Changing Workflows (Priority: P2)

As a user of the frontend, I need profile selection, chat, saved conversations, admin agent customization, skill editing, image display, toast notifications, and authentication flows to keep working while repeated API, local storage, image rendering, and form-management code is consolidated.

**Why this priority**: The frontend has repeated request handling, local storage handling, image filtering, and large stateful components that slow down future feature work.

**Independent Test**: Can be tested by building the frontend, running lint/type checks, and manually or visually verifying profile selection, chat send, saved conversation resume/delete, admin agent builder, and skill builder flows.

**Acceptance Scenarios**:

1. **Given** a user opens the chat page, **When** profiles load, a session starts, a message streams, and a conversation is saved, **Then** the UI behavior and stored conversation data match current behavior.
2. **Given** a user edits or creates a custom agent, **When** they change tools, skills, MCP servers, starter questions, search context, and temperature, **Then** validation, save, delete, and generated standard-agent candidate behavior remain unchanged.
3. **Given** a user creates, edits, generates, or deletes a skill, **When** the operation succeeds or fails, **Then** the displayed feedback and API behavior remain unchanged.

---

### User Story 3 - Clean Styling And Tests Safely (Priority: P3)

As a maintainer, I need dead CSS, repeated CSS variants, repeated test setup, and brittle source-inspection tests reduced while retaining the current visual design and behavioral test coverage.

**Why this priority**: CSS and tests contain easy cleanup opportunities, but UI appearance and regression coverage must not degrade.

**Independent Test**: Can be tested by building the frontend, performing automated screenshot verification for affected UI screens, and running backend tests.

**Acceptance Scenarios**:

1. **Given** unused stylesheet content exists, **When** it is removed or consolidated, **Then** affected screens render without clipping, overlap, broken assets, or unintended visual changes.
2. **Given** duplicated test fixtures and source-inspection tests exist, **When** they are refactored into shared fixtures or behavioral assertions, **Then** test coverage remains equivalent and tests no longer depend on specific function source text where behavior can be asserted.

---

### User Story 4 - Flatten Wrapper Layers Around Session And Agent Creation (Priority: P1 Follow-Up)

As a maintainer walking through session startup, I need the code path from frontend session request through backend runtime creation to read as a direct flow instead of a stack of pass-through wrappers, while preserving all user-visible behavior and compatibility exports.

**Why this priority**: The first refactor reduced large files but introduced or preserved layers such as `SessionCreationService`, `create_chat_runtime`, `spawn_agent`, `_create_agent`, and multiple frontend session wrappers. These make the most important flow harder to understand than it needs to be.

**Independent Test**: Can be tested by running backend session/API tests, frontend test/build/lint, API export compile checks, and `git diff -- config/agents.yaml` after flattening the wrapper layers.

**Acceptance Scenarios**:

1. **Given** a maintainer traces custom, standard, or customized built-in session creation, **When** they follow the call chain, **Then** they can see request validation, runtime creation, session persistence, and response shaping without passing through redundant create/spawn/service wrappers.
2. **Given** frontend code creates a standard, history, custom, or built-in override session, **When** the API client sends the request, **Then** mode-specific payload construction is centralized while existing exported API functions remain compatible.
3. **Given** canonical helper functions exist for streaming, validation, and agent building, **When** callers import helpers, **Then** obsolete underscore aliases and one-method wrapper classes are removed unless a test or public compatibility contract requires them.

### Edge Cases

- Refactor must preserve unauthorized responses and auth-disabled local development behavior.
- Refactor must preserve multipart image upload validation for MIME type, count, size, and magic bytes.
- Refactor must preserve MCP connection failure reporting without leaking credentials or bearer tokens.
- Refactor must preserve best-effort conversation persistence when local storage is corrupt or unavailable.
- Refactor must preserve frontend rendering of tool-result images from streamed responses and restored session history.
- Refactor must not edit `config/agents.yaml`, including YAML anchors, prompt content, profile entries, or MCP definitions.
- Refactor must not add new runtime dependencies unless a later task documents an immediate need and the dependency passes constitution review.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The backend MUST preserve existing API routes, status codes, response field names, and SSE event names for health, auth config, tools, profiles, profile definitions, MCP tests, skills, sessions, messages, history, and deletion.
- **FR-002**: The backend MUST extract repeated session creation concerns into focused units for profile resolution, custom-agent validation, profile-override validation, tool validation, skill validation, MCP request validation, runtime creation, history restoration, session persistence, and session response formatting.
- **FR-003**: The backend MUST preserve custom agent, standard profile, and built-in override behavior, including loaded tools, loaded skills, search context state, MCP results, user profile context injection, and override metadata.
- **FR-004**: The backend MUST extract or consolidate usage aggregation, image validation, retry/context error classification, skills CRUD path handling, and stream event transformation where doing so reduces duplication without changing behavior.
- **FR-005**: The frontend API client MUST consolidate repeated authenticated fetch, JSON body, unauthorized handling, HTTP error handling, and toast emission patterns while preserving existing exported function signatures where practical.
- **FR-006**: The frontend MUST consolidate repeated local storage parse/stringify/corruption handling for custom agents, built-in overrides, user profile, and conversations without changing storage keys or stored data shape.
- **FR-007**: The frontend MUST extract reusable helpers or components for tool-result image filtering/rendering and shared content-item conversion without changing visible image behavior.
- **FR-008**: The frontend MUST split large stateful screens and hooks into smaller units where the split is directly tied to current responsibilities: chat session lifecycle, conversation persistence, agent builder form state, MCP server editor, starter question editor, capability picker, and skill builder form behavior.
- **FR-009**: CSS cleanup MUST remove unused styles and consolidate repeated button, input, panel, message, admin, and builder variants while preserving the current visual design.
- **FR-010**: Test cleanup MUST move repeated test environment/client fixtures into shared fixtures and replace brittle source-inspection assertions with behavioral assertions where feasible.
- **FR-011**: Refactor tasks MUST keep `config/agents.yaml` read-only and out of scope. No feature artifact may require editing it.
- **FR-012**: Refactor tasks MUST avoid new backend or frontend dependencies unless explicitly justified as necessary for this refactor.
- **FR-013**: The backend MUST flatten the agent creation call chain so runtime construction no longer requires both `spawn_agent` and `_create_agent` as pass-through wrappers.
- **FR-014**: The backend MUST replace per-request service construction for session creation with a clearer function or stable service boundary that reduces constructor dependency plumbing.
- **FR-015**: The frontend MUST centralize `/api/sessions` POST body construction while keeping compatibility exports for current callers.
- **FR-016**: The refactor MUST remove compatibility aliases, one-method wrapper classes, and setter-bag hooks where they do not encode a meaningful domain boundary.

### Key Entities *(include if feature involves data)*

- **Session Creation Request**: Incoming session payload for standard profiles, custom agents, built-in overrides, optional history, user profile context, selected tools, selected skills, MCP servers, search context, and temperature.
- **Session Creation Result**: Created runtime/session metadata returned to the frontend, including session ID, profile identity, loaded tools and skills, search context state, MCP connection results, and override metadata.
- **Stream Event**: Server-sent event emitted during message processing, including text, function call, function result, usage, error, and done events.
- **Stored Conversation**: Frontend local-storage record containing conversation index metadata and backend session state for resume/delete flows.
- **Agent Builder Form State**: Frontend editable state for custom agents and built-in override customizations, including tools, skills, MCP servers, starter questions, search context, icon, description, prompt, and temperature.
- **Skill Definition**: Backend file-backed skill represented by name, description, and Markdown content and edited through the admin UI.
- **Visual Style Primitive**: Reusable CSS pattern for buttons, inputs, panels, message markdown, admin panels, and builder controls.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Runtime app code is reduced by at least 1,000 net lines across backend Python and frontend source/CSS, excluding generated artifacts and historical specs, while all existing user-visible behavior remains intact.
- **SC-002**: `main.py` is reduced below 1,200 lines by moving session, skill, validation, and streaming responsibilities into focused modules or helpers.
- **SC-003**: Frontend CSS is reduced by at least 400 net lines while automated visual verification shows no layout regressions on affected screens.
- **SC-004**: The frontend API client reduces repeated fetch/error-handling boilerplate by at least 50 net lines while preserving exported API behavior.
- **SC-005**: Backend tests pass with `uv run pytest`; frontend verification passes with `npm test`, `npm run build`, and `npm run lint`.
- **SC-006**: `git diff -- config/agents.yaml` remains empty throughout the feature.
- **SC-007**: The standard/custom/override session creation path crosses at least two fewer internal wrapper functions or classes than the current implementation while all backend and frontend verification gates still pass.
