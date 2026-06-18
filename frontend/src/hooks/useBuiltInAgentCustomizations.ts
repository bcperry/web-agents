import { useCallback, useEffect, useState } from 'react';
import type { AgentCustomizationOverride } from '../types/api';
import {
  listAgentCustomizations,
  saveAgentCustomization as saveAgentCustomizationApi,
  deleteAgentCustomization as deleteAgentCustomizationApi,
} from '../api/client';

/**
 * Server-backed built-in agent customizations (overrides). The authoritative
 * store is Azure Cosmos DB (via the backend API); mutations update local state
 * optimistically and persist in the background.
 */
export function useBuiltInAgentCustomizations() {
  const [overrides, setOverrides] = useState<AgentCustomizationOverride[]>([]);

  useEffect(() => {
    let cancelled = false;
    void listAgentCustomizations()
      .then((list) => { if (!cancelled) setOverrides(list); })
      .catch(() => { /* surfaced by the API layer */ });
    return () => { cancelled = true; };
  }, []);

  const save = useCallback((override: AgentCustomizationOverride) => {
    setOverrides((prev) => {
      const idx = prev.findIndex((item) => item.baseProfileId === override.baseProfileId);
      return idx >= 0 ? prev.map((item, i) => (i === idx ? override : item)) : [...prev, override];
    });
    void saveAgentCustomizationApi(override).catch(() => { /* surfaced by the API layer */ });
  }, []);

  const remove = useCallback((baseProfileId: string) => {
    setOverrides((prev) => prev.filter((item) => item.baseProfileId !== baseProfileId));
    void deleteAgentCustomizationApi(baseProfileId).catch(() => { /* surfaced by the API layer */ });
  }, []);

  const get = useCallback(
    (baseProfileId: string) => overrides.find((item) => item.baseProfileId === baseProfileId) ?? null,
    [overrides],
  );

  return { overrides, save, remove, get } as const;
}
