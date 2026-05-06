import type { AgentCustomizationOverride, StandardAgentCandidate } from '../types/api';

function quote(value: string): string {
  return JSON.stringify(value);
}

function listBlock(values: string[], indent: string): string[] {
  if (values.length === 0) return [`${indent}[]`];
  return values.map((value) => `${indent}- ${quote(value)}`);
}

function objectListBlock(values: Array<Record<string, unknown>>, indent: string): string[] {
  if (values.length === 0) return [`${indent}[]`];
  return values.flatMap((value) => {
    const entries = Object.entries(value).filter(([, item]) => item !== undefined && item !== null && item !== '');
    if (entries.length === 0) return [];
    const [firstKey, firstValue] = entries[0];
    return [
      `${indent}- ${firstKey}: ${quote(String(firstValue))}`,
      ...entries.slice(1).map(([key, item]) => `${indent}  ${key}: ${typeof item === 'boolean' ? String(item) : quote(String(item))}`),
    ];
  });
}

function literalBlock(value: string, indent: string): string[] {
  const lines = value.replace(/\s+$/g, '').split('\n');
  return lines.length > 0 ? lines.map((line) => `${indent}${line}`) : [`${indent}`];
}

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

  const yamlLines = [
    `${profileId}:`,
    `  name: ${quote(String(profile.name))}`,
    `  description: ${quote(String(profile.description))}`,
    `  icon: ${quote(String(profile.icon))}`,
    '  tools:',
    ...listBlock(override.tools, '    '),
    '  skills:',
    ...listBlock(override.skills, '    '),
    '  mcp_servers:',
    ...objectListBlock(override.mcpServers as unknown as Array<Record<string, unknown>>, '    '),
    `  search_context: ${override.useSearchContext}`,
    ...(override.temperature !== undefined ? [`  temperature: ${override.temperature}`] : []),
    '  starters:',
    ...objectListBlock(override.starters as unknown as Array<Record<string, unknown>>, '    '),
    '  system_prompt: |',
    ...literalBlock(override.systemPrompt, '    '),
    '',
  ];

  return {
    profileId,
    yaml: yamlLines.join('\n'),
    profile,
    generatedAt: new Date().toISOString(),
    sourceOverrideUpdatedAt: override.updatedAt,
  };
}
