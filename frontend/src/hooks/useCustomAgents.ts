import { useState, useCallback } from 'react';
import type { CustomAgentDefinition } from '../types/api';
import { readJson, writeJson } from '../utils/storage';

const STORAGE_KEY = 'webagents_custom_agents';

function persistAgents(agents: CustomAgentDefinition[]): void {
  writeJson(STORAGE_KEY, agents);
}

export function useCustomAgents() {
  const [agents, setAgents] = useState<CustomAgentDefinition[]>(() =>
    readJson<CustomAgentDefinition[]>(STORAGE_KEY, [], Array.isArray),
  );

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
