# Frontend Contract: Behavior-Preserving Refactor

This refactor may move frontend implementation details but must preserve exported APIs, storage data, and user workflows.

## API Client Exports

The following exports from `frontend/src/api/client.ts` must remain available with compatible signatures and return shapes:

- `AuthError`
- `fetchTools`
- `fetchSkills`
- `fetchSkill`
- `createSkill`
- `updateSkill`
- `deleteSkill`
- `generateSkillContent`
- `testMcpConnections`
- `createCustomSession`
- `fetchBuiltInProfileDefinition`
- `createSessionWithProfileOverride`
- `fetchProfiles`
- `createSession`
- `deleteSession`
- `fetchHistory`
- `createSessionWithHistory`
- `sendMessage`

Internal helpers may move to `frontend/src/api/helpers.ts`, but callers should not need to change except imports inside the API layer.

## Hook And Component Contracts

- `useChat()` must return the same `ChatState` fields and functions.
- `useConversationStore()` must preserve `loadIndex`, `saveConversation`, `loadConversation`, `deleteConversation`, and `deleteConversationsByCustomAgent` semantics.
- `useCustomAgents()` and `useBuiltInAgentCustomizations()` must preserve `save`/`remove` behavior and stored data shapes.
- `ChatPage`, `AgentBuilder`, `SkillBuilder`, and `AdminPage` exports must remain available.

## Storage Contract

Existing localStorage keys and data shapes must be preserved:

- `auth_token`
- `webagents_user_profile`
- `webagents_custom_agents`
- `webagents_builtin_agent_customizations`
- `webagents_conversation_index`
- `webagents_conversation_{id}`
- theme storage key currently owned by `useTheme`

Corrupt or invalid stored values must continue to fail safely without blocking the app.

## Visual Contract

- The current visual design remains the target.
- CSS class names used by rendered components should remain stable unless all usages are migrated in the same change.
- UI changes require `npm run build`, server startup, and Playwright screenshots for affected screens.

## Verification

- `npm test` must pass.
- `npm run build` must pass.
- `npm run lint` should pass for refactored frontend code.
- Visual verification must include chat/profile selection plus admin builder and skill builder screens when those areas change.