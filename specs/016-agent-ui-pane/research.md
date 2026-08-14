# Phase 0 Research: Agent Dynamic UI Pane

**Feature**: 016-agent-ui-pane | **Date**: 2026-08-14

All `NEEDS CLARIFICATION` items from Technical Context are resolved below. Every decision is
grounded in code that already exists in this repository; file references point at the code the
decision builds on.

---

## D1. How to render untrusted, agent-authored HTML safely

**Decision**: Render into an `<iframe sandbox="allow-scripts" srcdoc="...">` **without**
`allow-same-origin`, with a host-prepended
`<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; form-action 'none'; base-uri 'none'; frame-src 'none'; connect-src 'none'">`.

**Rationale**:

- Omitting `allow-same-origin` gives the frame an **opaque origin**. The document cannot read the
  host DOM, cannot touch `localStorage`/`sessionStorage` of the app origin, receives no cookies,
  and cannot reach `window.parent` beyond `postMessage`. This is the browser's own security
  boundary, not an application-level filter — it satisfies FR-004 without trusting our own parser.
- Omitting `allow-popups`, `allow-forms`, `allow-modals`, and `allow-top-navigation` removes
  window opening, native form submission, and host navigation hijacking.
- `default-src 'none'` + `connect-src 'none'` blocks `fetch`, `XMLHttpRequest`, `WebSocket`,
  `EventSource`, beacons, and subresource loads, which is exactly FR-005 ("no direct network
  requests to any destination"). `img-src data:` and `font-src data:` keep self-contained inline
  assets working, per the spec's "no external resources" assumption.
- Multiple CSP policies are enforced **conjunctively** — an agent that adds its own `<meta>` CSP
  can only make the policy stricter, never looser. Putting the host policy first is therefore
  sufficient; the agent cannot escape it.
- `postMessage` still works across the opaque origin, which is what the data bridge needs.

**Alternatives considered**:

- **Sanitize HTML with DOMPurify and render inline via `dangerouslySetInnerHTML`** — rejected.
  It adds a dependency (Constitution V), it is a denylist-shaped control with a long CVE history,
  and it must strip `<script>` to be safe, which would kill the "dynamic UI" requirement outright.
- **Render into a same-origin iframe** — rejected. `allow-same-origin` + `allow-scripts` lets the
  frame remove its own sandbox attribute and reach the host; it is explicitly warned against in the
  HTML specification.
- **Shadow DOM with a custom element allow-list** — rejected. Shadow DOM is an encapsulation
  boundary, not a security boundary; scripts still run in the host realm with host credentials.
- **Server-side rendering to a static image** — rejected. It destroys interactivity (FR-006) and
  adds a headless browser to the production runtime.
- **Serve views from a separate sandbox origin** — deferred. It is the strongest option and worth
  revisiting if views ever need `allow-same-origin`, but it requires a second hostname or a
  dedicated static route and TLS cert, which is disproportionate while `srcdoc` + opaque origin
  already satisfies every requirement.

---

## D2. How view-originated data requests inherit the agent's permissions

**Decision**: The broker resolves the requested tool by name against
`SessionData.tools` — the list of already-instantiated tool callables for that live session — and
invokes the same callable the agent itself would invoke. There is no second allow-list.

**Rationale**:

- `app_context.build_tool_instances(tool_names, *, session_id, user_id)` builds tools from the
  profile's `tools:` entry and binds each one to `user_id` at construction time
  (`tools.build_user_profile_tools(user_id)` closes over the user). Reusing those instances means
  the user binding, argument validation, row limits, and read-only behavior are inherited *by
  construction* rather than reimplemented — this is the cleanest possible satisfaction of FR-006.
- A parallel copy of the allow-list would be a drift hazard: the day someone changes tool
  resolution in `session_orchestration.py`, the broker would silently diverge. Structural parity
  cannot drift.
- Sub-agent-as-tool entries and profile overrides are already resolved into that same list, so
  they are handled with no extra code.
- The rendering agent's *current* permitted set is used on every call, satisfying the
  "permission change mid-conversation" edge case.

**Consequences**:

- The broker requires a **live session**. When `session_id` is absent from `_sessions`, the
  endpoint returns `409 session_inactive` and the client re-establishes the session (the existing
  `useSessionLifecycle` flow already resumes a conversation by id) and retries once. This is a
  deliberate trade: correctness of the permission model over convenience of an offline broker.
- `render_agent_view` itself is excluded from the broker-callable set so a view cannot recursively
  re-render itself.
- MCP tools live in `SessionData.mcp_tools`, a separate list, so they are naturally excluded in the
  MVP. Narrowing is safe: FR-006 requires a subset of the agent's tools, not the whole set.

**Alternatives considered**:

- **Snapshot the permitted tool names into the view record at render time** — rejected. It freezes
  a permission decision in storage; a revoked tool would keep working from an old view.
- **Rebuild the agent's tool set on demand for a dead session** — rejected for the MVP. It would
  duplicate profile resolution, custom-agent lookup, and override merging from
  `session_orchestration.py` for marginal benefit.
- **Let the view call the existing chat endpoint and have the model decide** — rejected. It costs a
  full model turn per click (violating SC-004's 3-second target) and makes a deterministic data
  refresh non-deterministic.

---

## D3. How the view content reaches the browser

**Decision**: The tool persists the HTML to Cosmos and returns a compact acknowledgement
(`{view_id, title, status, chars}`) to the model. `streaming.py` recognizes the
`function_result` for `render_agent_view` and emits an additional `agent_view` SSE event carrying
**metadata only**. The frontend then fetches the HTML from
`GET /api/sessions/{session_id}/views/{view_id}`.

**Rationale**:

- The model just wrote the HTML; returning it in the tool result would push a second full copy
  into the context window on the next turn — pure waste, and a fast path to context-length errors
  on a 250 KB view.
- FR-013 and FR-018 already require durable per-conversation storage (reload restore, autonomous
  runs). Once storage exists, fetching content by id makes the live path and the restore path the
  **same** code path in the frontend, which is less code, not more.
- Keeping SSE frames small avoids the multi-chunk reassembly fragility already documented in
  `frontend/src/api/client.ts` for large base64 image events.
- `streaming.py` already inspects `function_result` content and maps `call_id` back to a tool name
  via `tool_event_by_call_id`, so the emission point exists — the change is additive and small.

**Alternatives considered**:

- **Put the full HTML in the `agent_view` SSE payload** — rejected. It duplicates the restore path,
  bloats SSE frames, and gains only one saved round trip.
- **Have the frontend special-case `function_result` where `name === "render_agent_view"`** —
  rejected. It couples the client to a tool name string and gives no clean contract; an explicit
  event type is a handful of lines and is self-documenting.
- **A per-session side-channel queue the tool writes into** — rejected. It adds cross-task
  plumbing and lifetime management for no benefit over reading the tool result.

---

## D4. Where views are stored

**Decision**: A new Cosmos container `agent-views` partitioned by `/user_id`, accessed through a
`CosmosAgentViewRepository` modeled on `user_data.CosmosUserScopedRepository`, with
`conversation_id` promoted to a top-level document field so listing is a partition-scoped query.

**Rationale**:

- `/user_id` partitioning matches every other per-user store in this app (`user-profiles`,
  `custom-agents`, `user-skills`) and gives tenant isolation for free — the same property FR-017
  requires. A user's views are bounded (50 per conversation), so the partition stays small.
- The dominant query is "views for this conversation, oldest first", which is
  `WHERE c.user_id = @uid AND c.conversation_id = @cid ORDER BY c.created_at ASC` — single
  partition, no cross-partition fan-out.
- A dedicated container avoids mixing document shapes into `conversations`, whose
  `list_for_user` does an unfiltered `SELECT * FROM c WHERE c.user_id = @uid` and would otherwise
  start returning view documents.
- Terraform already declares containers individually in `infra/modules/cosmos/main.tf`; adding one
  that mirrors `user_profiles` is five lines and keeps Constitution VI satisfied. The runtime
  `create_container_if_not_exists` path keeps the Cosmos emulator working locally.

**Alternatives considered**:

- **Reuse the `conversations` container with a `doc_type` discriminator** — rejected. It would
  require touching an existing query that other features depend on.
- **Keep views in memory on `SessionData`** — rejected outright: fails FR-013 (reload) and FR-018
  (autonomous runs).
- **Partition by `/conversation_id`** — rejected. It splits a user's data across partitions and
  makes the per-user isolation check a filter rather than a partition boundary.

---

## D5. Bridge protocol between the sandboxed view and the host

**Decision**: A versioned `postMessage` envelope, with a tiny host-injected bootstrap script that
exposes `window.agentData(tool, args): Promise<unknown>` inside the frame. The host accepts a
message only when `event.source === iframeRef.current.contentWindow`, correlates it by
`requestId`, and replies into that same frame.

**Rationale**:

- The generated HTML needs one obvious, documented call to make. A promise-returning
  `agentData()` is what a model will produce correctly from a docstring; hand-rolled
  `postMessage` plumbing in every generated view would be error-prone and verbose.
- `event.origin` is the string `"null"` for opaque-origin frames, so origin comparison alone is
  not a usable check — identity comparison against the specific `contentWindow` is the correct
  control and also prevents a second frame or extension from spoofing requests.
- Versioning the envelope (`v: 1`) lets the contract evolve without breaking stored views.
- Correlating by `requestId` supports concurrent requests from one view without response mix-ups.

**Alternatives considered**:

- **`MessageChannel` with a transferred port** — rejected for the MVP. Slightly tighter, but it
  adds handshake state for a guarantee that source-identity checking already provides.
- **Expose a full RPC surface (arbitrary host function calls)** — rejected. The bridge is
  deliberately one verb wide; every additional verb is new attack surface.

---

## D6. Resource limits and abuse control

**Decision**: Environment-tunable limits in the `_env_int` style already used in `tools.py`:
`MAX_AGENT_VIEW_CHARS` (250,000), `MAX_AGENT_VIEWS_PER_CONVERSATION` (50, FIFO eviction),
`MAX_VIEW_DATA_RESPONSE_CHARS` (20,000), and a per-session broker budget of 60 requests/minute.

**Rationale**:

- 250 KB comfortably holds a rich self-contained view (inline CSS, inline SVG, inline data) while
  staying far below the 2 MB Cosmos item ceiling.
- A per-session token-bucket budget bounds a runaway `setInterval` in a generated view (FR-022)
  without punishing normal interactive use.
- Tools already truncate their own output (`MAX_QUERY_RESULT_CHARS`), so the broker cap is a
  backstop rather than the primary control.
- Matching the existing `_env_int` helper keeps configuration idiomatic and testable.

**Alternatives considered**:

- **No caps, rely on Cosmos and tool limits** — rejected. A view is model-authored and can loop;
  FR-014 and FR-022 require explicit bounds.
- **Hard-reject rendering once the per-conversation cap is hit** — rejected as a user-hostile
  reading of FR-014: a long conversation would permanently lose the capability. FIFO eviction
  enforces the cap while keeping the feature usable; the spec was amended to state this.

---

## D7. Audit trail for renders and view-originated requests

**Decision**: Reuse the existing tool-audit surfaces. Renders already appear as normal tool calls
in the transcript and in `eval_trace_logger` output. Broker calls are logged with structured
`logger.info` (user, session, view, tool, outcome, duration) and appended to the session's eval
trace when the trace logger is enabled.

**Rationale**: FR-008 asks for the *same* mechanism used for tool calls, not a parallel one.
`SessionData.eval_trace_logger` and the `tool_events` payload assembled in
`api_routes/sessions.py` are that mechanism, and refusals must be recorded as first-class outcomes
so a reviewer can see attempted escalation, not just successful calls.

**Alternatives considered**: a dedicated audit container — rejected as premature (Constitution V);
the eval trace plus structured logs already reconstruct the full sequence.

---

## D8. Frontend layout, persistence, and accessibility

**Decision**: Add a right-hand pane to `.chat-page` as a CSS grid column with a drag handle,
persisting `{open, width, activeViewId}` per conversation in `localStorage`. Below 900 px the pane
becomes a full-width overlay with an explicit "Back to chat" control. The iframe carries a
descriptive `title`; focus moves to the pane heading on open and returns to the triggering
transcript marker on close.

**Rationale**:

- `frontend/src/pages/ChatPage.tsx` is already a flex/grid layout with a collapsible left sidebar,
  so a right column follows the established pattern instead of inventing a new shell.
- Pane geometry is presentation state, not user data — `localStorage` is the right home for it and
  keeps it off the server (Pane State is explicitly *not* persisted in Cosmos in data-model.md).
- Which views exist is server state (Cosmos); which one is showing is client state. Splitting them
  this way keeps the restore path simple.
- Screen-reader users must never be trapped in an iframe, hence explicit focus management (FR-020).

**Alternatives considered**:

- **Render the view inline in the message list** — rejected. It fights the "side pane" requirement
  and makes a tall dashboard unusable inside a scrolling transcript.
- **A floating/detachable window** — rejected. `window.open` plus an opaque-origin sandbox is a bad
  combination, and the spec explicitly excludes multi-window layouts.
- **Persist pane geometry server-side** — rejected as unnecessary round trips for a cosmetic value.

---

## D9. Verification approach

**Decision**: Backend `pytest` covers the security-critical paths (ownership, refusal of
non-permitted tools, refusal against a dead session, rate limiting, size caps, FIFO eviction, SSE
emission). Frontend correctness is covered by `tsc -b` plus the mandatory Playwright screenshot
run via `scripts/capture_agent_view_screenshots.py`.

**Rationale**: The repository has no frontend unit-test runner (`npm test` is `tsc -b`), and the
Constitution's Visual Verification Protocol is the established substitute for UI regressions. The
isolation guarantees that matter most (no host access, no network) are browser-enforced, so the
Playwright run doubles as the isolation check: a deliberately hostile fixture view that attempts
`fetch`, `parent.document`, and `localStorage` access must visibly fail on all three.

**Alternatives considered**: adding Vitest + Testing Library — rejected for this feature under
Constitution V; it is a repo-wide tooling decision, not something to smuggle in here.
