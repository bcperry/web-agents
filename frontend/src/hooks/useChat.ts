import { useState, useCallback, useRef } from 'react';
import type {
  AgentProfile,
  ChatMessage,
  ChatSession,
  ConversationIndexEntry,
  McpConnectionResult,
  SSEAgentViewEvent,
  ToolInvocation,
  UsageDetails,
} from '../types/api';
import {
  sendMessage,
  AuthError,
} from '../api/client';
import { emitToast } from './useToast';
import { cleanupSession, emptyBuiltInOverride, emptyUsage, startChatSession } from './useSessionLifecycle';

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  session: ChatSession | null;
  sessionUsage: UsageDetails;
  mcpResults: McpConnectionResult[];
  toolsLoaded: string[];
  skillsLoaded: string[];
  agentsLoaded: string[];
  searchContext: boolean;
  error: string | null;
  conversationId: string | null;
  saveCounter: number;
  startSession: (profile: AgentProfile, resume?: ConversationIndexEntry) => Promise<void>;
  endSession: () => Promise<void>;
  send: (content: string, images?: File[]) => Promise<void>;
  clearError: () => void;
}

export function useChat(
  onCustomAgentsChanged?: () => void,
  onAgentView?: (event: SSEAgentViewEvent) => void,
): ChatState {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [session, setSession] = useState<ChatSession | null>(null);
  const [sessionUsage, setSessionUsage] = useState<UsageDetails>(emptyUsage);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [saveCounter, setSaveCounter] = useState(0);
  const [mcpResults, setMcpResults] = useState<McpConnectionResult[]>([]);
  const [toolsLoaded, setToolsLoaded] = useState<string[]>([]);
  const [skillsLoaded, setSkillsLoaded] = useState<string[]>([]);
  const [agentsLoaded, setAgentsLoaded] = useState<string[]>([]);
  const [searchContext, setSearchContext] = useState(false);

  // Accumulator refs for building the current assistant message during streaming
  const textAccRef = useRef('');
  const toolsRef = useRef<ToolInvocation[]>([]);
  const turnUsageRef = useRef<UsageDetails | null>(null);
  const createdAtRef = useRef<string | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const customAgentIdRef = useRef<string | null>(null);
  const builtInOverrideRef = useRef<{
    usedBuiltInOverride: boolean;
    baseProfileId?: string;
    overrideUpdatedAt?: string;
  }>(emptyBuiltInOverride());

  const startSession = useCallback(async (profile: AgentProfile, resume?: ConversationIndexEntry) => {
    try {
      const next = await startChatSession(profile, resume, session);
      createdAtRef.current = next.createdAt;
      conversationIdRef.current = next.conversationId;
      customAgentIdRef.current = next.customAgentId;
      builtInOverrideRef.current = next.builtInOverride;

      setConversationId(next.conversationId);
      setSession(next.session);
      setMcpResults(next.mcpResults);
      setToolsLoaded(next.toolsLoaded);
      setSkillsLoaded(next.skillsLoaded);
      setAgentsLoaded(next.agentsLoaded);
      setSearchContext(next.searchContext);
      setMessages(next.restoredMessages);
      setSessionUsage(emptyUsage());
      setError(null);

      const failed = next.mcpResults.filter((r) => r.status === 'failed');
      if (failed.length > 0) {
        const names = failed.map((r) => r.name).join(', ');
        emitToast({
          message: `MCP server${failed.length > 1 ? 's' : ''} failed to connect: ${names}`,
          type: 'warning',
        });
      }
    } catch (err) {
      if (err instanceof AuthError) {
        setError(err.message);
      }
      // Non-auth errors already emitted as toasts by client.ts
    }
  }, [session]);

  const endSession = useCallback(async () => {
    await cleanupSession(session);
    setSession(null);
    setMessages([]);
    setMcpResults([]);
    setToolsLoaded([]);
    setSkillsLoaded([]);
    setAgentsLoaded([]);
    setSearchContext(false);
    setConversationId(null);
    conversationIdRef.current = null;
    createdAtRef.current = null;
    customAgentIdRef.current = null;
    builtInOverrideRef.current = emptyBuiltInOverride();
    setSessionUsage(emptyUsage());
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
            const existingIdx = toolsRef.current.findIndex((t) => t.call_id === data.call_id);
            if (existingIdx >= 0) {
              // Continuation chunk — update the existing tool's arguments
              toolsRef.current = toolsRef.current.map((t, i) =>
                i === existingIdx ? { ...t, arguments: data.arguments } : t
              );
            } else {
              toolsRef.current = [
                ...toolsRef.current,
                {
                  call_id: data.call_id,
                  name: data.name,
                  arguments: data.arguments,
                  result: '',
                },
              ];
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
          onFunctionResult: (data) => {
            toolsRef.current = toolsRef.current.map((t) =>
              t.call_id === data.call_id
                ? {
                    ...t,
                    result: data.result,
                    arguments: (data.arguments && data.arguments.length > 0)
                      ? data.arguments
                      : t.arguments,
                    ...(data.content_items ? { content_items: data.content_items } : {}),
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
                  ...(data.content_items ? { content_items: data.content_items } : {}),
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
            });
          },
          onAgentView: (data) => {
            onAgentView?.(data);
          },
          onDone: () => {
            setIsStreaming(false);
            if (toolsRef.current.some((tool) =>
              tool.name === 'create_agent' || tool.name === 'edit_agent'
            )) {
              onCustomAgentsChanged?.();
            }
            // The backend already persisted this turn to Cosmos and updated the
            // conversation index; bump the save counter so the sidebar reloads
            // the server-sourced conversation list.
            if (session) {
              setSaveCounter((c) => c + 1);
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
  }, [session, messages.length, onCustomAgentsChanged, onAgentView]);

  const clearError = useCallback(() => setError(null), []);

  return {
    messages,
    isStreaming,
    session,
    sessionUsage,
    mcpResults,
    toolsLoaded,
    skillsLoaded,
    agentsLoaded,
    searchContext,
    error,
    conversationId,
    saveCounter,
    startSession,
    endSession,
    send,
    clearError,
  };
}
