import { useState } from 'react';
import type {
  AgentRef,
  CustomAgentDefinition,
  SubAgentToolRef,
} from '../types/api';
import {
  deriveSubAgentToolSurface,
  disambiguateToolNames,
  type SubAgentValidationError,
} from '../utils/agentToolValidation';

/** A single agent option exposed in the picker. */
export interface AgentToolOption {
  /** Stable id — built-in profile id OR custom agent id. */
  id: string;
  kind: 'builtin' | 'custom';
  name: string;
  description: string;
  /** For `kind === 'custom'`, the full local definition (inlined on save). */
  definition?: CustomAgentDefinition;
}

interface AgentAsToolPickerProps {
  availableAgents: AgentToolOption[];
  value: SubAgentToolRef[];
  parentAgentId: string;
  validationErrors: SubAgentValidationError[];
  onChange: (next: SubAgentToolRef[]) => void;
}

function refTargetId(ref: AgentRef): string {
  return ref.kind === 'builtin' ? ref.profileId : ref.customAgentId;
}

function buildRef(option: AgentToolOption): SubAgentToolRef {
  if (option.kind === 'builtin') {
    return { agentRef: { kind: 'builtin', profileId: option.id } };
  }
  return {
    agentRef: { kind: 'custom', customAgentId: option.id },
  };
}

export function AgentAsToolPicker({
  availableAgents,
  value,
  parentAgentId,
  validationErrors,
  onChange,
}: AgentAsToolPickerProps) {
  const [expanded, setExpanded] = useState(value.length > 0);
  const [query, setQuery] = useState('');

  // Self is always excluded; everything else is selectable via checkbox.
  const selectableAgents = availableAgents.filter((opt) => opt.id !== parentAgentId);
  const selectedById = new Map(value.map((entry, idx) => [refTargetId(entry.agentRef), idx]));

  // Derive tool-name previews in the same order as `value` and apply the
  // exact disambiguation rule the backend will use.
  const baseDerivations = value.map((entry) => {
    const opt = availableAgents.find((o) => o.id === refTargetId(entry.agentRef));
    const name = opt?.name ?? refTargetId(entry.agentRef);
    const desc = opt?.description ?? '';
    const fallback = refTargetId(entry.agentRef);
    return deriveSubAgentToolSurface(name, desc, fallback);
  });
  const finalToolNames = disambiguateToolNames(baseDerivations.map((d) => d.toolName));
  const finalToolNameByTargetId = new Map<string, string>();
  value.forEach((entry, idx) => {
    finalToolNameByTargetId.set(refTargetId(entry.agentRef), finalToolNames[idx]);
  });

  const errorsByIndex = new Map<number, SubAgentValidationError[]>();
  for (const err of validationErrors) {
    const list = errorsByIndex.get(err.index) ?? [];
    list.push(err);
    errorsByIndex.set(err.index, list);
  }

  const handleToggle = (option: AgentToolOption) => {
    const existingIdx = selectedById.get(option.id);
    if (existingIdx !== undefined) {
      onChange(value.filter((_, i) => i !== existingIdx));
    } else {
      onChange([...value, buildRef(option)]);
    }
  };

  const visibleAgents = (() => {
    const normalizedQuery = query.trim().toLowerCase();
    return [...selectableAgents]
      .sort((a, b) => Number(selectedById.has(b.id)) - Number(selectedById.has(a.id)))
      .filter((agent) => !normalizedQuery || `${agent.name} ${agent.description}`.toLowerCase().includes(normalizedQuery));
  })();

  return (
    <div className="agent-builder-section agent-builder-capability-section">
      <button
        className="agent-builder-capability-header"
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        <span className="agent-builder-section-title">AGENTS AS TOOLS</span>
        <span className="agent-builder-capability-summary">
          {value.length} selected
          <span aria-hidden="true">{expanded ? '−' : '+'}</span>
        </span>
      </button>
      {expanded && (
        <div className="agent-builder-capability-content">
          <span className="agent-builder-tool-desc">Other agents this agent can call as tools.</span>
          {selectableAgents.length > 8 && (
            <input
              className="agent-builder-input agent-builder-capability-search"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search agents"
              aria-label="Search agents"
            />
          )}
          {selectableAgents.length === 0 ? (
            <div className="agent-builder-tool-desc">No other agents available</div>
          ) : (
            <div className="agent-builder-tools">
              {visibleAgents.map((opt) => {
            const idx = selectedById.get(opt.id);
            const isSelected = idx !== undefined;
            const finalName = isSelected ? finalToolNameByTargetId.get(opt.id) : undefined;
            const rowErrors = isSelected ? (errorsByIndex.get(idx!) ?? []) : [];
            return (
              <label key={`${opt.kind}:${opt.id}`} className="agent-builder-tool-item" title={opt.description || 'No description'}>
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => handleToggle(opt)}
                />
                <span className="agent-builder-tool-name">
                  {opt.name}
                </span>
                <span className="agent-builder-tool-kind">{opt.kind === 'builtin' ? 'built-in' : 'custom'}</span>
                {finalName && <code className="agent-builder-tool-preview">{finalName}</code>}
                {rowErrors.length > 0 && (
                  <span className="agent-builder-error-text" style={{ display: 'block' }}>
                    {rowErrors.map((e) => e.message).join(' ')}
                  </span>
                )}
              </label>
            );
              })}
              {visibleAgents.length === 0 && <div className="agent-builder-tool-desc">No matches</div>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
