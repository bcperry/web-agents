# Tasks: Durable Cosmos-Backed Skills

**Input**: Design documents from `/specs/013-cosmos-durable-skills/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/skills-api.md

**Tests**: Included. This repository has an established offline pytest suite with in-memory Cosmos
doubles; tests are part of "done".

**Organization**: Tasks are grouped by user story so each slice is independently implementable and
testable. Priorities: US1 (P1), US2 (P1), US3 (P1), US4 (P2), US5 (P3).

> **Status: COMPLETE.** All phases implemented and verified — offline suite 293 passed (the only
> failure, `test_prompt_tools_yaml::test_each_profile_has_required_fields`, is pre-existing and
> unrelated: feature 012's `chief-of-staff` profile is missing from that test's allow-list on
> `main`; `agents.yaml`/that test were untouched here). Emulator suite 12 passed (incl. the new
> real `CosmosSkillRepository` CRUD). Terraform validates. A code-review pass was applied: the
> skills container is fully wired through Terraform like the directive store, seeding now requires
> a description (matching the create/update contract), a `_skill_name` helper removes duplication,
> and the accepted authorization/trust model is documented in the spec.
>
> **Repository consolidation (deeper review pass):** the per-container Cosmos repos now share a
> `_CosmosContainer` base (the create-database/container bootstrap was copy-pasted across 5
> classes), and the two identical `/id` stores (autonomous directives + skills) collapsed into one
> generic `_CosmosByIdRepository` with `list_all/get/create/upsert/delete` (the per-user analogue is
> `user_data.CosmosUserScopedRepository`). The two in-memory doubles merged into one
> `InMemoryByIdRepository`. Net −112 lines, behavior preserved (full suite still green).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- File paths are repository-root-relative (this repo is flat: backend modules at root, `infra/`,
  `skills/`, `tests/`)

## Path Conventions

- Backend (agent host): root-level Python modules (`cosmos_memory.py`, `skills_manager.py`,
  `agent_factory.py`, `validators.py`, `session_orchestration.py`, `main.py`)
- Seed source: `skills/` directory (default `SKILL.md` skills)
- Infrastructure: `infra/modules/cosmos/` (Terraform — one new container)
- Tests: `tests/`

---

## Phase 1: Setup

- [ ] T001 [P] Confirm no new dependencies are required (`agent-framework`, `azure-cosmos` already
  present); reserve `AZURE_COSMOS_SKILLS_CONTAINER` (default `skills`) as the container env var
  name. No `pyproject.toml` change expected. (uv only — never pip.)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The durable store + test doubles every user story depends on.

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete.

- [ ] T002 [US-shared] Add `CosmosSkillRepository` to `cosmos_memory.py` (container `skills`,
  partition `/id`) with `list_skills()`, `get_skill(name)`, `create_skill(doc)` (atomic
  create — conflict on existing id), `upsert_skill(doc)`, `delete_skill(name)`; add a module-level
  `get_skill_repository()` singleton (env `AZURE_COSMOS_SKILLS_CONTAINER`, default `skills`,
  database default `agent-memory`). Wire it into `close_cosmos()` reset. Mirror
  `CosmosAutonomousDirectiveRepository`. Doc shape per `data-model.md` (no secrets).
- [ ] T003 [P] [US-shared] Add `InMemorySkillRepository` to `tests/_doubles.py` mirroring the
  Cosmos repo interface (list/get/create/upsert/delete keyed by id, create raises on duplicate),
  loop-independent, accepting an optional `initial` list of skill docs.
- [ ] T004 [US-shared] Wire the in-memory skill repo into the autouse `_cosmos_doubles` fixture in
  `tests/conftest.py`, **seeded from the filesystem defaults** (parse `skills/`), and into
  `clear_cosmos_singletons` in `tests/_doubles.py` so unit tests never touch a real Cosmos account.

---

## Phase 3: US2 — Skill Builder CRUD Is Durable (P1)

**Goal**: Create/read/update/delete through `/api/skills*` write through to Cosmos durably.

**Independent test**: CRUD via the endpoints; each op reflects on a subsequent Cosmos-served read;
wire shapes unchanged.

- [ ] T005 [US2] Rewrite `SkillManager` (`skills_manager.py`) to be Cosmos-backed: async
  `list_summaries()`, `get(name)`, `create(name, description, content)` (409 on duplicate),
  `update(name, description, content)` (404 if absent, preserve `created_at`), `delete(name)`
  (404 if absent), backed by `get_skill_repository()`. Retain name/description/content validation;
  drop the filesystem path-traversal logic. Keep `_starter`/template helpers only if still used.
- [ ] T006 [US2] Update `main.py` skill endpoints (`GET /api/skills`, `GET/POST/PUT/DELETE
  /api/skills/{name}`) to `await` the now-async `SkillManager` methods; construct `SkillManager()`
  without a filesystem path. Leave `POST /api/skills/generate` behavior unchanged.
- [ ] T007 [P] [US2] Add `tests/test_skills_cosmos.py` covering SkillManager CRUD via the in-memory
  double: create→get→list→update(preserves created_at)→delete→404; duplicate create→409; invalid
  name/description/content→422. Add/keep `tests/test_api.py` assertions for the `/api/skills*`
  endpoints (durability + shapes).

---

## Phase 4: US4 — Default Skills Are Seeded From the Repository (P2)

**Goal**: Startup seeds repo `skills/` defaults into Cosmos idempotently without clobbering edits.

**Independent test**: empty container seeds defaults once; edit+restart preserves edit; new repo
default added on restart; no duplicates.

- [ ] T008 [US4] Add `seed_skills()` to `skills_manager.py` mirroring `seed_autonomous_directives()`:
  parse the filesystem `skills/` directory (reuse the existing `SkillManager.parse` /
  `FileSkillsSource`), and for each default whose id is **not** present in Cosmos, create it
  (`created_at = updated_at = now`). Return the seeded count. Never overwrite existing ids.
- [ ] T009 [US4] Call `seed_skills()` from the FastAPI `lifespan` in `main.py` (alongside
  `seed_autonomous_directives()`), logging the seeded count; wrap in try/except so a seed failure
  never blocks startup.
- [ ] T010 [P] [US4] Add seeding tests to `tests/test_skills_cosmos.py`: empty→seeds all defaults
  once; pre-existing edited id is left untouched; re-running seed is idempotent (no duplicates).

---

## Phase 5: US3 — Agents Load Their Skills From Cosmos (P1)

**Goal**: Agents load selected skills' content from Cosmos at run time; filtering + silent omission
of unknown names preserved.

**Independent test**: agent with `table-usage` advertises/loads it from Cosmos; unknown name → no
error; custom-agent skill subset filtered.

- [ ] T011 [US3] In `agent_factory.py`, add `CosmosSkillsSource(SkillsSource)` whose async
  `get_skills()` reads `get_skill_repository().list_skills()` and builds `InlineSkill`
  (`SkillFrontmatter(name, description)` + `instructions=content`) for each doc. Rewrite
  `_build_skills_provider(skill_names)` to wrap `FilteringSkillsSource(CosmosSkillsSource(),
  predicate=lambda s: s.frontmatter.name in selected)` in a `SkillsProvider` (return `None` when no
  names requested). Remove the `_SKILLS_DIR.is_dir()` guard and the `FileSkillsSource` import.
- [ ] T012 [US3] Update `validators.available_skill_names()` to read names from
  `get_skill_repository().list_skills()` (async, no `skills_dir` arg). Update
  `session_orchestration.py` call sites (and `SessionContext.get_skills_dir` wiring) accordingly;
  keep `filter_known_skill_names()` behavior unchanged. Keep `_get_skills_dir()` in `main.py` for
  seeding.
- [ ] T013 [P] [US3] Update `tests/test_skills.py`: `_build_skills_provider(None|[])` → `None`;
  `_build_skills_provider(["table-usage"])` → a `SkillsProvider`; add an async test asserting
  `CosmosSkillsSource.get_skills()` returns the seeded `table-usage` skill and that
  `FilteringSkillsSource` omits unknown names.

---

## Phase 6: US1 + US5 — Durability, Emulator & Infrastructure

**Goal**: Durable across restart/instances; declared in IaC; emulator-verified; no fallback.

- [ ] T014 [P] [US1] Declare the `skills` Cosmos container (partition `/id`) in
  `infra/modules/cosmos/main.tf` and add a `skills_container_name` output in
  `infra/modules/cosmos/outputs.tf`, consistent with `autonomous_directives`. (No app-service env
  var needed — code defaults to `skills`, matching the hardcoded container name.)
- [ ] T015 [P] [US5] Add a `@pytest.mark.emulator` test (`tests/test_skills_cosmos.py`) exercising
  the real `CosmosSkillRepository` CRUD against the local emulator (unique uuid skill ids,
  delete-in-finally), auto-skipped when the emulator is unreachable.
- [ ] T016 [US1] Add a durability test: create a skill via `SkillManager`, then construct a fresh
  `SkillManager` over the **same** repo instance (simulating a restart with shared durable store)
  and confirm the skill is still readable — proving reads come from the store, not process-local
  filesystem state.

---

## Phase 7: Polish & Cross-Cutting

- [ ] T017 Run the full offline suite (`uv run pytest -q`) and fix any regressions (especially any
  remaining `FileSkillsSource`/`skills_dir` references). Run `uv run pytest -q -m emulator` if the
  emulator is up.
- [ ] T018 [P] Update `README.md` / feature notes only if a skills-storage section exists and is now
  inaccurate (filesystem → Cosmos). Do not create new docs otherwise.
- [ ] T019 Code review (Code Reviewer subagent) over the diff; apply appropriate simplifications
  (remove dead filesystem code paths, inline single-use helpers, share duplicated logic) and re-run
  the suite.

---

## Dependencies & Execution Order

- **Phase 2 (T002–T004)** blocks everything (the repo + doubles).
- **US2 (T005–T007)**, **US4 (T008–T010)**, **US3 (T011–T013)** can proceed after Phase 2; US4
  seeding and US3 loading both read the repo created in Phase 2. US2 and US4 touch
  `skills_manager.py` (sequence T005 → T008 to avoid conflicts); US3 touches `agent_factory.py` /
  `validators.py` (parallel-safe with US2/US4).
- **Phase 6**: T014/T015 are independent (infra/test) and `[P]`; T016 depends on T005.
- **Phase 7**: after all implementation.

## Parallel Example

```
After T002–T004 complete:
  → T011 (agent_factory CosmosSkillsSource)  [P]
  → T014 (Terraform container)               [P]
  → T005 (SkillManager Cosmos)  → then T008 (seed_skills, same file)
```
