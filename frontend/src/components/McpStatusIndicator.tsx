import type { McpConnectionResult } from '../types/api';

interface Props {
  results: McpConnectionResult[];
}

export function McpStatusIndicator({ results }: Props) {
  if (results.length === 0) return null;

  return (
    <div className="mcp-status-indicator">
      {results.map((r) => (
        <div
          key={r.name}
          className={`mcp-status-item ${r.status === 'connected' ? 'mcp-connected' : 'mcp-failed'}`}
          title={r.status === 'failed' ? `Error: ${r.error}` : `${r.tool_count} tool${r.tool_count !== 1 ? 's' : ''} loaded`}
        >
          <span className="mcp-status-icon">{r.status === 'connected' ? '✓' : '✗'}</span>
          <span className="mcp-status-name">{r.name}</span>
        </div>
      ))}
    </div>
  );
}
