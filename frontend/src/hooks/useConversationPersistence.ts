import { useCallback } from 'react';
import type { MutableRefObject } from 'react';
import type { ChatMessage, ChatSession, StoredConversation } from '../types/api';
import { fetchHistory } from '../api/client';
import { useConversationStore } from './useConversationStore';
import type { BuiltInOverrideState } from './useSessionLifecycle';

interface ConversationPersistenceOptions {
  session: ChatSession | null;
  messages: ChatMessage[];
  createdAtRef: MutableRefObject<string | null>;
  conversationIdRef: MutableRefObject<string | null>;
  customAgentIdRef: MutableRefObject<string | null>;
  builtInOverrideRef: MutableRefObject<BuiltInOverrideState>;
}

function conversationDescription(messages: ChatMessage[]): string {
  const firstUserMessage = messages.find((message) => message.role === 'user');
  return firstUserMessage
    ? firstUserMessage.content.slice(0, 60) + (firstUserMessage.content.length > 60 ? '...' : '')
    : 'New conversation';
}

export function useConversationPersistence({
  session,
  messages,
  createdAtRef,
  conversationIdRef,
  customAgentIdRef,
  builtInOverrideRef,
}: ConversationPersistenceOptions) {
  const { saveConversation } = useConversationStore();

  const persistConversationSnapshot = useCallback((currentMessages: ChatMessage[], sessionData: Record<string, unknown>) => {
    if (!session) return;
    const now = new Date().toISOString();
    const conversation: StoredConversation = {
      id: conversationIdRef.current || session.session_id,
      profileId: session.profile_id,
      profileName: session.profile_name,
      description: conversationDescription(currentMessages),
      createdAt: createdAtRef.current || now,
      lastActivityAt: now,
      sessionData,
      ...(customAgentIdRef.current ? { customAgentId: customAgentIdRef.current } : {}),
      ...(builtInOverrideRef.current.usedBuiltInOverride ? {
        usedBuiltInOverride: true,
        baseProfileId: builtInOverrideRef.current.baseProfileId,
        overrideUpdatedAt: builtInOverrideRef.current.overrideUpdatedAt,
      } : {}),
    };
    saveConversation(conversation);
  }, [builtInOverrideRef, conversationIdRef, createdAtRef, customAgentIdRef, saveConversation, session]);

  const saveCurrentConversation = useCallback(async () => {
    if (!session) return;
    try {
      const historyResp = await fetchHistory(session.session_id);
      persistConversationSnapshot(messages, historyResp.session_data);
    } catch {
      // Non-fatal: persistence is best-effort.
    }
  }, [messages, persistConversationSnapshot, session]);

  const persistLatestConversation = useCallback(async (currentMessages: ChatMessage[]) => {
    if (!session) return;
    const historyResp = await fetchHistory(session.session_id);
    persistConversationSnapshot(currentMessages, historyResp.session_data);
  }, [persistConversationSnapshot, session]);

  return { persistConversationSnapshot, persistLatestConversation, saveCurrentConversation } as const;
}