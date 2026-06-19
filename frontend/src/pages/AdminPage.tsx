import { useState } from 'react';
import type { AgentCustomizationOverride, CustomAgentDefinition } from '../types/api';
import { useTheme, type ThemeMode } from '../hooks/useTheme';
import { AgentBuilder } from './AgentBuilder';
import { SkillBuilder } from '../components/SkillBuilder';
import { AutomationBuilder } from '../components/AutomationBuilder';

export type AdminTab = 'settings' | 'agents' | 'skills' | 'automations';

/** Where to land when opening Admin (e.g. deep-link straight into Automations). */
export interface AdminOpenOptions {
  tab?: AdminTab;
  automationCreate?: boolean;
  automationEditId?: string;
}

const THEME_OPTIONS: { value: ThemeMode; label: string; description: string }[] = [
  { value: 'light', label: 'LIGHT', description: 'Bright interface for high-visibility workspaces' },
  { value: 'dark', label: 'DARK', description: 'Reduced-glare interface for low-light workspaces' },
];

interface AdminPageProps {
  onBack: () => void;
  userEmail?: string;
  initialTab?: AdminTab;
  automationCreate?: boolean;
  automationEditId?: string;
  agents: CustomAgentDefinition[];
  builtInOverrides: AgentCustomizationOverride[];
  onSaveAgent: (agent: CustomAgentDefinition) => void;
  onDeleteAgent: (id: string) => void;
  onSaveBuiltInOverride: (override: AgentCustomizationOverride) => void;
  onResetBuiltInOverride: (baseProfileId: string) => void;
}

export function AdminPage({
  onBack,
  userEmail,
  initialTab,
  automationCreate,
  automationEditId,
  agents,
  builtInOverrides,
  onSaveAgent,
  onDeleteAgent,
  onSaveBuiltInOverride,
  onResetBuiltInOverride,
}: AdminPageProps) {
  const [activeTab, setActiveTab] = useState<AdminTab>(initialTab ?? 'settings');
  const { mode, setMode } = useTheme();

  return (
    <div className="admin-page">
      <div className="admin-header">
        <button className="admin-back-btn" onClick={onBack} type="button">
          BACK TO CHAT
        </button>
        <h2 className="admin-title">ADMIN SETTINGS</h2>
      </div>

      <div className="admin-tabs">
        <button
          className={`admin-tab ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
          type="button"
        >
          SETTINGS
        </button>
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
        <button
          className={`admin-tab ${activeTab === 'automations' ? 'active' : ''}`}
          onClick={() => setActiveTab('automations')}
          type="button"
        >
          AUTOMATIONS
        </button>
      </div>

      <div className="admin-content">
        {activeTab === 'settings' && (
          <div className="admin-settings">
            <section className="admin-settings-section">
              <div className="admin-settings-section-header">
                <h3 className="admin-settings-heading">APPEARANCE</h3>
                <p className="admin-settings-copy">Choose the color mode used across chat, admin, and builder screens.</p>
              </div>
              <div className="admin-theme-options" role="group" aria-label="Theme selection">
                {THEME_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    className={`admin-theme-option ${mode === option.value ? 'active' : ''}`}
                    onClick={() => setMode(option.value)}
                    type="button"
                    aria-pressed={mode === option.value}
                  >
                    <span className="admin-theme-option-label">{option.label}</span>
                    <span className="admin-theme-option-description">{option.description}</span>
                  </button>
                ))}
              </div>
            </section>

            <section className="admin-settings-section">
              <div className="admin-settings-section-header">
                <h3 className="admin-settings-heading">ACCOUNT</h3>
                <p className="admin-settings-copy">Signed-in identity used for this browser session.</p>
              </div>
              <div className="admin-account-summary" title={userEmail || 'Unknown user'}>
                {userEmail || 'Unknown user'}
              </div>
            </section>
          </div>
        )}
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
        {activeTab === 'automations' && (
          <AutomationBuilder intent={{ create: automationCreate, editId: automationEditId }} />
        )}
      </div>
    </div>
  );
}
