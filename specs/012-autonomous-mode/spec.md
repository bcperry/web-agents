# Feature Specification: Autonomous Mode (Scheduled Agent Duty Officer)

**Feature Branch**: `012-autonomous-mode`  
**Created**: 2026-06-18  
**Status**: Draft (revised — in-process scheduler design)  
**Input**: User description: "Implement an autonomous mode. It'll need to be a function app that fires on a timer and uses the agent backend here. It will request that the agent take an action and respond. This will ultimately need to snap into the NETCOM CCIR agentic triage architecture. Create a branch and implement this all the way; make best guesses." (original)

> **Design note (revised):** the original ask imagined an external Azure **Function App**
> firing the timer. Implementation experience showed that adds a whole deployment unit and a
> fragile service-to-service auth surface for no real benefit — the backend already owns the
> agent runtime, Cosmos access, config, and audit writing. The chosen design runs the
> schedule **in-process in the backend** with a durable **Cosmos lease** for at-most-once
> execution across instances. See [research.md](research.md) for the decision record. The
> requirements below are written to that design; "trigger" means the in-process scheduler
> (or the user-initiated "run now") unless stated otherwise.

## Overview

Today the platform is **interactive only**: a human opens the web UI, selects an agent
profile, and drives every turn by typing. The agent never acts unless a person is present
and prompting it. The target architecture (the NETCOM CCIR Agentic Triage Platform) calls
for an **always-on digital watch officer**: on a cadence, something wakes the agent, the
agent performs a standing directive (e.g., check signals, classify them, draft a
notification), records what it did, and routes the result to humans for review/approval —
all without a person initiating each cycle.

This feature adds **Autonomous Mode**: an **in-process scheduler in the agent backend** that,
on a configurable schedule, asks the existing agent runtime to execute a **standing directive**
and respond. Each autonomous cycle reuses the *same* agent runtime, tools, and durable
Cosmos memory that the interactive UI uses — so the autonomous agent and its human
counterparts share one brain and one audit trail. Every cycle is recorded as an auditable
**run record** and its output is delivered to a **notification sink** (logged by default,
or posted to an external review channel) so a human can see, and ultimately approve, what
the autonomous agent produced.

This is the "Timer / incoming content trigger" → "Duty Officer Agent" → "logs to Cosmos" →
"drafts a notification for approval" slice of the target diagram, built so it can later
snap into the full triage workflow (mailbox ingestion, CCIR classification, Teams approval
cards) without re-architecting.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent Acts on a Standing Directive Without a Human Present (Priority: P1)

As the operations owner of the platform, I want the agent to automatically execute a
standing directive on a recurring schedule, so the watch function continues 24/7 even when
no analyst is actively typing.

**Why this priority**: This is the core of the feature. Without an unattended,
timer-driven cycle that actually invokes the agent and captures its response, none of the
downstream value (audit, notification, triage) exists. It is the minimum viable
autonomous capability.

**Independent Test**: Configure a directive (a profile + an instruction) and a short
schedule, let the timer fire (or invoke the manual trigger), and confirm the agent ran the
directive end-to-end and produced a response — with no human typing the prompt.

**Acceptance Scenarios**:

1. **Given** Autonomous Mode is enabled with a standing directive, **When** the schedule
   elapses, **Then** the agent backend is invoked with that directive and produces a
   completed response, recorded as one autonomous run.
2. **Given** the timer fires, **When** the agent executes the directive, **Then** the run
   uses the same configured agent profile, tools, and reasoning the interactive UI would
   use for that profile.
3. **Given** an operator needs to trigger a cycle immediately (e.g., to test or to respond
   to a real-world event), **When** they invoke the manual trigger, **Then** the same
   autonomous cycle runs on demand and returns its result.

---

### User Story 2 - Every Autonomous Action Is Auditable (Priority: P1)

As an accountable watch supervisor in a government context, I want every autonomous cycle
to be durably recorded — what directive ran, when, what the agent decided, which tools it
used, and whether it succeeded — so the unattended agent's behavior is fully auditable
after the fact.

