import { useCallback, useState } from 'react';
import type { AgentCustomizationOverride } from '../types/api';

const STORAGE_KEY = 'webagents_builtin_agent_customizations';

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function isOverride(value: unknown): value is AgentCustomizationOverride {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.baseProfileId === 'string' &&
    typeof candidate.description === 'string' &&
    typeof candidate.systemPrompt === 'string' &&
    isStringArray(candidate.tools) &&
    isStringArray(candidate.skills) &&
    Array.isArray(candidate.mcpServers) &&
    typeof candidate.useSearchContext === 'boolean' &&
    typeof candidate.icon === 'string' &&
    Array.isArray(candidate.starters) &&
    candidate.source === 'builtin-override' &&
    typeof candidate.createdAt === 'string' &&
    typeof candidate.updatedAt === 'string'
  );
}

function loadOverrides(): AgentCustomizationOverride[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      localStorage.removeItem(STORAGE_KEY);
      return [];
    }
    return parsed.filter(isOverride);
  } catch {
    try { localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
    return [];
  }
}

function persistOverrides(overrides: AgentCustomizationOverride[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(overrides));
}

export function useBuiltInAgentCustomizations() {
  const [overrides, setOverrides] = useState<AgentCustomizationOverride[]>(loadOverrides);

  const save = useCallback((override: AgentCustomizationOverride) => {
    setOverrides((prev) => {
      const idx = prev.findIndex((item) => item.baseProfileId === override.baseProfileId);
      const next = idx >= 0 ? prev.map((item, i) => (i === idx ? override : item)) : [...prev, override];
      persistOverrides(next);
      return next;
    });
  }, []);

  const remove = useCallback((baseProfileId: string) => {
    setOverrides((prev) => {
      const next = prev.filter((item) => item.baseProfileId !== baseProfileId);
      persistOverrides(next);
      return next;
    });
  }, []);

  const get = useCallback(
    (baseProfileId: string) => overrides.find((item) => item.baseProfileId === baseProfileId) ?? null,
    [overrides],
  );

  return { overrides, save, remove, get } as const;
}
