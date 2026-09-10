# Code Review Remediation

## Constraints

- Preserve FastAPI, React, Cosmos DB, existing public routes, and the iframe sandbox.
- Preserve the existing authenticated-user access policy for shared configuration.
- Resume conversations using current agent definitions; persisted sub-agent references are identities, not snapshots.
- Keep trusted YAML environment expansion, but never expand values supplied by an HTTP caller.
- Use focused regression tests after each implementation slice. No cloud writes, live MCP calls, commits, or destructive data migrations.

## Implementation Order

| Batch | Review Findings | Implementation | Acceptance Checks |
| --- | --- | --- | --- |
| 1. Trust and ownership | 1, 2, 6 | Separate trusted MCP parsing; propagate cancellation; require session ownership before reads or mutation. | Dummy environment value remains literal in requests; trusted YAML expands; cross-user POST/DELETE return 404 without side effects. |
| 2. Runtime lifecycle | 5, 6, 11, 14 | Normalize session inputs into one construction path; centrally close live sessions; rollback failed setup; coordinate autonomous execution; replace streaming function attributes with request-local results. | Failed setup closes resources; replacement/delete/shutdown close once; concurrent runs cannot close each other; SSE and autonomous results remain equivalent. |
| 3. Definitions and stores | 7, 8, 9, 12, 13 | Strict profile resolution; shared reference validation; persist identity-only references; explicit skill write scope; real continuation tokens; one Cosmos bootstrap/reset path. | Missing profiles reject; owned skills edit/delete; references hydrate current owner records; pages are disjoint; all cached repositories reset. |
| 4. Frontend state | 3, 4, 15 | Await mutations before updating saved state/resetting forms; cancel and invalidate stale chat work; remove write-only metadata; use one session transition owner. | Failed saves retain drafts; late streams cannot update another conversation; incomplete streams terminate visibly; navigation closes sessions. |
| 5. Authentication and transport | 10, 14 | One auth provider; acquire fresh tokens for requests; shared HTTP/error handling; consume all conversation pages. | Token provider used by API requests; structured validation errors reach UI; no duplicate auth initialization; pagination supports cleanup. |
| 6. Deletions and boundaries | 15, 16 | Delete unused SQL helpers and direct dependencies; remove entry-point compatibility wrappers; relocate CSS to owning modules; lazy-load secondary screens. | No production references to deleted helpers; resolved lockfile and builds pass; browser layouts preserved; secondary screens split from initial bundle. |

## Verification Gates

1. Focused pytest tests for each backend slice, using in-memory doubles unless testing Cosmos paging itself.
2. Frontend lint and TypeScript checks after each frontend slice.
3. Browser regression coverage for failed saves, conversation switching, interrupted streams, and successful builder flows.
4. Full offline backend suite and fresh frontend production build.
5. Emulator tests when a local emulator is available; otherwise explicitly report the unverified integration gate.
6. Review the final diff for unrelated changes and update this document with outcomes and limitations.

## Progress

- Baseline: 350 offline backend tests passed during review; frontend lint, typecheck, build, and existing builder browser test passed.
- All six implementation batches completed. Changes are uncommitted.

## Resolution Record

