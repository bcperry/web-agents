import { useCallback } from 'react';
import type { ConversationIndexEntry } from '../types/api';
import { listConversations, deleteConversation as deleteConversationApi } from '../api/client';

/**
 * Server-backed conversation index. The authoritative store is Azure Cosmos DB
 * (via the backend API) — conversations are no longer kept in browser storage.
 */
export function useConversationStore() {
  const loadIndex = useCallback(async (): Promise<ConversationIndexEntry[]> => {
    try {
      return await listConversations();
    } catch {
      // Non-fatal: surfaced by the API layer; the pane shows an empty list.
      return [];
    }
  }, []);

  const deleteConversation = useCallback(async (id: string): Promise<void> => {
    await deleteConversationApi(id);
  }, []);

  const deleteConversationsByCustomAgent = useCallback(async (customAgentId: string): Promise<void> => {
    try {
      const all = await listConversations();
      const targets = all.filter((entry) => entry.customAgentId === customAgentId);
      await Promise.all(targets.map((entry) => deleteConversationApi(entry.id)));
    } catch {
      // Best-effort cleanup; individual deletes remain available to the user.
    }
  }, []);

  return { loadIndex, deleteConversation, deleteConversationsByCustomAgent };
}
