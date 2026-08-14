import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ChatMessage as ChatMessageType, ToolInvocation } from '../types/api';
import { ToolStep } from './ToolStep';
import { getRuntimeConfigSnapshot } from '../config/runtimeConfig';
import { hasToolImages, imageDataUri, toolImages } from '../utils/content';

interface Props {
  message: ChatMessageType;
  onOpenAgentView?: (viewId: string) => void;
}

const AGENT_VIEW_TOOL = 'render_agent_view';

/** A rendered view's marker replaces its raw tool accordion in the transcript. */
function agentViewResult(tool: ToolInvocation): { viewId: string; title: string } | null {
  if (tool.name !== AGENT_VIEW_TOOL || !tool.result) return null;
  try {
    const parsed = JSON.parse(tool.result);
    if (parsed?.status !== 'rendered' || !parsed?.view_id) return null;
    return { viewId: String(parsed.view_id), title: String(parsed.title || 'Agent view') };
  } catch {
    return null;
  }
}

export function ChatMessage({ message, onOpenAgentView }: Props) {
  const isUser = message.role === 'user';
  const { appName, appLogo } = getRuntimeConfigSnapshot();
  const invocations = message.tool_invocations ?? [];
  const viewMarkers = invocations
    .map((tool) => ({ tool, view: agentViewResult(tool) }))
    .filter((entry): entry is { tool: ToolInvocation; view: { viewId: string; title: string } } =>
      entry.view !== null);
  const otherInvocations = invocations.filter((tool) => agentViewResult(tool) === null);

  return (
    <div className={`chat-message ${isUser ? 'user-message' : 'assistant-message'}`}>
      <div className="message-header">
        {isUser
          ? <span className="message-avatar">👤</span>
          : <img className="message-avatar-img" src={appLogo} alt={appName} />
        }
        <span className="message-role">{isUser ? 'You' : `${appName}`}</span>
      </div>
      <div className="message-content">
        {otherInvocations.length > 0 && (
          <div className="tool-steps">
            {otherInvocations.map((tool) => (
              <ToolStep key={tool.call_id} invocation={tool} />
            ))}
          </div>
        )}
        {viewMarkers.map(({ tool, view }) => (
          <button
            key={tool.call_id}
            className="agent-view-marker"
            type="button"
            onClick={() => onOpenAgentView?.(view.viewId)}
          >
            <span className="agent-view-marker-tag">[VIEW]</span>
            <span>{view.title}</span>
          </button>
        ))}
        {/* Inline images from tool results — shown outside collapsed accordions */}
        {hasToolImages(message.tool_invocations) && (
          <div className="message-tool-images">
            {(message.tool_invocations ?? []).flatMap((t) =>
              toolImages(t)
                .map((item, idx) => (
                  <img
                    key={`${t.call_id}-${idx}`}
                    className="message-tool-image"
                    src={imageDataUri(item)}
                    alt={`Result from ${t.name}`}
                  />
                ))
            )}
          </div>
        )}
        <div className="message-text">
          {isUser ? message.content : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children, ...props }) => (
                  <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          )}
        </div>
        {message.images && message.images.length > 0 && (
          <div className="message-images">
            {message.images.map((img, i) => (
              <div key={i} className="message-image-thumb">
                <img src={img.data} alt={img.filename} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
