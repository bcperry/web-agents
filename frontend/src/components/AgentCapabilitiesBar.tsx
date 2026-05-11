import type { McpConnectionResult } from '../types/api';

interface Props {
  toolsLoaded: string[];
  skillsLoaded: string[];
  agentsLoaded?: string[];
  searchContext: boolean;
  mcpResults: McpConnectionResult[];
  isCustomized?: boolean;
}

export function AgentCapabilitiesBar({
  toolsLoaded,
  skillsLoaded,
  agentsLoaded = [],
  searchContext,
  mcpResults,
  isCustomized = false,
}: Props) {
  const hasTools = toolsLoaded.length > 0;
  const hasSkills = skillsLoaded.length > 0;
  const hasAgents = agentsLoaded.length > 0;
  const hasMcp = mcpResults.length > 0;
  const hasSearch = searchContext;

  if (!hasTools && !hasSkills && !hasAgents && !hasMcp && !hasSearch && !isCustomized) return null;

  return (
    <div className="capabilities-bar">
      {isCustomized && (
        <div className="capabilities-section">
          <span className="capabilities-label">PROFILE</span>
          <div className="capabilities-items">
            <span className="capabilities-pill capabilities-pill--customized">CUSTOMIZED</span>
          </div>
        </div>
      )}
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
      {hasAgents && (
        <div className="capabilities-section">
          <span className="capabilities-label">AGENTS</span>
          <div className="capabilities-items">
            {agentsLoaded.map((name) => (
              <span key={name} className="capabilities-pill capabilities-pill--tool">{name}</span>
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
