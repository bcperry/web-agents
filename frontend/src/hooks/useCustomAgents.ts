import { useState, useEffect, useCallback } from 'react';
import type { CustomAgentDefinition } from '../types/api';
import {
  listCustomAgents,
  saveCustomAgent as saveCustomAgentApi,
  deleteCustomAgent as deleteCustomAgentApi,
} from '../api/client';

/** Backward-compat shim: older entries stored without `agentsAsTools`. */
function normalizeAgent(agent: CustomAgentDefinition): CustomAgentDefinition {
  return Array.isArray(agent.agentsAsTools)
    ? agent
    : { ...agent, agentsAsTools: [] };
}

/**
 * Server-backed custom agents. The authoritative store is Azure Cosmos DB (via
 * the backend API); mutations update local state optimistically and persist in
 * the background.
 */
export function useCustomAgents() {
  const [agents, setAgents] = useState<CustomAgentDefinition[]>([]);

  useEffect(() => {
    let cancelled = false;
    void listCustomAgents()
      .then((list) => { if (!cancelled) setAgents(list.map(normalizeAgent)); })
      .catch(() => { /* surfaced by the API layer */ });
    return () => { cancelled = true; };
  }, []);

  const save = useCallback((agent: CustomAgentDefinition) => {
    const normalized = normalizeAgent(agent);
    setAgents((prev) => {
      const idx = prev.findIndex((a) => a.id === normalized.id);
      return idx >= 0 ? prev.map((a, i) => (i === idx ? normalized : a)) : [...prev, normalized];
    });
    void saveCustomAgentApi(normalized).catch(() => { /* surfaced by the API layer */ });
  }, []);

  const remove = useCallback((id: string) => {
    setAgents((prev) => prev.filter((a) => a.id !== id));
    void deleteCustomAgentApi(id).catch(() => { /* surfaced by the API layer */ });
  }, []);

  return { agents, save, remove } as const;
}
