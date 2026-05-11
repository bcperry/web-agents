import { useMemo, useState } from 'react';
import type {
  AgentCustomizationOverride,
  BuiltInAgentDefinition,
  CustomAgentDefinition,
  McpServerEntry,
  StarterQuestion,
  SubAgentToolRef,
} from '../types/api';

export interface AgentBuilderFormState {
  name: string;
  description: string;
  systemPrompt: string;
  tools: string[];
  skills: string[];
  mcpServers: McpServerEntry[];
  useSearchContext: boolean;
  icon: string;
  starters: StarterQuestion[];
  temperature: string;
  agentsAsTools: SubAgentToolRef[];
}

export const EMPTY_AGENT_FORM: AgentBuilderFormState = {
  name: '',
  description: '',
  systemPrompt: '',
  tools: [],
  skills: [],
  mcpServers: [],
  useSearchContext: false,
  icon: '/icons/custom.svg',
  starters: [],
  temperature: '',
  agentsAsTools: [],
};

export function useAgentBuilderForm() {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingBuiltInDefinition, setEditingBuiltInDefinition] = useState<BuiltInAgentDefinition | null>(null);
  const [form, setForm] = useState(EMPTY_AGENT_FORM);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [saveSuccess, setSaveSuccess] = useState(false);

  const parsedTemperature = form.temperature !== '' ? parseFloat(form.temperature) : undefined;
  const temperatureValid = parsedTemperature === undefined || (!isNaN(parsedTemperature) && parsedTemperature >= 0 && parsedTemperature <= 2);
  const isValid = Boolean((editingBuiltInDefinition || form.name.trim()) && form.systemPrompt.trim() && temperatureValid);

  const resetForm = () => {
    setForm(EMPTY_AGENT_FORM);
    setEditingId(null);
    setEditingBuiltInDefinition(null);
    setTouched({});
  };

  const markTouched = (field: string) => setTouched((prev) => ({ ...prev, [field]: true }));

  return useMemo(() => ({
    editingId,
    editingBuiltInDefinition,
    form,
    isValid,
    parsedTemperature,
    resetForm,
    saveSuccess,
    setEditingBuiltInDefinition,
    setEditingId,
    setForm,
    setSaveSuccess,
    setTouched,
    touched,
    markTouched,
    temperatureValid,
  }), [editingBuiltInDefinition, editingId, form, isValid, parsedTemperature, saveSuccess, touched, temperatureValid]);
}

export function prepareCustomAgent(
  form: AgentBuilderFormState,
  editingId: string | null,
  agents: CustomAgentDefinition[],
  parsedTemperature: number | undefined,
): CustomAgentDefinition {
  const now = new Date().toISOString();
  return {
    id: editingId || `custom_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    name: form.name.trim(),
    description: form.description.trim(),
    systemPrompt: form.systemPrompt,
    tools: form.tools,
    skills: form.skills,
    mcpServers: form.mcpServers,
    useSearchContext: form.useSearchContext,
    icon: form.icon,
    starters: form.starters,
    agentsAsTools: form.agentsAsTools,
    ...(parsedTemperature !== undefined ? { temperature: parsedTemperature } : {}),
    createdAt: editingId ? agents.find((agent) => agent.id === editingId)?.createdAt || now : now,
    updatedAt: now,
  };
}

export function prepareBuiltInOverride(
  form: AgentBuilderFormState,
  definition: BuiltInAgentDefinition,
  existingOverride: AgentCustomizationOverride | undefined,
  parsedTemperature: number | undefined,
): AgentCustomizationOverride {
  const now = new Date().toISOString();
  return {
    id: existingOverride?.id ?? `builtin_override_${definition.id}`,
    baseProfileId: definition.id,
    baseProfileName: definition.name,
    description: form.description.trim(),
    systemPrompt: form.systemPrompt,
    tools: form.tools,
    skills: form.skills,
    mcpServers: form.mcpServers,
    useSearchContext: form.useSearchContext,
    icon: definition.icon,
    starters: form.starters,
    agentsAsTools: form.agentsAsTools,
    ...(parsedTemperature !== undefined ? { temperature: parsedTemperature } : {}),
    source: 'builtin-override',
    createdAt: existingOverride?.createdAt ?? now,
    updatedAt: now,
  };
}