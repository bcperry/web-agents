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
  if (!option.definition) {
    throw new Error(`Custom agent option "${option.id}" missing definition`);
  }
  return {
    agentRef: { kind: 'custom', customAgentId: option.id, definition: option.definition },
  };
}

export function AgentAsToolPicker({
  availableAgents,
  value,
  parentAgentId,
  validationErrors,
  onChange,
}: AgentAsToolPickerProps) {
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

  return (
    <div className="agent-builder-section">
      <h3 className="agent-builder-section-title">AGENTS AS TOOLS</h3>
      <span className="agent-builder-tool-desc" style={{ display: 'block', marginBottom: '0.5rem' }}>
        Other agents this agent can call as tools. Tool name and description are derived automatically
        from the target agent and recomputed by the server.
      </span>

      {selectableAgents.length === 0 ? (
        <div className="agent-builder-tool-desc">No other agents available</div>
      ) : (
        <div className="agent-builder-tools">
          {selectableAgents.map((opt) => {
            const idx = selectedById.get(opt.id);
            const isSelected = idx !== undefined;
            const finalName = isSelected ? finalToolNameByTargetId.get(opt.id) : undefined;
            const rowErrors = isSelected ? (errorsByIndex.get(idx!) ?? []) : [];
            return (
              <label key={`${opt.kind}:${opt.id}`} className="agent-builder-tool-item">
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => handleToggle(opt)}
                />
                <span className="agent-builder-tool-name">
                  {opt.name}
                  <span className="agent-builder-tool-desc" style={{ marginLeft: '0.5rem' }}>
                    ({opt.kind === 'builtin' ? 'built-in' : 'custom'})
                  </span>
                </span>
                <span className="agent-builder-tool-desc">
                  {opt.description || 'No description'}
                  {finalName && (
                    <>
                      {' — tool: '}
                      <code>{finalName}</code>
                    </>
                  )}
                </span>
                {rowErrors.length > 0 && (
                  <span className="agent-builder-error-text" style={{ display: 'block' }}>
                    {rowErrors.map((e) => e.message).join(' ')}
                  </span>
                )}
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}
