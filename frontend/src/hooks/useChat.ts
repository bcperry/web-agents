import { useState, useCallback, useRef, useEffect } from 'react';
import type {
  AgentProfile,
  ChatMessage,
  ChatSession,
  ConversationIndexEntry,
  SessionCreateResponse,
  SSEAgentViewEvent,
  ToolInvocation,
  UsageDetails,
} from '../types/api';
import {
  sendMessage,
  AuthError,
} from '../api/client';
import { emitToast } from './useToast';
import { RequestError } from '../api/helpers';
import { cleanupSession, emptyUsage, startChatSession } from './useSessionLifecycle';

export function useChat(
  onCustomAgentsChanged?: () => void,
  onAgentView?: (event: SSEAgentViewEvent) => void,
) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [session, setSession] = useState<SessionCreateResponse | null>(null);
  const [sessionUsage, setSessionUsage] = useState<UsageDetails>(emptyUsage);
  const [error, setError] = useState<string | null>(null);
  const [saveCounter, setSaveCounter] = useState(0);

  const generationRef = useRef(0);
  const lifecycleRef = useRef<Promise<unknown>>(Promise.resolve());
  const sessionRef = useRef<ChatSession | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const imageUrlsRef = useRef<string[]>([]);

  const invalidateRequest = useCallback(() => {
    generationRef.current += 1;
    requestRef.current?.abort();
    requestRef.current = null;
    imageUrlsRef.current.forEach(url => URL.revokeObjectURL(url));
    imageUrlsRef.current = [];
    return generationRef.current;
  }, []);

  useEffect(() => () => {
    invalidateRequest();
    const previous = sessionRef.current;
    lifecycleRef.current = lifecycleRef.current.then(() => cleanupSession(previous));
    sessionRef.current = null;
  }, [invalidateRequest]);

  const startSession = useCallback(async (profile: AgentProfile, resume?: ConversationIndexEntry) => {
    const generation = invalidateRequest();
    const previous = sessionRef.current;
    sessionRef.current = null;
    setSession(null);
    setMessages([]);
    setIsStreaming(false);
    const operation = lifecycleRef.current.then(async () => {
      try {
        await cleanupSession(previous);
        if (generation !== generationRef.current) return false;
        const next = await startChatSession(profile, resume);
        if (generation !== generationRef.current) {
          await cleanupSession(next.session);
          return false;
        }
        sessionRef.current = next.session;
        setSession(next.session);
        setMessages(next.restoredMessages);
        setSessionUsage(emptyUsage());
        setError(null);

        const failed = next.session.mcp_results?.filter((r) => r.status === 'failed') ?? [];
        if (failed.length > 0) {
          const names = failed.map((r) => r.name).join(', ');
          emitToast({
            message: `MCP server${failed.length > 1 ? 's' : ''} failed to connect: ${names}`,
            type: 'warning',
          });
        }
        return true;
      } catch (err) {
        if (generation !== generationRef.current) return false;
        if (err instanceof AuthError) {
          setError(err.message);
        }
        return false;
      }
    });
    lifecycleRef.current = operation;
    return operation;
  }, [invalidateRequest]);

  const endSession = useCallback(async () => {
    invalidateRequest();
    const previous = sessionRef.current;
    sessionRef.current = null;
    setSession(null);
    setIsStreaming(false);
    setMessages([]);
    setSessionUsage(emptyUsage());
    lifecycleRef.current = lifecycleRef.current.then(() => cleanupSession(previous));
    await lifecycleRef.current;
  }, [invalidateRequest]);

  const send = useCallback(async (content: string, images?: File[]) => {
    if (!session || requestRef.current) {
      setError('No active session. Please select a profile first.');
      return;
    }
    const controller = new AbortController();
    requestRef.current = controller;
    const generation = generationRef.current;
    const isCurrent = () => generation === generationRef.current && !controller.signal.aborted;
    let text = '';
    let tools: ToolInvocation[] = [];
    const assistantIndex = messages.length + 1;
    const updateAssistant = (patch: Partial<ChatMessage>) => {
      setMessages(previous => previous.map((message, index) =>
        index === assistantIndex ? { ...message, ...patch } : message));
    };

    // Add user message
    const userMessage: ChatMessage = {
      role: 'user',
      content,
      images: images?.map(file => {
        const data = URL.createObjectURL(file);
        imageUrlsRef.current.push(data);
        return { filename: file.name, media_type: file.type, data };
      }),
    };
    setIsStreaming(true);
    setError(null);

    setMessages((prev) => [
      ...prev,
      userMessage,
      { role: 'assistant', content: '', tool_invocations: [], usage: null },
    ]);

    try {
      await sendMessage(
        session.session_id,
        content,
        images && images.length > 0 ? images : null,
        {
          onText: (data) => {
            if (!isCurrent()) return;
            text += data.content;
            updateAssistant({ content: text });
          },
          onFunctionCall: (data) => {
            if (!isCurrent()) return;
            const existingIdx = tools.findIndex((t) => t.call_id === data.call_id);
            if (existingIdx >= 0) {
              // Continuation chunk — update the existing tool's arguments
              tools = tools.map((t, i) =>
                i === existingIdx ? { ...t, arguments: data.arguments } : t
              );
            } else {
              tools = [
                ...tools,
                {
                  call_id: data.call_id,
                  name: data.name,
                  arguments: data.arguments,
                  result: '',
                },
              ];
            }
            updateAssistant({ tool_invocations: tools });
          },
          onFunctionResult: (data) => {
            if (!isCurrent()) return;
            const matching = tools.findIndex(tool => tool.call_id === data.call_id);
            const target = matching >= 0 ? matching : tools.findIndex(tool => !tool.result);
            tools = tools.map((tool, index) =>
              index === target
                ? {
                    ...tool,
                    result: data.result,
                    arguments: data.arguments || tool.arguments,
                    ...(data.content_items ? { content_items: data.content_items } : {}),
                  }
                : tool
            );
            updateAssistant({ tool_invocations: tools });
          },
          onUsage: (data) => {
            if (!isCurrent()) return;
            setSessionUsage((prev) => ({
              input_token_count: prev.input_token_count + data.input_token_count,
              output_token_count: prev.output_token_count + data.output_token_count,
              total_token_count: prev.total_token_count + data.total_token_count,
            }));
            updateAssistant({ usage: data });
          },
          onError: (data) => {
            if (!isCurrent()) return;
            const isRetryable = data.retry_after != null;
            emitToast({
              message: data.message,
              type: isRetryable ? 'warning' : 'error',
            });
          },
          onAgentView: (data) => {
            if (!isCurrent()) return;
            onAgentView?.(data);
          },
          onDone: () => {
            if (!isCurrent()) return;
            setIsStreaming(false);
            if (tools.some((tool) =>
              tool.name === 'create_agent' || tool.name === 'edit_agent'
            )) {
              onCustomAgentsChanged?.();
            }
            // The backend already persisted this turn to Cosmos and updated the
            // conversation index; bump the save counter so the sidebar reloads
            // the server-sourced conversation list.
            setSaveCounter((c) => c + 1);
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (!isCurrent()) return;
      if (err instanceof AuthError) {
        setError(err.message);
      } else if (!(err instanceof RequestError)) {
        emitToast({ message: err instanceof Error ? err.message : 'The response could not be completed.', type: 'error' });
      }
    } finally {
      if (isCurrent()) {
        requestRef.current = null;
        setIsStreaming(false);
      }
    }
  }, [session, messages.length, onCustomAgentsChanged, onAgentView]);

  return {
    messages,
    isStreaming,
    session,
    sessionUsage,
    mcpResults: session?.mcp_results ?? [],
    toolsLoaded: session?.tools_loaded ?? [],
    skillsLoaded: session?.skills_loaded ?? [],
    agentsLoaded: session?.agents_loaded ?? [],
    searchContext: session?.search_context ?? false,
    error,
    saveCounter,
    startSession,
    endSession,
    send,
  };
}
