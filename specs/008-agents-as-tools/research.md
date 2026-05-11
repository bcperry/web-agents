# Phase 0 — Research: Agents as Tools

## R1. `agent_framework.Agent.as_tool()` signature & behavior

**Decision**: Use `Agent.as_tool(name=..., description=..., arg_name=..., arg_description=...)` exactly as in the upstream sample. The returned object is a tool callable accepted by `as_agent(tools=[...])`.

**Rationale**: Mirrors the canonical Microsoft sample `client_with_agent_as_tool.py`. The framework already handles invocation lifecycle, argument binding (single `arg_name` string parameter that the LLM fills), and result conversion. Tool errors propagate as a structured tool-call result that the parent LLM can react to.

**Alternatives considered**:
- Hand-rolled `@tool`-decorated wrapper that calls `sub_agent.run(...)` ourselves — rejected: duplicates framework behavior, harder to keep in sync with upstream.
- Exposing sub-agents via MCP transport — rejected: massive overkill for in-process delegation; adds a serialization tier and a network dependency.

## R2. `RuntimeAgent` (from `OpenAIChatClient.as_agent()`) parity with `Agent`

**Decision**: Treat `RuntimeAgent` (the value returned by `primary_client.as_agent(...)` in `agent_factory.py`) as the same `Agent` class the upstream sample constructs directly. Call `.as_tool(...)` on it.

**Rationale**: `agent_factory.py` already imports `from agent_framework import Agent as RuntimeAgent`, confirming `RuntimeAgent` is the framework's `Agent` class — the only difference vs the upstream sample is that we reach it via `client.as_agent()` instead of `Agent(client=client, ...)`. Both paths produce instances of the same class with the same `.as_tool()` method.

**Verification step (during implementation)**: First implementation task asserts `hasattr(runtime_agent, "as_tool")` in a unit test before wiring further.

**Alternatives considered**: Falling back to `Agent(client=primary_client, name=..., instructions=..., tools=...)` constructor for sub-agents only — rejected: would bypass `_build_context_providers`, `as_agent`-injected defaults, and differ from how parent agents are built. Reusing `create_chat_runtime` for sub-agents keeps both code paths uniform.

## R3. Serialization across built-in vs custom agents

**Decision**: A single uniform on-the-wire shape — `SubAgentToolRef { agent_ref, tool_name, tool_description }` — where `agent_ref` is a tagged union: `{ kind: "builtin", profile_id }` or `{ kind: "custom", definition: <full custom agent definition> }`. The frontend resolves custom-agent IDs against its `localStorage` cache before sending and inlines the full definition. The backend treats both cases uniformly: `kind="builtin"` → loads via `load_agent_profile`; `kind="custom"` → builds via the same custom-agent code path used today for the parent.

**Rationale**: Custom agents currently live only in frontend `localStorage`; introducing a backend custom-agent store is out of scope (Constitution V — minimalism). Inlining the resolved definition keeps the backend stateless about custom agents while still letting any agent reference any other.

**Cycle-prevention implication**: Because the frontend has the full custom-agent table and resolves references just before sending, it can detect direct A↔B cycles client-side. The backend re-runs the same check on the inlined payload as defense in depth (per FR-014).

**Alternatives considered**:
- Lift custom agents to a backend store (e.g., Cosmos DB) — rejected: out of scope; introduces persistence + auth concerns.
- Reference custom agents by ID only and have the backend ask the frontend to resolve — rejected: requires a callback channel; not how the current API works.

## R4. Subsection header styling baseline

**Decision**: Introduce a single shared class (the existing `.agent-builder-section-title` already used by `AgentCapabilityPicker`) and apply it consistently to all six (soon seven) subsection headers: Tools, AI Search Context, Skills, MCP Servers, Starter Questions, Agents as Tools. Audit existing markup to remove ad-hoc heading styles and align to one rule (font-size, weight, color, top/bottom spacing, optional small uppercase tracking — pick whichever the picker components currently use). The page title (`.agent-builder-title`) keeps its current larger style; subsection titles must be visibly smaller / less prominent than the page title.

**Rationale**: `AgentBuilder.tsx` currently mixes `<AgentCapabilityPicker title="TOOLS" />` (which renders `.agent-builder-section-title`) with hand-written `<label>`/heading elements for AI Search Context, MCP Servers, and Starter Questions. Unifying on one class is a one-touch fix that satisfies FR-023/FR-024 without redesigning the form.

**Alternatives considered**:
- Introduce a dedicated `AgentBuilderSubheader` React component — viable, but for six headings it's overkill; a single CSS class plus a small JSX cleanup is simpler.
- Restyle the page title instead — rejected: the page title is correct; subsections are the inconsistent ones.

## Open Questions

None. All NEEDS CLARIFICATION items from the spec template are resolved or covered by the spec's Assumptions section.
