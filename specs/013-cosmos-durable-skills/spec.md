# Feature Specification: Durable Cosmos-Backed Skills

**Feature Branch**: `013-cosmos-durable-skills`  
**Created**: 2026-06-19  
**Status**: Draft  
**Input**: User description: "add the skills and skill builders into Cosmos durably like you did with the agents memories and automations"

## Overview

Today, agent **skills** (the progressive-disclosure `SKILL.md` capabilities surfaced in the
admin **Skill Builder**) live only on the backend's **local filesystem** under `skills/`. The
`SkillManager` reads and writes `SKILL.md` files directly, and agents load them through the
Agent Framework's `FileSkillsSource`. This is the same fragility the agent **memory** layer
(feature 011) and the autonomous **directive** store (feature 012) already eliminated: anything
written to the container's local disk is **ephemeral** — a redeploy, scale-out, or restart wipes
every skill an operator created or edited through the Skill Builder, and a second backend
instance never sees skills created on the first.

This feature moves skills to **Azure Cosmos DB** as the durable, shared source of truth, exactly
mirroring the autonomous directive pattern: the repository's `skills/` directory **seeds the
defaults** at startup (idempotent), but **Cosmos is the runtime store** for every create, edit,
and delete. Agents load their selected skills from Cosmos at run time. The Skill Builder's REST
contract is unchanged — only the storage tier moves — so the frontend is untouched.

## Clarifications

### Session 2026-06-19

- Q: Are skills global or per-user? → A: **Global** operational config (like autonomous
  directives), partitioned by `/id`. Skills are authored by operators in the admin Skill Builder
  and shared across all users and backend instances. (Custom *agents* remain per-user; skills do
  not.)
- Q: What happens to the `skills/` directory? → A: It remains as the **seed source** of default
  skills (e.g. `table-usage`). At startup, defaults are upserted into Cosmos only for ids not
  already present, so operator edits persist and brand-new repo defaults appear after deploy. A
  default deleted at runtime reappears on the next startup (delete it from the repo to retire it
  permanently) — identical semantics to the directive seeding.
- Q: Any non-durable fallback when Cosmos is unconfigured? → A: **No.** Consistent with features
  011/012, the backend requires Cosmos (emulator locally, real account deployed). There is no
  in-memory or filesystem write fallback for runtime skill storage.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Created Skills Survive Restarts and Redeploys (Priority: P1)

As an operator using the Skill Builder, I want a skill I create or edit to persist permanently —
across backend restarts, redeploys, and scale-out — so the capabilities I author are never lost
and are visible to every backend instance.

**Why this priority**: Durability is the entire point of the feature. Without it, every other
behavior (building, agent consumption, seeding) is writing to disposable storage.

**Independent Test**: Create a new skill through the Skill Builder, restart the backend process
(or simulate a fresh container with an empty local `skills/` directory), and confirm the skill is
still listed and fully readable. Its content was read back from Cosmos, not from local disk.

**Acceptance Scenarios**:

1. **Given** an operator creates a skill via the builder, **When** the backend process restarts,
   **Then** the skill still appears in the skills list with its original description and content.
2. **Given** a deployed environment with multiple backend instances, **When** instance A creates
   a skill, **Then** instance B lists and serves that same skill without a redeploy.
3. **Given** a fresh container whose local `skills/` directory contains only repo defaults,
   **When** it starts against the existing Cosmos account, **Then** previously authored skills are
   present (durable in Cosmos), not just the on-disk defaults.

---

### User Story 2 - Skill Builder CRUD Is Durable (Priority: P1)

As an operator, I want create, read, update, and delete in the Skill Builder to write through to
durable storage, so the builder is a real management surface rather than a scratchpad that resets.

**Why this priority**: The builder is the primary human entry point. Its operations must be the
authoritative, durable mutations of the skill catalog.

**Independent Test**: Through the existing `/api/skills` endpoints, create, fetch, update, and
delete a skill; confirm each operation is reflected on a subsequent read served from Cosmos, and
that the wire shapes (`{name, description, content}`) are byte-for-byte what the frontend already
consumes.

**Acceptance Scenarios**:

1. **Given** a `POST /api/skills` with a valid name/description/content, **When** it succeeds,
   **Then** a subsequent `GET /api/skills/{name}` returns the stored skill from Cosmos.
2. **Given** an existing skill, **When** an operator updates its description/content, **Then** the
   change is persisted and returned on the next read, and the skill's creation time is preserved.
3. **Given** an existing skill, **When** an operator deletes it, **Then** it no longer appears in
   the list and a direct fetch returns not-found.
