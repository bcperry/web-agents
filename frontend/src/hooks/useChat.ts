import { useState, useCallback, useRef } from 'react';
import type {
  ChatMessage,
  ChatSession,
  McpServerEntry,
  StoredConversation,
  ToolInvocation,
  UsageDetails,
} from '../types/api';
import {
  createSession,
  createCustomSession,
  createSessionWithHistory,
  deleteSession,
  fetchHistory,
  sendMessage,
  AuthError,
} from '../api/client';
import { emitToast } from './useToast';
import { useConversationStore } from './useConversationStore';
import { loadProfile, saveProfile } from './useUserProfile';

export interface CustomAgentParams {
  customAgentId: string;
  custom_name: string;
  custom_prompt: string;
  custom_tools: string[];
  custom_search_context: boolean;
  custom_temperature?: number;
  custom_skills?: string[];
  mcp_servers?: McpServerEntry[];
}

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  session: ChatSession | null;
  sessionUsage: UsageDetails;
  error: string | null;
  conversationId: string | null;
  saveCounter: number;
  startSession: (profileId: string, history?: StoredConversation, customParams?: CustomAgentParams) => Promise<void>;
  endSession: () => Promise<void>;
  send: (content: string, images?: File[]) => Promise<void>;
  clearError: () => void;
  saveCurrentConversation: () => Promise<void>;
}

