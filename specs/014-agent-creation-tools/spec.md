# Feature Specification: Agent Creation Tools

**Feature Branch**: `014-agent-creation-tools`  
**Created**: 2026-07-10  
**Status**: Draft  
**Input**: User description: "Agents need two optional/addable tools, one that can create a skill and one that can create an agent. Administrators can add them to an agent's configured tool set, after which the runtime agent may invoke them to durably create user-scoped skill definitions and custom agent definitions using existing persistence and validation paths."

## Overview

Administrators can already choose which tools an agent may use, and users can already create
skills and custom agents through management surfaces. This feature exposes two additional,
independently selectable runtime tools: one creates a skill and one creates a custom agent. An
agent receives neither capability by default. When an administrator adds either tool to the
agent's configured tool set, the running agent may create that type of definition on behalf of
the authenticated user.

Both tools use the same validation rules and durable stores as equivalent user-initiated
management actions. They are bound to the authenticated user before invocation, cannot choose a
different owner, never silently overwrite an existing definition, and return a small structured
result that lets the invoking agent accurately explain success or failure.

## Scope

### In Scope

- Two separately configurable runtime tools: **Create Skill** and **Create Agent**.
- Availability through the existing administrator tool-selection experience for built-in agent
  definitions, user overrides, and custom agents where ordinary tools are supported.
- Durable creation of user-owned skill definitions and custom agent definitions.
- Reuse of the existing validation, capability-resolution, persistence, and authenticated-user
  boundaries used by the corresponding management flows.
- Stable, structured tool results for successful creation and expected failures.

### Out of Scope

- Updating, deleting, publishing, sharing, or changing ownership of definitions through these
  tools.
- Creating or modifying built-in agent definitions or built-in agent overrides.
- Granting a runtime agent tools that its administrator did not configure.
- Automatically attaching a newly created skill or agent to the currently running agent.
- Automatically executing a newly created agent in the same conversation.
- Approval workflows, version history, cross-user sharing, and role-based administration changes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create a Durable Skill Through an Agent (Priority: P1)

As an authenticated user working with an agent that has the Create Skill tool, I want the agent
to create a valid skill from the instructions I provide, so I can reuse that capability in future
agent configurations without leaving the conversation.

**Why this priority**: Creating a skill is one of the two core capabilities and proves the full
configured-tool, validation, ownership, and durability path.

**Independent Test**: Configure only the Create Skill tool on an agent, ask it to create a valid
skill, and verify the result reports success, the skill appears only in the invoking user's
catalog, and the complete definition remains available after a restart and in a new session.

**Acceptance Scenarios**:

1. **Given** an authenticated user and an agent configured with Create Skill, **When** the agent
   invokes the tool with a valid unique name, description, and instruction body, **Then** one
   user-owned skill is durably created and a success result identifies it.
2. **Given** the same created skill and a later session or restarted service, **When** its owner
   opens the skill catalog, **Then** the original name, description, and content are present.
3. **Given** another authenticated user, **When** that user lists or resolves available skills,
   **Then** the first user's created skill is not visible or selectable.
4. **Given** an agent without Create Skill configured, **When** it runs, **Then** the tool is not
   available to invoke and no skill can be created through that session.

---

### User Story 2 - Create a Durable Custom Agent Through an Agent (Priority: P1)

As an authenticated user working with an agent that has the Create Agent tool, I want the agent
to create a complete custom agent definition from my requirements, so the new agent is available
in my agent catalog for later use and refinement.

**Why this priority**: This is the second core capability and must provide the same safety,
isolation, and durability guarantees as creation through the existing agent management flow.

**Independent Test**: Configure only the Create Agent tool, request a valid custom agent, and
verify the returned identity, owner-only visibility, persisted fields, and successful use in a
new session after restart.

**Acceptance Scenarios**:

1. **Given** an authenticated user and an agent configured with Create Agent, **When** the agent
   invokes the tool with a valid unique identity and complete definition, **Then** one user-owned
   custom agent is durably created and a success result identifies it.
2. **Given** a request containing configured tools, skills, search behavior, temperature, starter
   questions, or delegated agents, **When** creation succeeds, **Then** only valid and resolvable
   capabilities are persisted and the complete definition passes the same rules as a custom agent
   created through the management surface.