4. **Given** a create for a name that already exists, **When** it is processed, **Then** it is
   rejected as a conflict (no silent overwrite).
5. **Given** invalid input (bad name, empty/oversized description or content), **When** submitted,
   **Then** it is rejected with a validation error and nothing is written.

---

### User Story 3 - Agents Load Their Skills From Cosmos (Priority: P1)

As a user chatting with an agent that has skills attached, I want the agent to load those skills'
instructions at run time from the durable store, so agent behavior reflects the current, shared
skill catalog regardless of which backend instance serves the request.

**Why this priority**: Skills exist to shape agent behavior. If agents cannot load the
Cosmos-stored skills, the durable catalog is inert.

**Independent Test**: Attach a skill to an agent profile (or custom agent), start a conversation,
and confirm the agent advertises and can load that skill's content — sourced from Cosmos — and
that requesting an unknown skill name simply advertises nothing (no error).

**Acceptance Scenarios**:

1. **Given** an agent configured with skill `table-usage`, **When** a session is created, **Then**
   the agent advertises that skill and can load its body, retrieved from Cosmos.
2. **Given** a custom agent built with a set of skills, **When** it runs, **Then** only its
   selected skills are advertised (filtering is preserved).
3. **Given** an agent referencing a skill name that does not exist in Cosmos, **When** the session
   is created, **Then** no error occurs and the unknown skill is silently omitted.
4. **Given** a skill edited through the builder, **When** a *new* session is started afterward,
   **Then** the agent loads the updated content.

---

### User Story 4 - Default Skills Are Seeded From the Repository (Priority: P2)

As a developer, I want the repository's `skills/` directory to seed default skills into Cosmos at
startup without clobbering operator edits, so a clean environment comes up with the expected
built-in skills while authored skills remain authoritative.

**Why this priority**: Seeding delivers the out-of-the-box experience and a migration path from
the filesystem, but it depends on the durable store (US1) existing first.

**Independent Test**: Start the backend against an empty Cosmos skills container and confirm the
repo's default skills appear; edit one, restart, and confirm the edit survives (the default does
not overwrite it); confirm a brand-new repo default is added on the next startup.

**Acceptance Scenarios**:

1. **Given** an empty Cosmos skills container, **When** the backend starts, **Then** each default
   skill from `skills/` is created in Cosmos exactly once.
2. **Given** a default skill that was edited at runtime, **When** the backend restarts, **Then**
   the seeding step leaves the edited version untouched.
3. **Given** a new default skill added to the repo, **When** the backend restarts, **Then** it is
   seeded into Cosmos; existing skills are not duplicated.

---

### User Story 5 - Works Locally With the Cosmos Emulator (Priority: P3)

As a developer, I want skills to use the Cosmos emulator locally and in-memory doubles in the unit
suite, with no silent non-durable fallback, so iteration is fast and tests are deterministic while
behaving exactly like production.

**Why this priority**: Developer experience and testability matter, but production durability (P1)
is what delivers user value.

**Independent Test**: With the emulator running, exercise skill CRUD and agent skill-loading and
confirm durable persistence; with Cosmos unconfigured, confirm the backend fails fast (no
fallback); run the offline unit suite and confirm skill behavior is validated with in-memory
doubles.

**Acceptance Scenarios**:

1. **Given** the emulator is running and `AZURE_COSMOS_ENDPOINT` points at it, **When** the backend
   starts, **Then** skills persist durably (same behavior as production).
2. **Given** no Cosmos is configured, **When** the backend starts, **Then** it fails fast with a
   clear error — there is no non-durable skill fallback.
3. **Given** the offline unit suite, **When** it runs, **Then** skill CRUD, seeding, agent
   loading, and validation are covered with in-memory Cosmos doubles and no live dependency.
4. **Given** the local emulator is running, **When** the `emulator`-marked suite runs, **Then**
   skill persistence and CRUD are verified against the real provider and container; **When** the
   emulator is not running, **Then** those tests are skipped and the default suite still passes.

### Edge Cases

- A skill whose name collides with an existing id: create must conflict (409); seeding must skip
  (no duplicate, no overwrite).
- A skill name that is invalid per the spec (uppercase, leading/trailing/consecutive hyphens, >64
  chars): rejected at the validation boundary before any write.
- Description or content exceeding limits: rejected; nothing partially written.
- Cosmos temporarily unavailable or rate-limited (429): CRUD and list operations surface a clear,
  retryable error and must not partially persist a skill.