export function useChat(): ChatState {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [session, setSession] = useState<ChatSession | null>(null);
  const [sessionUsage, setSessionUsage] = useState<UsageDetails>({
    input_token_count: 0,
    output_token_count: 0,
    total_token_count: 0,
  });
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [saveCounter, setSaveCounter] = useState(0);

  // Accumulator refs for building the current assistant message during streaming
  const textAccRef = useRef('');
  const toolsRef = useRef<ToolInvocation[]>([]);
  const turnUsageRef = useRef<UsageDetails | null>(null);
  const createdAtRef = useRef<string | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const customAgentIdRef = useRef<string | null>(null);

  const { saveConversation } = useConversationStore();

  const saveCurrentConversation = useCallback(async () => {
    if (!session) return;
    const convId = conversationIdRef.current || session.session_id;
    try {
      const historyResp = await fetchHistory(session.session_id);
      const firstUserMsg = messages.find((m) => m.role === 'user');
      const desc = firstUserMsg
        ? firstUserMsg.content.slice(0, 60) + (firstUserMsg.content.length > 60 ? '...' : '')
        : 'New conversation';
      const now = new Date().toISOString();
      saveConversation({
        id: convId,
        profileId: session.profile_id,
        profileName: session.profile_name,
        description: desc,
        createdAt: createdAtRef.current || now,
        lastActivityAt: now,
        sessionData: historyResp.session_data,
        ...(customAgentIdRef.current ? { customAgentId: customAgentIdRef.current } : {}),
      });
    } catch {
      // Non-fatal — persistence is best-effort
    }
  }, [session, messages, saveConversation]);

  const startSession = useCallback(async (profileId: string, history?: StoredConversation, customParams?: CustomAgentParams) => {
    try {
      // Clean up previous session if any
      if (session) {
        await deleteSession(session.session_id).catch(() => {});
      }

      let newSession: ChatSession;
      let restoredMessages: ChatMessage[] = [];

      if (customParams) {
        // Custom agent session (fresh or with history resume)
        customAgentIdRef.current = customParams.customAgentId;
        const profile = loadProfile();
        newSession = await createCustomSession({
          ...customParams,
          ...(history?.sessionData ? { history: history.sessionData } : {}),
          ...(profile ? { user_profile: { name: profile.name, preferences: profile.preferences, notes: profile.notes } } : {}),
        });
        if (history) {
          createdAtRef.current = history.createdAt;
          setConversationId(history.id);
          conversationIdRef.current = history.id;
          restoredMessages = extractMessagesFromSessionData(history.sessionData);
        } else {
          createdAtRef.current = new Date().toISOString();
          setConversationId(newSession.session_id);
          conversationIdRef.current = newSession.session_id;
        }
      } else if (history?.sessionData) {
        // Resume standard profile with history
        customAgentIdRef.current = null;
        const profile = loadProfile();
        newSession = await createSessionWithHistory(profileId, history.sessionData, profile);
        createdAtRef.current = history.createdAt;
        setConversationId(history.id);
        conversationIdRef.current = history.id;
        restoredMessages = extractMessagesFromSessionData(history.sessionData);
      } else {
        // Fresh session
        customAgentIdRef.current = null;
        const profile = loadProfile();
        newSession = await createSession(profileId, profile);
        createdAtRef.current = new Date().toISOString();
        setConversationId(newSession.session_id);
        conversationIdRef.current = newSession.session_id;
      }

      setSession(newSession);
      setMessages(restoredMessages);
      setSessionUsage({ input_token_count: 0, output_token_count: 0, total_token_count: 0 });
      setError(null);
    } catch (err) {
      if (err instanceof AuthError) {
        setError(err.message);
      }
      // Non-auth errors already emitted as toasts by client.ts
    }
  }, [session]);

  const endSession = useCallback(async () => {
    if (session) {
      await deleteSession(session.session_id).catch(() => {});
    }
    setSession(null);
    setMessages([]);
    setConversationId(null);
    conversationIdRef.current = null;
    createdAtRef.current = null;
    setSessionUsage({ input_token_count: 0, output_token_count: 0, total_token_count: 0 });
  }, [session]);

  const send = useCallback(async (content: string, images?: File[]) => {
    if (!session) {
      setError('No active session. Please select a profile first.');
      return;
    }

    // Add user message
    const userMessage: ChatMessage = {
      role: 'user',
      content,
      images: images?.map((f) => ({
        filename: f.name,
        media_type: f.type,
        data: URL.createObjectURL(f),
      })),
    };
    setMessages((prev) => [...prev, userMessage]);
    setIsStreaming(true);
    setError(null);

    // Reset accumulators
    textAccRef.current = '';
    toolsRef.current = [];
    turnUsageRef.current = null;

    // Add placeholder assistant message
    const assistantIndex = messages.length + 1; // after user message
    setMessages((prev) => [
      ...prev,
      { role: 'assistant', content: '', tool_invocations: [], usage: null },
    ]);

    try {
      await sendMessage(
        session.session_id,
        content,
        images && images.length > 0 ? images : null,
        {
          onText: (data) => {
            textAccRef.current += data.content;
            setMessages((prev) => {
              const updated = [...prev];
              updated[assistantIndex] = {
                ...updated[assistantIndex],
                content: textAccRef.current,
              };
              return updated;
            });
          },
          onFunctionCall: (data) => {
            toolsRef.current = [
              ...toolsRef.current,
              {
                call_id: data.call_id,
                name: data.name,
                arguments: data.arguments,
                result: '',
              },
            ];
            setMessages((prev) => {
              const updated = [...prev];
              updated[assistantIndex] = {
                ...updated[assistantIndex],
                tool_invocations: [...toolsRef.current],
              };
              return updated;
            });
          },
          onFunctionResult: (data) => {
            toolsRef.current = toolsRef.current.map((t) =>
              t.call_id === data.call_id
                ? {
                    ...t,
                    result: data.result,
                    arguments: (data.arguments && data.arguments.length > 0)
                      ? data.arguments
                      : t.arguments,
                  }
                : t
            );
            // If no matching call_id found (MCP/framework mismatch), try matching by most recent pending tool
            if (!toolsRef.current.some((t) => t.call_id === data.call_id)) {
              const pending = toolsRef.current.findIndex((t) => !t.result);
              if (pending >= 0) {
                toolsRef.current[pending] = {
                  ...toolsRef.current[pending],
                  result: data.result,
                  arguments: (data.arguments && data.arguments.length > 0)
                    ? data.arguments
                    : toolsRef.current[pending].arguments,
                };
              }
            }
            setMessages((prev) => {
              const updated = [...prev];
              updated[assistantIndex] = {
                ...updated[assistantIndex],
                tool_invocations: [...toolsRef.current],
              };
              return updated;
            });
          },
          onUsage: (data) => {
            turnUsageRef.current = data;
            setSessionUsage((prev) => ({
              input_token_count: prev.input_token_count + data.input_token_count,
              output_token_count: prev.output_token_count + data.output_token_count,
              total_token_count: prev.total_token_count + data.total_token_count,
            }));
            setMessages((prev) => {
              const updated = [...prev];
              updated[assistantIndex] = {
                ...updated[assistantIndex],
                usage: data,
              };
              return updated;
            });
          },
          onError: (data) => {
            const isRetryable = data.retry_after != null;
            emitToast({
              message: data.message,
              type: isRetryable ? 'warning' : 'error',
              ...(isRetryable ? { action: { label: 'RETRY', onClick: () => send(content, images) } } : {}),
            });
          },
          onDone: () => {
            setIsStreaming(false);
            // Sync user profile if save_user_profile was called
            const profileSave = toolsRef.current.find((t) => t.name === 'save_user_profile');
            if (profileSave && session) {
              try {
                const args = JSON.parse(profileSave.arguments);
                saveProfile(session.profile_id, {
                  name: args.name ?? '',
                  preferences: args.preferences ?? '',
                  notes: args.notes ?? '',
                  updatedAt: new Date().toISOString(),
                });
              } catch { /* best-effort */ }
            }
            // Auto-save conversation after response completes
            if (session) {
              const convId = conversationIdRef.current || session.session_id;
              fetchHistory(session.session_id)
                .then((historyResp) => {
                  // Build description from the first user message in the conversation
                  // We need to use the messages including the one we just sent
                  setMessages((currentMessages) => {
                    const firstUserMsg = currentMessages.find((m) => m.role === 'user');
                    const desc = firstUserMsg
                      ? firstUserMsg.content.slice(0, 60) + (firstUserMsg.content.length > 60 ? '...' : '')
                      : 'New conversation';
                    const now = new Date().toISOString();
                    saveConversation({
                      id: convId,
                      profileId: session.profile_id,
                      profileName: session.profile_name,
                      description: desc,
                      createdAt: createdAtRef.current || now,
                      lastActivityAt: now,
                      sessionData: historyResp.session_data,
                      ...(customAgentIdRef.current ? { customAgentId: customAgentIdRef.current } : {}),
                    });
                    return currentMessages; // Don't modify messages
                  });
                  setSaveCounter((c) => c + 1);
                })
                .catch(() => { /* persistence is best-effort */ });
            }
          },
        },
      );
    } catch (err) {
      if (err instanceof AuthError) {
        setError(err.message);
      }
      // Non-auth errors already emitted as toasts by client.ts
      setIsStreaming(false);
    }
  }, [session, messages.length, saveConversation]);

  const clearError = useCallback(() => setError(null), []);

  return {
    messages,
    isStreaming,
    session,
    sessionUsage,
    error,
    conversationId,
    saveCounter,
    startSession,
    endSession,
    send,
    clearError,
    saveCurrentConversation,
  };
}

