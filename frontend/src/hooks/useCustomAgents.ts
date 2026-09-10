import { useState, useEffect, useCallback } from 'react';
import type { CustomAgentDefinition } from '../types/api';
import {
  listCustomAgents,
  saveCustomAgent as saveCustomAgentApi,
  deleteCustomAgent as deleteCustomAgentApi,
} from '../api/client';

export function useCustomAgents() {
  const [agents, setAgents] = useState<CustomAgentDefinition[]>([]);

  const reload = useCallback(async () => {
    setAgents(await listCustomAgents());
  }, []);

  useEffect(() => {
    let cancelled = false;
    void listCustomAgents()
      .then((list) => { if (!cancelled) setAgents(list); })
      .catch(() => { /* surfaced by the API layer */ });
    return () => { cancelled = true; };
  }, []);

  const save = useCallback(async (agent: CustomAgentDefinition) => {
    const saved = await saveCustomAgentApi(agent);
    setAgents((prev) => {
      const idx = prev.findIndex((a) => a.id === agent.id);
      return idx >= 0 ? prev.map((a, i) => (i === idx ? saved : a)) : [...prev, saved];
    });
  }, []);

  const remove = useCallback(async (id: string) => {
    await deleteCustomAgentApi(id);
    setAgents((prev) => prev.filter((a) => a.id !== id));
  }, []);

  return { agents, save, remove, reload } as const;
}
