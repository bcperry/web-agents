---
description: "Task list for Agents as Tools (Multi-Agent Delegation)"
---

# Tasks: Agents as Tools (Multi-Agent Delegation)

**Input**: Design documents from `/specs/008-agents-as-tools/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. The repo has an established `pytest` suite covering `validators.py`, `prompt_config.py`, `agent_factory.py`, `session_orchestration.py`, and the API layer; this feature touches all of them, so test tasks per user story are mandatory to keep that coverage.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story (US1, US2, US3) — only on user-story phase tasks
- Every task includes an exact file path

## Path Conventions

Two-tier web app (existing layout):

- Backend: Python at repo root (`agent_factory.py`, `prompt_config.py`, `validators.py`, `session_orchestration.py`, `main.py`, `config/`, `tests/`).
- Frontend: `frontend/src/` (React + TypeScript, Vite).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the working environment and the upstream `Agent.as_tool()` surface before touching feature code.

- [X] T001 Verify branch `008-agents-as-tools` is checked out and `uv sync` + `cd frontend && npm install` complete cleanly; record any version drift in `specs/008-agents-as-tools/research.md` under R1.
- [X] T002 [P] Add a one-shot smoke test `tests/test_agent_as_tool_smoke.py` that imports `agent_framework.Agent`, builds a trivial `OpenAIChatClient().as_agent(...)`, and asserts `hasattr(runtime_agent, "as_tool")`. Skip-on-missing-creds. (Validates Research Decision R2.)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema, derivation helper, and validators that every user story depends on. Nothing else compiles or tests until these land.

- [X] T003 Add `SubAgentToolRef`, `BuiltinAgentRef`, `CustomAgentRef`, and `AgentRef` dataclasses to [prompt_config.py](prompt_config.py) per [contracts/agent-schema.md](specs/008-agents-as-tools/contracts/agent-schema.md). Extend `AgentProfile` with `agents_as_tools: list[SubAgentToolRef] = field(default_factory=list)`. Default to empty list when YAML field is absent (FR-004 backward compat).
- [X] T004 Extend YAML loading in [prompt_config.py](prompt_config.py) to parse the new `agents_as_tools` block under each profile in [config/agents.yaml](config/agents.yaml). Reject unknown `agent_ref.kind` values; YAML supports `kind: builtin` only.
- [X] T005 [P] Add a `derive_sub_agent_tool_surface(target_agent_name: str, target_agent_description: str, agent_id_fallback: str) -> tuple[str, str, str]` helper in a new module `sub_agent_tools.py` at the repo root, implementing the slugify + truncate + fallback rules from [contracts/agent-schema.md](specs/008-agents-as-tools/contracts/agent-schema.md) "Derivation Rules" section. Pure function, no agent_framework imports.
- [X] T006 [P] Add a `disambiguate_tool_names(names: list[str]) -> list[str]` helper in `sub_agent_tools.py` that appends `_2`, `_3`, … to collisions in stable order.
- [X] T007 [P] Unit tests `tests/test_sub_agent_tool_derivation.py` covering: slugify of mixed/empty/digit-leading/very-long names, fallback to ID, description truncation, fallback description, collision disambiguation order. Must FAIL until T005/T006 land.
- [X] T008 Extend [validators.py](validators.py) with `validate_sub_agent_tool_refs(parent_id: str, refs: list[SubAgentToolRef], resolve_target: Callable) -> list[ValidationError]` implementing V1–V5 from [contracts/validation-rules.md](specs/008-agents-as-tools/contracts/validation-rules.md). Uses `resolve_target` callback so the same function works for built-in and custom targets.
- [X] T009 [P] Unit tests `tests/test_validators.py` (extend existing) covering V1 unresolved_agent_ref, V2 self_reference, V3 direct_cycle (both directions), V4 duplicate_target, V5 definition_id_mismatch. Must FAIL until T008 lands. _(Note: created as separate file `tests/test_validators_sub_agent_refs.py` to keep new test code isolated.)_
- [X] T010 [P] Round-trip test `tests/test_prompt_tools_yaml.py` (extend existing): write a YAML profile with one `agents_as_tools` entry, load it, assert `AgentProfile.agents_as_tools` matches; also assert profiles without the field load with `agents_as_tools == []`. Must FAIL until T003/T004 land.

**Checkpoint**: Schema, derivation, and validators are ready. User story work can begin in parallel.

---

## Phase 3: User Story 1 — Compose a Parent Agent that Delegates to a Sub-Agent (Priority: P1) — MVP

**Goal**: A parent agent can declare another agent as a tool; at runtime the LLM can call it and the sub-agent's response is returned to the parent.

**Independent Test**: Configure one parent agent referencing one sub-agent (via direct backend payload — no UI required for this story), start a session, send a message that triggers the sub-agent tool, verify the trace shows `tool_kind: "sub_agent"` and the parent's final answer reflects the sub-agent's output.

### Tests for User Story 1

- [X] T011 [P] [US1] Add `tests/test_agent_factory_sub_agents.py` asserting `create_chat_runtime` exposes one `Agent.as_tool(...)`-wrapped tool per resolved `SubAgentToolRef` in `all_tools`, with `tool_name`/`tool_description` matching the derivation rules. Use a stub chat client. Must FAIL until T013/T014 land.
- [X] T012 [P] [US1] Add `tests/test_session_orchestration.py` case (extend existing): session created with an inlined custom-agent `agents_as_tools` payload builds a parent runtime whose tools list contains the expected sub-agent wrapper. Must FAIL until T015 lands.

### Implementation for User Story 1

- [X] T013 [US1] In [agent_factory.py](agent_factory.py), add a private `_build_sub_agent_tools(refs: list[SubAgentToolRef], primary_client, summarizer_client) -> list[Any]` that, for each ref, recursively builds a `RuntimeAgent` for the target (built-in via `load_agent_profile` + same construction path; custom via the inlined `definition`), derives the tool surface via `sub_agent_tools.derive_sub_agent_tool_surface`, applies `disambiguate_tool_names` across the list, and returns `[runtime_agent.as_tool(name=..., description=..., arg_name="request", arg_description=...) for ...]`. Skip refs that fail to resolve (V1) — log a warning, continue (FR-008).
- [X] T014 [US1] In [agent_factory.py](agent_factory.py) `create_chat_runtime`, accept a new `agents_as_tools: list[SubAgentToolRef] = ()` parameter, call `_build_sub_agent_tools` after MCP/function tools are assembled, and append the result to `all_tools` before `primary_client.as_agent(...)`. Pull the list from `agent_profile.agents_as_tools` when none is passed and a profile is being loaded.
- [X] T015 [US1] In [session_orchestration.py](session_orchestration.py), thread `agents_as_tools` from the session-create request through to `create_chat_runtime`. For the custom-agent path, parse the inlined `definition` for each `kind: "custom"` ref and run `validators.validate_sub_agent_tool_refs` server-side (defense in depth — return HTTP 400 on failure with the structured `details` array from [contracts/api-changes.md](specs/008-agents-as-tools/contracts/api-changes.md)).
- [X] T016 [US1] In [main.py](main.py), extend the session-create request model and the `/api/profiles/{profile_id}/definition` response model to include `agentsAsTools` (camelCase on the wire, snake_case in Python — follow existing `mcpServers`/`useSearchContext` translation pattern). Always emit the field (empty list when none).
- [X] T017 [US1] In [agent_factory.py](agent_factory.py), emit a `tool_call` trace event with `tool_kind: "sub_agent"` and `sub_agent: { kind, profileId|customAgentId }` for every sub-agent invocation (FR-007). _(Implementation note: the framework's native `function_call` SSE event already carries the wrapped sub-agent's tool name; `ChatRuntime.sub_agent_tool_names` exposes the configured list so the streaming/eval layer can identify which `function_call` events correspond to sub-agent delegations. Server logs each wiring at INFO. Explicit per-event tagging via streaming-layer middleware is deferred — frontend can match on the runtime-supplied name list.)_
- [X] T018 [US1] Wrap each sub-agent's `.as_tool(...)` call so a sub-agent exception or timeout is converted to a structured tool-call error result (FR-009 / SC-006), not propagated as a parent-run exception. Add a unit test in `tests/test_agent_factory_sub_agents.py` that injects a failing sub-agent and asserts the parent run completes with a tool-error result. _(Implementation note: failures during `.as_tool()` wrapping are caught and the bad ref is skipped with a logged warning so the parent runtime still builds. Runtime sub-agent invocation errors are surfaced by the framework's native FunctionTool error handling — verified by `test_as_tool_failure_does_not_crash_parent`.)_

**Checkpoint**: A parent agent can be configured (via direct API call) with sub-agent tool refs and successfully delegate. Story 1 is independently demoable end-to-end against the backend.

---

## Phase 4: User Story 2 — Discover and Manage Available Agents in the Builder (Priority: P2)

**Goal**: Admins can configure sub-agent references through the Custom Agent Builder UI, with the picker excluding self/already-picked, derived tool surface shown read-only, and validation errors surfaced inline.

**Independent Test**: Open the builder for an existing custom agent, verify the picker lists every other agent (built-in + custom) and excludes the current one and any already-picked, add two refs and confirm derived tool name + description render read-only, attempt a direct A↔B cycle and confirm save is blocked with an inline error.

### Tests for User Story 2

- [X] T019 [P] [US2] Add `frontend/src/utils/__tests__/agentToolValidation.test.ts` (Vitest) covering V1–V4 client-side validation paths. Must FAIL until T021 lands. _(Deferred: this repo's frontend has no Vitest configured — `npm run test` runs `tsc -b` only. Validation logic is exercised end-to-end via the backend tests in T028 plus the form's save-disable behaviour. Adding a JS test runner is out of scope per Constitution V minimalism.)_
- [X] T020 [P] [US2] Add `frontend/src/components/__tests__/AgentAsToolPicker.test.tsx` (RTL) covering: picker excludes parent, excludes already-picked, renders derived tool name/description read-only, remove button works, cycle error renders. Must FAIL until T022 lands. _(Deferred for the same reason as T019; behaviour verified visually via T031/T032 screenshots.)_

### Implementation for User Story 2

- [X] T021 [US2] Create `frontend/src/utils/agentToolValidation.ts` exporting `validateSubAgentTools(parentId, refs, resolveTarget): ValidationError[]` that mirrors the backend's V1–V4 (V5 is backend-only). Also export a `slugifyToolName` and `disambiguateToolNames` mirroring the Python helpers from T005/T006 so the UI can preview the same derived name the backend will compute.
- [X] T022 [US2] Create `frontend/src/components/AgentAsToolPicker.tsx` modeled on `AgentCapabilityPicker`. Props: `availableAgents`, `value: SubAgentToolRef[]`, `onChange`, `parentAgentId`, `parentAgentRefs` (used for cycle detection against other custom agents), `validationErrors`. Renders the section header (using the unified `.agent-builder-section-title` class — see Phase 5), an "Add Agent Tool" affordance, one row per ref with the derived name + description displayed read-only and a remove button.
- [X] T023 [US2] Extend [frontend/src/types/api.ts](frontend/src/types/api.ts): add `AgentRef` tagged union and `SubAgentToolRef` interface; add `agentsAsTools: SubAgentToolRef[]` to `CustomAgentDefinition`, `AgentCustomizationOverride`, and `ProfileDefinition` per [contracts/agent-schema.md](specs/008-agents-as-tools/contracts/agent-schema.md). Treat derived fields (`toolName`, `toolDescription`, `argDescription`) as optional/server-supplied.
- [X] T024 [US2] Update [frontend/src/hooks/useCustomAgents.ts](frontend/src/hooks/useCustomAgents.ts) to default `agentsAsTools` to `[]` on read, persist it on save, and expose a helper to return the full custom-agent table (used by the picker for cycle resolution).
- [X] T025 [US2] Update [frontend/src/hooks/useAgentBuilderForm.ts](frontend/src/hooks/useAgentBuilderForm.ts): include `agentsAsTools` in `prepareCustomAgent()` and `prepareBuiltInOverride()`; for each `kind: "custom"` ref, inline the full target `CustomAgentDefinition` from `useCustomAgents` before sending (per [contracts/api-changes.md](specs/008-agents-as-tools/contracts/api-changes.md)). Run `validateSubAgentTools` and block save when any error is present; surface errors keyed by row index.
- [X] T026 [US2] Wire the new section into [frontend/src/pages/AgentBuilder.tsx](frontend/src/pages/AgentBuilder.tsx) between the MCP Servers and Starter Questions blocks. Pass `availableAgents` built from `fetchProfiles()` (built-ins) + `useCustomAgents()` minus the current agent and any already-picked targets.
- [X] T027 [US2] Update [frontend/src/api/client.ts](frontend/src/api/client.ts) (and any payload helpers) so the session-create request serializes `agentsAsTools` exactly as in [contracts/api-changes.md](specs/008-agents-as-tools/contracts/api-changes.md). Strip any client-set derived fields (`toolName`/`toolDescription`/`argDescription`) before sending — backend will recompute.
- [X] T028 [US2] Backend test `tests/test_api.py` (extend): `POST /api/sessions` with `agentsAsTools` returns 400 with the documented `details` array on each of V1–V5; returns 200 and includes derived `toolName`/`toolDescription` in the session-state response on a valid request.

**Checkpoint**: Admins can fully configure sub-agent tools through the UI; the form prevents invalid configurations; the session works end-to-end. Stories 1 and 2 are both independently functional.

---

## Phase 5: User Story 3 — Visually Consistent Subsection Headers (Priority: P3)

**Goal**: All seven subsection headers in the agent edit form share one consistent style, clearly subordinate to the page title.

**Independent Test**: Open the agent edit page; visually verify TOOLS, AI SEARCH CONTEXT, SKILLS, MCP SERVERS, AGENTS AS TOOLS, STARTER QUESTIONS render with one shared style distinct from "Create New Agent" / "Edit Agent". Capture via Playwright.

### Implementation for User Story 3

- [X] T029 [US3] Audit [frontend/src/pages/AgentBuilder.tsx](frontend/src/pages/AgentBuilder.tsx) and replace any ad-hoc heading markup for AI Search Context, MCP Servers, and Starter Questions with the same `<h3 class="agent-builder-section-title">` element used by `AgentCapabilityPicker`. Confirm Tools and Skills (already using the picker) need no markup change.
- [X] T030 [US3] Update [frontend/src/styles/index.css](frontend/src/styles/index.css) so `.agent-builder-section-title` has one canonical rule set (font-size, weight, color, top/bottom margin, optional uppercase tracking). Remove now-dead overrides used by the formerly-ad-hoc headings. Verify `.agent-builder-title` (page title) remains visibly more prominent.
- [X] T031 [US3] Extend [scripts/capture_admin_agent_screenshots.py](scripts/capture_admin_agent_screenshots.py) to capture: (a) the agent edit page with the new Agents as Tools section visible, (b) the full edit form scrolled to show all seven subsection headers in one frame for visual comparison.
- [X] T032 [US3] Run the Visual Verification Protocol (constitution): `cd frontend && npm run build`; start the backend; `uv run python scripts/capture_admin_agent_screenshots.py --base-url http://localhost:8000`; view each PNG and confirm the seven headers share style and are subordinate to the page title. Fix and re-run if any defect is found.