**Why this priority**: An agent that acts on its own without a tamper-evident record is
unacceptable in this environment. Auditability is a non-negotiable peer to the action
itself, and it is what makes later human approval meaningful.

**Independent Test**: Run several autonomous cycles, then retrieve the run history and
confirm each cycle is present with its directive, timestamp, status, response summary, and
tool activity — surviving a backend restart.

**Acceptance Scenarios**:

1. **Given** an autonomous cycle completes, **When** the run record is written, **Then** it
   durably captures the directive identifier, start/finish time, agent profile, status
   (success/failure), the agent's response, the tools invoked, and token usage.
2. **Given** multiple cycles have run, **When** an operator lists autonomous run history,
   **Then** the runs are returned most-recent-first and remain available after a process
   restart.
3. **Given** a cycle fails (e.g., the agent or a dependency errors), **When** the run is
   recorded, **Then** the failure and its reason are captured as a run record rather than
   silently lost.

---

### User Story 3 - Autonomous Output Is Routed to Humans for Review (Priority: P2)

As a watch officer, I want each autonomous cycle's result delivered to a review channel, so
I can see what the agent produced and (in the target workflow) approve or act on it — the
agent drafts, a human decides.

**Why this priority**: Closing the loop to a human is what turns raw autonomous output into
a usable watch product. It depends on US1/US2 existing first, and the exact downstream
channel (Teams card, email) is environment-specific, so it ships after the core cycle and
audit.

**Independent Test**: Configure a notification destination, run a cycle, and confirm the
agent's output (and a link/handle to the audit record) is delivered to that destination;
with no destination configured, confirm the output is still captured and logged without
error.

**Acceptance Scenarios**:

1. **Given** a notification destination is configured, **When** an autonomous cycle
   completes, **Then** the agent's response and a reference to its run record are delivered
   to that destination.
2. **Given** no external destination is configured, **When** a cycle completes, **Then** the
   result is recorded and logged through the default sink without error (no hard dependency
   on an external channel).
3. **Given** delivery to the external destination fails, **When** the cycle finishes,
   **Then** the run is still recorded as completed and the delivery failure is captured,
   not raised as a lost cycle.

---

### User Story 4 - Operators Configure and Control Autonomous Behavior (Priority: P2)

As the operations owner, I want to define which directive(s) run, how often, and which agent
profile each uses — and be able to turn autonomous mode off — so the unattended behavior is
deliberate, reviewable, and safely reversible.

**Why this priority**: Autonomous behavior must be intentional and controllable. This makes
the feature operable and safe, but it builds on the core cycle existing.

**Independent Test**: Disable autonomous mode and confirm no cycles run on the timer; define
a directive with a specific profile and cadence and confirm it is the one that executes;
list the configured directives.

**Acceptance Scenarios**:

1. **Given** autonomous mode is disabled, **When** the timer would fire, **Then** no agent
   cycle is executed.
2. **Given** a directive specifies a particular agent profile and instruction, **When** its
   cycle runs, **Then** that profile and instruction are the ones used.
3. **Given** multiple directives are configured, **When** an operator inspects the
   configuration, **Then** each directive's identifier, profile, instruction summary,
   schedule, and enabled state are visible.

---

### User Story 5 - The Scheduler Is Gated and the Manual Trigger Is Authenticated (Priority: P2)

As a security owner, I want the unattended scheduler to run only when explicitly enabled and
only against pre-defined directives, and the on-demand "run now" action to require a normal
authenticated user — so autonomous execution cannot be abused to run arbitrary prompts or be
triggered by an anonymous caller.

**Why this priority**: An entry point that makes an LLM with tools and data access act on its
own is security-sensitive. With the schedule running in-process there is **no external
service endpoint to attack** — the surface reduces to (a) a config gate and (b) the existing
user-authenticated API — but those still must be constrained.

