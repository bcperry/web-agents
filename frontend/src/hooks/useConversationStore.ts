import { useCallback } from 'react';
import type { ConversationIndexEntry, StoredConversation } from '../types/api';

declare const __MAX_SESSIONS__: string;

const INDEX_KEY = 'webagents_conversation_index';
const CONVERSATION_KEY_PREFIX = 'webagents_conversation_';

function getMaxSessions(): number {
  return parseInt(__MAX_SESSIONS__, 10) || 5;
}

function conversationKey(id: string): string {
  return `${CONVERSATION_KEY_PREFIX}${id}`;
}

export function useConversationStore() {
  const loadIndex = useCallback((): ConversationIndexEntry[] => {
    try {
      const raw = localStorage.getItem(INDEX_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      // Validate entries have required fields
      let entries = parsed.filter(
        (e: Record<string, unknown>) => e && typeof e.id === 'string' && typeof e.description === 'string',
      ) as ConversationIndexEntry[];
      // Trim to max if config changed between deployments
      const max = getMaxSessions();
      if (entries.length > max) {
        entries.sort((a, b) => new Date(b.lastActivityAt).getTime() - new Date(a.lastActivityAt).getTime());
        const evicted = entries.splice(max);
        for (const e of evicted) {
          try { localStorage.removeItem(conversationKey(e.id)); } catch { /* ignore */ }
        }
        try { localStorage.setItem(INDEX_KEY, JSON.stringify(entries)); } catch { /* ignore */ }
      }
      return entries;
    } catch {
      // Corrupted data — discard
      try { localStorage.removeItem(INDEX_KEY); } catch { /* ignore */ }
      return [];
    }
  }, []);

  const saveIndex = useCallback((index: ConversationIndexEntry[]) => {
    try {
      localStorage.setItem(INDEX_KEY, JSON.stringify(index));
    } catch (e) {
      console.warn('Failed to save conversation index to localStorage:', e);
    }
  }, []);

  const saveConversation = useCallback((conversation: StoredConversation) => {
    let index = loadIndex();

    // Update or add to index
    const existing = index.findIndex((e) => e.id === conversation.id);
    const entry: ConversationIndexEntry = {
      id: conversation.id,
      profileId: conversation.profileId,
      profileName: conversation.profileName,
      description: conversation.description,
      createdAt: conversation.createdAt,
      lastActivityAt: conversation.lastActivityAt,
      ...(conversation.customAgentId ? { customAgentId: conversation.customAgentId } : {}),
    };

    if (existing >= 0) {
      index[existing] = entry;
    } else {
      index.unshift(entry);
    }

    // Sort newest-first
    index.sort((a, b) => new Date(b.lastActivityAt).getTime() - new Date(a.lastActivityAt).getTime());

    // Evict oldest if over limit
    const max = getMaxSessions();
    while (index.length > max) {
      const evicted = index.pop();
      if (evicted) {
        try { localStorage.removeItem(conversationKey(evicted.id)); } catch { /* ignore */ }
      }
    }

    saveIndex(index);

    // Save full conversation data
    try {
      localStorage.setItem(conversationKey(conversation.id), JSON.stringify(conversation));
    } catch (e) {
      console.warn('Failed to save conversation to localStorage:', e);
    }
  }, [loadIndex, saveIndex]);

  const loadConversation = useCallback((id: string): StoredConversation | null => {
    try {
      const raw = localStorage.getItem(conversationKey(id));
      if (!raw) return null;
      const parsed = JSON.parse(raw) as StoredConversation;
      if (!parsed || typeof parsed.id !== 'string' || !parsed.sessionData) return null;
      return parsed;
    } catch {
      // Corrupted — remove it
      try { localStorage.removeItem(conversationKey(id)); } catch { /* ignore */ }
      return null;
    }
  }, []);

  const deleteConversation = useCallback((id: string) => {
    const index = loadIndex().filter((e) => e.id !== id);
    saveIndex(index);
    try { localStorage.removeItem(conversationKey(id)); } catch { /* ignore */ }
  }, [loadIndex, saveIndex]);

  const deleteConversationsByCustomAgent = useCallback((customAgentId: string) => {
    const index = loadIndex();
    const keep: ConversationIndexEntry[] = [];
    for (const e of index) {
      if (e.customAgentId === customAgentId) {
        try { localStorage.removeItem(conversationKey(e.id)); } catch { /* ignore */ }
      } else {
        keep.push(e);
      }
    }
    saveIndex(keep);
  }, [loadIndex, saveIndex]);

  return {
    loadIndex,
    saveConversation,
    loadConversation,
    deleteConversation,
    deleteConversationsByCustomAgent,
  };
}
