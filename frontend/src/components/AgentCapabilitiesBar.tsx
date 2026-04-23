import type { McpConnectionResult } from '../types/api';

interface Props {
  toolsLoaded: string[];
  skillsLoaded: string[];
  searchContext: boolean;
  mcpResults: McpConnectionResult[];
}

export function AgentCapabilitiesBar({
  toolsLoaded,
  skillsLoaded,
  searchContext,
  mcpResults,
}: Props) {
  const hasTools = toolsLoaded.length > 0;
  const hasSkills = skillsLoaded.length > 0;
  const hasMcp = mcpResults.length > 0;
  const hasSearch = searchContext;

  if (!hasTools && !hasSkills && !hasMcp && !hasSearch) return null;

  return (
    <div className="capabilities-bar">
      {hasTools && (
        <div className="capabilities-section">
          <span className="capabilities-label">TOOLS</span>
          <div className="capabilities-items">
            {toolsLoaded.map((name) => (
              <span key={name} className="capabilities-pill capabilities-pill--tool">{name}</span>
            ))}
          </div>
        </div>
      )}
      {hasSkills && (
        <div className="capabilities-section">
          <span className="capabilities-label">SKILLS</span>
          <div className="capabilities-items">
            {skillsLoaded.map((name) => (
              <span key={name} className="capabilities-pill capabilities-pill--skill">{name}</span>
            ))}
          </div>
        </div>
      )}
      {hasSearch && (
        <div className="capabilities-section">
          <span className="capabilities-label">SEARCH</span>
          <div className="capabilities-items">
            <span className="capabilities-pill capabilities-pill--search">
              <span className="capabilities-icon capabilities-icon--ok">✓</span>
              AI Search
            </span>
          </div>
        </div>
      )}
      {hasMcp && (
        <div className="capabilities-section">
          <span className="capabilities-label">MCP</span>
          <div className="capabilities-items">
            {mcpResults.map((r) => (
              <span
                key={r.name}
                className={`capabilities-pill capabilities-pill--mcp ${r.status === 'connected' ? 'capabilities-pill--ok' : 'capabilities-pill--fail'}`}
                title={r.status === 'failed' ? `Error: ${r.error}` : `${r.tool_count} tool${r.tool_count !== 1 ? 's' : ''} loaded`}
              >
                <span className={`capabilities-icon ${r.status === 'connected' ? 'capabilities-icon--ok' : 'capabilities-icon--fail'}`}>
                  {r.status === 'connected' ? '✓' : '✗'}
                </span>
                {r.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