**Independent Test**: With the scheduler flag off, confirm no cycles run; with it on, confirm
the configured directive runs on cadence. Call the on-demand run endpoint as an
unauthenticated caller and confirm it is rejected; as a signed-in user, confirm a cycle runs.

**Acceptance Scenarios**:

1. **Given** the in-process scheduler flag is disabled, **When** the schedule would elapse,
   **Then** no autonomous cycle runs (no external component exists that could trigger one).
2. **Given** the on-demand "run now" endpoint, **When** it is called without a valid user
   session, **Then** it is rejected; **When** called by a signed-in user, **Then** a cycle
   runs — and in both cases only a *pre-configured* directive can be selected, never an
   arbitrary free-form prompt.
3. **Given** the system runs in a deployed environment, **When** cycles run, **Then** no
   credential, key, or connection string appears in logs, run records, or responses.

### User Story 6 - All Users Can See and Ask the Autonomous Agent (Priority: P2)

As any authenticated user, I want to see what the autonomous "duty officer" is and what it has
been doing, and to ask it questions in the app, so the autonomous agent is transparent and
approachable rather than a hidden background process.

**Why this priority**: Transparency and access build trust in an agent that acts on its own.
This depends on the cycle, audit trail, and directive listing existing first (US1–US4), then
surfaces them to every user.

**Independent Test**: As a non-admin user, open the Duty Officer page and confirm the enabled
status, standing orders, and recent run history are visible (runs expandable to details), then
send a chat message to the duty officer agent and receive a response.

**Acceptance Scenarios**:

1. **Given** any authenticated user (no admin role), **When** they open the Duty Officer page,
   **Then** they see the master enabled status, the configured standing orders (no secrets),
   and the recent activity audit trail (most-recent-first).
2. **Given** the activity list, **When** the user expands a run, **Then** they see its
   response text, tool count, token usage, and notification status — with no secrets.
3. **Given** the Duty Officer page, **When** the user asks a question in the chat panel,
   **Then** a session runs against the directive's agent profile and the response streams back
   like any other chat.

### Edge Cases

- **Overlapping cycles / multiple instances**: a slot comes due while the previous cycle is
  still running, or two backend instances see the same slot. A per-(directive, slot) Cosmos
  lease makes execution at-most-once: the slot is claimed atomically and any duplicate is
  skipped, so run history is never double-counted.
- **Agent/dependency throttling (429) or transient failure** during a cycle: the cycle must
  be recorded as a failure with a reason and must not leave a half-written run record.
- **Directive references a profile that no longer exists** or is misconfigured: the cycle
  must fail cleanly with a recorded reason rather than crash the trigger.
- **No directives enabled / empty configuration**: a timer fire must be a well-defined no-op
  that records nothing harmful, not an error loop.
- **Long-running directive exceeds the trigger's time budget**: the system must handle the
  timeout gracefully and record the outcome rather than hang.
- **Backend unreachable** when the timer fires: the trigger must surface/record the
  reachability failure and not silently drop the cycle.
- **Memory growth**: unattended cycles accumulate conversation history and run records
  indefinitely; the design must define how autonomous memory is scoped so it does not grow
  without bound or pollute interactive users' history.
- **Unauthenticated or replayed trigger calls**: must be rejected.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST run an in-process scheduler in the agent backend that, on a
  configurable recurring schedule (per directive), initiates an autonomous agent cycle
  without any human interaction.
- **FR-002**: The scheduler MUST run inside the existing agent backend process (no separate
  deployable unit) and MUST be independently enable/disable-able via configuration so it can
  be turned off (e.g., locally) without affecting the interactive web application.
- **FR-003**: An autonomous cycle MUST invoke the existing agent backend to execute a
  configured standing directive (an agent profile plus an instruction) and capture the
  agent's complete response.
- **FR-004**: Autonomous cycles MUST reuse the same agent runtime, tool surface, and durable
  memory as the interactive experience; the feature MUST NOT fork or duplicate the core
  agent-execution logic.
