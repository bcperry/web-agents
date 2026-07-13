# Phase 0 Research: Agent Creation Tools

## R1 - Tool discovery must be independent of default profile grants

**Decision**: Introduce a small backend function-tool registry used by `/api/tools`, strict tool-name
validation, and `build_tool_instances`. Register `create_skill` and `create_agent` there, but do not
add either name to any profile or custom-agent default.

**Rationale**: `/api/tools` currently discovers only names already present in `agents.yaml`. That
cannot advertise a new optional tool without granting it to an existing profile. A registry makes
availability explicit while saved profile/custom-agent tool lists remain the grant boundary.

**Alternatives considered**:
- Add both names to a hidden or existing YAML profile: rejected because it creates an implicit grant
  and violates the single-file profile semantics.
- Hard-code only the two names in the route: rejected because inventory, validation, and runtime
  construction could drift.

## R2 - Bind ownership in closure factories, never in model-visible input

**Decision**: Follow `build_user_profile_tools(user_id)`: construct `create_skill` and
`create_agent` closures only after authentication, capture the immutable `user_id`, and expose no
owner/user/tenant parameter in either function signature.

**Rationale**: `session_orchestration._resolve_runtime_dependencies` already passes the authenticated
user to `build_tool_instances` for parents and built-in sub-agents. Closure binding makes every
existence check, capability lookup, and write owner-scoped by construction.

**Alternatives considered**:
- Accept `user_id` as a tool argument: rejected because a model could redirect writes.
- Call management HTTP routes with a bearer token: rejected because it duplicates transport/auth
  concerns, complicates tests, and bypasses owning Python abstractions.

## R3 - Shared creation services own strict validation and persistence

**Decision**: Add `definition_creation.py` with typed request/result models and two services. The
services invoke reusable skill/custom-agent validators, resolve capabilities for the bound user,
and call repositories directly. Runtime tools map expected exceptions to stable result objects;
management routes map the same failures to HTTP responses.

**Rationale**: Skill validation already lives in `SkillManager`, but custom-agent management writes
currently upsert raw JSON while session creation performs validation. A shared business layer is the
smallest way to make tool and management creation equivalent without one calling the other's route.

**Alternatives considered**:
- Put all logic inside tool closures: rejected because management and tool behavior would diverge.
- Reuse `_create_custom_chat_session` directly: rejected because it creates a runtime/conversation,
  silently drops stale skills, and mixes validation with MCP connections.

## R4 - Creation validation is strict; session loading remains compatible

**Decision**: Extract capability validation into a strict mode for saved creation/update and retain
the current tolerant mode only when starting a previously saved session definition. Strict mode
rejects unknown tools, skills, delegated agents, malformed/unsafe MCP servers, cycles, and invalid
temperature instead of dropping or rewriting entries.

**Rationale**: FR-009 requires strict creation while FR-020 protects existing saved agents whose
referenced skill was later deleted. These are different lifecycle operations and should call a
shared validator with explicit policy rather than accidental route-specific behavior.

**Alternatives considered**:
- Make all resolution strict: rejected because it breaks the existing stale-skill compatibility
  regression tests.
- Keep management writes unvalidated: rejected because tool creation would not match the
  management flow and invalid definitions would remain durable.

## R5 - Atomic owner-scoped create belongs in the repository

**Decision**: Add `create(user_id, item_id, data)` to `CosmosUserScopedRepository` using Cosmos
`create_item`, with `id=item_id` and partition key `user_id`. Use it for runtime create-only custom
agents and user skills; keep `upsert` for explicit management updates.

**Rationale**: A pre-read followed by upsert races. Cosmos create is atomic within the owner
partition, permits the same id in different user partitions, and raises a duplicate conflict for
exactly one concurrent loser.

**Alternatives considered**:
- Read then upsert: rejected because two concurrent calls can both report success and overwrite.
- Transactional batch: rejected because a single-item create already provides the required
  guarantee.

## R6 - User-owned skills require a separate `/user_id` container

**Decision**: Add a `user-skills` container through Terraform and expose it via the generic
`CosmosUserScopedRepository`. Store bare skill data inside the established wrapper. Keep global
skills in the existing `/id` container and reserve their names during user creation.

**Rationale**: Global and owner-scoped data have different partition/access patterns. A dedicated
container keeps point operations partition-scoped, avoids a shared unpartitioned record and 2 MB
item growth, and reuses the custom-agent storage abstraction.

**Alternatives considered**:
- Add `user_id` variants to the global skills container: rejected because the container partition
  key is `/id`, making owner queries cross-partition and id semantics ambiguous.
- One skill-catalog item per user: rejected because updates contend and catalog growth is capped by
  Cosmos's 2 MB item limit.

## R7 - Skill resolution is a global-plus-owner overlay with no shadowing

**Decision**: Add an owner-aware catalog abstraction that lists/resolves global skills plus only the
current user's skills. Reject user skill creation when the name exists in either set. Thread the
bound user into runtime `CosmosSkillsSource`, including built-in sub-agent resources.

**Rationale**: This satisfies user isolation and keeps existing global skills available. Since
global names are reserved, resolution is deterministic and does not need precedence rules.

**Alternatives considered**:
- User skills shadow globals: rejected because it changes built-in agent behavior and creates
  ambiguous references.
- Load all user skills then filter in memory: rejected because it exposes cross-partition data to
  application logic and violates isolation by design.

## R8 - Tool outcomes are bounded typed data, not exception text

**Decision**: Return a discriminated Pydantic-compatible object for created/error outcomes. Map
validation, duplicate, unauthorized, and storage failures to stable codes and retryability. Log only
kind, safe requested identity, code, and exception class; never raw payloads/provider diagnostics.

**Rationale**: Model-mediated calls need predictable machine-readable results, and the spec forbids
content, owner identifiers, secrets, and raw diagnostics in both output and logs.

**Alternatives considered**:
- Return strings: rejected because callers cannot reliably distinguish outcomes.
- Let exceptions escape: rejected because framework/provider messages can leak internals and do not
  provide the required stable contract.

## R9 - Focus tests at ownership and lifecycle boundaries

**Decision**: Unit-test services with in-memory repositories, tool closures independently, exact
runtime grants, strict capability failures, combined skill catalogs, and sanitized storage errors.
Use emulator tests for real partition isolation and concurrent create conflicts.

**Rationale**: The highest risks are authority expansion, race-driven overwrite, validator drift,
and cross-user leakage. Existing test doubles already mirror the relevant repository interfaces;
the emulator is reserved for Cosmos semantics the double cannot prove.

**Alternatives considered**:
- Only end-to-end model tests: rejected because nondeterminism obscures business-layer failures.
- Only repository unit tests: rejected because they cannot prove grant wiring and result contracts.