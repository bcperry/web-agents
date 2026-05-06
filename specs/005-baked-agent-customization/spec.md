# Feature Specification: Baked Agent Customization

**Feature Branch**: `005-baked-agent-customization`  
**Created**: 2026-05-06  
**Status**: Draft  
**Input**: User description: "lets do that. and make sure any custom agent overrides are easily noticed on the UI side with a quick way to make it the standard agent if needed"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Customize a Built-In Agent Locally (Priority: P1)

As an app user, I can customize an existing built-in/pre-baked agent using the same behavior and capability fields available for custom agents, while keeping the official agent name fixed, so I can tune the official agent for my workflow without creating a duplicate custom agent.

**Why this priority**: This is the core value of the feature. Users need to adapt standard agents while preserving the familiar profile slot and avoiding confusion between cloned and official agents.

**Independent Test**: Open Admin, choose a built-in agent, edit its prompt/tools/skills/MCP/search/starters/temperature, save, return to chat, and verify that selecting that same built-in profile starts with the customized behavior.

**Acceptance Scenarios**:

1. **Given** a built-in agent with no local customization, **When** the user opens it in Admin, edits supported fields, and saves, **Then** the customization is stored locally under the built-in profile identity.
2. **Given** a built-in agent has a saved local customization, **When** the user selects that built-in agent from the profile selector, **Then** the app uses the customized prompt/capability configuration instead of the default server/YAML profile for that user.
3. **Given** another browser/device/user has no saved customization for the same built-in agent, **When** that user selects the agent, **Then** the default server/YAML profile is used.

---

### User Story 2 - Notice Customized Built-In Agents (Priority: P2)

As a user, I can quickly tell which built-in agents have local overrides, so I do not accidentally confuse official defaults with personalized behavior.

**Why this priority**: Local overrides affect trust and troubleshooting. Users need visible indicators before starting a chat and while managing agents.

**Independent Test**: Save a local override for one built-in agent and confirm the profile selector and Admin agent list clearly mark it as customized while unmodified built-ins remain visually standard.

**Acceptance Scenarios**:

1. **Given** a built-in agent has a saved local customization, **When** the profile selector renders, **Then** that profile displays a clear `CUSTOMIZED` indicator.
2. **Given** the user opens Admin agent management, **When** built-in agents are listed, **Then** customized built-ins are visually distinct from unmodified built-ins and user-created custom agents.
3. **Given** a customized built-in agent is running in chat, **When** the session capabilities are shown, **Then** the UI indicates that local override settings are active.

---

### User Story 3 - Reset or Promote a Customization (Priority: P3)

As an admin or power user, I can reset a local built-in customization back to the standard agent or quickly prepare/promote it as the new standard agent definition, so successful local changes can become shared defaults.

**Why this priority**: Users need an escape hatch for local experiments and a fast path to operationalize a proven customization.

**Independent Test**: For a customized built-in agent, use Admin to reset it and verify defaults return; use the promote action and verify the UI provides the exact standard-agent update payload or action path.

**Acceptance Scenarios**:

1. **Given** a built-in agent has a local customization, **When** the user chooses reset, **Then** the local override is removed and the built-in profile returns to server/YAML defaults.
2. **Given** a built-in agent has a local customization, **When** the user chooses the promote/make standard action, **Then** the app exposes the customization as a standard-agent candidate with all fields needed to update the canonical profile.
3. **Given** the user has promoted or exported a customization candidate, **When** they review it, **Then** the standard-agent payload includes prompt, tools, skills, MCP servers, search context, starters, icon, description, and temperature.

### Edge Cases

- Built-in profile is removed from the server/YAML catalog while a local override still exists.
- Server/YAML built-in profile changes after a local override was saved.
- Saved override references a tool, skill, or search context capability that is no longer available.
- Saved override references an MCP server that fails connection testing.
- User attempts to save a built-in override with invalid temperature or missing system prompt.
- Local storage is unavailable, full, or contains invalid JSON.
- User deletes a built-in override while conversations created with the override remain in history.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow users to create, edit, and delete local customizations for built-in/pre-baked agents.
- **FR-002**: Built-in agent customizations MUST use the same editable behavior/capability fields as existing custom agents: description, system prompt, tools, skills, MCP servers, AI Search context flag, icon, starter questions, and temperature.
- **FR-002a**: Built-in agent customizations MUST NOT allow users to edit the agent name; the display name MUST remain inherited from the standard server/YAML profile.
- **FR-003**: System MUST store built-in agent customizations locally per browser/user context and key them by the original built-in profile id.
- **FR-004**: When a built-in profile has a local customization, System MUST use the customization when starting a chat session for that profile.
- **FR-005**: When no local customization exists, System MUST use the standard server/YAML built-in agent definition unchanged.
- **FR-006**: Customized built-in agents MUST remain in their original profile selector position and identity rather than appearing as duplicate custom agents.
- **FR-007**: UI MUST make customized built-in agents easy to notice in the profile selector, Admin built-in list, and active chat/capabilities area.
- **FR-008**: Users MUST be able to reset a customized built-in agent to the standard server/YAML definition by removing its local override.
- **FR-009**: Users MUST have a quick way to make a customized built-in agent the standard agent candidate, exposing/copying/exporting the complete canonical profile payload needed to update the shared `agents.yaml` profile.
- **FR-010**: System MUST validate customized built-in agent settings using the same rules as custom agents before saving.
- **FR-011**: System MUST gracefully ignore or surface unavailable tools, skills, search context, and MCP failures without breaking profile selection.
- **FR-012**: Conversations created from customized built-in agents MUST preserve enough metadata to show that the conversation used an override at the time it was started.
- **FR-013**: System MUST NOT mutate `config/agents.yaml` directly from the browser.
- **FR-014**: System MUST NOT store credentials, tokens, or secrets in built-in agent customization records.

### Key Entities *(include if feature involves data)*

- **BuiltInAgentProfile**: A standard profile loaded from the backend/YAML catalog. Key attributes: id, name, description, icon, starters, skills summary, MCP server count, default capability metadata.
- **AgentCustomizationOverride**: A local user override for a built-in profile. Key attributes mirror custom agents and include builtInProfileId, updatedAt, and source/default version metadata where available.
- **StandardAgentCandidate**: A generated/exportable profile payload representing a local customization ready to become a shared standard profile entry.
- **ConversationIndexEntry**: Existing stored conversation metadata extended to note whether an override was active when the conversation was created.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can customize and save a built-in agent from Admin in under 2 minutes using the existing custom-agent form pattern.
- **SC-002**: 100% of customized built-in agents are marked with a visible `CUSTOMIZED` indicator in profile selection and Admin.
- **SC-003**: Starting a customized built-in agent applies the override fields without creating a duplicate profile card.
- **SC-004**: Users can reset a customized built-in agent to defaults in one explicit action.
- **SC-005**: Users can generate or access a complete standard-agent candidate payload in one explicit action.
- **SC-006**: Existing custom agents and unmodified built-in agents continue to work without behavior changes.
