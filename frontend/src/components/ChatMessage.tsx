import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ChatMessage as ChatMessageType, ContentItem } from '../types/api';
import { ToolStep } from './ToolStep';
import { getRuntimeConfigSnapshot } from '../config/runtimeConfig';

const ALLOWED_IMAGE_MIMES = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/webp']);

interface Props {
  message: ChatMessageType;
}

export function ChatMessage({ message }: Props) {
  const isUser = message.role === 'user';
  const { appName, appLogo } = getRuntimeConfigSnapshot();

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
        {message.tool_invocations && message.tool_invocations.length > 0 && (
          <div className="tool-steps">
            {message.tool_invocations.map((tool) => (
              <ToolStep key={tool.call_id} invocation={tool} />
            ))}
          </div>
        )}
        {/* Inline images from tool results — shown outside collapsed accordions */}
        {message.tool_invocations && message.tool_invocations.some((t) => t.content_items?.some((item: ContentItem) => item.type === 'image')) && (
          <div className="message-tool-images">
            {message.tool_invocations.flatMap((t) =>
              (t.content_items ?? [])
                .filter((item: ContentItem): item is ContentItem & { type: 'image' } =>
                  item.type === 'image' && ALLOWED_IMAGE_MIMES.has((item as { mimeType?: string }).mimeType ?? '')
                )
                .map((item, idx) => (
                  <img
                    key={`${t.call_id}-${idx}`}
                    className="message-tool-image"
                    src={`data:${item.mimeType};base64,${item.data}`}
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
