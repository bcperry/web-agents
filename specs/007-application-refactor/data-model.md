# Data Model: Application Refactor And Deduplication

This feature preserves existing runtime data shapes. The entities below describe the contracts and state that refactor tasks must protect.

## Session Creation Request

**Purpose**: Represents the incoming payload for `POST /api/sessions`.

**Fields**:

- `profile_id`: string; either a configured profile key/display name or `custom`.
- `custom_name`: string; required for custom agents, max 100 characters.
- `custom_prompt`: string; required for custom agents and built-in overrides, max `MAX_USER_INPUT_CHARS`.
- `custom_tools`: string array; validated against known backend tools.
- `custom_skills`: string array; validated against discovered skill names.
- `custom_search_context`: boolean; enables search context for custom/override flows.
- `custom_temperature`: optional number; valid range 0.0 through 2.0.
- `mcp_servers`: MCP server entries; custom and override flows support only HTTP entries from request body.
- `profile_override`: object; built-in profile customization fields.
- `history`: optional backend session state for resume.
- `user_profile`: optional `{ name, preferences, notes }` context for user profile tools.

**Validation Rules**:

- Unknown profile IDs are rejected.
- Built-in profile overrides cannot change the canonical agent name.
- Unknown tools and skills are rejected before runtime creation.
- Inline MCP server entries must be objects with name, HTTP transport, and URL.
- `config/agents.yaml` remains read-only; profile definitions are loaded, not modified.

## Session Creation Result

**Purpose**: Represents the `POST /api/sessions` success response and frontend session metadata.

**Fields**:

- `session_id`: generated UUID string.
- `profile_id`: logical profile key or `custom`.
- `profile_name`: display name shown to the user.
- `tools_loaded`: string array.
- `skills_loaded`: string array.
- `search_context`: boolean.
- `mcp_results`: array of per-server connection outcomes.
- `used_profile_override`: optional boolean for built-in override sessions.
- `override_updated_at`: optional ISO timestamp for built-in override sessions.

**Relationships**:

- Created from a Session Creation Request.
- Stored in backend `_sessions` and consumed by frontend `useChat`.
- Included in conversation persistence through history export.

## Stream Event

**Purpose**: Represents an SSE message emitted by `POST /api/sessions/{session_id}/messages`.

**Types**:

- `text`: assistant text delta.
- `function_call`: tool call with `call_id`, `name`, and accumulated `arguments`.
- `function_result`: tool result with optional `content_items` for images.
- `usage`: token usage counts.
- `error`: user-displayable error plus optional retry hint.
- `done`: stream completion marker.

**Validation Rules**:

- Event names and payload field names must remain stable.
- Tool-result image items must preserve supported MIME filtering.
- Usage counts must continue to aggregate into session usage.

## Stored Conversation

**Purpose**: Represents frontend localStorage data for saved/resumable conversations.

**Fields**:

- `id`: conversation ID, usually session ID.
- `profileId`, `profileName`: associated agent profile.
- `description`: first user message summary.
- `createdAt`, `lastActivityAt`: ISO timestamps.
- `sessionData`: backend `AgentSession.to_dict()` payload.
- `customAgentId`: optional ID for custom agent sessions.
- `usedBuiltInOverride`, `baseProfileId`, `overrideUpdatedAt`: optional built-in override metadata.

**Validation Rules**:

- Existing localStorage keys and stored shapes must not change.
- Corrupt records are discarded or ignored as today.
- Conversation index remains sorted newest-first and capped by `__MAX_SESSIONS__`.

## Agent Builder Form State

**Purpose**: Represents editable frontend state for custom agents and built-in override customizations.

**Fields**:

- `name`, `description`, `systemPrompt`, `icon`.
- `tools`, `skills`, `mcpServers`.
- `useSearchContext`, `temperature`.
- `starters` with label/message pairs.

**State Transitions**:

- Empty form -> create custom agent.
- Saved custom agent -> edit/delete.
- Built-in profile definition -> local override -> reset override.
- Override -> generated standard-agent candidate YAML.

**Validation Rules**:

- Existing UI validation behavior remains unchanged.
- Built-in profile name remains read-only.
- MCP test results map by server name and are cleared when relevant inputs are reset.

## Skill Definition

**Purpose**: Represents a file-backed skill exposed through admin CRUD endpoints.

**Fields**:

- `name`: lowercase alphanumeric plus hyphen, starts with alphanumeric, max 64 characters.
- `description`: non-empty, max 256 characters.
- `content`: non-empty Markdown, max 65,536 characters.

**Relationships**:

- Stored as `skills/{name}/SKILL.md`.
- Listed by backend skill endpoints and selected by the agent builder.

**Validation Rules**:

- Path traversal protections remain in place.
- Duplicate creates return conflict.
- Missing skill reads/updates/deletes return not found.

## Visual Style Primitive

**Purpose**: Represents shared CSS patterns extracted from repeated app styles.

**Fields/Patterns**:

- Button variants: primary, secondary/cancel, icon/action, disabled.
- Input variants: text input, textarea, invalid state.
- Panel/list primitives: admin list panel, saved entry, form panel.
- Message markdown primitives: headings, paragraphs, code, tables, blockquotes, links.

**Validation Rules**:

- Existing class names used by components should remain stable unless all usages and screenshots are updated.
- Visual verification is required before CSS cleanup is considered complete.