import { useCallback } from 'react';
import type { ConversationIndexEntry, StoredConversation } from '../types/api';
import { readJson, removeStorageItem, tryWriteJson } from '../utils/storage';

declare const __MAX_SESSIONS__: string;

const INDEX_KEY = 'webagents_conversation_index';
const CONVERSATION_KEY_PREFIX = 'webagents_conversation_';

function getMaxSessions(): number {
  return parseInt(__MAX_SESSIONS__, 10) || 5;
}

function conversationKey(id: string): string {
  return `${CONVERSATION_KEY_PREFIX}${id}`;
}

function isConversationIndex(value: unknown): value is ConversationIndexEntry[] {
  return Array.isArray(value) && value.every(
    (entry) => entry && typeof entry.id === 'string' && typeof entry.description === 'string',
  );
}

export function useConversationStore() {
  const loadIndex = useCallback((): ConversationIndexEntry[] => {
    const entries = readJson<ConversationIndexEntry[]>(INDEX_KEY, [], isConversationIndex);
    const max = getMaxSessions();
    if (entries.length > max) {
      entries.sort((a, b) => new Date(b.lastActivityAt).getTime() - new Date(a.lastActivityAt).getTime());
      const evicted = entries.splice(max);
      for (const entry of evicted) {
        removeStorageItem(conversationKey(entry.id));
      }
      tryWriteJson(INDEX_KEY, entries);
    }
    return entries;
  }, []);

  const saveIndex = useCallback((index: ConversationIndexEntry[]) => {
    tryWriteJson(INDEX_KEY, index, (error) => console.warn('Failed to save conversation index to localStorage:', error));
  }, []);

  const saveConversation = useCallback((conversation: StoredConversation) => {
    const index = loadIndex();

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
      ...(conversation.usedBuiltInOverride ? {
        usedBuiltInOverride: true,
        baseProfileId: conversation.baseProfileId,
        overrideUpdatedAt: conversation.overrideUpdatedAt,
      } : {}),
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
        removeStorageItem(conversationKey(evicted.id));
      }
    }

    saveIndex(index);

    // Save full conversation data
    tryWriteJson(
      conversationKey(conversation.id),
      conversation,
      (error) => console.warn('Failed to save conversation to localStorage:', error),
    );
  }, [loadIndex, saveIndex]);

  const loadConversation = useCallback((id: string): StoredConversation | null => {
    return readJson<StoredConversation | null>(conversationKey(id), null, (value): value is StoredConversation => (
      Boolean(value && typeof value === 'object' && typeof (value as StoredConversation).id === 'string' && (value as StoredConversation).sessionData)
    ));
  }, []);

  const deleteConversation = useCallback((id: string) => {
    const index = loadIndex().filter((e) => e.id !== id);
    saveIndex(index);
    removeStorageItem(conversationKey(id));
  }, [loadIndex, saveIndex]);

  const deleteConversationsByCustomAgent = useCallback((customAgentId: string) => {
    const index = loadIndex();
    const keep: ConversationIndexEntry[] = [];
    for (const e of index) {
      if (e.customAgentId === customAgentId) {
        removeStorageItem(conversationKey(e.id));
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
