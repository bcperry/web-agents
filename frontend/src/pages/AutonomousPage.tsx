import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type {
  AgentProfile,
  AutonomousDirective,
  AutonomousRun,
  ConversationIndexEntry,
} from '../types/api';
import {
  AuthError,
  fetchAutonomousDirectives,
  fetchAutonomousRuns,
  fetchProfiles,
  listConversations,
  triggerAutonomousRun,
} from '../api/client';
import { useChat } from '../hooks/useChat';
import { useAuth } from '../hooks/useAuth';
import { emitToast } from '../hooks/useToast';
import { ChatMessage } from '../components/ChatMessage';
import { ChatInput } from '../components/ChatInput';
import { SettingsMenu } from '../components/SettingsMenu';
import { getRuntimeConfigSnapshot } from '../config/runtimeConfig';
import type { AdminOpenOptions } from './AdminPage';

interface AutonomousPageProps {
  onBack: () => void;
  onOpenAdmin: (opts?: AdminOpenOptions) => void;
}

function formatDateTime(iso: string): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return (
    date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) +
    ' ' +
    date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  );
}

function statusClass(status: string): string {
  const s = status.toLowerCase();
  if (s === 'success' || s === 'completed' || s === 'ok' || s === 'sent') return 'ok';
  if (s === 'failure' || s === 'failed' || s === 'error') return 'err';
  return 'warn';
}

