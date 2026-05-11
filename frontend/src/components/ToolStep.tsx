import { useState } from 'react';
import type { ToolInvocation } from '../types/api';
import { formatToolResult, imageDataUri, toolImages } from '../utils/content';

interface Props {
  invocation: ToolInvocation;
}

export function ToolStep({ invocation }: Props) {
  const [expanded, setExpanded] = useState(false);
  const images = toolImages(invocation);

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
            <pre className="tool-step-code">{formatToolResult(invocation.arguments)}</pre>
          </div>
          {invocation.result && (
            <div className="tool-step-section">
              <div className="tool-step-label">Result</div>
              <pre className="tool-step-code">{formatToolResult(invocation.result)}</pre>
              {images.length > 0 && (
                <div className="tool-result-images">
                  {images.map((item, idx) => (
                      <img
                        key={idx}
                        className="tool-result-image"
                        src={imageDataUri(item)}
                        alt={`Tool result image ${idx + 1}`}
                        onClick={() => window.open(imageDataUri(item), '_blank')}
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
