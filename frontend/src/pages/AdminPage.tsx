import { useState } from 'react';
import type { AgentCustomizationOverride, CustomAgentDefinition } from '../types/api';
import { AgentBuilder } from './AgentBuilder';
import { SkillBuilder } from '../components/SkillBuilder';

type AdminTab = 'agents' | 'skills';

interface AdminPageProps {
  onBack: () => void;
  agents: CustomAgentDefinition[];
  builtInOverrides: AgentCustomizationOverride[];
  onSaveAgent: (agent: CustomAgentDefinition) => void;
  onDeleteAgent: (id: string) => void;
  onSaveBuiltInOverride: (override: AgentCustomizationOverride) => void;
  onResetBuiltInOverride: (baseProfileId: string) => void;
}

export function AdminPage({
  onBack,
  agents,
  builtInOverrides,
  onSaveAgent,
  onDeleteAgent,
  onSaveBuiltInOverride,
  onResetBuiltInOverride,
}: AdminPageProps) {
  const [activeTab, setActiveTab] = useState<AdminTab>('agents');

  return (
    <div className="admin-page">
      <div className="admin-header">
        <button className="admin-back-btn" onClick={onBack} type="button">
          BACK TO CHAT
        </button>
        <h2 className="admin-title">ADMIN</h2>
      </div>

      <div className="admin-tabs">
        <button
          className={`admin-tab ${activeTab === 'agents' ? 'active' : ''}`}
          onClick={() => setActiveTab('agents')}
          type="button"
        >
          AGENTS
        </button>
        <button
          className={`admin-tab ${activeTab === 'skills' ? 'active' : ''}`}
          onClick={() => setActiveTab('skills')}
          type="button"
        >
          SKILLS
        </button>
      </div>

      <div className="admin-content">
        {activeTab === 'agents' && (
          <AgentBuilder
            agents={agents}
            builtInOverrides={builtInOverrides}
            onSave={onSaveAgent}
            onDelete={onDeleteAgent}
            onSaveBuiltInOverride={onSaveBuiltInOverride}
            onResetBuiltInOverride={onResetBuiltInOverride}
            onBack={onBack}
          />
        )}
        {activeTab === 'skills' && <SkillBuilder />}
      </div>
    </div>
  );
}
