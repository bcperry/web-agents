import { useState, useEffect, useCallback } from 'react';
import type { CustomAgentDefinition } from '../types/api';
import {
  listCustomAgents,
  saveCustomAgent as saveCustomAgentApi,
  deleteCustomAgent as deleteCustomAgentApi,
} from '../api/client';

/**
 * Server-backed custom agents. The authoritative store is Azure Cosmos DB (via
 * the backend API); mutations update local state optimistically and persist in
 * the background.
 */
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

  const save = useCallback((agent: CustomAgentDefinition) => {
    setAgents((prev) => {
      const idx = prev.findIndex((a) => a.id === agent.id);
      return idx >= 0 ? prev.map((a, i) => (i === idx ? agent : a)) : [...prev, agent];
    });
    void saveCustomAgentApi(agent).catch(() => { /* surfaced by the API layer */ });
  }, []);

  const remove = useCallback((id: string) => {
    setAgents((prev) => prev.filter((a) => a.id !== id));
    void deleteCustomAgentApi(id).catch(() => { /* surfaced by the API layer */ });
  }, []);

  return { agents, save, remove, reload } as const;
}
