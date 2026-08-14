# Contract: `render_agent_view` Tool

**Feature**: 016-agent-ui-pane

Registered in `app_context.function_tool_registry()` and built by
`tools.build_render_agent_view_tool(user_id, session_id)`. Granted to an agent by adding
`render_agent_view` to its `tools:` list in `config/agents.yaml` (or to a custom agent
definition). All usage guidance lives in the Python docstring — never restated in YAML
(Constitution II).

---

## Signature

```python
async def render_agent_view(title: str, html: str) -> dict[str, Any]
```

| Parameter | Rules |
|---|---|
| `title` | Non-empty after trimming, ≤ 120 chars. Shown in the pane header and the transcript marker. |
| `html` | Self-contained markup, ≤ `MAX_AGENT_VIEW_CHARS`. Inline `<style>` and `<script>` are supported. External URLs of any kind will not load. |

## Returns

```json
{ "status": "rendered", "view_id": "0f1e...", "title": "Readiness by unit", "chars": 18422 }
```

```json
{ "status": "rejected", "reason": "too_large", "limit": 250000, "chars": 361204,
  "message": "View exceeds the size limit. Reduce inline data or split into a smaller view." }
```

The result is intentionally tiny: the model just authored the HTML, so echoing it back would
duplicate it in context on the next turn (research.md D3). Rejections are phrased so the model can
correct and retry without further instruction.

---

## Docstring requirements

The docstring is what the model actually reads, so it must state:

- The view renders in a side pane next to the chat, isolated from the application.
- Everything must be **self-contained**: inline CSS, inline SVG, `data:` images. External
  scripts, stylesheets, fonts, and images will silently fail to load.
- To show live data, call `await window.agentData("<tool_name>", { ...args })`, which resolves with
  that tool's result and rejects with `{code, message}`.
- Only the tools this agent already has can be requested; anything else is refused.
- Still answer in chat — the view supplements the reply, it does not replace it.
- No emoji in rendered UI (Constitution Visual Verification rules); use text indicators.

## Session binding

`build_tool_instances` already accepts `session_id`; `FunctionToolRegistration` gains a
`session_scoped` flag so this factory receives `(user_id, session_id)` while existing
user-only factories keep their current single-argument shape. The tool closes over both, so a view
is always written into the correct conversation partition without the model supplying — or being
able to forge — either value.

## Behavior

1. Validate `title` and `html`; on failure return `status: "rejected"` and write nothing.
2. Persist an Agent View document (data-model.md) under the bound `user_id` / `conversation_id`.
3. Evict the oldest view if the conversation exceeds `MAX_AGENT_VIEWS_PER_CONVERSATION`.
4. Return the acknowledgement, which `streaming.py` turns into an `agent_view` SSE event.

## Broker exclusion

`render_agent_view` is excluded from the set of tools a view may call through the bridge, so a view
cannot re-render itself in a loop.
