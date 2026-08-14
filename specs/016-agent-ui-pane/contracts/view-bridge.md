# Contract: View Bridge (host ↔ sandboxed view)

**Feature**: 016-agent-ui-pane

The only channel between a rendered view and the rest of the world. The view has an opaque origin
and `connect-src 'none'`, so this bridge is not one way among several — it is the *sole* path.

---

## Frame construction (host side)

```html
<iframe
  sandbox="allow-scripts"
  title="Agent-generated view: {title}"
  srcdoc="{CSP_META}{BOOTSTRAP_SCRIPT}{agent_html}"
></iframe>
```

- **No `allow-same-origin`** — this is the security boundary. Adding it would let the frame remove
  its own sandbox and reach the host. It must never be added.
- No `allow-popups`, `allow-forms`, `allow-modals`, or `allow-top-navigation`.
- `CSP_META` is prepended by the host and is the first element in the document:

  ```html
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; form-action 'none'; base-uri 'none'; frame-src 'none'; connect-src 'none'">
  ```

  CSP policies combine conjunctively, so any policy the agent adds can only tighten this one.

---

## Bootstrap API (host-injected, available to agent markup)

```js
window.agentData(tool, args) // → Promise<unknown>, rejects with { code, message }
```

This is the call the tool docstring instructs the model to emit. It wraps the envelope below,
generates the `requestId`, and resolves or rejects the matching response. The docstring in
`render_agent_view` is the single source of truth for how to use it (Constitution II).

---

## Envelope: view → host

```json
{ "v": 1, "type": "agentui.request", "requestId": "r-7", "tool": "get_user_profile", "args": {} }
```

```json
{ "v": 1, "type": "agentui.ready" }
```

`agentui.ready` is optional and lets the host know the view mounted, for the loading state.

## Envelope: host → view

```json
{ "v": 1, "type": "agentui.response", "requestId": "r-7", "ok": true, "data": {}, "truncated": false }
```

```json
{ "v": 1, "type": "agentui.response", "requestId": "r-7", "ok": false,
  "error": { "code": "not_permitted", "message": "That data is not available to this view." } }
```

`error.code` mirrors the REST broker codes: `not_permitted`, `invalid_arguments`,
`session_inactive`, `rate_limited`, `tool_failed`.

---

## Host-side validation (every inbound message)

1. `event.source === iframeRef.current.contentWindow` — identity, not origin. Opaque-origin frames
   report `event.origin === "null"`, so an origin string check is not a usable control and must not
   be relied on.
2. `data.v === 1` and `data.type === "agentui.request"`; anything else is dropped silently.
3. `tool` is a non-empty string; `args` is a plain object.
4. `requestId` is a string, unseen, and the in-flight count for this view is within bounds.
5. Forward to `POST /api/sessions/{id}/views/{view_id}/data`. **The client performs no permission
   check of its own** — it is a transport. The server is the authority (research.md D2).
6. Reply only into the originating frame's `contentWindow` with `targetOrigin: "*"`, which is
   required for opaque-origin recipients and is safe because the frame is `srcdoc` content the host
   itself mounted.

## Host-side outbound rules

- Never post host state, tokens, user identity, or session ids into the frame.
- Response payloads carry tool output only.
- Tear down the listener and drop pending requests when the view unmounts or is replaced.