- **FR-005**: The system MUST allow an operator to trigger an autonomous cycle on demand
  (manual invocation) in addition to the scheduled timer.
- **FR-006**: The system MUST persist a durable, auditable run record for every autonomous
  cycle, including at minimum: directive identifier, agent profile, start and finish time,
  status (success/failure), the agent's response, the tools/actions invoked, token usage,
  and a failure reason when applicable.
- **FR-007**: The system MUST expose a way to retrieve autonomous run history, returned
  most-recent-first, that survives backend restarts.
- **FR-008**: The system MUST deliver each completed cycle's result to a notification sink;
  it MUST provide a safe default sink (durable record + log) that requires no external
  dependency, and MUST support an external destination when one is configured.
- **FR-009**: Failure to deliver to an external notification destination MUST NOT cause the
  cycle to be lost; the run MUST still be recorded and the delivery failure captured.
- **FR-010**: Operators MUST be able to define one or more directives, each specifying its
  identifier, target agent profile, instruction, schedule/cadence intent, enabled state, and
  notification routing.
- **FR-011**: The system MUST allow autonomous mode to be disabled so that no autonomous
  cycles execute, and a disabled or empty configuration MUST result in a safe no-op rather
  than an error.
- **FR-012**: The on-demand "run now" endpoint MUST require a normal authenticated user
  session (the same auth as the rest of the API) and MUST reject unauthenticated calls
  outside local development. The scheduled path runs in-process and exposes no external
  trigger endpoint.
- **FR-013**: Both the scheduler and the on-demand run endpoint MUST only execute
  pre-configured directives; neither MUST accept or forward an arbitrary free-form prompt
  from an untrusted source.
- **FR-014**: Autonomous activity (conversation history and run records) MUST be attributed
  to a distinct, non-human system identity so it is isolated from and does not pollute
  interactive users' conversation histories.
- **FR-015**: Credentials, keys, and connection strings used by the trigger or backend MUST
  never appear in logs, run records, API responses, or any client bundle.
- **FR-016**: A single autonomous cycle MUST be self-contained: a failure mid-cycle MUST be
  recorded as a failed run without leaving partially written or inconsistent audit state.
- **FR-017**: The system MUST guarantee at-most-once execution per scheduled slot, including
  when the backend runs on multiple instances, via a durable Cosmos lease keyed by
  (directive, slot); a slot already claimed (or already handled by this instance) MUST be
  skipped so run history is never duplicated or corrupted.
- **FR-018**: All deployed Azure endpoints used by this feature MUST target the Azure
  Government cloud, consistent with the rest of the platform.
- **FR-019**: All Azure resources this feature needs (notably the Cosmos `autonomous-runs`
  audit container and the `autonomous-leases` scheduler-lease container) MUST be provisioned
  through the project's infrastructure-as-code; the scheduler reuses the backend's existing
  identity and Cosmos access (no new compute or identity).
- **FR-020**: New backend dependencies MUST be added via `uv`, consistent with project
  package-management rules. (The feature adds no separate deployment unit, and therefore no
  second dependency manifest.)
- **FR-021**: The autonomous capability MUST be designed so it can later be extended to the
  full triage workflow (signal ingestion, classification against a CCIR matrix, human
  approval cards) without re-architecting the trigger, audit, or notification seams.

### Key Entities *(include if feature involves data)*

- **Directive (Standing Order)**: A pre-defined unit of autonomous work. Key attributes:
  identifier, target agent profile, the instruction the agent is asked to perform, cadence
  intent (how often), enabled flag, and notification routing. The set of directives is the
  operator-controlled definition of "what the autonomous agent does."
- **Autonomous Run (Audit Record)**: One execution of a directive. Key attributes: run
  identifier, directive identifier, agent profile, start/finish timestamps, status, the
  agent's response text, tools/actions invoked, token usage, and failure reason. Durable and
  queryable; the system's tamper-evident memory of autonomous behavior.
- **System Identity (Autonomous Duty Officer)**: The non-human identity that owns autonomous
  conversations and run records, keeping them isolated from interactive users.
