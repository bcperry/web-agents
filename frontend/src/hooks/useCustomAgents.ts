import { useState, useEffect, useCallback } from 'react';
import type { CustomAgentDefinition } from '../types/api';

const STORAGE_KEY = 'webagents_custom_agents';

function loadAgents(): CustomAgentDefinition[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function persistAgents(agents: CustomAgentDefinition[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(agents));
}

export function useCustomAgents() {
  const [agents, setAgents] = useState<CustomAgentDefinition[]>(loadAgents);

  // Sync from localStorage on mount
  useEffect(() => {
    setAgents(loadAgents());
  }, []);

  const save = useCallback((agent: CustomAgentDefinition) => {
    setAgents((prev) => {
      const idx = prev.findIndex((a) => a.id === agent.id);
      const next = idx >= 0 ? prev.map((a, i) => (i === idx ? agent : a)) : [...prev, agent];
      persistAgents(next);
      return next;
    });
  }, []);

  const remove = useCallback((id: string) => {
    setAgents((prev) => {
      const next = prev.filter((a) => a.id !== id);
      persistAgents(next);
      return next;
    });
  }, []);

  return { agents, save, remove } as const;
}
