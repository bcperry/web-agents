# Quickstart: Agent Dynamic UI Pane

**Feature**: 016-agent-ui-pane

How to enable, run, and verify the feature locally. Assumes the repo is set up per
[README.md](../../README.md).

---

## 1. Enable the capability for an agent

Add the tool to a profile's tool list in [config/agents.yaml](../../config/agents.yaml):

```yaml
profiles:
  hybrid:
    tools:
      - get_user_profile
      - render_agent_view   # <-- grants the dynamic UI pane
```

No other configuration is required. Removing the entry removes the capability for new
conversations; existing views remain viewable (FR-001, US3).

## 2. Optional limits

Defaults are fine for local work. To exercise the limit paths:

```bash
export MAX_AGENT_VIEW_CHARS=2000              # force the oversize rejection path
export MAX_AGENT_VIEWS_PER_CONVERSATION=3     # force FIFO eviction
export MAX_VIEW_DATA_REQUESTS_PER_MINUTE=5    # force the rate-limit refusal
```

## 3. Run

```bash
bash scripts/start_cosmos_emulator.sh
cd frontend && npm install && npm run build && cd ..
AUTH_DISABLED=true uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The `agent-views` container is created on first use by `create_container_if_not_exists`, so the
emulator needs no manual setup.

## 4. Try it

Open `http://localhost:8000`, pick the enabled agent, and ask for something visual:

> Show me a table of my saved profile fields, with a refresh button.

Expected:

1. A `render_agent_view` tool step appears in the transcript.
2. The right-hand pane opens with the rendered view, labeled as agent-generated.
3. Clicking refresh calls `agentData("get_user_profile", {})` and updates the view in place.
4. Collapse the pane, reload the page, reopen the conversation — the view is restored.

## 5. Verify the security contract

Ask the agent to render a view containing these three probes (or use the test fixture):

```js
fetch('https://example.com').catch(e => show('network blocked: ' + e));
try { show('parent: ' + parent.document.title); } catch (e) { show('host DOM blocked'); }
try { show('storage: ' + localStorage.length); } catch (e) { show('storage blocked'); }
await window.agentData('some_tool_the_agent_does_not_have', {})
  .catch(e => show('refused: ' + e.code));
```

All four must fail: network blocked by CSP, host DOM and storage blocked by the opaque origin, and
the tool request refused with `not_permitted` (SC-002, SC-003).

## 6. Tests

```bash
uv run pytest tests/test_agent_views.py tests/test_agent_views_api.py tests/test_streaming.py
cd frontend && npm test        # tsc -b
```

Backend tests must cover: ownership rejection, `not_permitted` refusal returning zero data,
`session_inactive` on a dead session, rate limiting, oversize rejection, FIFO eviction, and
`agent_view` SSE emission.

## 7. Visual verification (required — Constitution)

```bash
cd frontend && npm run build && cd ..
AUTH_DISABLED=true uv run uvicorn main:app --host 0.0.0.0 --port 8000 &
uv run python scripts/capture_agent_view_screenshots.py --base-url http://localhost:8000
```

Capture and review: pane open with a rendered view, pane collapsed, view switcher with two views,
the render-failure error state, and the responsive layouts at 768×1024 and 360×640. Each
screenshot must be viewed and assessed for clipping, contrast, alignment, and missing assets
before the work is considered done.

## 8. Deploy notes

`infra/modules/cosmos/main.tf` gains an `agent_views` container partitioned by `/user_id`. Run
`terraform plan` and review before applying — no other infrastructure changes are needed.
