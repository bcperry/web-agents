# Feature Specification: Agents as Tools (Multi-Agent Delegation)

**Feature Branch**: `008-agents-as-tools`  
**Created**: 2026-05-11  
**Status**: Draft  
**Input**: User description: "Enable agents to call other agents as tools (multi-agent delegation), modeled after the Microsoft agent-framework sample `client_with_agent_as_tool.py`. Backend: agent definitions can declare other agents (built-in or custom) as callable tools. Frontend: new 'Agents as Tools' section in the Custom Agent Builder. UI polish: clarify subheaders. Validation: prevent self-reference and direct cycles. Persistence + API: extend schema."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compose a Parent Agent that Delegates to a Sub-Agent (Priority: P1)

An admin building a custom "Research Coordinator" agent wants it to delegate focused subtasks to an existing "Azure Government Specialist" agent. From the Custom Agent Builder, they open the new **Agents as Tools** section and pick the specialist agent from a list — nothing else to fill in. The tool name and description the LLM will see are derived automatically from the specialist agent's own name and description. After saving, when an end user chats with the Research Coordinator and asks an Azure Government question, the LLM invokes the sub-agent as a tool, the sub-agent runs to completion, and its response is returned into the parent agent's reasoning so the parent can compose a final answer.

**Why this priority**: This is the core value proposition — without it the feature does not exist. It enables specialization and reuse of existing agents without copy/pasting prompts and tool sets.

**Independent Test**: Configure one parent agent with one sub-agent reference via the UI, save, then run a chat session that elicits a tool call. Verify the sub-agent's reply is incorporated into the parent's final response and that the tool invocation is observable in the trace/UI.

**Acceptance Scenarios**:

1. **Given** an admin is editing a custom agent, **When** they open the Agents as Tools section and pick another agent, **Then** the configuration is persisted (just the reference) and the derived tool name + description appear read-only on reload.
2. **Given** a parent agent has a sub-agent configured as a tool, **When** an end user sends a message that should trigger delegation, **Then** the LLM invokes the sub-agent tool, the sub-agent's response is returned to the parent, and the parent's final answer reflects that response.
3. **Given** a parent agent has multiple sub-agent tools configured, **When** the LLM chooses one based on the descriptions, **Then** only the selected sub-agent runs and its output is delivered back to the parent.

---

### User Story 2 - Discover and Manage Available Agents in the Builder (Priority: P2)

An admin opens the Custom Agent Builder and sees, in the Agents as Tools section, a list of available agents to pick from (both built-in agents from `config/agents.yaml` and other custom agents). The currently-edited agent is excluded from the list to prevent self-reference. The admin picks one or more sub-agents — the LLM-visible tool name and description are derived automatically from each picked agent (no manual entry). The admin can remove any reference. The form prevents saving when the configuration is invalid (a sub-agent that would directly reference back to the parent, or an unresolved reference).

**Why this priority**: Without good discovery and validation, admins will produce broken configurations. This story makes the feature usable in practice.

**Independent Test**: Open the builder for an existing agent, verify the picker excludes itself and any already-picked agents, add two sub-agent references and confirm the derived tool name + description appear read-only on each row, attempt a self-loop via reciprocal references, and confirm errors surface clearly and saving is blocked until fixed.

**Acceptance Scenarios**:

1. **Given** the admin is editing agent A, **When** they open the agents picker, **Then** agent A does not appear in the list of selectable agents.
2. **Given** agent B already references agent A as a tool, **When** the admin tries to add agent B as a tool on agent A, **Then** the form shows a clear cycle-prevention error and blocks save.
3. **Given** the admin picks an agent, **When** the row renders, **Then** the derived tool name and description are shown read-only and no further input is required to save.
4. **Given** the admin renames or edits the description of an agent that other agents reference as a tool, **When** those parent agents are next loaded, **Then** they automatically reflect the new tool name and description with no admin action.

---

### User Story 3 - Visually Consistent and Scannable Agent Form Subheaders (Priority: P3)

An admin editing an agent should be able to scan the form and instantly distinguish the page title ("Create New Agent" / "Edit Agent") from the subsection headers (Tools, AI Search Context, Skills, MCP Servers, Starter Questions, and the new Agents as Tools). All subsection headers share a consistent style that is clearly subordinate to the page title and consistent across sections.

**Why this priority**: Polish/usability bundled with the feature so that adding the new section does not introduce visual inconsistency. Important but not blocking the core delegation behavior.

**Independent Test**: Open the agent edit page and visually verify all six subsection headers render with the same typographic style, distinct from the page title, with consistent spacing and alignment.

**Acceptance Scenarios**:

1. **Given** the agent edit page is open, **When** the admin scans the form, **Then** all subsection headers (Tools, AI Search Context, Skills, MCP Servers, Starter Questions, Agents as Tools) share one consistent style distinct from the page title.
2. **Given** the page title and subheaders are rendered, **When** compared visually, **Then** the page title is clearly the most prominent heading and subsection headers are clearly secondary.

---

### Edge Cases

- **Self-reference**: Admin tries to add the agent being edited as one of its own tools — must be prevented (the picker excludes it; backend also rejects it).
- **Direct cycle (A→B and B→A)**: The system must detect and block creating the second leg of a direct two-agent cycle. (Deeper multi-hop cycle prevention is out of scope.)
- **Referenced agent deleted**: A parent agent references a sub-agent that is later deleted. The parent must continue to load and run; the orphaned reference is surfaced in the UI as an invalid entry the admin can remove, and at runtime the missing tool is omitted with a clear log/trace entry.
- **Referenced agent renamed**: References must remain valid across renames (i.e., the reference is by stable identifier, not display name).
- **Duplicate tool names**: Two sub-agent references on the same parent must not share a tool name (the LLM tool catalog requires uniqueness).
- **Sub-agent error/timeout**: If the sub-agent fails or times out, the tool call returns a structured error to the parent LLM rather than crashing the parent run.
- **Empty configuration**: An agent with zero sub-agent references must behave exactly as today (no regression).

## Requirements *(mandatory)*

### Functional Requirements

**Agent configuration & persistence**

- **FR-001**: An agent definition MUST support an optional collection of sub-agent tool references. Each reference contains a stable identifier of the target agent. The tool name and tool description exposed to the LLM are derived automatically from the referenced agent (see FR-001b) — the admin does not enter them. The collection MAY contain zero, one, several, or all other available agents — there is no upper bound and no required minimum (subject to validation rules below).
- **FR-001a**: The Custom Agent Builder picker MUST list every available agent except the agent being edited (built-in profiles from `config/agents.yaml` plus all custom agents). The admin selects an arbitrary subset (including the empty set or every available agent) by adding one reference per chosen agent.
- **FR-001b**: For each sub-agent reference, the system MUST derive the LLM-visible `tool_name` from the referenced agent's name (slugified to satisfy the LLM tool-name format — alphanumerics + underscores) and the LLM-visible `tool_description` from the referenced agent's `description` field. The admin MUST NOT be required (or able, in the standard flow) to enter these manually. Derivation MUST be deterministic and re-evaluated on read so that renaming/redescribing the target agent automatically updates the tool surface for parents that reference it.
- **FR-002**: The collection MUST be supported for both built-in agents defined in `config/agents.yaml` and custom agents stored in the existing custom-agent persistence layer, using a single shared schema.
- **FR-003**: The agent schema/validators MUST be extended so that loading, saving, and round-tripping an agent preserves the sub-agent tool references without data loss.
- **FR-004**: An agent with no sub-agent tool references MUST behave identically to today (backward compatibility).

**Backend runtime behavior**

- **FR-005**: When a parent agent runs, each configured sub-agent reference MUST be exposed to the LLM as an invokable tool whose name and description match the configured values.
- **FR-006**: When the LLM invokes a sub-agent tool, the system MUST execute the referenced sub-agent with the input the LLM provided and return the sub-agent's textual response to the parent agent's tool-call result, following the pattern in the Microsoft agent-framework `client_with_agent_as_tool.py` sample.
- **FR-007**: Sub-agent tool invocations MUST appear in the existing trace/observability output so admins can see which sub-agent was called, with what input, and what it returned.
- **FR-008**: If a referenced sub-agent cannot be resolved at runtime (deleted, misconfigured), the system MUST omit that single tool, log a clear warning, and continue running the parent agent without crashing.
- **FR-009**: If a sub-agent invocation fails or times out, the system MUST return a structured error result for that tool call so the parent LLM can react, rather than aborting the parent run.

**Validation & cycle prevention**

- **FR-010**: The system MUST reject any agent configuration that lists the same agent (the one being edited) as one of its own sub-agent tools (self-reference).
- **FR-011**: The system MUST reject any agent configuration that would create a direct two-agent cycle (A references B as a tool when B already references A as a tool).
- **FR-012**: Two sub-agent references on the same parent MUST NOT resolve to the same derived `tool_name`. Because tool names are derived from the target agent's name (FR-001b) and the picker prevents picking the same agent twice, this collision is structurally avoided; if it does occur (e.g., two distinct agents slugify to the same name), the system MUST disambiguate deterministically (append a numeric suffix) and surface the resolved names in the UI.
- **FR-013**: The derived `tool_name` MUST always be non-empty and MUST match the LLM tool-name format (alphanumerics and underscores). Slugification MUST guarantee this; if the source agent name is empty after slugification, the system MUST fall back to the agent's stable identifier.
- **FR-014**: All validation errors above MUST be surfaced via the API with clear, actionable messages, and MUST be enforced both in the frontend form and in the backend (defense in depth).