| Finding | Implemented Resolution | Verification |
| --- | --- | --- |
| 1. MCP environment expansion | Request parsing leaves environment expressions literal; only trusted YAML opts into expansion. Shared HTTP validation rejects non-HTTP URLs and embedded credentials. Connection-test errors are sanitized. | Dummy-value trust-boundary regression; session/API tests. |
| 2. Live session ownership | Message and live-delete routes require the authenticated owner before touching runtime state. | Cross-owner POST/DELETE return 404 without side effects. |
| 3. Stale chat streams | Request-local accumulators, AbortController, and session-generation guards prevent late work from mutating a new conversation. Unmount/navigation closes live sessions. | Desktop/mobile browser Alpha-to-Beta regression. |
| 4. False save success | Custom-agent and override mutations are awaited; saved lists and form reset update only after success. Failures preserve drafts. | Desktop/mobile custom-save and override-save 503 regressions. |
| 5. Autonomous overlap | Atomic per-directive Cosmos execution lease, owner-checked ETag release, and bounded run duration supplement the existing scheduler-slot lease. | Concurrent-run test and direct repository ownership/ETag tests. |
| 6. Resource lifecycle | Shared idempotent close operation handles replacement, live deletion, conversation deletion, and shutdown. Setup failures roll back accumulated MCP resources; cancellation propagates. | Cancellation, close-once, runtime-failure, and index-failure regressions. |
| 7. Definition validation | Unknown profiles reject instead of falling back. Session/autonomous lookup uses the shared resolver. Creation and customization saves use shared normalization/reference validation and the registered tool catalog. | Profile, session, custom-save, override-save, and validator tests. |
| 8. Private skill writes | Skill detail includes scope; update/delete resolve scope or accept explicit shared/user scope while retaining owner isolation and current shared-edit permissions. | Private skill edit/delete and cross-owner denial tests. |
| 9. Paging | Cosmos continuation tokens flow through the API; frontend follows all pages, including agent-associated conversation cleanup. | Repository page-token contract, API page traversal, frontend opaque-cursor test. |
| 10. Authentication | One AuthProvider owns initialization/state; requests acquire current tokens through its provider. Protected data loads only after authentication. Legacy standalone token storage is removed. | Fresh-token-per-request test; auth-disabled browser flows; typecheck. Live MSAL remains an integration gate. |
| 11. Session construction | Custom, built-in, and overridden agents share runtime construction, persistence, registration, response assembly, and rollback. Capability names come from the constructed runtime. | Session/API suite and rollback tests. |
| 12. Definition snapshots | Newly saved custom references contain identities only. Owner-scoped runtime resolution retrieves current definitions; legacy inline data remains accepted and validated. | Identity-only persistence and owner-scoped hydration tests. |
| 13. Cosmos bootstrap | User-scoped repositories share the container base; Cosmos shutdown clears all user repository singleton caches. | Repository/API regressions and cache-reset test. |
| 14. Streaming and HTTP | Structured agent events and request-local results replace the global result attribute. HTTP/error handling is shared; eventsource-parser handles SSE framing and malformed/truncated responses fail visibly. | Structured/SSE parity, split-frame, callback-error, truncation, and malformed-data tests. |
| 15. Dead paths | Removed SQL helpers, unused Search client factory, duplicate capability derivation, write-only chat metadata, and unused Semantic Kernel/PDF/ODBC/MSAL React dependencies. Direct runtime dependencies are declared explicitly. | Exact uv sync; full offline suite; frontend tests/build. |
| 16. Module boundaries | Autonomous routes invoke their own imported runner; non-builder CSS moved to existing owning modules; Admin and Autonomous pages load as separate chunks. | Route tests; desktop/mobile browser coverage; production build without chunk-size warnings. |

## Deletion Follow-Up

- Removed entry-point compatibility re-exports; tests import handlers and state from their actual owners.
- Removed empty `prompt_manifest` runtime/session state and unused `sub_agent_mcp_tools` aggregation. The trace schema retains an empty manifest for compatibility; resource ownership remains centralized in session setup.
- Deleted `known_tool_names_from_profiles`, whose argument was unused, and use the registered tool catalog directly. Removed the now-unused custom-session profile-data parameter.
- Reused shared MCP validation for connection tests and moved error sanitization into the MCP module.
- Routed view-data requests through shared authenticated fetch while retaining structured refusals and avoiding global transport toasts on that path.

## Package-Backed Simplification

- Replaced four handwritten YAML emitters and manual profile assembly with the frontend `yaml` package. Round-trip tests preserve MCP tool arrays, timeouts, booleans, empty strings, and exact multiline prompt content; exported formatting may change.
- Replaced skill metadata's line splitting and quote stripping with existing PyYAML `safe_load`. Folded descriptions and quoted values work; malformed YAML, non-mapping metadata, and non-string name/description values are skipped during seeding.
- Reused FastAPI's `jsonable_encoder` for structured tool results, including dates and UUIDs. Removed the frontend regex-based Python-repr converter: JSON is pretty-printed, other text is displayed verbatim. False and zero results no longer disappear.
- Tool-result regression tests exposed a streaming variable shadowing the caller-owned aggregate. Separated per-tool output from the aggregate and verified both string/dictionary outputs across function and MCP result events.
- Only one new dependency was needed (`yaml`); the backend uses existing packages. Its serializer adds about 16 KB gzipped to the lazy Admin chunk without growing the main entry chunk.

## Five-Round Follow-Up