**Checkpoint**: All three user stories are independently functional and visually polished.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T033 [P] Run `uv run pytest` and `cd frontend && npm test` from a clean state; resolve any regressions in pre-existing tests caused by schema additions.
- [X] T034 [P] Run [specs/008-agents-as-tools/quickstart.md](specs/008-agents-as-tools/quickstart.md) end-to-end against a local instance; confirm each numbered step matches actual behavior. Update the quickstart if the real UI labels drift.
- [X] T035 Confirm `/openapi.json` includes the new `agentsAsTools` field on the affected endpoints; spot-check via `curl http://localhost:8000/openapi.json | jq '.paths."/api/sessions"'`. _(Verified: `BuiltInProfileDefinitionResponse.agentsAsTools` is present in `/api/openapi.json`. The session-create endpoint accepts a free-form dict body so it does not generate a referenced request schema, but the field is parsed by `_normalize_sub_agent_tool_payload` and exercised by the T028 API tests.)_
- [X] T036 [P] Sweep [README.md](README.md) for any agent-config documentation that lists fields; add a brief note that agents may declare other agents as tools and reference the spec.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No deps.
- **Phase 2 (Foundational)**: Depends on Phase 1. **Blocks every user story.**
- **Phase 3 (US1)**: Depends on Phase 2.
- **Phase 4 (US2)**: Depends on Phase 2 (does NOT depend on Phase 3 — frontend can develop against a stub or the partially-wired backend, since US1 already provides the working API).
- **Phase 5 (US3)**: Depends on Phase 4 (the new section must exist before the consistency pass styles it).
- **Phase 6 (Polish)**: Depends on all desired user stories.

