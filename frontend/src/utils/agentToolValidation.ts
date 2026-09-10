// Client-side validation + tool-name derivation for sub-agent tool refs.
// Mirrors backend rules in validators.py + sub_agent_tools.py so the UI can
// preview the same derived tool name the backend will compute and block
// obvious errors before the round-trip.
//
// V5 (definition_id_mismatch) is intentionally backend-only.

import type { AgentRef, SubAgentToolRef } from '../types/api';

export interface SubAgentValidationError {
  index: number;
  field: string;
  code:
    | 'unresolved_agent_ref'
    | 'self_reference'
    | 'direct_cycle'
    | 'duplicate_target';
  message: string;
}

/** Resolved view of a sub-agent target — minimal shape needed for cycle checks. */
export interface ResolvedAgentTarget {
  id: string;
  name: string;
  description: string;
  /** The target's own sub-agent refs (used for direct A↔B cycle detection). */
  agentsAsTools: SubAgentToolRef[];
}

export type ResolveTargetFn = (ref: AgentRef) => ResolvedAgentTarget | null;

function refTargetId(ref: AgentRef): string {
  return ref.kind === 'builtin' ? ref.profileId : ref.customAgentId;
}

export function validateSubAgentTools(
  parentId: string,
  refs: SubAgentToolRef[],
  resolveTarget: ResolveTargetFn,
): SubAgentValidationError[] {
  const errors: SubAgentValidationError[] = [];
  const seen = new Set<string>();

  refs.forEach((entry, index) => {
    const ref = entry.agentRef;
    const targetId = refTargetId(ref);
    const fieldPrefix = `agentsAsTools[${index}]`;

    // V2 self_reference
    if (parentId && targetId === parentId) {
      errors.push({
        index,
        field: `${fieldPrefix}.agentRef`,
        code: 'self_reference',
        message: 'An agent cannot reference itself as a tool.',
      });
      return;
    }

    // V4 duplicate_target
    const key = `${ref.kind}:${targetId}`;
    if (seen.has(key)) {
      errors.push({
        index,
        field: `${fieldPrefix}.agentRef`,
        code: 'duplicate_target',
        message: `Sub-agent "${targetId}" is referenced more than once.`,
      });
      return;
    }
    seen.add(key);

    // V1 unresolved_agent_ref
    const target = resolveTarget(ref);
    if (!target) {
      errors.push({
        index,
        field: `${fieldPrefix}.agentRef`,
        code: 'unresolved_agent_ref',
        message: `Sub-agent "${targetId}" could not be found.`,
      });
      return;
    }

    // V3 direct_cycle (A↔B only — multi-hop cycles are explicit non-goal)
    if (parentId) {
      for (const targetEntry of target.agentsAsTools || []) {
        const tRef = targetEntry.agentRef;
        if (refTargetId(tRef) === parentId) {
          errors.push({
            index,
            field: `${fieldPrefix}.agentRef`,
            code: 'direct_cycle',
            message:
              `Sub-agent "${target.name}" already references this agent — ` +
              'direct cycles are not allowed.',
          });
          break;
        }
      }
    }
  });

  return errors;
}

// Derivation helpers --------------------------------------------------------
// Mirror sub_agent_tools.py exactly so the preview matches what the backend
// will actually wire as the tool name.

const TOOL_NAME_MAX = 64;
const TOOL_DESC_MAX = 500;

export function slugifyToolName(raw: string, fallbackId = ''): string {
  const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  let slug = normalize(raw) || normalize(fallbackId) || 'sub_agent';
  if (/^\d/.test(slug)) slug = `a_${slug}`;
  if (slug.length > TOOL_NAME_MAX) slug = slug.slice(0, TOOL_NAME_MAX);
  return slug;
}

export function disambiguateToolNames(names: string[]): string[] {
  const used = new Set<string>();
  return names.map((name) => {
    if (!used.has(name)) {
      used.add(name);
      return name;
    }
    let suffix = 2;
    let out: string;
    do {
      const ending = `_${suffix++}`;
      out = `${name.slice(0, TOOL_NAME_MAX - ending.length)}${ending}`;
    } while (used.has(out));
    used.add(out);
    return out;
  });
}

export interface DerivedToolSurface {
  toolName: string;
  toolDescription: string;
  argDescription: string;
}

export function deriveSubAgentToolSurface(
  targetName: string,
  targetDescription: string,
  fallbackId: string,
): DerivedToolSurface {
  const toolName = slugifyToolName(targetName, fallbackId);
  let toolDescription = (targetDescription || '').trim();
  toolDescription = toolDescription
    ? toolDescription.slice(0, TOOL_DESC_MAX)
    : `Delegate to the ${targetName.trim() || fallbackId || toolName} agent.`;
  return {
    toolName,
    toolDescription,
    argDescription: `Request for the ${toolName} agent.`,
  };
}
