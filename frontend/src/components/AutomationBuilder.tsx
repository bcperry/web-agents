import { useCallback, useEffect, useState } from 'react';
import type {
  AgentProfile,
  AutonomousDirective,
  AutonomousDirectiveCreate,
  AutonomousDirectiveUpdate,
} from '../types/api';
import {
  createAutonomousDirective,
  deleteAutonomousDirective,
  fetchAutonomousDirectives,
  fetchProfiles,
  updateAutonomousDirective,
} from '../api/client';
import { emitToast } from '../hooks/useToast';

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

// Friendly cadence presets (6-field, seconds-first NCRONTAB) + an advanced escape
// hatch for a raw cron expression. `cron: null` means "manual only" (no schedule).
const SCHEDULE_PRESETS: { key: string; label: string; cron: string | null }[] = [
  { key: 'manual', label: 'Manual only (no schedule)', cron: null },
  { key: 'every-15-min', label: 'Every 15 minutes', cron: '0 */15 * * * *' },
  { key: 'every-30-min', label: 'Every 30 minutes', cron: '0 */30 * * * *' },
  { key: 'hourly', label: 'Hourly', cron: '0 0 * * * *' },
  { key: 'every-6-hours', label: 'Every 6 hours', cron: '0 0 */6 * * *' },
  { key: 'daily-8', label: 'Daily at 08:00', cron: '0 0 8 * * *' },
  { key: 'weekdays-8', label: 'Weekdays at 08:00', cron: '0 0 8 * * 1-5' },
  { key: 'advanced', label: 'Advanced (custom cron)…', cron: '__advanced__' },
];

function matchPreset(schedule: string | null): string {
  if (!schedule) return 'manual';
  const found = SCHEDULE_PRESETS.find((p) => p.cron === schedule);
  return found ? found.key : 'advanced';
}

interface DirectiveDraft {
  id: string;
  profile_id: string;
  instruction: string;
  schedule: string | null;
  enabled: boolean;
  notify_webhook: string | null;
}

interface DirectiveEditorProps {
  mode: 'create' | 'edit';
  initial?: AutonomousDirective;
  profiles: AgentProfile[];
  busy: boolean;
  onSubmit: (draft: DirectiveDraft) => void;
  onCancel: () => void;
  onDelete?: () => void;
}

// Inline create/edit form for one automation. Owns its own field state; the
// parent performs the API call and owns the busy flag + error toasts.
function DirectiveEditor({ mode, initial, profiles, busy, onSubmit, onCancel, onDelete }: DirectiveEditorProps) {
  const [id, setId] = useState(initial?.id ?? '');
  const [profileId, setProfileId] = useState(initial?.profileId ?? profiles[0]?.id ?? 'chief-of-staff');
  const [instruction, setInstruction] = useState(initial?.instruction ?? '');
  const initialPreset = matchPreset(initial?.schedule ?? null);
  const [presetKey, setPresetKey] = useState(initialPreset);
  const [advancedCron, setAdvancedCron] = useState(initialPreset === 'advanced' ? (initial?.schedule ?? '') : '');
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [notifyWebhook, setNotifyWebhook] = useState(initial?.notifyWebhook ?? '');

  const resolveSchedule = (): string | null => {
    const preset = SCHEDULE_PRESETS.find((p) => p.key === presetKey);
    if (!preset) return null;
    if (preset.cron === '__advanced__') return advancedCron.trim() || null;
    return preset.cron;
  };

  const submit = () => {
    onSubmit({
      id: id.trim(),
      profile_id: profileId,
      instruction: instruction.trim(),
      schedule: resolveSchedule(),
      enabled,
      notify_webhook: notifyWebhook.trim() || null,
    });
  };

  const canSubmit =
    (mode === 'edit' || id.trim().length > 0) &&
    instruction.trim().length > 0 &&
    (presetKey !== 'advanced' || advancedCron.trim().length > 0);

  return (
    <div className="auto-editor">
      {mode === 'create' && (
        <label className="auto-field">
          <span>ID (lowercase slug)</span>
          <input
            className="auto-input"
            value={id}
            onChange={(e) => setId(e.target.value)}
            placeholder="morning-brief"
            autoFocus
          />
        </label>
      )}
      <label className="auto-field">
        <span>Agent</span>
        <select className="auto-input" value={profileId} onChange={(e) => setProfileId(e.target.value)}>
          {profiles.length === 0 && <option value={profileId}>{profileId}</option>}
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </label>
      <label className="auto-field">
        <span>Schedule</span>
        <select className="auto-input" value={presetKey} onChange={(e) => setPresetKey(e.target.value)}>
          {SCHEDULE_PRESETS.map((p) => (
            <option key={p.key} value={p.key}>{p.label}</option>
          ))}
        </select>
      </label>
      {presetKey === 'advanced' && (
        <label className="auto-field">
          <span>Custom cron — 6 fields: second minute hour day month weekday</span>
          <input
            className="auto-input"
            value={advancedCron}
            onChange={(e) => setAdvancedCron(e.target.value)}
            placeholder="0 */15 * * * *"
          />
        </label>
      )}
      <label className="auto-field">
        <span>Instruction (standing order)</span>
        <textarea
          className="auto-input auto-textarea"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          rows={6}
          placeholder="What should this automation do each run?"
        />
      </label>
      <label className="auto-field auto-field-inline">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        <span>Enabled</span>
      </label>
      <label className="auto-field">
        <span>Notify webhook (optional — env-var name or https URL)</span>
        <input
          className="auto-input"
          value={notifyWebhook}
          onChange={(e) => setNotifyWebhook(e.target.value)}
          placeholder="AUTONOMOUS_NOTIFY_WEBHOOK_URL"
        />
      </label>
      <div className="auto-editor-actions">
        <button className="auto-btn-primary" onClick={submit} disabled={busy || !canSubmit} type="button">
          {busy ? 'SAVING…' : mode === 'create' ? 'CREATE' : 'SAVE'}
        </button>
        <button className="auto-btn-ghost" onClick={onCancel} disabled={busy} type="button">
          CANCEL
        </button>
        {mode === 'edit' && onDelete && (
          <button className="auto-btn-danger" onClick={onDelete} disabled={busy} type="button">
            DELETE
          </button>
        )}
      </div>
    </div>
  );
}