3. **Given** the created custom agent and a later session or restarted service, **When** its owner
   selects it, **Then** the saved definition is available and can start a session.
4. **Given** another authenticated user, **When** that user lists, retrieves, references, or tries
   to create against the first user's custom agent identity, **Then** the first user's definition
   is neither disclosed nor modified.
5. **Given** an agent without Create Agent configured, **When** it runs, **Then** the tool is not
   available to invoke and no custom agent can be created through that session.

---

### User Story 3 - Administrators Control Each Creation Capability (Priority: P2)

As an administrator configuring agents, I want Create Skill and Create Agent to appear as two
independent optional tools, so I can grant only the authoring capability appropriate for each
agent's purpose and risk level.

**Why this priority**: Agent-authored durable configuration is powerful. Explicit, granular
selection prevents accidental authority expansion.

**Independent Test**: Save agents with neither tool, each tool individually, and both tools;
start sessions for each configuration and verify the runtime tool inventory exactly matches the
saved selection.

**Acceptance Scenarios**:

1. **Given** the administrator's tool selector, **When** available tools are listed, **Then**
   Create Skill and Create Agent appear as distinct choices with descriptions that state they
   create durable user-owned definitions.
2. **Given** an agent configured with only Create Skill, **When** a session starts, **Then** Create
   Skill is available and Create Agent is absent.
3. **Given** an agent configured with both creation tools, **When** a session starts, **Then** both
   tools are available and each is bound to the session's authenticated user.
4. **Given** an existing agent configuration that predates this feature, **When** it is loaded or
   run, **Then** neither creation tool is added implicitly and existing behavior is unchanged.

---

### User Story 4 - Receive Actionable, Non-Destructive Results (Priority: P2)

As a user relying on an agent to create reusable definitions, I want duplicate and validation
failures to be explicit and non-destructive, so I know what to correct and can trust that existing
work was not overwritten.

**Why this priority**: Tool calls are mediated by a language model. Predictable results and strict
no-overwrite behavior are necessary for safe retries and truthful user feedback.

**Independent Test**: Invoke each tool with a valid payload, a duplicate identity, invalid fields,
an unknown capability reference, and a simulated storage failure; verify the documented result
shape and that failed calls create or change no definition.

**Acceptance Scenarios**:

1. **Given** a definition identity already owned by the invoking user, **When** either creation
   tool uses that identity, **Then** it returns a duplicate result and leaves the existing
   definition byte-for-byte unchanged.
2. **Given** invalid or incomplete input, **When** either tool is invoked, **Then** it returns a
   validation result containing field-level issues and persists nothing.
3. **Given** a custom agent referencing an unknown tool, unavailable skill, invalid delegated
   agent, unsafe server configuration, or out-of-range setting, **When** Create Agent validates
   the request, **Then** creation fails rather than silently dropping or rewriting the value.
4. **Given** a transient persistence failure, **When** either tool is invoked, **Then** it returns
   a retryable failure without claiming success or exposing internal credentials or diagnostics.

### Edge Cases

- The tool is present in a submitted configuration but is not a recognized available tool: the
  configuration is rejected through the existing unknown-tool validation path.
- A user requests a skill name that collides with a built-in/global skill visible in their
  catalog: creation is rejected as a duplicate to avoid ambiguous resolution or shadowing.
- Two calls concurrently create the same identity for the same user: exactly one succeeds; the
  other returns a duplicate result, and neither call overwrites the winner.
- Two different users create the same custom agent id or user-owned skill name: both may succeed
  because uniqueness and storage ownership are scoped to each user, provided neither skill name
  collides with a built-in/global skill.
- Leading or trailing whitespace is normalized only where the existing management validation
  already normalizes it; normalization must not turn a duplicate into an overwrite.
- A Create Agent request references the parent agent itself or creates a direct delegated-agent
  cycle: validation rejects the request with the existing delegated-agent validation semantics.
- A referenced skill or delegated custom agent belongs to another user: it is treated as
  unresolved and no information about the other user's definition is returned.
- The authenticated identity is absent or invalid when the session is established: the tools are
  not bound and creation is denied.
- A tool call is retried after a success because its result was interrupted: the retry receives a
  duplicate result identifying the requested identity, never a second record or silent update.
