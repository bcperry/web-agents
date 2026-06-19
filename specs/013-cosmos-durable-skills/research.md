# Phase 0 Research: Durable Cosmos-Backed Skills

## R1 — Partition strategy: global `/id` (mirror autonomous directives)

**Decision**: Store skills in a dedicated `skills` container partitioned by `/id`, where the id is
the skill name. Skills are global operator config — not per-user.

**Rationale**: Skills are authored in the admin Skill Builder and shared by all users and agents,
exactly like autonomous **directives** (feature 012), which use `/id`. The catalog is small (tens
of skills), so the dominant "list all" read is a cheap cross-partition query and point
reads/writes are partition-scoped by id. Per-user partitioning (as used for custom *agents*) is
inappropriate because skills are not user-scoped.

**Alternatives considered**:
- `/user_id` partition (like `custom-agents`) — rejected: skills are not per-user; this would
  fragment a shared catalog and complicate agent loading.
- A single document holding all skills — rejected: contention on every edit, and a 2 MB item cap
  that a growing catalog could approach.

## R2 — Agent loading: `CosmosSkillsSource` with lazy async `get_skills()`

**Decision**: Implement `CosmosSkillsSource(SkillsSource)` whose async `get_skills()` reads all
skill docs from the Cosmos repo and constructs `InlineSkill` objects
(`SkillFrontmatter(name, description)` + `instructions=content`). `_build_skills_provider()` stays
**synchronous**: it constructs `FilteringSkillsSource(CosmosSkillsSource(), predicate=...)` and
wraps it in a `SkillsProvider`. The Cosmos fetch happens **lazily** when the Agent Framework calls
`get_skills()` during an agent run (an async context).

**Rationale**: The Agent Framework's `SkillsProvider` invokes its source's `get_skills()` lazily
and **caches per provider instance** (verified in `agent_framework/_skills.py`). A new provider is
built per agent/session, so each session sees a consistent snapshot and a new session picks up the
latest edits — identical semantics to the current `FileSkillsSource` (which also re-reads per
provider). Keeping `_build_skills_provider()` synchronous means **no new async threading** through
the agent construction call chain; the existing sync `create_agent` path is preserved.

**Alternatives considered**:
- Materialize Cosmos skills into a temp directory and keep `FileSkillsSource` — rejected: extra
  disk I/O, cleanup, and a second copy of the source of truth; defeats the durability goal.
- Pre-fetch skill docs in the async orchestration layer and thread them into `create_agent` —
  rejected: threads a new parameter through several layers for no benefit over a lazy source.
- `InMemorySkillsSource([...])` built eagerly at provider-construction — rejected: construction is
  synchronous, so it cannot `await` the Cosmos fetch there.

## R3 — Seeding: filesystem `skills/` as idempotent default source

**Decision**: Add `seed_skills()` mirroring `seed_autonomous_directives()`. At startup it parses
the repo `skills/` directory (via the Agent Framework `FileSkillsSource` / existing `SkillManager`
parse) and **upserts only ids not already present** in Cosmos. Called from the FastAPI lifespan.

**Rationale**: Provides the out-of-the-box experience and a migration path from the filesystem
while ensuring operator edits persist (existing ids are never overwritten). A repo default deleted
at runtime reappears on the next startup — identical, well-understood semantics to directive
seeding. To retire a default permanently, remove it from `skills/`.

**Alternatives considered**:
- One-time migration script — rejected: less robust than idempotent startup seeding; would not
  re-add new repo defaults after deploy.
- No seeding (empty catalog on fresh deploy) — rejected: loses built-in skills like `table-usage`
  that profiles in `agents.yaml` reference.

## R4 — `SkillManager`: retain validation, swap storage

**Decision**: Keep `SkillManager` as the business/validation layer but back it with the Cosmos
repo. Its methods become `async`. Retain name validation (`^[a-z0-9][a-z0-9-]*$`, ≤64 chars),
description (≤256) and content (≤65536) checks, and the create-conflict (409) behavior. Drop the
filesystem-only path-traversal guard (no longer relevant — the id is a validated partition key).

**Rationale**: The validation is good and matches the Agent Framework skill-name rules; only the
storage mechanism is ephemeral. Keeping the class boundary minimizes churn in `main.py` endpoints
(they keep calling `SkillManager`, now awaiting it).

## R5 — No non-durable fallback (consistency with 011/012)

**Decision**: Skills require Cosmos (emulator locally, real account deployed). There is no
in-memory or filesystem **write** fallback for runtime skill storage. The existing
`require_cosmos_configured()` startup gate already enforces Cosmos presence.

**Rationale**: Consistent with the agent-memory and autonomous features. A silent non-durable
fallback would reintroduce exactly the data-loss class this feature eliminates.

## R6 — Testing: in-memory double seeded from filesystem defaults

**Decision**: Add `InMemorySkillRepository` to `tests/_doubles.py` mirroring the Cosmos repo
interface (list/get/create/upsert/delete keyed by id). The autouse `_cosmos_doubles` fixture
injects it, **seeded from the filesystem defaults** (parse the `skills/` directory) so offline
reads return the built-in skills — mirroring the production startup seed. Add a
`@pytest.mark.emulator` suite for the real repository CRUD.

**Rationale**: Matches the established directive-double pattern (`InMemoryAutonomousDirectiveRepository`
seeded from YAML). Keeps the offline suite deterministic and loop-independent, with the real
provider covered by the emulator suite. `uv` only; never pip.