/**
 * Extract displayable messages from the framework's opaque session data.
 * The session state has `in_memory` containing serialized Message objects.
 */
function extractMessagesFromSessionData(sessionData: Record<string, unknown>): ChatMessage[] {
  try {
    const state = sessionData.state as Record<string, unknown> | undefined;
    if (!state) return [];
    const inMemoryProvider = state.in_memory as Record<string, unknown> | undefined;
    if (!inMemoryProvider) return [];
    const inMemory = inMemoryProvider.messages as Array<Record<string, unknown>> | undefined;
    if (!Array.isArray(inMemory)) return [];

    const result: ChatMessage[] = [];
    for (const msg of inMemory) {
      const role = msg.role as string;
      const contents = msg.contents as Array<Record<string, unknown>> | undefined;
      if (!Array.isArray(contents)) continue;

      if (role === 'tool') {
        // Attach tool results to the last assistant message's tool_invocations
        const lastAssistant = result.length > 0 ? result[result.length - 1] : null;
        if (lastAssistant?.role === 'assistant' && lastAssistant.tool_invocations) {
          for (const content of contents) {
            if (content.type === 'function_result' || content.type === 'mcp_server_tool_result') {
              const callId = content.call_id as string;
              const existing = lastAssistant.tool_invocations.find((t) => t.call_id === callId);
              if (existing) {
                const rawResult = content.type === 'mcp_server_tool_result' ? content.output : content.result;
                if (Array.isArray(rawResult)) {
                  const textParts = rawResult
                    .filter((item: Record<string, unknown>) => item.type === 'text')
                    .map((item: Record<string, unknown>) => item.text as string || '');
                  existing.result = textParts.length > 0 ? textParts.join('\n') : JSON.stringify(rawResult);
                } else {
                  existing.result = typeof rawResult === 'string'
                    ? rawResult
                    : JSON.stringify(rawResult ?? '');
                }
              }
            }
          }
        }
        continue;
      }

      if (role !== 'user' && role !== 'assistant') continue;

      let text = '';
      const toolInvocations: ToolInvocation[] = [];

      for (const content of contents) {
        const type = content.type as string;
        if (type === 'text') {
          text += content.text as string || '';
        } else if (type === 'function_call' || type === 'mcp_server_tool_call') {
          const args = content.arguments;
          toolInvocations.push({
            call_id: (content.call_id as string) || '',
            name: (content.name as string) || (content.tool_name as string) || '',
            arguments: typeof args === 'string' ? args : JSON.stringify(args ?? ''),
            result: '',
          });
        }
      }

      result.push({
        role: role as 'user' | 'assistant',
        content: text,
        tool_invocations: toolInvocations.length > 0 ? toolInvocations : undefined,
      });
    }
    return result;
  } catch {
    return [];
  }
}
