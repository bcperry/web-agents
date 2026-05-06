# Research: Baked Agent Customization

## Decision: Store built-in customizations as localStorage overrides keyed by built-in profile id

**Rationale**: The existing app already stores custom agents in localStorage and the user explicitly asked for local storage overrides. Keeping built-in customizations client-local avoids adding a persistence service, preserves per-user experimentation, and satisfies the requirement that unmodified users continue seeing standard YAML behavior.

**Alternatives considered**:

- Server-side persistence: rejected for MVP because it requires identity-scoped storage, migration, and authorization rules beyond the current feature scope.
- Cloning built-ins into custom agents: rejected because it creates duplicate profile cards and weakens the mental model of standard agents.
- Mutating `config/agents.yaml` from the UI: rejected by security/audit constraints and because browser-origin writes to canonical server config are unsafe.

## Decision: Reuse the custom-agent behavior field shape, but keep built-in names read-only

**Rationale**: Existing custom agents already model the desired editable behavior surface: description, system prompt, tools, skills, MCP servers, search context, icon, starters, and temperature. Reusing those fields reduces code paths and makes the builder experience predictable. The built-in agent name must remain inherited from the canonical profile because changing it turns the override into a disguised custom agent rather than a tuned standard agent.

**Alternatives considered**:

- Allowing local name changes: rejected because a renamed baked agent is effectively a custom agent and weakens profile identity, history, eval trace, and support semantics.
- Partial patch objects: rejected because merging partial field overrides with changing YAML defaults creates subtle drift and makes promotion/export ambiguous.
- Separate built-in override schema: rejected because it duplicates validation and UI handling without delivering user-visible value.

## Decision: Add a backend profile definition endpoint for safe built-in defaults

**Rationale**: The current `/api/profiles` endpoint intentionally returns display summaries only. The editor needs full profile defaults, including system prompt, tool names, skill names, MCP server metadata, search context, starters, icon, and temperature, to pre-populate the same builder used for custom agents. Exposing a safe definition endpoint through FastAPI preserves the API-first architecture and avoids hardcoding YAML parsing in the browser.

**Alternatives considered**:

- Include full definitions in `/api/profiles`: rejected because profile selection only needs summaries and should not eagerly ship all prompts/MCP config.
- Reconstruct editable defaults from summaries: rejected because summaries omit required fields.
- Fetch raw YAML as a static file: rejected because it bypasses backend validation/filtering and may expose fields the frontend should not receive.

## Decision: Start customized built-in sessions with an override while preserving the built-in profile identity

**Rationale**: Using `profile_id: custom` would work technically but would lose traceability and conversation identity. Extending session creation to accept an override for a known built-in profile lets the backend log `profile_id` as the original agent while using the overridden runtime prompt/capabilities.

**Alternatives considered**:

- Use existing `createCustomSession`: rejected for the final design because it degrades history/eval trace identity and makes customized built-ins look like unrelated custom agents.
- Create a new `/api/sessions/customized-built-in` endpoint: rejected because the current `POST /api/sessions` already handles profile-specific session creation and can accept a scoped optional override.

## Decision: Make customized states visible in profile selector, Admin, and active chat/capabilities

**Rationale**: Overrides change agent behavior and trust posture. Visible indicators reduce accidental use of personalized settings and make support/debugging easier. The UI should mark customized built-ins without duplicating them as custom cards.

**Alternatives considered**:

- Only mark in Admin: rejected because the user needs notice before starting a chat.
- Only mark in the active chat header: rejected because it is too late; the agent is already selected.

## Decision: `Make standard` exports/copies a canonical YAML candidate, not direct browser mutation

**Rationale**: The requirement asks for a quick way to make the override the standard agent if needed. The safe implementation is to generate a complete profile payload/YAML snippet for review and commit. Direct edits to `config/agents.yaml` from the browser would violate auditability and deployment controls.

**Alternatives considered**:

- Direct backend write to `config/agents.yaml`: rejected because it would mutate source/config at runtime and bypass tests/evals/PR review.
- Download JSON only: acceptable but less useful than a YAML-shaped candidate matching `agents.yaml`.
- Create a GitHub PR automatically: deferred; useful later but requires GitHub auth/integration not present in the app.

## Decision: Treat unavailable capabilities as warnings and filter where safe

**Rationale**: Existing custom-agent editing already filters unavailable tools at edit time and shows MCP test results. Built-in overrides should follow the same behavior: do not break profile selection, but surface missing tools/skills/search/MCP issues in Admin/session feedback.

**Alternatives considered**:

- Block loading customized built-ins with any unavailable capability: rejected because it can strand users after environment changes.
- Silently ignore missing capabilities: rejected because users need to understand behavior differences.
