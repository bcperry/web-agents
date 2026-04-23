import { useState } from 'react';
import type { ToolInvocation, ContentItem } from '../types/api';

const ALLOWED_IMAGE_MIMES = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/webp']);

interface Props {
  invocation: ToolInvocation;
}

function prettyFormat(raw: string): string {
  // Try direct JSON parse first
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    // Try converting Python repr to JSON (single quotes → double, True/False/None)
    try {
      const jsonified = raw
        .replace(/datetime\.datetime\([^)]+\)/g, (m) => {
          const nums = m.match(/\d+/g);
          if (nums && nums.length >= 3) {
            const [y, mo, d, h = '0', mi = '0', s = '0'] = nums;
            return `"${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}T${h.padStart(2, '0')}:${mi.padStart(2, '0')}:${s.padStart(2, '0')}"`;
          }
          return `"${m}"`;
        })
        .replace(/'/g, '"')
        .replace(/\bTrue\b/g, 'true')
        .replace(/\bFalse\b/g, 'false')
        .replace(/\bNone\b/g, 'null');
      return JSON.stringify(JSON.parse(jsonified), null, 2);
    } catch {
      return raw;
    }
  }
}

export function ToolStep({ invocation }: Props) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="tool-step">
      <button
        className="tool-step-header"
        onClick={() => setExpanded(!expanded)}
        type="button"
      >
        <span className="tool-step-icon">{expanded ? '▼' : '►'}</span>
        <span className="tool-step-name">[TOOL] {invocation.name}</span>
        {invocation.result ? (
          <span className="tool-step-status">✓</span>
        ) : (
          <span className="tool-step-status tool-step-pending">⏳</span>
        )}
      </button>
      {expanded && (
        <div className="tool-step-details">
          <div className="tool-step-section">
            <div className="tool-step-label">Arguments</div>
            <pre className="tool-step-code">{prettyFormat(invocation.arguments)}</pre>
          </div>
          {invocation.result && (
            <div className="tool-step-section">
              <div className="tool-step-label">Result</div>
              <pre className="tool-step-code">{prettyFormat(invocation.result)}</pre>
              {invocation.content_items && invocation.content_items.length > 0 && (
                <div className="tool-result-images">
                  {invocation.content_items
                    .filter((item: ContentItem): item is ContentItem & { type: 'image' } =>
                      item.type === 'image' && ALLOWED_IMAGE_MIMES.has((item as { mimeType?: string }).mimeType ?? '')
                    )
                    .map((item, idx) => (
                      <img
                        key={idx}
                        className="tool-result-image"
                        src={`data:${item.mimeType};base64,${item.data}`}
                        alt={`Tool result image ${idx + 1}`}
                        onClick={() => window.open(`data:${item.mimeType};base64,${item.data}`, '_blank')}
                      />
                    ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
