import { useCallback, useEffect, useMemo, useRef } from 'react';
import type { AgentViewBridgeResponse } from '../types/api';
import { requestAgentViewData } from '../api/client';

/**
 * Renders agent-authored HTML inside an opaque-origin sandbox.
 *
 * Two controls make that safe, and both are load-bearing:
 *   1. `sandbox="allow-scripts"` WITHOUT `allow-same-origin` gives the frame an
 *      opaque origin, so it cannot read the host DOM, host storage, or cookies.
 *      Adding `allow-same-origin` would let the frame remove its own sandbox.
 *   2. The host CSP below is the first element in the document, and CSP policies
 *      combine conjunctively, so anything the agent adds can only tighten it.
 *      `connect-src 'none'` is what removes network egress entirely.
 *
 * The only way out is `window.agentData()`, which posts to this component; the
 * backend then decides what may actually run.
 *
 * See specs/016-agent-ui-pane/contracts/view-bridge.md.
 */

const HOST_CSP =
  "<meta http-equiv=\"Content-Security-Policy\" content=\"" +
  "default-src 'none'; " +
  "script-src 'unsafe-inline'; " +
  "style-src 'unsafe-inline'; " +
  "img-src data:; " +
  "font-src data:; " +
  "form-action 'none'; " +
  "base-uri 'none'; " +
  "frame-src 'none'; " +
  "connect-src 'none'" +
  '">';

const BASE_STYLE_TEMPLATE =
  '<style>:root{__PALETTE__}' +
  'html,body{margin:0;padding:0;background:transparent;color:var(--text);' +
  "font-family:'Segoe UI',system-ui,sans-serif;font-size:14px;line-height:1.5}" +
  'body{padding:16px}' +
  'a{color:var(--accent)}' +
  'th{color:var(--muted);font-weight:600}' +
  'table{border-collapse:collapse}' +
  'th,td{border-color:var(--border)}' +
  '</style>';

/**
 * The frame has an opaque origin and cannot read the host stylesheet, so the
 * resolved theme colors are inlined into the document instead. The tool docstring
 * tells the agent to style with these variables.
 */
function hostPalette(): string {
  const styles = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) =>
    (styles.getPropertyValue(name) || fallback).trim();
  return [
    `--text:${read('--text-primary', '#f3f2f1')}`,
    `--muted:${read('--text-muted', '#c8c6c4')}`,
    `--border:${read('--border-olive', '#3b3a39')}`,
    `--accent:${read('--accent-gold', '#0078d4')}`,
    `--panel:${read('--bg-panel', '#252423')}`,
  ].join(';');
}

const BRIDGE_SCRIPT = `<script>
(function () {
  var pending = {};
  var seq = 0;
  window.addEventListener('message', function (event) {
    var msg = event.data;
    if (!msg || msg.v !== 1 || msg.type !== 'agentui.response') return;
    var entry = pending[msg.requestId];
    if (!entry) return;
    delete pending[msg.requestId];
    if (msg.ok) entry.resolve(msg.data);
    else entry.reject(msg.error || { code: 'tool_failed', message: 'Request failed.' });
  });
  window.agentData = function (tool, args) {
    return new Promise(function (resolve, reject) {
      var requestId = 'r-' + (++seq);
      pending[requestId] = { resolve: resolve, reject: reject };
      parent.postMessage(
        { v: 1, type: 'agentui.request', requestId: requestId, tool: tool, args: args || {} },
        '*'
      );
    });
  };
  parent.postMessage({ v: 1, type: 'agentui.ready' }, '*');
})();
</script>`;

interface AgentViewFrameProps {
  sessionId: string | null;
  viewId: string;
  title: string;
  html: string;
}

export function AgentViewFrame({ sessionId, viewId, title, html }: AgentViewFrameProps) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const theme = document.documentElement.getAttribute('data-theme') || 'dark';
  const srcDoc = useMemo(() => {
    void theme; // rebuild the document when the host theme changes
    const style = BASE_STYLE_TEMPLATE.replace('__PALETTE__', hostPalette());
    return `${HOST_CSP}${style}${BRIDGE_SCRIPT}${html}`;
  }, [html, theme]);

  const reply = useCallback((message: AgentViewBridgeResponse) => {
    // targetOrigin must be '*': an opaque-origin frame has no origin to name.
    frameRef.current?.contentWindow?.postMessage(message, '*');
  }, []);

  useEffect(() => {
    const seen = new Set<string>();

    async function onMessage(event: MessageEvent) {
      // Identity, not origin: sandboxed frames always report origin "null".
      if (!frameRef.current || event.source !== frameRef.current.contentWindow) return;
      const msg = event.data;
      if (!msg || msg.v !== 1 || msg.type !== 'agentui.request') return;
      const { requestId, tool, args } = msg;
      if (typeof requestId !== 'string' || seen.has(requestId)) return;
      if (typeof tool !== 'string' || (args && typeof args !== 'object')) return;
      seen.add(requestId);

      if (!sessionId) {
        reply({
          v: 1,
          type: 'agentui.response',
          requestId,
          ok: false,
          error: { code: 'session_inactive', message: 'This conversation is no longer active.' },
        });
        return;
      }

      const result = await requestAgentViewData(sessionId, viewId, tool, args || {});
      reply(
        result.ok
          ? {
              v: 1,
              type: 'agentui.response',
              requestId,
              ok: true,
              data: result.data,
              truncated: Boolean(result.truncated),
            }
          : {
              v: 1,
              type: 'agentui.response',
              requestId,
              ok: false,
              error: result.error || { code: 'tool_failed', message: 'Request failed.' },
            },
      );
    }

    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [sessionId, viewId, reply]);

  return (
    <iframe
      ref={frameRef}
      className="agent-view-frame"
      // Never add allow-same-origin: it would dissolve the isolation boundary.
      sandbox="allow-scripts"
      title={`Agent-generated view: ${title}`}
      srcDoc={srcDoc}
    />
  );
}
