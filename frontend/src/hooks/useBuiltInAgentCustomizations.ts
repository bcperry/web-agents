import { useCallback, useEffect, useState } from 'react';
import type { AgentCustomizationOverride } from '../types/api';
import {
  listAgentCustomizations,
  saveAgentCustomization as saveAgentCustomizationApi,
  deleteAgentCustomization as deleteAgentCustomizationApi,
} from '../api/client';

export function useBuiltInAgentCustomizations() {
  const [overrides, setOverrides] = useState<AgentCustomizationOverride[]>([]);

  useEffect(() => {
    let cancelled = false;
    void listAgentCustomizations()
      .then((list) => { if (!cancelled) setOverrides(list); })
      .catch(() => { /* surfaced by the API layer */ });
    return () => { cancelled = true; };
  }, []);

  const save = useCallback(async (override: AgentCustomizationOverride) => {
    await saveAgentCustomizationApi(override);
    setOverrides((prev) => {
      const idx = prev.findIndex((item) => item.baseProfileId === override.baseProfileId);
      return idx >= 0 ? prev.map((item, i) => (i === idx ? override : item)) : [...prev, override];
    });
  }, []);

  const remove = useCallback(async (baseProfileId: string) => {
    await deleteAgentCustomizationApi(baseProfileId);
    setOverrides((prev) => prev.filter((item) => item.baseProfileId !== baseProfileId));
  }, []);

  return { overrides, save, remove } as const;
}
