import { useState } from 'react';
import type { ToolInvocation } from '../types/api';

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
            </div>
          )}
        </div>
      )}
    </div>
  );
}