- **Notification Sink**: The destination that receives a completed cycle's output for human
  review. Has a safe default (durable + logged) and an optional external channel.
- **In-Process Scheduler**: A background loop inside the agent backend that wakes on a poll
  interval, determines which directives are due per their schedule, and runs the cycle
  directly (no HTTP hop). Gated by a config flag so it can be disabled (e.g., locally).
- **Scheduler Lease**: A durable, self-expiring Cosmos document keyed by (directive, slot)
  that the scheduler atomically creates to claim a scheduled slot, guaranteeing at-most-once
  execution across backend instances.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With autonomous mode enabled and a directive configured, an unattended cycle
  executes the directive and produces a completed agent response on schedule in 100% of
  manual verification attempts, with no human typing the prompt.
- **SC-002**: Every autonomous cycle (success or failure) produces exactly one durable run
  record; across a test of at least 10 cycles, 100% are retrievable most-recent-first and
  remain present after a backend restart.
- **SC-003**: When an external notification destination is configured, 100% of completed
  cycles deliver their output (or, on delivery failure, still record the run and capture the
  delivery error); with no destination configured, 100% of cycles still complete and are
  logged.
- **SC-004**: With autonomous mode disabled, 0 cycles execute on the timer over the
  observation window.
- **SC-005**: With the scheduler flag disabled, 0 cycles run; and 100% of on-demand "run now"
  calls made without a valid user session are rejected (0 cycles from unauthenticated calls).
- **SC-006**: No credential, key, or connection string appears in any log line, run record,
  or API response (verified by inspection).
- **SC-007**: Autonomous conversations and run records are attributed to the system identity
  and never appear in any interactive user's conversation list (verified across at least two
  test identities).
- **SC-008**: The offline automated test suite validates the autonomous cycle, audit
  recording, notification routing, and authentication using in-memory doubles — with no live
  cloud dependency — and passes.

## Assumptions

- The existing agent backend (agent runtime, tools, durable Cosmos memory) is the single
  source of agent execution; autonomous mode invokes it rather than reimplementing it.
- A reasonable default directive uses an existing agent profile (e.g., a senior
  coordinating profile such as Chief of Staff) so the feature is demonstrable out of the box;
  operators can change it.
- The "action" the agent takes is expressed as a natural-language standing instruction in
  the directive; deep, structured triage steps (mailbox parsing, CCIR-matrix RAG, approval
  cards) are future extensions layered on this seam, not part of this slice.
- No service-to-service channel is required: the schedule runs in the backend process, so the
  only authenticated entry point is the existing user-session API (the on-demand "run now").
- The notification "external destination" is an outbound webhook-style endpoint (e.g., a
  Teams incoming webhook or a Logic App) supplied by configuration; the specific downstream
  formatting (Adaptive Cards) is a future extension.
- Autonomous memory is scoped to the system identity and is acceptable to retain for audit;
  long-term retention/rotation policy is out of scope for this slice.
- Local development and the automated unit suite run without any live cloud account, using
  the project's existing in-memory test doubles and the Cosmos emulator where durability is
  exercised.

## Out of Scope

- The full CCIR triage pipeline: mailbox/portal ingestion, signal preprocessing,
  retrieval-augmented classification against the CCIR matrix / MIRPs / RCAs, and routing
  decisions. This feature provides the trigger/audit/notification seams those will plug
  into, not the pipeline itself.
- Teams Adaptive Card authoring and the interactive approve/deny workflow (the human
  decision UI). This slice delivers output to a review sink; the approval UX is a later
  feature.
- Email/Exchange and Bot Service integrations for sending approved notifications.
- A frontend admin screen for editing directives in the web UI (directives are
  configuration-defined in this slice; a UI editor is a potential future enhancement).
- Vector/semantic search over autonomous run history.
- Autonomous retention, archival, or rotation policies for accumulated run records and
  conversation history.
- Multi-tenant or per-customer scheduling beyond the single deployment's configured
  directives.