- An agent references a skill that was deleted: agent creation must not error; the skill is simply
  not advertised.
- A default skill deleted at runtime: it is allowed (delete succeeds) but reappears on next
  startup because it is a repo default — to retire it permanently, remove it from `skills/`.
- The `skills/` directory is absent or empty at startup: seeding is a no-op; Cosmos remains the
  source of truth and the catalog is whatever already lives there.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Skills MUST be stored in Azure Cosmos DB as the durable runtime source of truth,
  partitioned by skill id, in a dedicated container, reusing the application's shared Cosmos client.
- **FR-002**: The Skill Builder REST surface (`GET /api/skills`, `GET/POST/PUT/DELETE
  /api/skills/{name}`, `POST /api/skills/generate`) MUST be preserved with identical request and
  response shapes; only the storage tier changes (frontend untouched).
- **FR-003**: Create MUST reject a duplicate skill id with a conflict and MUST validate name,
  description, and content at the boundary before writing.
- **FR-004**: Update MUST persist description/content changes durably while preserving the skill's
  original creation timestamp; delete MUST remove the skill from the durable store.
- **FR-005**: Agents MUST load their selected skills' content from Cosmos at run time, preserving
  name-based filtering and the silent omission of unknown skill names.
- **FR-006**: At startup the backend MUST seed default skills from the repository `skills/`
  directory into Cosmos idempotently — creating only ids not already present, never overwriting
  existing (possibly edited) skills.
- **FR-007**: The backend MUST require Cosmos to be configured (emulator locally, real account
  deployed) and MUST NOT provide a non-durable in-memory or filesystem write fallback for runtime
  skill storage.
- **FR-008**: The new Cosmos container MUST be declared as infrastructure-as-code (Terraform),
  consistent with the existing Cosmos containers.
- **FR-009**: Skill operations MUST NOT emit secrets or credentials in logs, responses, or stored
  documents.
- **FR-010**: The offline unit suite MUST validate skill CRUD, seeding, agent loading, and
  validation using in-memory Cosmos doubles; an `emulator`-marked suite MUST verify the real
  repository and container, and MUST be skipped when the emulator is unavailable.

### Key Entities

- **Skill**: A global, operator-authored capability. Identity is its `name` (lowercase letters,
  numbers, hyphens; ≤64 chars). Attributes: `description` (short summary advertised to agents) and
  `content` (the `SKILL.md` body / instructions). Storage bookkeeping: creation and update
  timestamps. Partitioned by id; not scoped to any user.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A skill created through the builder is still present and readable after a backend
  restart and on a fresh container with an empty local `skills/` directory (100% of created skills
  survive restart).
- **SC-002**: Skill create/read/update/delete through the existing endpoints reflect durably on a
  subsequent read served from Cosmos, with unchanged wire shapes.
- **SC-003**: An agent attached to a Cosmos-stored skill advertises and loads that skill's current
  content; unknown skill names cause no error.
- **SC-004**: Starting against an empty container seeds every repo default exactly once; restarting
  after an edit preserves the edit (no overwrite, no duplicates).
- **SC-005**: With Cosmos unconfigured, the backend fails fast; with the emulator, skills persist;
  the offline unit suite passes with doubles and the emulator suite passes against the emulator.

## Assumptions

- Skills are global operational configuration, authored by trusted operators in the admin Skill
  Builder, and are not per-user data. (Per-user *custom agents* are out of scope and unchanged.)
- **Authorization model (accepted, not introduced by this feature):** The skill CRUD endpoints are
  gated by the same authenticated-user check (`get_current_user`) as the rest of the admin surface
  (custom agents, agent customizations, autonomous directives). The application currently has no
  role/claim distinction, so **every authenticated user is treated as a trusted operator**. Because
  this feature makes skills *durable and shared fleet-wide* (instead of ephemeral per-instance), and
  a skill's `content` is injected as agent instructions for any user who selects it, operator trust
  is a precondition. Adding role-based authorization to the whole admin surface is a separate,
  cross-cutting concern deliberately kept out of this storage-migration feature so skills are not
  gated inconsistently with the sibling admin endpoints.
- The `skills/` directory continues to exist in the repository as the seed source of default
  skills; it is no longer the runtime read/write store.
- The Agent Framework's skills provider invokes its source's `get_skills()` lazily in an async
  context during agent runs, allowing a Cosmos-backed source to be constructed synchronously and
  fetched lazily.
- Skill catalog volume is small (tens of skills), so a "list all" read is a cheap query and point
  reads/writes are partition-scoped by id.
