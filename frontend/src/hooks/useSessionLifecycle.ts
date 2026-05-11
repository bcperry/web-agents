import type {
  AgentProfile,
  ChatMessage,
  ChatSession,
  McpConnectionResult,
  SessionCreateResponse,
  UserMemoryProfile,
  StoredConversation,
  ToolInvocation,
  UsageDetails,
} from '../types/api';
import { createSessionRequest, deleteSession, type SessionRequestPayload } from '../api/client';
import { convertFrameworkContentItems } from '../utils/content';
import { loadProfile } from './useUserProfile';

export interface BuiltInOverrideState {
  usedBuiltInOverride: boolean;
  baseProfileId?: string;
  overrideUpdatedAt?: string;
}

export interface SessionStartResult {
  session: ChatSession;
  mcpResults: McpConnectionResult[];
  toolsLoaded: string[];
  skillsLoaded: string[];
  searchContext: boolean;
  restoredMessages: ChatMessage[];
  conversationId: string;
  createdAt: string;
  customAgentId: string | null;
  builtInOverride: BuiltInOverrideState;
}

export function emptyUsage(): UsageDetails {
  return {
    input_token_count: 0,
    output_token_count: 0,
    total_token_count: 0,
  };
}

export function emptyBuiltInOverride(): BuiltInOverrideState {
  return { usedBuiltInOverride: false };
}

export async function cleanupSession(session: ChatSession | null): Promise<void> {
  if (session) {
    await deleteSession(session.session_id).catch(() => {});
  }
}

export async function startChatSession(
  profile: AgentProfile,
  history: StoredConversation | undefined,
  previousSession: ChatSession | null,
): Promise<SessionStartResult> {
  await cleanupSession(previousSession);

  const userProfile = loadProfile();
  const payload = buildSessionRequest(profile, history, userProfile);
  const newSession: SessionCreateResponse = await createSessionRequest(payload);
  const customAgentId = profile.customAgent?.id ?? null;
  let builtInOverride: BuiltInOverrideState;
  if (profile.builtInOverride) {
    builtInOverride = {
      usedBuiltInOverride: true,
      baseProfileId: profile.builtInOverride.baseProfileId,
      overrideUpdatedAt: profile.builtInOverride.updatedAt,
    };
  } else if (history?.usedBuiltInOverride) {
    builtInOverride = {
      usedBuiltInOverride: true,
      baseProfileId: history.baseProfileId ?? profile.id,
      overrideUpdatedAt: history.overrideUpdatedAt,
    };
  } else {
    builtInOverride = emptyBuiltInOverride();
  }

  if (newSession.used_profile_override) {
    builtInOverride = {
      usedBuiltInOverride: true,
      baseProfileId: profile.builtInOverride?.baseProfileId ?? profile.id,
      overrideUpdatedAt: newSession.override_updated_at ?? profile.builtInOverride?.updatedAt,
    };
  }

  const { mcp_results, tools_loaded, skills_loaded, search_context, ...session } = newSession;
  return {
    session,
    mcpResults: mcp_results ?? [],
    toolsLoaded: tools_loaded ?? [],
    skillsLoaded: skills_loaded ?? [],
    searchContext: search_context ?? false,
    restoredMessages: history ? extractMessagesFromSessionData(history.sessionData) : [],
    conversationId: history?.id ?? newSession.session_id,
    createdAt: history?.createdAt ?? new Date().toISOString(),
    customAgentId,
    builtInOverride,
  };
}

function buildSessionRequest(
  profile: AgentProfile,
  history: StoredConversation | undefined,
  userProfile: UserMemoryProfile | null,
): SessionRequestPayload {
  const userProfilePayload = userProfile
    ? { user_profile: { name: userProfile.name, preferences: userProfile.preferences, notes: userProfile.notes } }
    : {};

  if (profile.customAgent) {
    return {
      profile_id: 'custom',
      custom_name: profile.customAgent.name,
      custom_prompt: profile.customAgent.systemPrompt,
      custom_tools: profile.customAgent.tools,
      custom_search_context: profile.customAgent.useSearchContext,
      ...(profile.customAgent.temperature !== undefined ? { custom_temperature: profile.customAgent.temperature } : {}),
      ...(profile.customAgent.skills.length > 0 ? { custom_skills: profile.customAgent.skills } : {}),
      ...(profile.customAgent.mcpServers.length > 0 ? { mcp_servers: profile.customAgent.mcpServers } : {}),
      ...(history?.sessionData ? { history: history.sessionData } : {}),
      ...userProfilePayload,
    };
  }

  if (profile.builtInOverride) {
    return {
      profile_id: profile.builtInOverride.baseProfileId,
      profile_override: {
        description: profile.builtInOverride.description,
        custom_prompt: profile.builtInOverride.systemPrompt,
        custom_tools: profile.builtInOverride.tools,
        custom_search_context: profile.builtInOverride.useSearchContext,
        ...(profile.builtInOverride.temperature !== undefined ? { custom_temperature: profile.builtInOverride.temperature } : {}),
        ...(profile.builtInOverride.skills.length > 0 ? { custom_skills: profile.builtInOverride.skills } : {}),
        ...(profile.builtInOverride.mcpServers.length > 0 ? { mcp_servers: profile.builtInOverride.mcpServers } : {}),
        override_updated_at: profile.builtInOverride.updatedAt,
      },
      ...(history?.sessionData ? { history: history.sessionData } : {}),
      ...userProfilePayload,
    };
  }

  return {
    profile_id: profile.id,
    ...(history?.sessionData ? { history: history.sessionData } : {}),
    ...userProfilePayload,
  };
}