1. MCP request contracts: normalized omitted HTTP transport so accepted servers are actually connected; corrected case-insensitive bearer parsing for connection tests.
2. Tool identity: reserved suffix space within the 64-character tool-name limit and aligned frontend fallback names/descriptions with the backend. Added long-name collision coverage in both tiers.
3. Durable deletion: required the installed history provider's `clear` contract instead of silently skipping history deletion. Verified failed clearing preserves the conversation for retry, and successful retry removes runtime state. Corrected the view-test provider fixture.
4. Request boundaries: malformed session/message JSON and non-string message content return 400 rather than crashing. Applied bearer parsing to session creation and tightened a test that previously allowed an invalid-profile 500.
5. Final regression: 409 Python/browser/emulator cases and 9 frontend tests pass; build, lint, diagnostics, and diff checks pass. No additional failures surfaced. Stopped at the requested five-round cap; this is not a claim of exhaustive defect freedom.

## Second Five-Round Follow-Up

1. Streaming errors: stopped returning raw exception text to chat clients. A regression with a synthetic credential reproduces the disclosure; the retry/image slice passes 72 tests after correction.
2. Text validation: custom names and prompts now require strings rather than silently stringifying JSON objects, lists, numbers, or booleans. Ten new API cases cover invalid types; 79 focused tests pass.
3. Conversation deletion race: replaced the activity update's upsert with a replace, treating a concurrent missing record as a no-op. A real-emulator regression reproduces and prevents recreation of a deleted conversation; 27 focused tests pass with the known paging xfail.
4. Frontend lifecycle race: serialized session startup and cleanup within each chat hook. Desktop/mobile coverage delays one resume while requesting another for the same conversation, verifying stale cleanup finishes before replacement creation. This does not coordinate separate browser tabs or backend workers.
5. MCP allowlists: preserved explicit empty allowlists through parsing and SDK construction instead of converting them to unrestricted defaults. Six new cases cover absent, empty, and populated allowlists for HTTP and stdio; 22 focused tests pass. No override fields were added without evidence of a supported UI contract.

Final combined result: 427 Python/browser/emulator tests and 9 frontend tests pass. Build, lint, editor diagnostics, and diff checks pass. Stopped after the five requested additional review rounds; live-service limitations below remain.

## Third Five-Round Follow-Up

1. Client authentication: preserved an explicitly supplied credential instead of overwriting it with the default Entra provider. Agent-factory coverage passes 10 tests. Mixed primary/secondary key and managed-identity configurations remain unverified.
2. Delegated tool names: reserved existing parent tool names when suffixing delegate names, preventing a delegate from shadowing a parent function. Runtime and name-derivation coverage passes 29 tests. Dynamically discovered MCP function-name collisions are not covered by this change.
3. MCP configuration: malformed allowlists now fail closed in request validation and configuration parsing rather than becoming unrestricted. Five new cases verify rejection before connection; 88 focused tests pass.
4. Concurrent conversation updates: added ETag conditions to activity updates. An emulator regression reproduced stale title overwrites and now verifies that newer state survives; conflicting best-effort activity updates are discarded. The conversation slice passes 28 tests with the existing paging xfail.
5. MCP request boundary: malformed JSON now returns HTTP 400, consistent with session endpoints. Six new request cases verify the connector is never called; 9 focused endpoint tests pass.

Final combined result: 441 Python/browser/emulator tests and 9 frontend tests pass, with clean editor diagnostics and diff checks. No frontend source changed in this batch; the previously verified build and lint results remain applicable. Stopped at five additional rounds, without claiming exhaustive defect freedom.

## Five Cleanup Passes

1. Removed duplicate delegate-name state and a redundant empty-result branch. Names now come from successfully constructed tools; 29 focused tests pass.
2. Reviewed persistence hooks without introducing a shared abstraction. Removed stale documentation claiming saves were optimistic and backgrounded; TypeScript and 9 frontend tests pass.
3. Reduced scheduler shutdown to task cancellation, deleting the stop event, timeout wrapper, and duplicate cancellation handler. Replaced sleep-based test timing with deterministic checks for shutdown during polling and idle waits; 28 focused tests pass.
4. Deleted 13 low-value tests of SDK constructors, test-local arithmetic, function signatures/existence, and a hardcoded constant. Retained application regressions for retry classification, error disclosure, cleanup, usage accumulation, and input limits; 92 focused tests pass.
5. Replaced dynamic delegate kwargs assembly with explicit SDK arguments and consolidated skill-provider construction. Added built-in delegate coverage with and without resolved resources, including zero temperature; 33 focused tests pass.

Combined verification: 431 tests pass, with the existing emulator paging xfail; 9 frontend tests, TypeScript, lint, editor diagnostics, and diff checks pass. The lower test count reflects 13 removals and 3 added cases. No dependencies or new abstraction layers were added. Frontend changes were comments only, so no new production build was needed.

## Delegate Cleanup Follow-Through

