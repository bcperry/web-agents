import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentView, AgentViewSummary, SSEAgentViewEvent } from '../types/api';
import { getAgentView, listAgentViews } from '../api/client';

export interface AgentViewsState {
  views: AgentViewSummary[];
  activeView: AgentView | null;
  activeViewId: string | null;
  isOpen: boolean;
  isLoading: boolean;
  error: string | null;
  width: number;
  setWidth: (width: number) => void;
  setSessionId: (sessionId: string | null) => void;
  handleAgentViewEvent: (event: SSEAgentViewEvent) => void;
  selectView: (viewId: string) => void;
  open: () => void;
  close: () => void;
  retry: () => void;
}

const DEFAULT_WIDTH = 480;
export const MIN_PANE_WIDTH = 320;
export const MAX_PANE_WIDTH = 720;

interface StoredPaneState {
  open: boolean;
  width: number;
  activeViewId: string | null;
}

function paneStateKey(sessionId: string): string {
  return `agentViewPane:${sessionId}`;
}

function readPaneState(sessionId: string): StoredPaneState {
  const fallback: StoredPaneState = { open: false, width: DEFAULT_WIDTH, activeViewId: null };
  try {
    const raw = localStorage.getItem(paneStateKey(sessionId));
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return {
      open: typeof parsed?.open === 'boolean' ? parsed.open : fallback.open,
      width: typeof parsed?.width === 'number'
        ? Math.min(MAX_PANE_WIDTH, Math.max(MIN_PANE_WIDTH, parsed.width))
        : fallback.width,
      activeViewId: typeof parsed?.activeViewId === 'string' ? parsed.activeViewId : null,
    };
  } catch {
    return fallback;
  }
}

function writePaneState(sessionId: string, state: StoredPaneState): void {
  try {
    localStorage.setItem(paneStateKey(sessionId), JSON.stringify(state));
  } catch {
    /* storage full or unavailable — pane geometry is not worth failing over */
  }
}

/**
 * Owns the agent views for the active conversation.
 *
 * Which views exist is server state; which one is showing, and how the pane is
 * laid out, is client state persisted per conversation in localStorage.
 *
 * The session id lives in a ref as well as state so `handleAgentViewEvent` stays
 * referentially stable — `useChat` captures it once when the stream starts.
 */
export function useAgentViews(): AgentViewsState {
  const [views, setViews] = useState<AgentViewSummary[]>([]);
  const [activeViewId, setActiveViewId] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<AgentView | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [width, setWidthState] = useState(DEFAULT_WIDTH);

  const sessionIdRef = useRef<string | null>(null);

  const persist = useCallback((patch: Partial<StoredPaneState>) => {
    const sessionId = sessionIdRef.current;
    if (!sessionId) return;
    writePaneState(sessionId, { ...readPaneState(sessionId), ...patch });
  }, []);

  const loadView = useCallback(async (viewId: string) => {
    const sessionId = sessionIdRef.current;
    if (!sessionId) return;
    setIsLoading(true);
    setError(null);
    try {
      const view = await getAgentView(sessionId, viewId);
      // Ignore a late response for a view the user has already navigated away from.
      setActiveViewId((current) => {
        if (current === viewId) setActiveView(view);
        return current;
      });
    } catch {
      setError('This view could not be loaded.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const setSessionId = useCallback((sessionId: string | null) => {
    if (sessionIdRef.current === sessionId) return;
    sessionIdRef.current = sessionId;
    setViews([]);
    setActiveViewId(null);
    setActiveView(null);
    setError(null);

    if (!sessionId) {
      setIsOpen(false);
      setWidthState(DEFAULT_WIDTH);
      return;
    }

    const stored = readPaneState(sessionId);
    setWidthState(stored.width);
    setIsOpen(false);

    // Restore views stored for this conversation, including any produced by an
    // unattended run while nobody was watching.
    void (async () => {
      try {
        const restored = await listAgentViews(sessionId);
        if (sessionIdRef.current !== sessionId) return;
        setViews(restored);
        if (restored.length === 0) return;
        const preferred = restored.find((v) => v.viewId === stored.activeViewId)
          || restored[restored.length - 1];
        setActiveViewId(preferred.viewId);
        setIsOpen(stored.open);
        void loadView(preferred.viewId);
      } catch {
        /* a conversation with no views, or a transient read failure */
      }
    })();
  }, [loadView]);

  const handleAgentViewEvent = useCallback((event: SSEAgentViewEvent) => {
    setViews((prev) =>
      prev.some((v) => v.viewId === event.view_id)
        ? prev
        : [...prev, {
            viewId: event.view_id,
            title: event.title,
            createdAt: event.created_at,
            chars: 0,
            source: 'chat',
          }],
    );
    setActiveViewId(event.view_id);
    setActiveView(null);
    setIsOpen(true);
    persist({ open: true, activeViewId: event.view_id });
    void loadView(event.view_id);
  }, [loadView, persist]);

  const selectView = useCallback((viewId: string) => {
    setActiveViewId(viewId);
    setActiveView(null);
    setIsOpen(true);
    persist({ open: true, activeViewId: viewId });
    void loadView(viewId);
  }, [loadView, persist]);

  const open = useCallback(() => {
    setIsOpen(true);
    persist({ open: true });
  }, [persist]);

  const close = useCallback(() => {
    setIsOpen(false);
    persist({ open: false });
  }, [persist]);

  const setWidth = useCallback((next: number) => {
    const clamped = Math.min(MAX_PANE_WIDTH, Math.max(MIN_PANE_WIDTH, next));
    setWidthState(clamped);
    persist({ width: clamped });
  }, [persist]);

  const retry = useCallback(() => {
    if (activeViewId) void loadView(activeViewId);
  }, [activeViewId, loadView]);

  useEffect(() => {
    if (activeViewId) persist({ activeViewId });
  }, [activeViewId, persist]);

  return {
    views,
    activeView,
    activeViewId,
    isOpen,
    isLoading,
    error,
    width,
    setWidth,
    setSessionId,
    handleAgentViewEvent,
    selectView,
    open,
    close,
    retry,
  };
}