- A valid creation succeeds but the current session's cached catalog is unchanged: the new
  definition is guaranteed for subsequent catalog reads and new sessions; hot attachment to the
  active runtime is out of scope.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST register Create Skill and Create Agent as two distinct tools that
  administrators can independently add to or remove from an agent's configured tool set.
- **FR-002**: Neither creation tool MUST be included in any existing or newly created agent by
  default; tool availability MUST continue to be determined by the agent's saved configuration.
- **FR-003**: At session creation, each enabled creation tool MUST be bound to the authenticated
  user's immutable identity. Tool input MUST NOT accept an owner, user id, tenant id, or equivalent
  field capable of redirecting the write.
- **FR-004**: Create Skill MUST accept a skill name, description, and instruction content and MUST
  apply the same name, description, and content validation rules as the existing skill creation
  flow before persistence.
- **FR-005**: Create Skill MUST durably persist successful creations as user-owned skills, isolated
  from every other user's reads, selection, references, updates, and deletes.
- **FR-006**: A user-owned skill catalog MUST combine built-in/global skills with skills owned by
  the current user for selection and runtime loading, without exposing skills owned by other users.
- **FR-007**: Create Skill MUST reject a name already used by the invoking user's skill or by a
  built-in/global skill visible to that user. It MUST NOT overwrite, merge, version, or shadow the
  existing skill.
- **FR-008**: Create Agent MUST accept the complete custom-agent definition supported by the
  existing management flow: stable id, name, description, system instructions, selected tools,
  selected skills, server connections, search behavior, icon, starter questions, temperature,
  and delegated-agent references, with optional fields retaining existing defaults.
- **FR-009**: Create Agent MUST pass input through the same validation and capability-resolution
  rules as a custom agent created through the management flow. Unlike session-time compatibility
  behavior, creation MUST reject unknown or unavailable references rather than silently drop them.
- **FR-010**: Create Agent MUST durably persist successful creations in the existing per-user
  custom-agent store under the invoking user's ownership and MUST preserve the established custom
  agent data shape needed by catalog, management, and session-start flows.
- **FR-011**: Create Agent MUST reject an id already used by a custom agent owned by the invoking
  user and MUST NOT overwrite, merge, or update it. The existence of the same id under another user
  MUST NOT block creation or be disclosed.
- **FR-012**: Each tool MUST perform validation before its write and MUST make creation atomic from
  the caller's perspective: success creates exactly one complete definition; any failure leaves no
  partial definition and changes no existing definition.
- **FR-013**: Each successful tool result MUST be a structured object containing `status` set to
  `created`, `kind` set to `skill` or `agent`, the created definition's `id`, its display `name`,
  and a concise human-readable `message`. It MUST NOT include storage metadata, owner identifiers,
  credentials, tokens, or full instruction content.
- **FR-014**: Each expected failure result MUST be a structured object containing `status` set to
  `error`, `kind`, a stable `code`, and a concise human-readable `message`; validation failures MUST
  additionally contain an `issues` list whose entries identify the invalid field and reason.
- **FR-015**: Stable failure codes MUST distinguish at least `validation_error`, `duplicate`,
  `unauthorized`, and `temporarily_unavailable`, and MUST indicate whether retrying the unchanged
  call may succeed.
- **FR-016**: Duplicate responses MAY identify the requested id or name but MUST NOT return the
  existing definition, its content, or ownership metadata.
- **FR-017**: Successful creations MUST be observable through the same user-facing catalog and
  management reads as manually created definitions and MUST remain available across service
  restarts, deployments, backend instances, and later sessions.
- **FR-018**: Creation tool calls MUST use the application's existing authenticated persistence
  boundaries and MUST NOT fall back to process memory, local files, browser-only storage, or a
  shared unpartitioned user-data record when durable storage is unavailable.
- **FR-019**: Logs and tool results MUST NOT contain credentials, access tokens, connection secrets,
  full system instructions, full skill content, or another user's data. Operational failures MUST
  be sanitized before being returned to the runtime agent.
- **FR-020**: Existing agents, skill management, custom-agent management, and session creation MUST
  retain their current behavior when the new tools are not selected.

### Authorization and Isolation Rules

