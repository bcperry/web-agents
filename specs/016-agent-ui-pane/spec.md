# Feature Specification: Agent Dynamic UI Pane

**Feature Branch**: `016-agent-ui-pane`  
**Created**: 2026-08-14  
**Status**: Draft  
**Input**: User description: "lets give the option for a tool that provides an agent with a dynamic ui on the side, uses agents permissions for any data tool calls elsewise, but can render and show html. in that agent ui pane."

## Overview

Today an agent can only answer in chat text, tool accordions, and inline images. Some
answers are far more useful as a *view*: a comparison table, a readiness dashboard, a
filterable list, a step-by-step form. This feature adds an **optional agent capability**
that gives an enabled agent a dedicated **side pane** in which it can compose and show a
rendered view (HTML presentation markup) next to the conversation.

The view is not a second application with its own reach into data. It is a presentation
surface: it can display what the agent already gathered, and it can ask for more data —
but every such request is executed by the backend **using only the tools the rendering
agent is already permitted to use, on behalf of the signed-in user who owns the
conversation**. The view itself has no credentials, no direct network access, and no
access to the host application.

## Scope

### In Scope

- An opt-in, per-agent capability that lets an agent produce a rendered view.
- A side pane in the chat experience that displays the current view, with open, collapse,
  close, resize, and narrow-viewport behavior.
- Interactive controls inside a view (filters, refresh, selection, form submission) whose
  data requests are brokered by the backend under the agent's existing tool permissions.
- Isolation of rendered content from the host application, user credentials, other
  conversations, and the network.
- Persistence of views with their conversation, including views produced during
  unattended/autonomous runs.
- Audit of view renders and view-originated data requests alongside normal tool activity.
- Administrator control to enable or disable the capability per agent.

### Out of Scope

