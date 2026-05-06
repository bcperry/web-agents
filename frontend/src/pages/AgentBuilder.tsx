import { useState, useEffect } from 'react';
import type {
  AgentCustomizationOverride,
  AgentProfile,
  BuiltInAgentDefinition,
  ToolInfo,
  CustomAgentDefinition,
  StarterQuestion,
  McpServerEntry,
  McpConnectionResult,
  StandardAgentCandidate,
} from '../types/api';
import { fetchBuiltInProfileDefinition, fetchProfiles, fetchSkills, fetchTools, testMcpConnections } from '../api/client';
import { generateStandardAgentCandidate } from '../utils/standardAgentCandidate';

interface AgentBuilderProps {
  agents: CustomAgentDefinition[];
  builtInOverrides: AgentCustomizationOverride[];
  onSave: (agent: CustomAgentDefinition) => void;
  onDelete: (id: string) => void;
  onSaveBuiltInOverride: (override: AgentCustomizationOverride) => void;
  onResetBuiltInOverride: (baseProfileId: string) => void;
  onBack: () => void;
}

function generateId(): string {
  return `custom_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

const EMPTY_FORM = {
  name: '',
  description: '',
  systemPrompt: '',
  tools: [] as string[],
  skills: [] as string[],
  mcpServers: [] as McpServerEntry[],
  useSearchContext: false,
  icon: '/icons/custom.svg',
  starters: [] as StarterQuestion[],
  temperature: '' as string,
};

export function AgentBuilder({
  agents,
  builtInOverrides,
  onSave,
  onDelete,
  onSaveBuiltInOverride,
  onResetBuiltInOverride,
  onBack,
}: AgentBuilderProps) {
  const [availableTools, setAvailableTools] = useState<ToolInfo[]>([]);
  const [builtInProfiles, setBuiltInProfiles] = useState<AgentProfile[]>([]);
  const [searchContextAvailable, setSearchContextAvailable] = useState(true);
  const [availableSkills, setAvailableSkills] = useState<ToolInfo[]>([]);
  const [loadingTools, setLoadingTools] = useState(true);
  const [loadingSkills, setLoadingSkills] = useState(true);
  const [loadingBuiltIns, setLoadingBuiltIns] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingBuiltInDefinition, setEditingBuiltInDefinition] = useState<BuiltInAgentDefinition | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [newStarterLabel, setNewStarterLabel] = useState('');
  const [newStarterMessage, setNewStarterMessage] = useState('');
  const [newMcpName, setNewMcpName] = useState('');
  const [newMcpUrl, setNewMcpUrl] = useState('');
  const [newMcpAuth, setNewMcpAuth] = useState(false);
  const [newMcpAuthScope, setNewMcpAuthScope] = useState('');
  const [mcpTestResults, setMcpTestResults] = useState<Record<string, McpConnectionResult>>({});
  const [mcpTesting, setMcpTesting] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [candidate, setCandidate] = useState<StandardAgentCandidate | null>(null);
  const [builtInsCollapsed, setBuiltInsCollapsed] = useState(false);
  const [customAgentsCollapsed, setCustomAgentsCollapsed] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetchTools()
      .then((resp) => {
        setAvailableTools(resp.tools);
        setSearchContextAvailable(resp.search_context_available);
      })
      .catch((err) => console.error('Failed to load tools:', err))
      .finally(() => setLoadingTools(false));
    fetchSkills()
      .then(setAvailableSkills)
      .catch((err) => console.error('Failed to load skills:', err))
      .finally(() => setLoadingSkills(false));
    fetchProfiles()
      .then(({ profiles }) => setBuiltInProfiles(profiles))
      .catch((err) => console.error('Failed to load built-in agents:', err))
      .finally(() => setLoadingBuiltIns(false));
  }, []);

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setEditingBuiltInDefinition(null);
    setTouched({});
    setNewStarterLabel('');
    setNewStarterMessage('');
    setNewMcpName('');
    setNewMcpUrl('');
    setNewMcpAuth(false);
    setNewMcpAuthScope('');
    setMcpTestResults({});
  };

  const handleEdit = (agent: CustomAgentDefinition) => {
    setEditingId(agent.id);
    setEditingBuiltInDefinition(null);
    setTouched({});
    const availableToolNames = new Set(availableTools.map((tool) => tool.name));
    setForm({
      name: agent.name,
      description: agent.description,
      systemPrompt: agent.systemPrompt,
      tools: agent.tools.filter((tool) => availableToolNames.has(tool)),
      skills: [...(agent.skills || [])],
      mcpServers: [...(agent.mcpServers || [])],
      useSearchContext: searchContextAvailable ? agent.useSearchContext : false,
      icon: agent.icon,
      starters: [...agent.starters],
      temperature: agent.temperature !== undefined ? String(agent.temperature) : '',
    });
  };

  const handleEditBuiltIn = async (profile: AgentProfile) => {
    try {
      const definition = await fetchBuiltInProfileDefinition(profile.id);
      const override = builtInOverrides.find((item) => item.baseProfileId === definition.id);
      const source = override ?? definition;
      const availableToolNames = new Set(availableTools.map((tool) => tool.name));
      setEditingId(null);
      setEditingBuiltInDefinition(definition);
      setTouched({});
      setForm({
        name: definition.name,
        description: source.description,
        systemPrompt: source.systemPrompt,
        tools: source.tools.filter((tool) => availableToolNames.has(tool)),
        skills: [...source.skills],
        mcpServers: [...source.mcpServers],
        useSearchContext: searchContextAvailable ? source.useSearchContext : false,
        icon: source.icon,
        starters: [...source.starters],
        temperature: source.temperature !== undefined ? String(source.temperature) : '',
      });
    } catch (err) {
      console.error('Failed to load built-in agent definition:', err);
    }
  };

  const handleToolToggle = (toolName: string) => {
    setForm((prev) => ({
      ...prev,
      tools: prev.tools.includes(toolName)
        ? prev.tools.filter((t) => t !== toolName)
        : [...prev.tools, toolName],
    }));
  };

  const handleSkillToggle = (skillName: string) => {
    setForm((prev) => ({
      ...prev,
      skills: prev.skills.includes(skillName)
        ? prev.skills.filter((s) => s !== skillName)
        : [...prev.skills, skillName],
    }));
  };

  const handleAddStarter = () => {
    if (!newStarterLabel.trim() || !newStarterMessage.trim()) return;
    setForm((prev) => ({
      ...prev,
      starters: [...prev.starters, { label: newStarterLabel.trim(), message: newStarterMessage.trim() }],
    }));
    setNewStarterLabel('');
    setNewStarterMessage('');
  };

  const handleRemoveStarter = (index: number) => {
    setForm((prev) => ({
      ...prev,
      starters: prev.starters.filter((_, i) => i !== index),
    }));
  };

  const handleTestMcpConnections = async () => {
    if (form.mcpServers.length === 0) return;
    setMcpTesting(true);
    setMcpTestResults({});
    try {
      const results = await testMcpConnections(form.mcpServers);
      const map: Record<string, McpConnectionResult> = {};
      for (const r of results) {
        map[r.name] = r;
      }
      setMcpTestResults(map);
    } catch {
      // Error already shown via toast by client.ts
    } finally {
      setMcpTesting(false);
    }
  };

  const parsedTemp = form.temperature !== '' ? parseFloat(form.temperature) : undefined;
  const tempValid = parsedTemp === undefined || (!isNaN(parsedTemp) && parsedTemp >= 0 && parsedTemp <= 2);

  const handleSave = () => {
    if ((!editingBuiltInDefinition && !form.name.trim()) || !form.systemPrompt.trim() || !tempValid) return;

    const now = new Date().toISOString();
    if (editingBuiltInDefinition) {
      const existingOverride = builtInOverrides.find((item) => item.baseProfileId === editingBuiltInDefinition.id);
      const override: AgentCustomizationOverride = {
        id: existingOverride?.id ?? `builtin_override_${editingBuiltInDefinition.id}`,
        baseProfileId: editingBuiltInDefinition.id,
        baseProfileName: editingBuiltInDefinition.name,
        description: form.description.trim(),
        systemPrompt: form.systemPrompt,
        tools: form.tools,
        skills: form.skills,
        mcpServers: form.mcpServers,
        useSearchContext: form.useSearchContext,
        icon: editingBuiltInDefinition.icon,
        starters: form.starters,
        ...(parsedTemp !== undefined ? { temperature: parsedTemp } : {}),
        source: 'builtin-override',
        createdAt: existingOverride?.createdAt ?? now,
        updatedAt: now,
      };

      onSaveBuiltInOverride(override);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
      resetForm();
      return;
    }

    const agent: CustomAgentDefinition = {
      id: editingId || generateId(),
      name: form.name.trim(),
      description: form.description.trim(),
      systemPrompt: form.systemPrompt,
      tools: form.tools,
      skills: form.skills,
      mcpServers: form.mcpServers,
      useSearchContext: form.useSearchContext,
      icon: form.icon,
      starters: form.starters,
      ...(parsedTemp !== undefined ? { temperature: parsedTemp } : {}),
      createdAt: editingId
        ? agents.find((a) => a.id === editingId)?.createdAt || now
        : now,
      updatedAt: now,
    };

    onSave(agent);
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 2000);
    resetForm();
  };

  const handleDelete = (id: string) => {
    if (editingId === id) resetForm();
    onDelete(id);
  };

  const handleMakeStandard = (override: AgentCustomizationOverride) => {
    setCandidate(generateStandardAgentCandidate(override));
  };

  const handleCopyCandidate = async () => {
    if (!candidate) return;
    await navigator.clipboard.writeText(candidate.yaml);
  };

  const handleDownloadCandidate = () => {
    if (!candidate) return;
    const blob = new Blob([candidate.yaml], { type: 'text/yaml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${candidate.profileId}.agents.yaml`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const isValid = (editingBuiltInDefinition || form.name.trim()) && form.systemPrompt.trim() && tempValid;

  return (
    <div className="agent-builder">
      <div className="agent-builder-header">
        <button className="agent-builder-back" onClick={onBack} type="button">
          ← BACK TO AGENTS
        </button>
        <h2 className="agent-builder-title">CUSTOM AGENT BUILDER</h2>
      </div>

      <div className="agent-builder-layout">
        <div className="agent-builder-lists">
          <div className={`agent-builder-saved ${builtInsCollapsed ? 'collapsed' : ''}`}>
          <button
            className="agent-builder-section-toggle"
            type="button"
            aria-expanded={!builtInsCollapsed}
            onClick={() => setBuiltInsCollapsed((collapsed) => !collapsed)}
          >
            <span className="agent-builder-section-title">BUILT-IN AGENTS</span>
            <span className="agent-builder-section-toggle-icon" aria-hidden="true">{builtInsCollapsed ? '+' : '-'}</span>
          </button>
          {!builtInsCollapsed && (
            loadingBuiltIns ? (
              <div className="agent-builder-loading">Loading built-in agents...</div>
            ) : (
              builtInProfiles.map((profile) => {
                const override = builtInOverrides.find((item) => item.baseProfileId === profile.id);
                return (
                  <div
                    key={profile.id}
                    className={`agent-builder-saved-entry ${editingBuiltInDefinition?.id === profile.id ? 'editing' : ''}`}
                  >
                    <div className="agent-builder-saved-info">
                      <div className="agent-builder-saved-name">
                        {profile.name}
                        {override && <span className="agent-builder-mcp-badge agent-builder-mcp-badge--customized">CUSTOMIZED</span>}
                      </div>
                      <div className="agent-builder-saved-desc">{profile.description || 'No description'}</div>
                    </div>
                    <div className="agent-builder-saved-actions">
                      <button onClick={() => handleEditBuiltIn(profile)} type="button" title="Customize built-in agent">EDIT</button>
                      {override && (
                        <>
                          <button onClick={() => onResetBuiltInOverride(profile.id)} type="button" title="Reset local customization">RESET</button>
                          <button
                            onClick={() => handleMakeStandard(override)}
                            type="button"
                            title="Save a downloadable standard agent candidate to provide to devs for consideration"
                          >
                            SAVE
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })
            )
          )}
          </div>

          {/* Custom agents list */}
          {agents.length > 0 && (
            <div className={`agent-builder-saved ${customAgentsCollapsed ? 'collapsed' : ''}`}>
            <button
              className="agent-builder-section-toggle"
              type="button"
              aria-expanded={!customAgentsCollapsed}
              onClick={() => setCustomAgentsCollapsed((collapsed) => !collapsed)}
            >
              <span className="agent-builder-section-title">CUSTOM AGENTS</span>
              <span className="agent-builder-section-toggle-icon" aria-hidden="true">{customAgentsCollapsed ? '+' : '-'}</span>
            </button>
            {!customAgentsCollapsed && agents.map((agent) => (
                <div key={agent.id} className={`agent-builder-saved-entry ${editingId === agent.id ? 'editing' : ''}`}>
                  <div className="agent-builder-saved-info">
                    <div className="agent-builder-saved-name">{agent.name}</div>
                    <div className="agent-builder-saved-desc">{agent.description || 'No description'}</div>
                  </div>
                  <div className="agent-builder-saved-actions">
                    <button onClick={() => handleEdit(agent)} type="button" title="Edit custom agent">EDIT</button>
                    <button onClick={() => handleDelete(agent.id)} type="button" title="Delete custom agent">DELETE</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Form */}
        <div className="agent-builder-form">
          <h3 className="agent-builder-section-title">
            {editingBuiltInDefinition ? 'CUSTOMIZE BUILT-IN AGENT' : editingId ? 'EDIT AGENT' : 'CREATE NEW AGENT'}
          </h3>

          <label className="agent-builder-label">
            NAME *
            <input
              className={`agent-builder-input${touched.name && !form.name.trim() ? ' agent-builder-input-error' : ''}`}
              type="text"
              value={form.name}
              onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
              onBlur={() => setTouched((prev) => ({ ...prev, name: true }))}
              placeholder="e.g. Data Analyst"
              maxLength={100}
              readOnly={Boolean(editingBuiltInDefinition)}
            />
            {touched.name && !form.name.trim() && (
              <span className="agent-builder-error-text">Name is required</span>
            )}
          </label>

          <label className="agent-builder-label">
            DESCRIPTION
            <input
              className="agent-builder-input"
              type="text"
              value={form.description}
              onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
              placeholder="Brief description of this agent's purpose"
              maxLength={200}
            />
          </label>

          <label className="agent-builder-label">
            SYSTEM PROMPT *
            <textarea
              className={`agent-builder-textarea${touched.systemPrompt && !form.systemPrompt.trim() ? ' agent-builder-input-error' : ''}`}
              value={form.systemPrompt}
              onChange={(e) => setForm((prev) => ({ ...prev, systemPrompt: e.target.value }))}
              onBlur={() => setTouched((prev) => ({ ...prev, systemPrompt: true }))}
              placeholder="You are a specialized agent that..."
              rows={8}
            />
            {touched.systemPrompt && !form.systemPrompt.trim() && (
              <span className="agent-builder-error-text">System prompt is required</span>
            )}
          </label>

          <label className="agent-builder-label">
            TEMPERATURE
            <span className="agent-builder-tool-desc" style={{ display: 'block', marginBottom: '0.5rem' }}>
              Controls the Agent's Creativity (0.0 = deterministic, 2.0 = creative).
            </span>
            <input
              className={`agent-builder-input${!tempValid ? ' agent-builder-input-error' : ''}`}
              type="number"
              value={form.temperature}
              onChange={(e) => setForm((prev) => ({ ...prev, temperature: e.target.value }))}
              placeholder="e.g. 0.2"
              min={0}
              max={2}
              step={0.1}
            />
            {!tempValid && (
              <span className="agent-builder-error-text">Temperature must be between 0.0 and 2.0</span>
            )}
          </label>

          {/* Tools */}
          <div className="agent-builder-label">
            TOOLS
            <span className="agent-builder-tool-desc" style={{ display: 'block', marginBottom: '0.5rem' }}>
              Backend capabilities the agent can invoke during a conversation
            </span>
            {loadingTools ? (
              <div className="agent-builder-loading">Loading available tools...</div>
            ) : (
              <div className="agent-builder-tools">
                {availableTools.map((tool) => (
                  <label key={tool.name} className="agent-builder-tool-item">
                    <input
                      type="checkbox"
                      checked={form.tools.includes(tool.name)}
                      onChange={() => handleToolToggle(tool.name)}
                    />
                    <span className="agent-builder-tool-name">{tool.name.replace(/_/g, ' ')}</span>
                    <span className="agent-builder-tool-desc">{tool.description}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* AI Search context provider — hidden when not configured */}
          {searchContextAvailable && (
            <label className="agent-builder-tool-item agent-builder-search-toggle">
              <input
                type="checkbox"
                checked={form.useSearchContext}
                onChange={(e) => setForm((prev) => ({ ...prev, useSearchContext: e.target.checked }))}
              />
              <span className="agent-builder-tool-name">AI SEARCH CONTEXT</span>
              <span className="agent-builder-tool-desc">ENABLE AI SEARCH ACROSS INDEXED DOCUMENTS</span>
            </label>
          )}

          {/* Skills */}
          <div className="agent-builder-label">
            SKILLS
            <span className="agent-builder-tool-desc" style={{ display: 'block', marginBottom: '0.5rem' }}>
              Domain-specific knowledge packages that give the agent specialized expertise
            </span>
            {loadingSkills ? (
              <div className="agent-builder-loading">Loading available skills...</div>
            ) : availableSkills.length > 0 ? (
              <div className="agent-builder-tools">
                {availableSkills.map((skill) => (
                  <label key={skill.name} className="agent-builder-tool-item">
                    <input
                      type="checkbox"
                      checked={form.skills.includes(skill.name)}
                      onChange={() => handleSkillToggle(skill.name)}
                    />
                    <span className="agent-builder-tool-name">{skill.name.replace(/-/g, ' ')}</span>
                    <span className="agent-builder-tool-desc">{skill.description}</span>
                  </label>
                ))}
              </div>
            ) : (
              <div className="agent-builder-tool-desc">No skills available</div>
            )}
          </div>

          {/* MCP Servers */}
          <div className="agent-builder-label">
            MCP SERVERS
            <span className="agent-builder-tool-desc" style={{ display: 'block', marginBottom: '0.5rem' }}>
              Connect to remote tool servers using the Model Context Protocol
            </span>
            {form.mcpServers.length > 0 && (
              <>
                <div className="agent-builder-starters-list">
                  {form.mcpServers.map((server, i) => {
                    const result = mcpTestResults[server.name];
                    return (
                      <div key={i} className="agent-builder-starter-item">
                        {result && (
                          <span
                            className={`mcp-test-status ${result.status === 'connected' ? 'mcp-connected' : 'mcp-failed'}`}
                            title={result.status === 'connected' ? `${result.tool_count} tool${result.tool_count !== 1 ? 's' : ''} loaded` : `Error: ${result.error}`}
                          >
                            {result.status === 'connected' ? '✓' : '✗'}
                          </span>
                        )}
                        <span className="agent-builder-starter-label">
                          {server.name} — {server.url}
                          {server.authScope ? ` [OBO: ${server.authScope}]` : server.authenticated ? ' [Auth]' : ''}
                        </span>
                        <button
                          onClick={() => {
                            setForm((prev) => ({
                              ...prev,
                              mcpServers: prev.mcpServers.filter((_, idx) => idx !== i),
                            }));
                            setMcpTestResults((prev) => {
                              const next = { ...prev };
                              delete next[server.name];
                              return next;
                            });
                          }}
                          type="button"
                          title="Remove"
                        >
                          ✕
                        </button>
                      </div>
                    );
                  })}
                </div>
                <button
                  className="agent-builder-test-mcp-btn"
                  onClick={handleTestMcpConnections}
                  type="button"
                  disabled={mcpTesting}
                >
                  {mcpTesting ? 'TESTING...' : 'TEST CONNECTIONS'}
                </button>
              </>
            )}
            <div className="agent-builder-mcp-add">
              <input
                className="agent-builder-input"
                type="text"
                value={newMcpName}
                onChange={(e) => setNewMcpName(e.target.value)}
                placeholder="Server name"
                maxLength={100}
              />
              <input
                className="agent-builder-input agent-builder-input--wide"
                type="text"
                value={newMcpUrl}
                onChange={(e) => setNewMcpUrl(e.target.value)}
                placeholder="Server URL (e.g. https://my-server.com/mcp)"
                maxLength={500}
              />
              <label className="agent-builder-tool-item" style={{ margin: 0, whiteSpace: 'nowrap' }}>
                <input
                  type="checkbox"
                  checked={newMcpAuth}
                  onChange={(e) => setNewMcpAuth(e.target.checked)}
                />
                <span className="agent-builder-tool-name">Authenticated</span>
              </label>
              {newMcpAuth && (
                <input
                  className="agent-builder-input agent-builder-input--wide"
                  type="text"
                  value={newMcpAuthScope}
                  onChange={(e) => setNewMcpAuthScope(e.target.value)}
                  placeholder="OBO scope (optional, e.g. api://client-id/.default)"
                  maxLength={500}
                />
              )}
              <button
                className="agent-builder-starter-add-btn"
                onClick={() => {
                  if (!newMcpName.trim() || !newMcpUrl.trim()) return;
                  setForm((prev) => ({
                    ...prev,
                    mcpServers: [...prev.mcpServers, {
                      name: newMcpName.trim(),
                      transport: 'http' as const,
                      url: newMcpUrl.trim(),
                      ...(newMcpAuth ? { authenticated: true } : {}),
                      ...(newMcpAuthScope.trim() ? { authScope: newMcpAuthScope.trim() } : {}),
                    }],
                  }));
                  setNewMcpName('');
                  setNewMcpUrl('');
                  setNewMcpAuth(false);
                  setNewMcpAuthScope('');
                }}
                type="button"
                disabled={!newMcpName.trim() || !newMcpUrl.trim()}
              >
                + ADD
              </button>
            </div>
          </div>

          {/* Starter questions */}
          <div className="agent-builder-label">
            STARTER QUESTIONS
            {form.starters.length > 0 && (
              <div className="agent-builder-starters-list">
                {form.starters.map((s, i) => (
                  <div key={i} className="agent-builder-starter-item">
                    <span className="agent-builder-starter-label">{s.label}</span>
                    <button onClick={() => handleRemoveStarter(i)} type="button" title="Remove">✕</button>
                  </div>
                ))}
              </div>
            )}
            <div className="agent-builder-starter-add">
              <input
                className="agent-builder-input"
                type="text"
                value={newStarterLabel}
                onChange={(e) => setNewStarterLabel(e.target.value)}
                placeholder="Button label"
                maxLength={80}
              />
              <input
                className="agent-builder-input"
                type="text"
                value={newStarterMessage}
                onChange={(e) => setNewStarterMessage(e.target.value)}
                placeholder="Message to send"
                maxLength={500}
              />
              <button
                className="agent-builder-starter-add-btn"
                onClick={handleAddStarter}
                type="button"
                disabled={!newStarterLabel.trim() || !newStarterMessage.trim()}
              >
                + ADD
              </button>
            </div>
          </div>

          {/* Actions */}
          <div className="agent-builder-actions">
            {(editingId || editingBuiltInDefinition) && (
              <button className="agent-builder-cancel" onClick={resetForm} type="button">
                CANCEL
              </button>
            )}
            <button
              className="agent-builder-save"
              onClick={handleSave}
              type="button"
              disabled={!isValid}
            >
              {editingBuiltInDefinition ? 'SAVE CUSTOMIZATION' : editingId ? 'UPDATE AGENT' : 'SAVE AGENT'}
            </button>
          </div>

          {saveSuccess && (
            <div className="agent-builder-success">Agent saved successfully</div>
          )}
        </div>
      </div>

      {candidate && (
        <div className="agent-builder-modal-backdrop" role="presentation" onClick={() => setCandidate(null)}>
          <div className="agent-builder-candidate-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="agent-builder-candidate-header">
              <h3 className="agent-builder-section-title">STANDARD AGENT CANDIDATE</h3>
              <button onClick={() => setCandidate(null)} type="button" title="Close">CLOSE</button>
            </div>
            <div className="agent-builder-candidate-meta">
              <span>{candidate.profileId}</span>
              <span>{candidate.generatedAt}</span>
            </div>
            <div className="agent-builder-candidate-notice">
              Download this candidate to save as a standard agent. Provide it to devs for source review, tests, and evals before adding it to shared agents.yaml.
            </div>
            <textarea
              className="agent-builder-candidate-code"
              value={candidate.yaml}
              readOnly
              rows={16}
            />
            <div className="agent-builder-actions">
              <button
                className="agent-builder-cancel"
                onClick={handleDownloadCandidate}
                type="button"
                title="Download this to save as a standard agent"
              >
                DOWNLOAD CANDIDATE
              </button>
              <button className="agent-builder-save" onClick={handleCopyCandidate} type="button">
                COPY YAML
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
