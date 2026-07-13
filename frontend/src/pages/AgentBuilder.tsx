import { useState, useEffect, useMemo } from 'react';
import type {
  AgentCustomizationOverride,
  AgentProfile,
  AgentRef,
  BuiltInAgentDefinition,
  ToolInfo,
  CustomAgentDefinition,
  StandardAgentCandidate,
  SubAgentToolRef,
} from '../types/api';
import { fetchBuiltInProfileDefinition, fetchProfiles, fetchSkills, fetchTools } from '../api/client';
import { generateStandardAgentCandidate } from '../utils/standardAgentCandidate';
import { AgentCapabilityPicker } from '../components/AgentCapabilityPicker';
import { AgentAsToolPicker, type AgentToolOption } from '../components/AgentAsToolPicker';
import { StarterQuestionEditor } from '../components/StarterQuestionEditor';
import { useAgentMcpEditor } from '../hooks/useAgentMcpEditor';
import { prepareBuiltInOverride, prepareCustomAgent, useAgentBuilderForm } from '../hooks/useAgentBuilderForm';
import { validateSubAgentTools, type ResolvedAgentTarget } from '../utils/agentToolValidation';

interface AgentBuilderProps {
  agents: CustomAgentDefinition[];
  builtInOverrides: AgentCustomizationOverride[];
  onSave: (agent: CustomAgentDefinition) => void;
  onDelete: (id: string) => void;
  onSaveBuiltInOverride: (override: AgentCustomizationOverride) => void;
  onResetBuiltInOverride: (baseProfileId: string) => void;
  onBack: () => void;
}

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
  const {
    editingBuiltInDefinition,
    editingId,
    form,
    isValid,
    markTouched,
    parsedTemperature,
    resetForm: resetAgentForm,
    saveSuccess,
    setEditingBuiltInDefinition,
    setEditingId,
    setForm,
    setSaveSuccess,
    setTouched,
    temperatureValid,
    touched,
  } = useAgentBuilderForm();
  const [newStarterLabel, setNewStarterLabel] = useState('');
  const [newStarterMessage, setNewStarterMessage] = useState('');
  const {
    addMcpServer,
    mcpTesting,
    mcpTestResults,
    newMcpAuth,
    newMcpAuthScope,
    newMcpName,
    newMcpUrl,
    removeMcpServer,
    resetMcpEditor,
    setNewMcpAuth,
    setNewMcpAuthScope,
    setNewMcpName,
    setNewMcpUrl,
    testConnections,
  } = useAgentMcpEditor(setForm);
  const [candidate, setCandidate] = useState<StandardAgentCandidate | null>(null);
  const [builtInsCollapsed, setBuiltInsCollapsed] = useState(false);
  const [customAgentsCollapsed, setCustomAgentsCollapsed] = useState(false);
  const [builtInDefinitionsById, setBuiltInDefinitionsById] = useState<Record<string, BuiltInAgentDefinition>>({});

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
    resetAgentForm();
    setNewStarterLabel('');
    setNewStarterMessage('');
    resetMcpEditor();
  };

  const handleEdit = (agent: CustomAgentDefinition) => {
    setEditingId(agent.id);
    setEditingBuiltInDefinition(null);
    setTouched({});
    setForm({
      name: agent.name,
      description: agent.description,
      group: agent.group ?? '',
      systemPrompt: agent.systemPrompt,
      tools: [...agent.tools],
      skills: [...(agent.skills || [])],
      mcpServers: [...(agent.mcpServers || [])],
      useSearchContext: searchContextAvailable ? agent.useSearchContext : false,
      icon: agent.icon,
      starters: [...agent.starters],
      temperature: agent.temperature !== undefined ? String(agent.temperature) : '',
      agentsAsTools: [...agent.agentsAsTools],
    });
  };

  const handleEditBuiltIn = async (profile: AgentProfile) => {
    try {
      const definition = await fetchBuiltInProfileDefinition(profile.id);
      setBuiltInDefinitionsById((prev) => ({ ...prev, [definition.id]: definition }));
      const override = builtInOverrides.find((item) => item.baseProfileId === definition.id);
      const source = override ?? definition;
      setEditingId(null);
      setEditingBuiltInDefinition(definition);
      setTouched({});
      setForm({
        name: definition.name,
        description: source.description,
        group: (override?.group ?? profile.group) ?? '',
        systemPrompt: source.systemPrompt,
        tools: [...source.tools],
        skills: [...source.skills],
        mcpServers: [...source.mcpServers],
        useSearchContext: searchContextAvailable ? source.useSearchContext : false,
        icon: source.icon,
        starters: [...source.starters],
        temperature: source.temperature !== undefined ? String(source.temperature) : '',
        agentsAsTools: [...source.agentsAsTools],
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

  const handleUpdateStarter = (index: number, field: 'label' | 'message', value: string) => {
    setForm((prev) => ({
      ...prev,
      starters: prev.starters.map((starter, i) =>
        i === index ? { ...starter, [field]: value } : starter
      ),
    }));
  };

  // ---- Agents-as-Tools picker support ------------------------------------
  // The current agent's id (built-in profile id, custom agent id, or '' when
  // creating a brand-new custom agent — empty parentId disables self-ref check).
  const parentAgentId = editingBuiltInDefinition?.id ?? editingId ?? '';

  const availableAgentOptions = useMemo<AgentToolOption[]>(() => {
    const builtinOptions: AgentToolOption[] = builtInProfiles.map((profile) => ({
      id: profile.id,
      kind: 'builtin',
      name: profile.name,
      description: profile.description || '',
    }));
    const customOptions: AgentToolOption[] = agents.map((agent) => ({
      id: agent.id,
      kind: 'custom',
      name: agent.name,
      description: agent.description || '',
      definition: agent,
    }));
    return [...builtinOptions, ...customOptions];
  }, [agents, builtInProfiles]);

  const subAgentValidationErrors = useMemo(() => {
    const optionsById = new Map(availableAgentOptions.map((o) => [o.id, o]));
    const customById = new Map(agents.map((a) => [a.id, a]));
    const overrideByProfileId = new Map(builtInOverrides.map((override) => [override.baseProfileId, override]));
    return validateSubAgentTools(parentAgentId, form.agentsAsTools, (ref: AgentRef): ResolvedAgentTarget | null => {
      const targetId = ref.kind === 'builtin' ? ref.profileId : ref.customAgentId;
      const opt = optionsById.get(targetId);
      if (!opt) return null;
      const targetRefs: SubAgentToolRef[] =
        opt.kind === 'custom'
          ? (customById.get(targetId)?.agentsAsTools ?? [])
          : (overrideByProfileId.get(targetId)?.agentsAsTools ?? builtInDefinitionsById[targetId]?.agentsAsTools ?? []);
      return {
        id: targetId,
        name: opt.name,
        description: opt.description,
        agentsAsTools: targetRefs,
      };
    });
  }, [parentAgentId, form.agentsAsTools, availableAgentOptions, agents, builtInOverrides, builtInDefinitionsById]);

  const handleAgentsAsToolsChange = (next: SubAgentToolRef[]) => {
    setForm((prev) => ({ ...prev, agentsAsTools: next }));
  };

  const handleSave = () => {
    if (!isValid) return;
    if (subAgentValidationErrors.length > 0) return;
    if (editingBuiltInDefinition) {
      const existingOverride = builtInOverrides.find((item) => item.baseProfileId === editingBuiltInDefinition.id);
      const override = prepareBuiltInOverride(form, editingBuiltInDefinition, existingOverride, parsedTemperature);
      onSaveBuiltInOverride(override);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
      resetForm();
      return;
    }

    const agent = prepareCustomAgent(form, editingId, agents, parsedTemperature);
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

  return (
    <div className="agent-builder">
      <div className="agent-builder-header">
        <button className="agent-builder-back" onClick={onBack} type="button">
          BACK TO AGENTS
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
              onBlur={() => markTouched('name')}
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
            GROUP
            <input
              className="agent-builder-input"
              type="text"
              list="agent-builder-group-options"
              value={form.group}
              onChange={(e) => setForm((prev) => ({ ...prev, group: e.target.value }))}
              placeholder="Optional group name (e.g., General Staff)"
              maxLength={100}
            />
            <datalist id="agent-builder-group-options">
              {Array.from(new Set([
                ...builtInProfiles.map((p) => p.group).filter((g): g is string => Boolean(g)),
                ...agents.map((a) => a.group).filter((g): g is string => Boolean(g)),
                ...builtInOverrides.map((o) => o.group).filter((g): g is string => Boolean(g)),
              ])).sort().map((groupName) => (
                <option key={groupName} value={groupName} />
              ))}
            </datalist>
          </label>

          <label className="agent-builder-label">
            SYSTEM PROMPT *
            <textarea
              className={`agent-builder-textarea${touched.systemPrompt && !form.systemPrompt.trim() ? ' agent-builder-input-error' : ''}`}
              value={form.systemPrompt}
              onChange={(e) => setForm((prev) => ({ ...prev, systemPrompt: e.target.value }))}
              onBlur={() => markTouched('systemPrompt')}
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
              className={`agent-builder-input${!temperatureValid ? ' agent-builder-input-error' : ''}`}
              type="number"
              value={form.temperature}
              onChange={(e) => setForm((prev) => ({ ...prev, temperature: e.target.value }))}
              placeholder="e.g. 0.2"
              min={0}
              max={2}
              step={0.1}
            />
            {!temperatureValid && (
              <span className="agent-builder-error-text">Temperature must be between 0.0 and 2.0</span>
            )}
          </label>

          <AgentCapabilityPicker
            title="TOOLS"
            description="Backend capabilities the agent can invoke during a conversation"
            items={availableTools}
            selected={form.tools}
            loading={loadingTools}
            nameFormatter={(name) => name.replace(/_/g, ' ')}
            onToggle={handleToolToggle}
          />

          {/* AI Search context provider — hidden when not configured */}
          {searchContextAvailable && (
            <div className="agent-builder-section">
              <h3 className="agent-builder-section-title">AI SEARCH CONTEXT</h3>
              <label className="agent-builder-tool-item agent-builder-search-toggle">
                <input
                  type="checkbox"
                  checked={form.useSearchContext}
                  onChange={(e) => setForm((prev) => ({ ...prev, useSearchContext: e.target.checked }))}
                />
                <span className="agent-builder-tool-name">ENABLE AI SEARCH</span>
                <span className="agent-builder-tool-desc">Search across indexed documents during the conversation</span>
              </label>
            </div>
          )}

          <AgentCapabilityPicker
            title="SKILLS"
            description="Domain-specific knowledge packages that give the agent specialized expertise"
            items={availableSkills}
            selected={form.skills}
            loading={loadingSkills}
            emptyText="No skills available"
            nameFormatter={(name) => name.replace(/-/g, ' ')}
            onToggle={handleSkillToggle}
          />

          {/* MCP Servers */}
          <div className="agent-builder-section">
            <h3 className="agent-builder-section-title">MCP SERVERS</h3>
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
                          onClick={() => removeMcpServer(server, i)}
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
                  onClick={() => testConnections(form.mcpServers)}
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
                onClick={addMcpServer}
                type="button"
                disabled={!newMcpName.trim() || !newMcpUrl.trim()}
              >
                + ADD
              </button>
            </div>
          </div>

          <AgentAsToolPicker
            availableAgents={availableAgentOptions}
            value={form.agentsAsTools}
            parentAgentId={parentAgentId}
            validationErrors={subAgentValidationErrors}
            onChange={handleAgentsAsToolsChange}
          />

          <StarterQuestionEditor
            starters={form.starters}
            newStarterLabel={newStarterLabel}
            newStarterMessage={newStarterMessage}
            onAdd={handleAddStarter}
            onRemove={handleRemoveStarter}
            onUpdate={handleUpdateStarter}
            onLabelChange={setNewStarterLabel}
            onMessageChange={setNewStarterMessage}
          />

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
              disabled={!isValid || subAgentValidationErrors.length > 0}
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