export function extractMessagesFromSessionData(sessionData: Record<string, unknown>): ChatMessage[] {
  try {
    const state = sessionData.state as Record<string, unknown> | undefined;
    const inMemoryProvider = state?.in_memory as Record<string, unknown> | undefined;
    const inMemory = inMemoryProvider?.messages as Array<Record<string, unknown>> | undefined;
    if (!Array.isArray(inMemory)) return [];

    const result: ChatMessage[] = [];
    for (const msg of inMemory) {
      const role = msg.role as string;
      const contents = msg.contents as Array<Record<string, unknown>> | undefined;
      if (!Array.isArray(contents)) continue;

      if (role === 'tool') {
        attachToolResults(result, contents);
        continue;
      }

      if (role !== 'user' && role !== 'assistant') continue;
      result.push(toChatMessage(role, contents));
    }
    return result;
  } catch {
    return [];
  }
}

function attachToolResults(messages: ChatMessage[], contents: Array<Record<string, unknown>>): void {
  const lastAssistant = messages.length > 0 ? messages[messages.length - 1] : null;
  if (lastAssistant?.role !== 'assistant' || !lastAssistant.tool_invocations) return;

  for (const content of contents) {
    if (content.type !== 'function_result' && content.type !== 'mcp_server_tool_result') continue;
    const callId = content.call_id as string;
    const existing = lastAssistant.tool_invocations.find((tool) => tool.call_id === callId);
    if (!existing) continue;

    const rawResult = content.type === 'mcp_server_tool_result' ? content.output : content.result;
    existing.result = renderFrameworkToolResult(rawResult);
    const converted = convertFrameworkContentItems(content.items as Array<Record<string, unknown>> | undefined);
    if (converted.some((item) => item.type === 'image')) {
      existing.content_items = converted;
    }
  }
}

function renderFrameworkToolResult(rawResult: unknown): string {
  if (Array.isArray(rawResult)) {
    const textParts = rawResult
      .filter((item: Record<string, unknown>) => item.type === 'text')
      .map((item: Record<string, unknown>) => item.text as string || '');
    return textParts.length > 0 ? textParts.join('\n') : JSON.stringify(rawResult);
  }
  return typeof rawResult === 'string' ? rawResult : JSON.stringify(rawResult ?? '');
}

function toChatMessage(role: string, contents: Array<Record<string, unknown>>): ChatMessage {
  let text = '';
  const toolInvocations: ToolInvocation[] = [];
  const toolByCallId: Record<string, ToolInvocation> = {};

  for (const content of contents) {
    const type = content.type as string;
    if (type === 'text') {
      text += content.text as string || '';
    } else if (type === 'function_call' || type === 'mcp_server_tool_call') {
      const args = content.arguments;
      const callId = (content.call_id as string) || '';
      const renderedArgs = typeof args === 'string' ? args : JSON.stringify(args ?? '');
      const existing = callId ? toolByCallId[callId] : undefined;
      if (existing) {
        if (renderedArgs) existing.arguments = (existing.arguments || '') + renderedArgs;
        if (!existing.name) existing.name = (content.name as string) || (content.tool_name as string) || '';
      } else {
        const invocation: ToolInvocation = {
          call_id: callId,
          name: (content.name as string) || (content.tool_name as string) || '',
          arguments: renderedArgs,
          result: '',
        };
        toolInvocations.push(invocation);
        if (callId) toolByCallId[callId] = invocation;
      }
    }
  }

  return {
    role: role as 'user' | 'assistant',
    content: text,
    tool_invocations: toolInvocations.length > 0 ? toolInvocations : undefined,
  };
}