- A general plugin, widget, or extension marketplace.
- User-authored or user-edited views; views are agent-authored only.
- Views that call third-party services directly, or that hold their own credentials.
- Long-lived application state that outlives the conversation (a view is a view of the
  conversation's data, not a separate app).
- Exporting a view as a standalone file, print layout, or shareable public link.
- Replacing existing inline rich content (images in tool results and messages) — that
  behavior stays as-is.
- New mutating data operations introduced solely for views; views inherit the agent's
  existing tools and their existing constraints, nothing more.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An Agent Shows a View Instead of Describing One (Priority: P1)

A user is talking to an agent that has the dynamic UI capability enabled. They ask for
something that is hard to read as prose — "compare these four units across the last three
inspections" or "show me the open items grouped by owner". The agent gathers the data with
its normal tools, composes a view, and the view appears in a pane beside the conversation.
The chat reply continues to stream and read normally, with a short summary and a marker
pointing at the view.

**Why this priority**: This is the core value of the feature. Without it, nothing else
matters. A read-only, non-interactive view already delivers real value on its own.

**Independent Test**: Enable the capability for one agent, ask a question that warrants a
visual answer, and verify a rendered view appears in the side pane while the conversation
remains readable and responsive. Disable the capability and verify no pane appears.

**Acceptance Scenarios**:

1. **Given** an agent with the capability enabled, **When** the agent produces a view during
   its reply, **Then** the side pane opens showing the rendered view, clearly labeled as
   agent-generated content, and the chat reply continues to stream without interruption.
2. **Given** a view is displayed, **When** the user reads the conversation, **Then** the
   transcript contains a marker for that view and selecting it brings that view into the pane.
3. **Given** an agent **without** the capability, **When** the user asks for a visual answer,
   **Then** no pane appears and the agent answers using its normal chat capabilities.
4. **Given** the agent produces content the system cannot render, **When** the view is
   received, **Then** the pane shows a clear error state, the conversation continues to work,
   and the agent is told the render failed so it can retry or fall back to text.

---

### User Story 2 - The View Fetches Fresh Data Under the Agent's Permissions (Priority: P1)

The view the agent produced includes controls — a date filter, a refresh button, a dropdown
that changes which record is shown. When the user interacts with a control, the view asks
for data. That request is executed by the backend as the signed-in user, restricted to the
exact tools the rendering agent is permitted to use. Anything outside that set is refused,
returns no data, and is shown to the user as a refusal.

**Why this priority**: This is the security contract of the feature and the part the user
explicitly called out. An interactive view that could reach data outside the agent's
permissions would be a privilege-escalation path, so it must be correct from day one.

**Independent Test**: Render a view with a refresh control bound to a tool the agent is
permitted to use and verify the data updates in place. Then exercise a view whose request
names a tool the agent is *not* permitted to use and verify it is refused with no data
returned and a visible, auditable refusal.

**Acceptance Scenarios**:

1. **Given** a view with a control bound to a tool in the agent's permitted set, **When** the
   user activates the control, **Then** the request runs as the signed-in user, the view
   updates with the returned data, and the request appears in the conversation's tool trace.
2. **Given** a view whose request names a tool outside the agent's permitted set, **When** the
   request is submitted, **Then** it is refused, no data is returned, the pane shows a
   plain-language refusal, and the refusal is recorded for audit.
3. **Given** a view whose request supplies invalid or out-of-bounds arguments, **When** the
   request is submitted, **Then** it is rejected with a clear message and no partial data leaks.
4. **Given** a rendered view, **When** it attempts to reach any external destination directly or
   to read the host application's session, storage, or other conversations, **Then** the attempt
   fails and the user's credentials and other data remain inaccessible.
5. **Given** a view-originated request fails (tool error, rate limit, timeout), **When** the
   failure is returned, **Then** the view shows a retry-able error state and the conversation
   is unaffected.

---

### User Story 3 - Administrators Decide Which Agents Get a UI Pane (Priority: P2)

An administrator reviews which agents should be allowed to draw their own UI. They enable
the capability for the agents where it makes sense and leave it off elsewhere. Users can
see, from the active agent's capabilities, whether the agent can produce views.

**Why this priority**: Governance matters, but the capability can ship configured for a
single pilot agent first. It becomes important as soon as more than one agent uses it.

**Independent Test**: Toggle the capability for an agent, start a new conversation, and
verify the agent can (or cannot) produce a view accordingly, with the capabilities
indicator reflecting the current state.

**Acceptance Scenarios**:

1. **Given** an administrator enables the capability for an agent, **When** a user starts a new
   conversation with that agent, **Then** the agent can produce views and the capabilities
   indicator shows the capability as available.
2. **Given** an administrator disables the capability, **When** a user starts a new conversation
   with that agent, **Then** the agent cannot produce views and no pane can be opened.
3. **Given** the capability is disabled after views already exist in older conversations,
   **When** the user reopens one of those conversations, **Then** previously produced views are
   still viewable but no new views can be produced.

---

### User Story 4 - The Pane Behaves Like a Well-Mannered Part of the App (Priority: P2)

A user works with the pane over a long conversation: collapsing it to focus on chat,
reopening it, resizing it, switching between two views the agent produced, and coming back
the next day to find the conversation and its views intact.

**Why this priority**: Without this, the feature is usable but annoying — a pane that
cannot be dismissed, or that loses its content on reload, will be abandoned quickly.

**Independent Test**: Produce two views in one conversation, switch between them, collapse
and reopen the pane, reload the page, and reopen the conversation later; verify the latest
view is restored and earlier views remain reachable from the transcript.

**Acceptance Scenarios**:

1. **Given** a view is open, **When** the user collapses or closes the pane, **Then** the chat
   uses the full width and the view is not deleted.
2. **Given** the pane is closed, **When** the agent produces a new view, **Then** the user is
   notified in the transcript and can open the pane to see it.
3. **Given** two or more views exist in a conversation, **When** the user opens the pane, **Then**
   the most recent view is shown and earlier views can be selected from their transcript markers.
4. **Given** a conversation with views, **When** the user reloads the page or reopens the
   conversation later, **Then** the views are restored intact.
5. **Given** a narrow or mobile-width screen, **When** a view is opened, **Then** the pane
   presents full-width with an obvious control to return to the conversation.

---

### Edge Cases

- **Oversized content**: the agent produces a view larger than the allowed size — the view is
  rejected with a clear message to the user and feedback to the agent, and nothing partial renders.
- **Malformed content**: the agent produces content that cannot be rendered — the pane shows an
  error state and the conversation continues normally.
- **Heavy or unresponsive view**: a view consumes excessive resources — the conversation stays
  responsive and the user can always close the view.
- **Rapid re-render**: the agent replaces the view several times in one turn — the pane settles on
  the final view without flicker loops, and intermediate versions are not silently lost from the
  transcript.
- **Pane closed mid-render**: the user closes the pane while the agent is producing a view — the
  view is still saved and announced in the transcript.
- **Unattended runs**: an autonomous run produces a view with no user present — the view is stored
  and shown when the user next opens that conversation.
- **Stale view**: a user interacts with a view from a conversation that has since expired, or whose
  agent lost the required permission — the request is refused with an explanation rather than
  failing silently.
- **Permission change mid-conversation**: the agent's tool permissions change while a view is open —
  the next view-originated request is evaluated against the *current* permissions.
- **Multiple tabs**: the same conversation is open in two browser tabs — each tab renders the same
  stored views without corrupting the other's pane state.
- **Sensitive data**: a view displays data the user is entitled to see — the same retention, masking,
  and logging rules that apply to chat content apply to view content.
- **Accessibility**: a keyboard-only or screen-reader user must be able to reach, operate, and leave
  the pane, and must not be trapped inside a rendered view.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The dynamic UI capability MUST be opt-in per agent; an agent without it MUST NOT be
  able to produce or display a view.
- **FR-002**: When an enabled agent produces a view, the system MUST display it in a dedicated pane
  alongside the conversation without interrupting or delaying the streaming chat reply.
- **FR-003**: The system MUST render agent-authored presentation markup (HTML and styling) as a
  visual view, not as raw source text.
- **FR-004**: Rendered views MUST be isolated from the host application: no access to the signed-in
  user's tokens or credentials, the host application's stored state, the host page, or any other
  conversation.
- **FR-005**: Rendered views MUST NOT be able to initiate network requests to any destination
  directly; every byte of data a view receives MUST come through the backend broker.
- **FR-006**: A data request originating from a view MUST be executed only through tools the
  rendering agent is permitted to use, under the identity of the signed-in user who owns the
  conversation, with the same validation, limits, and read-only constraints that apply when the
  agent calls that tool during chat.
- **FR-007**: A view-originated request that names a tool outside the agent's permitted set, or that
  supplies invalid arguments, MUST be refused, MUST return no data, MUST surface a plain-language
  message in the pane, and MUST be recorded for audit.
- **FR-008**: View renders and view-originated data requests MUST be recorded in the same
  conversation history and trace mechanism used for tool calls, so users and evaluators can audit
  what was shown and what was fetched.
- **FR-009**: Users MUST be able to open, collapse, and close the pane at any time; closing the pane
  MUST NOT delete the view.
- **FR-010**: The pane MUST be resizable within sensible bounds on wide screens and MUST switch to a
  full-width presentation with an explicit return-to-conversation control on narrow screens.
- **FR-011**: The conversation transcript MUST contain a marker for each view the agent produced, and
  selecting a marker MUST bring that view into the pane.
- **FR-012**: Opening the pane MUST show the most recent view for that conversation by default.
- **FR-013**: Views MUST be persisted with their conversation and restored intact when the
  conversation is reopened, including after a full page reload, subject to the same retention rules
  as the rest of the conversation.
- **FR-014**: The system MUST enforce a maximum size for a single view, rejecting oversized content
  with a clear message to the user and actionable feedback to the agent. The system MUST also cap
  the number of stored views per conversation; when the cap is reached the oldest view is evicted so
  the agent can keep rendering.
- **FR-015**: Content that cannot be rendered MUST fail safely — the pane shows an error state, the
  conversation continues to function, and the agent receives feedback describing the failure.
- **FR-016**: A slow, heavy, or unresponsive view MUST NOT block, freeze, or crash the conversation
  experience, and the user MUST always be able to close it.
- **FR-017**: View-originated requests MUST inherit the same per-user data isolation as chat tool
  calls; a view MUST NOT be able to read or modify another user's data.
- **FR-018**: Views produced during unattended or autonomous runs MUST be stored and made available
  the next time the user opens that conversation.
- **FR-019**: The active agent's capability summary MUST indicate whether that agent can produce views.
- **FR-020**: The pane MUST be operable by keyboard and announced to assistive technology, including
  a reliable way to move focus into and out of a rendered view.
- **FR-021**: The pane MUST label its content as agent-generated so users do not mistake it for
  first-party application UI.
- **FR-022**: View-originated data requests MUST be bounded in frequency and response size so a view
  cannot exhaust user, session, or backend resources.
- **FR-023**: Credentials, tokens, connection strings, and other secrets MUST never appear in view
  content or in data returned to a view.
- **FR-024**: Enabling or disabling the capability for an agent MUST take effect for new
  conversations without requiring a redeploy or application restart.

### Authorization and Isolation Rules

- The rendering agent's permitted tool set is the **only** authority for what a view can fetch. The
  view cannot widen it, and the backend MUST re-evaluate it on every request rather than trusting
  anything supplied by the view.
- The signed-in user who owns the conversation is the **only** identity used for view-originated
  requests. A view MUST NOT be able to act as another user, another agent, or the service itself.
- Isolation is enforced on the client side (the view cannot reach the host app or the network) **and**
  on the server side (the broker refuses anything outside the agent's permitted set). Neither side
  may be the sole control.
- A view is untrusted content for the purposes of security review: it is authored by a language model
  and may be influenced by tool output, so it MUST be treated as potentially hostile.

### Key Entities

- **Agent View**: a single agent-authored rendered unit belonging to one conversation turn. Attributes:
  title, presentation content, creation time, owning conversation and turn, size, render status.
- **View Data Request**: a data request originating from a rendered view. Attributes: the named tool,
  supplied arguments, requesting user, rendering agent, outcome (fulfilled / refused / failed), and
  timestamp.
- **UI Capability Grant**: the per-agent enablement of the dynamic UI capability, managed alongside
  the agent's other tool permissions.
- **Pane State**: per-user, per-conversation presentation state — open or collapsed, width, and which
  view is currently displayed.

## Assumptions

- **Opt-in like any other tool**: the capability is granted to an agent the same way other tools are
  granted today (an entry in the agent's permitted tool list), so administrators use an existing,
  familiar control rather than a new permission system.
- **Views are interactive**: the request ("uses agent's permissions for any data tool calls") implies
  views can request data, so interactivity is in scope. A view may contain behavior, but that behavior
  runs inside the isolation boundary and can only reach data through the broker.
- **No external resources**: views are self-contained. They may not load remote scripts, styles,
  fonts, or images from external origins. This follows the Azure Government posture in the project
  constitution; anything a view shows must be inline or fetched through the broker.
- **Data requests do not require a new model turn**: a control that simply refetches permitted data
  resolves directly through the broker for responsiveness. Interactions that need reasoning are sent
  into the conversation as a normal message instead.
- **One pane, many views**: a conversation has a single pane; the agent's newest view is shown by
  default and earlier views remain reachable from transcript markers. There is no multi-window or
  tiled layout.
- **Views are read-mostly**: views inherit only the tools the agent already has. If an agent has no
  mutating tools, its views cannot mutate anything.
- **Retention follows the conversation**: views live and die with their conversation and are stored
  with the same isolation and retention as chat history.
- **Text-first fallback**: an agent with the capability is still expected to answer in chat; the view
  supplements the answer rather than replacing it, so users who close the pane are never stranded.

## Dependencies

- The existing per-agent permitted tool list, which defines what a view may fetch.
- The existing authenticated-user identity on every request, which scopes view-originated data access.
- The existing conversation streaming channel, which carries view renders to the client.
- The existing conversation persistence and per-user isolation, which stores and restores views.
- The existing tool trace/history mechanism, which records view renders and view-originated requests.
- The existing unattended/autonomous run behavior, for views produced with no user present.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For an enabled agent, a produced view is visible in the pane within 3 seconds of the
  agent finishing it, and the conversation stays interactive throughout with no perceptible freeze.
- **SC-002**: 100% of view-originated requests naming a tool outside the rendering agent's permitted
  set are refused and return zero bytes of data, verified by an automated security test suite.
- **SC-003**: Zero successful attempts, across the isolation test suite, for a rendered view to reach
  the host application's session or storage, another conversation, another user's data, or any
  external network destination.
- **SC-004**: 95% of permitted data requests triggered from a view return updated content in under
  3 seconds, comparable to an equivalent tool call made from chat.
- **SC-005**: 100% of malformed, oversized, or failing views result in a visible error state with the
  conversation still fully usable — no blank screens and no lost chat history.
- **SC-006**: Views are restored intact in 100% of reopen and page-reload tests, including views
  produced during unattended runs.
- **SC-007**: Agents without the capability produce zero views in 100% of attempts, including when a
  user explicitly asks them to draw one.
- **SC-008**: Enabling or disabling the capability for an agent is reflected in the next new
  conversation without a restart, in 100% of tests.
- **SC-009**: In usability checks, at least 90% of first-time users can open, collapse, and reopen a
  view and correctly identify it as agent-generated without assistance.
- **SC-010**: 100% of view renders and view-originated requests appear in the conversation's audit
  trace, so a reviewer can reconstruct exactly what was shown and what was fetched.
