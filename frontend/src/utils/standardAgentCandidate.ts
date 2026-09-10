import { stringify } from 'yaml';
import type { AgentCustomizationOverride, StandardAgentCandidate } from '../types/api';

function profileIdFromOverride(override: AgentCustomizationOverride): string {
  const base = override.baseProfileId.replace(/[^a-zA-Z0-9_-]/g, '-');
  return `${base}-customized`;
}

export function generateStandardAgentCandidate(override: AgentCustomizationOverride): StandardAgentCandidate {
  const profileId = profileIdFromOverride(override);
  const profile = {
    name: override.baseProfileName ?? override.baseProfileId,
    description: override.description,
    icon: override.icon,
    tools: override.tools,
    skills: override.skills,
    mcp_servers: override.mcpServers,
    search_context: override.useSearchContext,
    ...(override.temperature !== undefined ? { temperature: override.temperature } : {}),
    starters: override.starters,
    system_prompt: override.systemPrompt,
  };

  return {
    profileId,
    yaml: stringify({ [profileId]: profile }, { lineWidth: 0 }),
    profile,
    generatedAt: new Date().toISOString(),
    sourceOverrideUpdatedAt: override.updatedAt,
  };
}