// Admin "AUTOMATIONS" tab — full management of autonomous directives (create,
// edit, enable/disable, delete), mirroring the SKILLS builder pattern.
export function AutomationBuilder({ intent }: { intent?: { create?: boolean; editId?: string } } = {}) {
  const [directives, setDirectives] = useState<AutonomousDirective[]>([]);
  const [profiles, setProfiles] = useState<AgentProfile[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [schedulerEnabled, setSchedulerEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [managingId, setManagingId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);

  // Deep-link intent from the Duty Officer page: open a blank create form, or a
  // specific automation in edit mode, as soon as the tab mounts.
  useEffect(() => {
    if (intent?.create) {
      setCreating(true);
      setManagingId(null);
    } else if (intent?.editId) {
      setManagingId(intent.editId);
      setCreating(false);
    }
  }, [intent?.create, intent?.editId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [dir, profResp] = await Promise.all([fetchAutonomousDirectives(), fetchProfiles()]);
        if (cancelled) return;
        setEnabled(dir.enabled);
        setSchedulerEnabled(dir.schedulerEnabled);
        setDirectives(dir.directives);
        setProfiles(profResp.profiles);
      } catch (err) {
        if (!cancelled) emitToast({ message: err instanceof Error ? err.message : 'Failed to load automations.', type: 'error' });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const applyDirective = useCallback((updated: AutonomousDirective) => {
    setDirectives((prev) =>
      prev.some((d) => d.id === updated.id)
        ? prev.map((d) => (d.id === updated.id ? updated : d))
        : [...prev, updated],
    );
  }, []);

  const handleSaveNew = useCallback(
    async (draft: DirectiveDraft) => {
      setSaving(true);
      try {
        const created = await createAutonomousDirective(draft as AutonomousDirectiveCreate);
        applyDirective(created);
        setCreating(false);
      } catch (err) {
        emitToast({ message: err instanceof Error ? err.message : 'Failed to create automation.', type: 'error' });
      } finally {
        setSaving(false);
      }
    },
    [applyDirective],
  );

  const handleSaveEdit = useCallback(
    async (id: string, draft: DirectiveDraft) => {
      setSaving(true);
      try {
        const update: AutonomousDirectiveUpdate = {
          profile_id: draft.profile_id,
          instruction: draft.instruction,
          schedule: draft.schedule,
          enabled: draft.enabled,
          notify_webhook: draft.notify_webhook,
        };
        const updated = await updateAutonomousDirective(id, update);
        applyDirective(updated);
        setManagingId(null);
      } catch (err) {
        emitToast({ message: err instanceof Error ? err.message : 'Failed to save automation.', type: 'error' });
      } finally {
        setSaving(false);
      }
    },
    [applyDirective],
  );

  const handleToggleEnabled = useCallback(
    async (directive: AutonomousDirective) => {
      setSaving(true);
      try {
        const updated = await updateAutonomousDirective(directive.id, { enabled: !directive.enabled });
        applyDirective(updated);
      } catch (err) {
        emitToast({ message: err instanceof Error ? err.message : 'Failed to update automation.', type: 'error' });
      } finally {
        setSaving(false);
      }
    },
    [applyDirective],
  );

  const handleDelete = useCallback(async (id: string) => {
    if (!window.confirm(`Delete automation "${id}"? This cannot be undone.`)) return;
    setSaving(true);
    try {
      await deleteAutonomousDirective(id);
      setDirectives((prev) => prev.filter((d) => d.id !== id));
      setManagingId(null);
    } catch (err) {
      emitToast({ message: err instanceof Error ? err.message : 'Failed to delete automation.', type: 'error' });
    } finally {
      setSaving(false);
    }
  }, []);

  return (
    <div className="agent-builder automation-builder">
      <div className="agent-builder-header">
        <h2 className="agent-builder-title">AUTOMATIONS</h2>
      </div>

      <div className="automation-builder-body">
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
            The unattended scheduler is disabled on this server, so automations only fire when triggered
            from the Duty Officer page. To run them on their schedule, start the backend with{' '}
            <code>AUTONOMOUS_SCHEDULER_ENABLED=true</code>.
          </p>
        )}

        <div className="auto-section-head">
          <h3 className="auto-section-title">STANDING ORDERS</h3>
          {!creating && (
            <button
              className="auto-new-btn"
              type="button"
              onClick={() => { setCreating(true); setManagingId(null); }}
              disabled={saving}
            >
              + NEW AUTOMATION
            </button>
          )}
        </div>

        {creating && (
          <DirectiveEditor
            mode="create"
            profiles={profiles}
            busy={saving}
            onSubmit={handleSaveNew}
            onCancel={() => setCreating(false)}
          />
        )}

        {loading ? (
          <div className="auto-empty-line">Loading automations…</div>
        ) : directives.length === 0 && !creating ? (
          <div className="auto-empty-line">No automations configured.</div>
        ) : (
          directives.map((d) =>
            managingId === d.id ? (
              <DirectiveEditor
                key={d.id}
                mode="edit"
                initial={d}
                profiles={profiles}
                busy={saving}
                onSubmit={(draft) => handleSaveEdit(d.id, draft)}
                onCancel={() => setManagingId(null)}
                onDelete={() => handleDelete(d.id)}
              />
            ) : (
              <div key={d.id} className="auto-directive">
                <div className="auto-directive-top">
                  <span className="auto-directive-id">{d.id}</span>
                  <button
                    type="button"
                    className={`auto-badge auto-badge-btn ${d.enabled ? 'ok' : 'off'}`}
                    onClick={() => handleToggleEnabled(d)}
                    disabled={saving}
                    title={d.enabled ? 'Click to pause this automation' : 'Click to enable this automation'}
                    aria-pressed={d.enabled}
                  >
                    {d.enabled ? 'ENABLED' : 'PAUSED'}
                  </button>
                </div>
                <div className="auto-directive-summary">{d.instructionSummary}</div>
                <div className="auto-directive-meta">
                  <span>Agent: {d.profileId}</span>
                  {d.schedule && <span>Schedule: {d.schedule}</span>}
                  {enabled && schedulerEnabled && d.enabled && d.nextRun && (
                    <span>Next review: {formatDateTime(d.nextRun)}</span>
                  )}
                  <span>Notify: {d.notify}</span>
                </div>
                <div className="auto-directive-controls">
                  <button
                    className="auto-btn-ghost"
                    type="button"
                    onClick={() => { setManagingId(d.id); setCreating(false); }}
                    disabled={saving}
                  >
                    EDIT
                  </button>
                  <button
                    className="auto-btn-danger"
                    type="button"
                    onClick={() => handleDelete(d.id)}
                    disabled={saving}
                  >
                    DELETE
                  </button>
                </div>
              </div>
            ),
          )
        )}
      </div>
    </div>
  );
}