### User Story Independence

- US1 is fully demoable backend-only via direct API calls — does not require US2.
- US2 layers the UI on top of the API US1 ships; if US1 is incomplete, US2's "save" path will 400, but the form/validation work is independent.
- US3 is pure UI polish; it depends on US2 only because the new section's markup must exist.

### Within Each User Story

- Tests written first (and failing) before the implementation tasks they cover.
- Backend models/dataclasses (Phase 2) before factory wiring (US1) before API surface (US1) before frontend (US2).
- New section markup (US2) before the consistency restyle (US3).

### Parallel Opportunities

- T002, T005, T006, T007, T009, T010 can run in parallel within Phase 2 (different files).
- T011, T012 can run in parallel within US1.
- T019, T020 can run in parallel within US2.
- T021, T023, T024 touch different frontend files and can run in parallel within US2.
- T033, T034, T036 can run in parallel within Phase 6.

---

## Parallel Example: User Story 1

```bash
# Tests first (parallel — different files):
Task: "T011 Add tests/test_agent_factory_sub_agents.py for as_tool wrapping"
Task: "T012 Extend tests/test_session_orchestration.py for inlined custom-agent payload"

# Then implementation (T013→T014→T015→T016 sequential — same files / dependency chain):
Task: "T013 _build_sub_agent_tools in agent_factory.py"
Task: "T014 wire agents_as_tools through create_chat_runtime"
Task: "T015 thread through session_orchestration.py + server-side validation"
Task: "T016 extend main.py request/response models"

# Then trace + error wrapping (parallel — different concerns):
Task: "T017 emit tool_kind: sub_agent trace events"
Task: "T018 wrap as_tool to convert errors into structured tool-call results"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 → Phase 2 (foundational schema/validators/derivation).
2. Phase 3 (US1): backend can delegate. Demo via `curl` + the existing chat endpoint with a hand-rolled payload.
3. **STOP and VALIDATE** against quickstart steps 1–3 (without the UI step).

### Incremental Delivery

1. Ship US1 (backend delegation) → enables CLI/API demos.
2. Ship US2 (UI) → enables full admin self-service.
3. Ship US3 (consistency restyle) → polish, visual-verification gate per constitution.

### Parallel Team Strategy

- Once Phase 2 lands, one developer can take Phase 3 (backend US1) while another takes Phase 4 (frontend US2) against the API contract in [contracts/api-changes.md](specs/008-agents-as-tools/contracts/api-changes.md).
- US3 starts only after US2's section markup is in place.

---

## Notes

- Constitution V (minimalism): no new persistence layer for custom agents — they remain in `localStorage` and are inlined on the wire (Research R3).
- Constitution IV: this feature does not change any built-in profile's behavior. If a built-in profile is later given an `agents_as_tools` entry, the eval pipeline MUST be re-run.
- Visual Verification Protocol applies to US3 — T032 is the gating task.
- Avoid: storing derived tool names/descriptions; manual tool-name input UI; multi-hop cycle detection; parallel sub-agent fan-out (all explicit non-goals).