// Extract the "Bottom Line Up Front" summary for the collapsed card preview.
// Prefer an explicit "BLUF" line (tolerating leading markdown markers like "## "
// or "**"); fall back to the first paragraph when the report has no BLUF marker.
// Markdown markers are stripped and whitespace collapsed to a clean one-liner.
function extractBluf(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return '';
  const blufMatch = trimmed.match(/(?:^|\n)[ \t>#*_]*BLUF\b[ :.\-—*]*([\s\S]*?)(?:\n\s*\n|$)/i);
  const block = blufMatch ? blufMatch[1] : (trimmed.split(/\n\s*\n/)[0] ?? '');
  return block.replace(/[*_`#>]/g, '').replace(/\s+/g, ' ').trim();
}

export function AutonomousPage({ onBack, onOpenAdmin }: AutonomousPageProps) {
  const [enabled, setEnabled] = useState(false);
  const [schedulerEnabled, setSchedulerEnabled] = useState(false);
  const [directives, setDirectives] = useState<AutonomousDirective[]>([]);
  const [runs, setRuns] = useState<AutonomousRun[]>([]);
  const [dutyProfile, setDutyProfile] = useState<AgentProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [authError, setAuthError] = useState(false);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const startedRef = useRef(false);

  const { messages, isStreaming, session, startSession, endSession, send } = useChat();
  const { user, logout, classificationBanner } = useAuth();
  const { appName, appLogo } = getRuntimeConfigSnapshot();

  // End the chat session when leaving the page, regardless of identity churn.
  const endSessionRef = useRef(endSession);
  endSessionRef.current = endSession;
  useEffect(() => () => { void endSessionRef.current(); }, []);

  // Load directives, run history, and the duty officer profile on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      // Directives + profiles drive the page and chat; load them together.
      try {
        const [dir, profResp] = await Promise.all([
          fetchAutonomousDirectives(),
          fetchProfiles(),
        ]);
        if (cancelled) return;
        setEnabled(dir.enabled);
        setSchedulerEnabled(dir.schedulerEnabled);
        setDirectives(dir.directives);

        const primary = dir.directives.find((d) => d.enabled) ?? dir.directives[0] ?? null;
        if (primary) {
          // The directive's profileId may be a display name (e.g. "G-6 Signal")
          // rather than a logical id (e.g. "g6-signal"). Match by id first, then
          // by name, so dutyProfile carries the canonical id the backend stores
          // on conversations — otherwise resume can never find prior chats.
          const resolved =
            profResp.profiles.find((p) => p.id === primary.profileId) ??
            profResp.profiles.find((p) => p.name === primary.profileId) ?? {
              id: primary.profileId,
              name: primary.profileId,
              description: primary.instructionSummary,
              icon: '/icons/custom.svg',
              starters: [],
            };
          setDutyProfile(resolved);
        }
      } catch (err) {
        if (err instanceof AuthError) setAuthError(true);
        console.error('Failed to load autonomous directives:', err);
      }
      // Run history is best-effort; a store outage must not blank the page.
      try {
        const runResp = await fetchAutonomousRuns(50);
        if (!cancelled) setRuns(runResp.runs);
      } catch (err) {
        console.error('Failed to load autonomous runs:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Auto-start the duty officer chat once the profile resolves. Resume the most
  // recent existing conversation for this agent instead of spawning a fresh blank
  // chat on every visit; only create a new session when none exists yet.
  useEffect(() => {
    if (!dutyProfile || startedRef.current) return;
    startedRef.current = true;
    void (async () => {
      let resume: ConversationIndexEntry | undefined;
      try {
        const conversations = await listConversations(50);
        resume = conversations
          .filter((c) =>
            (dutyProfile.customAgent?.id && c.customAgentId === dutyProfile.customAgent.id) ||
            c.profileId === dutyProfile.id ||
            c.profileName === dutyProfile.name,
          )
          .sort((a, b) => b.lastActivityAt.localeCompare(a.lastActivityAt))[0];
      } catch (err) {
        console.error('Failed to list conversations for duty officer resume:', err);
      }
      await startSession(dutyProfile, resume);
    })();
  }, [dutyProfile, startSession]);

  // Keep the chat scrolled to the latest message.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const refreshRuns = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await fetchAutonomousRuns(50);
      setRuns(r.runs);
    } catch (err) {
      console.error('Failed to refresh autonomous runs:', err);
    } finally {
      setRefreshing(false);
    }
  }, []);

  // Trigger an on-demand cycle (same behavior as the scheduled timer). The
  // returned run is surfaced immediately at the top of RECENT ACTIVITY.
  const handleRunNow = useCallback(
    async (directiveId: string) => {
      if (triggeringId) return;
      setTriggeringId(directiveId);
      try {
        const run = await triggerAutonomousRun(directiveId);
        setRuns((prev) => [run, ...prev.filter((r) => r.id !== run.id)]);
        setExpandedRunId(run.id);
        if (run.status !== 'success') {
          emitToast({
            message: `Duty Officer run finished with status: ${run.status || 'unknown'}.`,
            type: 'warning',
          });
        }
      } catch (err) {
        emitToast({
          message: err instanceof Error ? err.message : 'Failed to trigger autonomous run.',
          type: 'error',
        });
      } finally {
        setTriggeringId(null);
      }
    },
    [triggeringId],
  );

  const askAboutRun = useCallback(
    (run: AutonomousRun) => {
      if (!session || isStreaming) return;
      const when = formatDateTime(run.startedAt);
      // This chat is a separate session from the autonomous run, so the agent has
      // no memory of it. Inline the run's own output as context so it can answer.
      const report = (run.responseText || '').trim();
      const message = report
        ? `Here is the watch note from the autonomous run on ${when} (status: ${run.status}):\n\n` +
          `"""\n${report}\n"""\n\n` +
          `Summarize the key points and tell me anything I should act on.`
        : run.error
          ? `The autonomous run on ${when} failed with this error:\n\n` +
            `"""\n${run.error}\n"""\n\n` +
            `Explain what likely went wrong and what I should check.`
          : `The autonomous run on ${when} (status: ${run.status}) produced no report text. ` +
            `What might that indicate, and what should I check?`;
      void send(message);
    },
    [session, isStreaming, send],
  );

  const canChat = Boolean(dutyProfile);

  return (
    <div className="auto-page">
      <header className="auto-header">
        <button className="auto-back-btn" onClick={onBack} type="button">
          BACK TO CHAT
        </button>
        <div className="auto-header-brand">
          <img className="auto-header-logo" src={appLogo} alt={appName} />
          <h2 className="auto-title">DUTY OFFICER</h2>
        </div>
        <div className="auto-header-actions">
          <SettingsMenu userEmail={user?.email} onOpenAdmin={onOpenAdmin} onLogout={logout} />
        </div>
      </header>

      {authError ? (
        <div className="auth-error-panel">
          <h2>Unauthorized</h2>
          <p>Your session has expired or your credentials are invalid.</p>
          <button className="login-btn" onClick={logout} type="button">
            Log In
          </button>
        </div>
      ) : (
        <div className="auto-body">
          <aside className="auto-activity">
            <div className={`auto-status ${!enabled ? 'off' : schedulerEnabled ? 'ok' : 'warn'}`}>
              <span className="auto-status-dot" />
              <span>
                {!enabled
                  ? 'AUTONOMOUS MODE DISABLED'
                  : schedulerEnabled
                    ? 'AUTONOMOUS MODE ACTIVE — SCHEDULER RUNNING'
                    : 'SCHEDULER OFF — MANUAL RUNS ONLY'}
              </span>
            </div>
            {enabled && !schedulerEnabled && (
              <p className="auto-status-note">
                The unattended scheduler is disabled on this server, so automations only fire when you
                press <strong>RUN NOW</strong>. To run them on their schedule, start the backend with{' '}
                <code>AUTONOMOUS_SCHEDULER_ENABLED=true</code>.
              </p>
            )}

            <section className="auto-section">
              <div className="auto-section-head">
                <h3 className="auto-section-title">STANDING ORDERS</h3>
                <button
                  className="auto-new-btn"
                  type="button"
                  onClick={() => onOpenAdmin({ tab: 'automations', automationCreate: true })}
                  title="Create a new automation in Admin"
                >
                  + NEW
                </button>
              </div>

              {directives.length === 0 ? (
                <div className="auto-empty-line">No automations configured.</div>
              ) : (
                directives.map((d) => (
                  <div key={d.id} className="auto-directive">
                    <div className="auto-directive-top">
                      <span className="auto-directive-id">{d.id}</span>
                      <span className={`auto-badge ${d.enabled ? 'ok' : 'off'}`}>
                        {d.enabled ? 'ENABLED' : 'PAUSED'}
                      </span>
                    </div>
                    <div className="auto-directive-summary">{d.instructionSummary}</div>
                    <div className="auto-directive-meta">
                      <span>Agent: {d.profileId}</span>
                      {d.schedule && <span>Schedule: {d.schedule}</span>}
                      {enabled && schedulerEnabled && d.enabled && d.nextRun && (
                        <span>Next review: {formatDateTime(d.nextRun)}</span>
                      )}
                      {enabled && !schedulerEnabled && d.enabled && d.schedule && (
                        <span className="auto-meta-warn">Scheduler off — RUN NOW only</span>
                      )}
                      <span>Notify: {d.notify}</span>
                    </div>
                    <div className="auto-directive-controls">
                      {enabled && d.enabled && (
                        <button
                          className="auto-run-now"
                          type="button"
                          onClick={() => handleRunNow(d.id)}
                          disabled={Boolean(triggeringId)}
                        >
                          {triggeringId === d.id ? 'RUNNING REVIEW…' : 'RUN NOW'}
                        </button>
                      )}
                      <button
                        className="auto-btn-ghost"
                        type="button"
                        onClick={() => onOpenAdmin({ tab: 'automations', automationEditId: d.id })}
                        title="Edit this automation in Admin"
                      >
                        EDIT
                      </button>
                    </div>
                  </div>
                ))
              )}
            </section>

            <section className="auto-section">
              <div className="auto-section-head">
                <h3 className="auto-section-title">RECENT ACTIVITY</h3>
                <button
                  className="auto-refresh"
                  onClick={refreshRuns}
                  disabled={refreshing}
                  type="button"
                  title="Refresh activity"
                  aria-label="Refresh activity"
                >
                  {refreshing ? '…' : '⟳'}
                </button>
              </div>
              {loading ? (
                <div className="auto-empty-line">Loading…</div>
              ) : runs.length === 0 ? (
                <div className="auto-empty-line">No autonomous runs yet.</div>
              ) : (
                runs.map((run) => {
                  const expanded = expandedRunId === run.id;
                  const bluf = extractBluf(run.responseText || '');
                  return (
                    <div key={run.id} className="auto-run">
                      <button
                        className="auto-run-head"
                        onClick={() => setExpandedRunId(expanded ? null : run.id)}
                        type="button"
                        aria-expanded={expanded}
                      >
                        <span className="auto-run-head-row">
                          <span className={`auto-badge ${statusClass(run.status)}`}>
                            {run.status || 'unknown'}
                          </span>
                          <span className="auto-run-when">{formatDateTime(run.startedAt)}</span>
                          <span className="auto-run-trigger">{run.trigger}</span>
                          <span className="auto-run-caret">{expanded ? '▾' : '▸'}</span>
                        </span>
                        {!expanded && bluf && <span className="auto-run-bluf">{bluf}</span>}
                      </button>
                      {expanded && (
                        <div className="auto-run-body">
                          {run.responseText && (
                            <div className="auto-run-text message-text">
                              <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                components={{
                                  a: ({ href, children, ...props }) => (
                                    <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>
                                  ),
                                }}
                              >
                                {run.responseText}
                              </ReactMarkdown>
                            </div>
                          )}
                          {run.error && <p className="auto-run-error">Error: {run.error}</p>}
                          <div className="auto-run-stats">
                            <span>Tools: {run.toolEvents.length}</span>
                            {typeof run.usage.total_token_count === 'number' && (
                              <span>Tokens: {run.usage.total_token_count}</span>
                            )}
                            <span>Notify: {run.notifyStatus}</span>
                          </div>
                          {canChat && session && (
                            <button
                              className="auto-run-ask"
                              onClick={() => askAboutRun(run)}
                              disabled={isStreaming}
                              type="button"
                            >
                              ASK ABOUT THIS
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </section>
          </aside>

          <section className="auto-chat">
            <div className="auto-chat-head">
              <h3 className="auto-chat-title">ASK THE DUTY OFFICER</h3>
              {dutyProfile && <span className="auto-chat-sub">{dutyProfile.name}</span>}
            </div>
            <div className="chat-messages auto-chat-messages">
              {!canChat ? (
                <div className="auto-empty">
                  <p>The autonomous agent is not configured, so chat is unavailable.</p>
                </div>
              ) : messages.length === 0 ? (
                <div className="auto-empty">
                  <p>
                    Ask the autonomous Duty Officer about its standing orders, recent activity,
                    or anything else on your mind.
                  </p>
                </div>
              ) : (
                messages.map((msg, i) => <ChatMessage key={i} message={msg} />)
              )}
              <div ref={messagesEndRef} />
            </div>
            {canChat && (
              <ChatInput onSend={(content) => send(content)} disabled={isStreaming || !session} />
            )}
          </section>
        </div>
      )}

      <footer className="classification-footer">{classificationBanner}</footer>
    </div>
  );
}