**API contract**

- **FR-015**: The API endpoints used to read, create, and update agents MUST include the new sub-agent tool references field in their request and response payloads.
- **FR-016**: The API MUST return validation errors (FR-010 through FR-013) with enough structure for the frontend to attach error messages to specific fields.

**Frontend — Custom Agent Builder**

- **FR-017**: The Custom Agent Builder edit form MUST include a new section titled "Agents as Tools" placed alongside the existing sections (Tools, AI Search Context, Skills, MCP Servers, Starter Questions).
- **FR-018**: The section MUST allow the admin to add one or more sub-agent references; for each, the admin only picks an agent from a list of available agents. Tool name and description are shown (read-only, derived from the picked agent) but not edited.
- **FR-019**: The picker MUST exclude the agent currently being edited.
- **FR-020**: The picker MUST show enough information for an admin to identify each available agent (display name and a short description if available).
- **FR-021**: The admin MUST be able to remove existing sub-agent references in the form.
- **FR-022**: Client-side validation MUST mirror backend validation (self-reference, direct cycle, duplicate target, unresolved reference) and disable save while invalid, with inline error messages on the offending row.

**UI polish — subsection header consistency**

- **FR-023**: All subsection headers within the agent edit form (Tools, AI Search Context, Skills, MCP Servers, Starter Questions, and the new Agents as Tools) MUST share a single consistent visual style.
- **FR-024**: Subsection headers MUST be visually subordinate to and clearly distinct from the page title ("Create New Agent" / "Edit Agent").

**Out of scope (explicitly)**

- Deep multi-hop cycle detection beyond the direct A↔B case.
- Orchestration policies (max delegation depth, recursion budgets, cost controls).
- Parallel agent fan-out UI or parallel sub-agent invocation patterns.
- Streaming of intermediate sub-agent tokens up through the parent (sub-agent response is returned as a completed result to the parent tool call).

### Key Entities

- **Agent**: An existing entity (built-in or custom). Gains a new optional collection of sub-agent tool references. Identified by a stable identifier that survives display-name changes.
- **Sub-Agent Tool Reference**: A new entity belonging to a parent Agent. Stored attribute: stable identifier of the referenced target agent. Derived (not stored) attributes: `tool_name` (slugified target agent name) and `tool_description` (target agent's description), both recomputed on read so target-agent edits propagate automatically.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An admin can configure a parent agent with a sub-agent tool reference and successfully observe the sub-agent being invoked in a real chat session, end-to-end, in under 5 minutes of configuration time.
- **SC-002**: 100% of invalid configurations defined in FR-010 through FR-013 are blocked at save time, both in the UI and via the API.
- **SC-003**: Existing agents (with no sub-agent tool references) continue to load, save, and run with zero behavioral change — verified by existing agent and API tests passing without modification to their assertions about runtime behavior.
- **SC-004**: When a sub-agent referenced by a parent is deleted, the parent agent still loads and runs successfully on the next request; the orphaned reference is visible to the admin in the builder so they can clean it up.
- **SC-005**: An admin viewing the agent edit form can correctly identify the page title vs. subsection headers in a quick visual scan; all six subsection headers render with one consistent style.
- **SC-006**: A sub-agent failure or timeout never causes the parent agent's chat turn to crash; the parent receives a structured error and can continue.

## Assumptions

- The existing custom-agent persistence layer supports schema extension without a destructive migration; the new field is additive and optional.
- Built-in agents in `config/agents.yaml` and custom agents share (or can share) a stable identifier scheme suitable for cross-referencing.
- The runtime is built on the Microsoft agent-framework (consistent with the referenced sample), so exposing an agent as a tool follows that framework's `as_tool` / equivalent pattern.
- "Direct cycle" is defined narrowly as a two-agent A↔B mutual reference. Deeper cycles (A→B→C→A) are explicitly out of scope and deferred.
- Tool name format follows common LLM tool-calling constraints (alphanumerics and underscores, reasonable length limit).
- Sub-agent invocation is synchronous from the parent's perspective: the parent's tool call completes when the sub-agent returns its final response.
- The new section in the UI follows the same form patterns and component conventions already used by the Tools, Skills, and MCP Servers sections.
