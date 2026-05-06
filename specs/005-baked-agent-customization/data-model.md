# Data Model: Baked Agent Customization

## BuiltInAgentProfile

Represents a standard/pre-baked agent loaded from the backend profile catalog.

### Fields

- `id: string` - Stable profile key from `config/agents.yaml`.
- `name: string` - Display name.
- `description: string` - Display description.
- `icon: string` - Icon URL/path.
- `starters: StarterQuestion[]` - Suggested starter prompts.
- `skills?: string[]` - Skill names associated with the default profile.
- `mcp_server_count?: number` - Summary count for profile selection.
- `isCustom?: false` - Built-in profiles are not user-created custom agents.
- `isCustomized?: boolean` - Frontend-only marker after applying local override state.

### Relationships

- May have zero or one `AgentCustomizationOverride` keyed by the same `id`.
- May produce sessions using default backend/YAML config or an override.

## BuiltInAgentDefinition

Full safe editable built-in profile definition returned by backend for Admin customization.

### Fields

- `id: string` - Built-in profile id.
- `name: string` - Canonical display name from the built-in profile; returned for display but not editable in local overrides.
- `description: string`
- `systemPrompt: string` - Editable system prompt from YAML.
- `tools: string[]` - Tool names declared for the profile.
- `skills: string[]` - Skill names declared for the profile.
- `mcpServers: McpServerEntry[]` - MCP server config safe for frontend display/editing.
- `useSearchContext: boolean`
- `icon: string`
- `starters: StarterQuestion[]`
- `temperature?: number`
- `source: 'builtin'`
- `updatedAt?: string | null` - Optional source metadata if available.

### Validation Rules

- Must only be returned for known built-in profile ids.
- Must not include secrets, tokens, connection strings, or environment-expanded credential values.
- MCP server entries may include URL, name, transport, `authenticated`, and `authScope`; they must not include raw auth tokens.

## AgentCustomizationOverride

Local override record for a built-in profile. Uses the same editable behavior/capability fields as custom agents, but inherits the built-in profile name.

### Fields

- `id: string` - Built-in profile id, not a generated `custom_*` id.
- `name?: string` - Optional cached canonical name for display only; local overrides must not edit or persist a replacement display name.
- `description: string`
- `systemPrompt: string`
- `tools: string[]`
- `skills: string[]`
- `mcpServers: McpServerEntry[]`
- `useSearchContext: boolean`
- `icon: string`
- `starters: StarterQuestion[]`
- `temperature?: number`
- `source: 'builtin-override'`
- `createdAt: string`
- `updatedAt: string`
- `baseProfileId: string` - Same value as `id`; explicit for readability and future migrations.
- `baseProfileName?: string` - Name of the source profile when override was created.

### Validation Rules

- `id` and `baseProfileId` must match a currently known built-in profile id to edit/apply.
- `systemPrompt` is required.
- Local override save flows must not accept a changed agent name; UI should render the canonical name as read-only context.
- `temperature`, if present, must be between 0 and 2 inclusive.
- `tools` and `skills` should be validated against current availability during edit; unavailable values should be surfaced and omitted from runtime if unsafe.
- Must not store credentials, tokens, connection strings, or raw user bearer tokens.

### State Transitions and Actions

- `none -> customized`: User saves a built-in customization.
- `customized -> customized`: User edits and saves the override.
- `customized -> default`: User resets/removes local override.

### Non-State-Changing Actions

- `make standard`: User receives/copies a generated canonical profile payload. The local override remains `customized` until the user explicitly resets/removes it or a reviewed source change updates the shared default profile.

## StandardAgentCandidate

Exportable/copyable profile payload generated from an override to support promotion into `config/agents.yaml`.

### Fields

- `profileId: string` - Target built-in profile id.
- `yaml: string` - YAML snippet matching `agents.yaml` profile entry structure.
- `profile: Record<string, unknown>` - Structured equivalent for review/testing.
- `generatedAt: string`
- `sourceOverrideUpdatedAt: string`

### Validation Rules

- Must include all standard profile fields needed for canonical replacement: canonical name inherited from the built-in profile, description, icon, tools, skills, mcp_servers, search_context, temperature if set, starters, and system_prompt.
- Must not include `createdAt`, `updatedAt`, local-only source flags, tokens, or browser-only metadata.
- Must communicate that committing the candidate to shared standard config requires review, tests, and eval pipeline for prompt/parameter changes.

## ConversationIndexEntry Extension

Existing local conversation summary extended for override visibility.

### Additional Fields

- `customAgentId?: string` - Existing custom-agent marker.
- `usedBuiltInOverride?: boolean` - True when conversation started with a built-in override.
- `baseProfileId?: string` - Built-in profile id used for override sessions.
- `overrideUpdatedAt?: string` - Override timestamp captured at session start.

### Validation Rules

- Existing entries without these fields remain valid.
- Deleting/resetting an override must not delete conversation history automatically; historical conversations should retain their marker.

## Local Storage Keys

- `webagents_custom_agents` - Existing user-created custom agents.
- `webagents_builtin_agent_customizations` - New built-in profile overrides, stored as an array of `AgentCustomizationOverride` records.
- Existing conversation/user/theme keys remain unchanged.
