import { useCallback, useEffect, useRef } from 'react';
import type { AgentView, AgentViewSummary } from '../types/api';
import { AgentViewFrame } from './AgentViewFrame';
import { MAX_PANE_WIDTH, MIN_PANE_WIDTH } from '../hooks/useAgentViews';

interface AgentViewPaneProps {
  sessionId: string | null;
  views: AgentViewSummary[];
  activeView: AgentView | null;
  activeViewId: string | null;
  isLoading: boolean;
  error: string | null;
  width: number;
  onSelectView: (viewId: string) => void;
  onSetWidth: (width: number) => void;
  onClose: () => void;
  onRetry: () => void;
}

export function AgentViewPane({
  sessionId,
  views,
  activeView,
  activeViewId,
  isLoading,
  error,
  width,
  onSelectView,
  onSetWidth,
  onClose,
  onRetry,
}: AgentViewPaneProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const activeSummary = views.find((v) => v.viewId === activeViewId) || null;
  const title = activeView?.title || activeSummary?.title || 'Agent view';
  const isAutonomous = activeSummary?.source === 'autonomous';

  // Focus the pane heading on open so keyboard users land inside it; Escape
  // returns them to the conversation rather than trapping them in the frame.
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const startResize = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;

    function onMove(move: PointerEvent) {
      onSetWidth(startWidth + (startX - move.clientX));
    }
    function onUp() {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    }
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [onSetWidth, width]);

  const nudgeWidth = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowLeft') onSetWidth(width + 32);
    else if (event.key === 'ArrowRight') onSetWidth(width - 32);
  }, [onSetWidth, width]);

  return (
    <aside className="agent-view-pane" style={{ width }} aria-label="Agent-generated view">
      <div
        className="agent-view-resize"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize view pane"
        aria-valuenow={width}
        aria-valuemin={MIN_PANE_WIDTH}
        aria-valuemax={MAX_PANE_WIDTH}
        tabIndex={0}
        onPointerDown={startResize}
        onKeyDown={nudgeWidth}
      />

      <div className="agent-view-header">
        <div className="agent-view-titles">
          <h2 className="agent-view-title" ref={headingRef} tabIndex={-1}>{title}</h2>
          <div className="agent-view-tags">
            <span className="agent-view-provenance">AGENT-GENERATED</span>
            {isAutonomous && <span className="agent-view-provenance">UNATTENDED RUN</span>}
          </div>
        </div>
        <button
          className="agent-view-close"
          onClick={onClose}
          type="button"
          title="Back to chat"
          aria-label="Close view and return to the conversation"
        >
          ×
        </button>
      </div>

      {views.length > 1 && (
        <div className="agent-view-switcher" role="tablist" aria-label="Agent views">
          {views.map((view) => (
            <button
              key={view.viewId}
              className={`agent-view-tab ${view.viewId === activeViewId ? 'active' : ''}`}
              onClick={() => onSelectView(view.viewId)}
              type="button"
              role="tab"
              aria-selected={view.viewId === activeViewId}
            >
              {view.title}
            </button>
          ))}
        </div>
      )}

      <div className="agent-view-body">
        {error ? (
          <div className="agent-view-state agent-view-state--error">
            <p>{error}</p>
            <button className="agent-view-retry" onClick={onRetry} type="button">
              RETRY
            </button>
          </div>
        ) : isLoading || !activeView ? (
          <div className="agent-view-state">
            <div className="spinner-ring" />
            <p>Loading view...</p>
          </div>
        ) : (
          <AgentViewFrame
            sessionId={sessionId}
            viewId={activeView.viewId}
            title={activeView.title}
            html={activeView.html}
          />
        )}
      </div>

      <button className="agent-view-back" onClick={onClose} type="button">
        BACK TO CHAT
      </button>
    </aside>
  );
}