- Co-located resolved delegates with derived tool metadata, removing a parallel list and traversal. Extended collision coverage with a skipped reference between valid delegates.
- Confirmed custom reference parsing guarantees a dictionary, not typed contents. Retained legacy string/temperature normalization; removed redundant skill conversion and copying.
- Removed unused reference-list copies and guaranteed-field fallbacks from runtime construction. Tests cover profile defaults, explicit overrides, and non-mutation.
- Replaced repeated post-parser attribute probes and shape checks with the established `AgentRef` union. Owner hydration, prompt checks, and missing-profile handling remain.
- The full suite exposed an incomplete profile test double; replaced it with `AgentProfile`. Final result: 436 passed, 1 known emulator xfail, clean diagnostics and diff checks. No frontend behavior changed.

## Final Verification

### Defensive-Code Deletion Pass

- Removed four single-caller HTTP helpers, unused retry metadata, unreachable error fallbacks, and JSON handling for bodyless responses.
- Reused `requestJson` and removed client-side defaults for fields guaranteed by the backend. Corrected the browser fixture to return the real empty view-list shape.
- Removed six session-related state variables, deriving capabilities from the session response and deleting the unused conversation ID. Deleted the duplicate session-start and chat-state interfaces and unused hook methods.
- This pass alone removes **149 application lines**, adds **3 test-fixture lines**, and introduces no dependencies or abstractions. Auth, cancellation, resource cleanup, and ownership protections remain intact.

### Tool-Event Bookkeeping Pass

- Removed duplicate backend tool-event and argument collections; one ordered dictionary now owns each event and its accumulated arguments.
- Consolidated four frontend assistant-message update copies and two tool-result assignment paths. Removed the nested image-URL function and unused notification/context-provider parameters.
- Removed **62 net application lines**, with no new dependencies. Extended existing tests for fragmented/interleaved calls and matched/fallback results on desktop/mobile; all 391 Python/browser tests and 8 frontend tests pass, with the existing emulator expected failure unchanged.

- `uv run --frozen --group dev pytest -q`: **436 passed, 1 xfailed**, including desktop/mobile browser scenarios and real-emulator coverage. Two upstream experimental-feature warnings remain.
- `npm --prefix frontend test`: TypeScript passes; **9 frontend tests pass** using Node's built-in runner and the existing Vite loader, with unnecessary dependency scanning disabled.
- `npm --prefix frontend run lint`: passes.
- `npm --prefix frontend run build`: passes. Admin (~93 KB) and Autonomous (~10 KB) are separate chunks; no chunk exceeds the warning threshold. CSS size is unchanged at ~62 KB.
- `npm --prefix frontend audit --omit=dev --audit-level=high`: **0 production vulnerabilities**. Installation reports 9 development-inclusive advisories; broad tooling upgrades were not part of this remediation.
- Editor diagnostics: no errors. `git diff --check`: passes.
- The emulator was started with the same script used by Ctrl+Shift+B and remains running. The script recreated the existing container to repair missing published ports, resetting local emulator data.
- Emulator tests now exercise execution-lease contention and owner-checked release. The expected failure records a directly reproduced vNext limitation: ordered queries ignore `max_item_count` and return all records without a continuation token, while unordered queries honor it. Ordered pagination still needs verification against the Cosmos service; no production workaround was added solely for the emulator.

## Compatibility and Rollout

1. No destructive migration is required. Existing inline custom references remain readable and become identity-only on save. Resumed conversations use current owner-scoped definitions.
2. Saves reject invalid or missing capabilities. The existing resume behavior that drops deleted skills with a warning is deliberately retained, so removing a skill does not strand an old conversation.
3. Shared configuration retains its existing authenticated-user editing policy; this change does not introduce an administrator role.
4. Before deployment, verify ordered pagination against Cosmos service, manual/scheduled overlap across two workers, and execution-lease expiry after process termination. The passing emulator suite does not establish these remaining properties.
5. In an authenticated environment, verify MSAL silent renewal and interaction-required redirect behavior, then check a real MCP connection and cancellation. These live integrations were not validated here.
6. Keep the reduced lockfile and rebuild both services together. `AUTONOMOUS_RUN_TIMEOUT_SECONDS` is a positive integer, default 840; its execution lease expires 60 seconds later as a crash-recovery fallback.

During wrapper removal, one test still patched the former entry-point export and
attempted a model call that returned 401. Its patch now targets the actual route
owner; subsequent focused and full runs passed. No successful live-model behavior
is claimed from that run.