- Only an authenticated session may receive either creation tool.
- Configuring a tool grants the runtime agent permission to invoke that creation operation on
  behalf of the current user; it does not grant access to another user's definitions.
- Ownership is derived exclusively from the authenticated session and is applied to every
  existence check, validation lookup, persistence write, and subsequent read.
- Cross-user definitions must behave as nonexistent to the caller. Errors must not reveal whether
  a requested identity exists for another user.
- Global/built-in skills remain read-only through the runtime tool and reserve their names across
  all user-owned skill catalogs.

### Tool Result Contract

Successful creation:

```json
{
  "status": "created",
  "kind": "skill | agent",
  "id": "stable-definition-id",
  "name": "Display name",
  "message": "Concise confirmation"
}
```

Expected failure:

```json
{
  "status": "error",
  "kind": "skill | agent",
  "code": "validation_error | duplicate | unauthorized | temporarily_unavailable",
  "message": "Concise corrective explanation",
  "retryable": false,
  "issues": [
    {"field": "fieldName", "reason": "Why the value was rejected"}
  ]
}
```

`issues` is required for validation failures and omitted for failures without a field-specific
cause. Unexpected internal failures use the same sanitized error envelope rather than exposing a
stack trace or raw provider error.

### Key Entities

- **Creation Tool Grant**: An agent configuration entry that enables Create Skill or Create Agent.
  It determines runtime availability but contains no user identity or storage authority by itself.
- **User-Owned Skill**: A reusable skill definition owned by one authenticated user. Key attributes
  are owner-scoped identity, name, description, instruction content, and creation/update timestamps.
  Its name must not collide with a global/built-in skill.
- **Custom Agent Definition**: An existing user-owned agent shape containing identity, presentation,
  instructions, selected capabilities, behavior settings, and timestamps. This feature creates new
  definitions but does not update or delete them.
- **Tool Creation Result**: A bounded, non-secret outcome returned to the runtime agent. It records
  created/error status, definition kind, safe identity fields, and stable corrective information.

## Assumptions

- The request for user-scoped skills intentionally introduces user ownership for agent-created
  skills even though the current administrator-managed skill catalog is global. Existing global
  skills remain available and unchanged; user-owned skills form an additional owner-isolated
  catalog layer.
- Existing custom-agent definitions are already durable and user-scoped; Create Agent uses that
  ownership model rather than creating a second kind of agent record.
- An agent's configured tool list is an administrator-controlled capability boundary. No separate
  human approval prompt is required for each invocation in this feature.
- Skill names remain lowercase slug identifiers with the existing length limit; descriptions and
  content retain their existing non-empty and maximum-length rules.
- Custom agent name, prompt, temperature, server, selected tool/skill, and delegated-agent rules
  remain authoritative. Any management route that currently bypasses those rules must converge on
  the shared validation path before it can be considered equivalent for this feature.
- Per-user uniqueness applies to custom agent ids and user-owned skill names. Global skill names are
  reserved to prevent ambiguous runtime resolution.
- Creation timestamps and storage bookkeeping are maintained by the persistence layer and are not
  accepted from or returned to the runtime agent.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of tested agent configurations, each creation tool is available only when it
  was explicitly selected, and selecting one never enables the other.
- **SC-002**: At least 95% of valid first-attempt Create Skill and Create Agent requests complete
  with a truthful structured result within 5 seconds under normal operating conditions.
- **SC-003**: 100% of successful creations are visible to their owner in the corresponding catalog
  on the next read and remain available after restart and from another backend instance.
- **SC-004**: 100% of cross-user isolation tests prevent listing, reading, referencing, changing,
  or inferring another user's created skill or custom agent.
- **SC-005**: 100% of duplicate, invalid, unauthorized, and simulated storage-failure calls leave
  existing definitions unchanged and create no partial records.
- **SC-006**: 100% of tested tool outcomes conform to the documented result contract and contain no
  credentials, owner identifiers, full skill content, full agent instructions, or raw diagnostics.
- **SC-007**: A user can ask an enabled agent to create a valid reusable skill or custom agent and
  find it in the corresponding management catalog without manual re-entry in one conversational
  workflow.
- **SC-008**: Existing agents without either new tool complete their established session and
  management workflows with no observed behavior change.