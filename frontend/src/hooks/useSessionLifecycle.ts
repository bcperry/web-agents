import type {
  AgentProfile,
  ChatMessage,
  ChatSession,
  ConversationIndexEntry,
  McpConnectionResult,
  SessionCreateResponse,
  UsageDetails,
} from '../types/api';
import { createSessionRequest, deleteSession, getConversationMessages, type SessionRequestPayload } from '../api/client';

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
  agentsLoaded: string[];
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
  resume: ConversationIndexEntry | undefined,
  previousSession: ChatSession | null,
): Promise<SessionStartResult> {
  await cleanupSession(previousSession);

  const payload = buildSessionRequest(profile, resume);
  const newSession: SessionCreateResponse = await createSessionRequest(payload);
  const customAgentId = profile.customAgent?.id ?? null;
  let builtInOverride: BuiltInOverrideState;
  if (profile.builtInOverride) {
    builtInOverride = {
      usedBuiltInOverride: true,
      baseProfileId: profile.builtInOverride.baseProfileId,
      overrideUpdatedAt: profile.builtInOverride.updatedAt,
    };
  } else if (resume?.usedBuiltInOverride) {
    builtInOverride = {
      usedBuiltInOverride: true,
      baseProfileId: resume.baseProfileId ?? profile.id,
      overrideUpdatedAt: resume.overrideUpdatedAt,
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

  // History now lives server-side (Cosmos). On resume, load the prior messages
  // through the backend instead of from any client-held blob.
  let restoredMessages: ChatMessage[] = [];
  if (resume) {
    try {
      const loaded = await getConversationMessages(resume.id);
      restoredMessages = loaded.messages ?? [];
    } catch {
      restoredMessages = [];
    }
  }

  const { mcp_results, tools_loaded, skills_loaded, agents_loaded, search_context, ...session } = newSession;
  return {
    session,
    mcpResults: mcp_results ?? [],
    toolsLoaded: tools_loaded ?? [],
    skillsLoaded: skills_loaded ?? [],
    agentsLoaded: agents_loaded ?? [],
    searchContext: search_context ?? false,
    restoredMessages,
    conversationId: resume?.id ?? newSession.session_id,
    createdAt: resume?.createdAt ?? new Date().toISOString(),
    customAgentId,
    builtInOverride,
  };
}

function buildSessionRequest(
  profile: AgentProfile,
  resume: ConversationIndexEntry | undefined,
): SessionRequestPayload {
  const resumePayload = resume ? { conversation_id: resume.id } : {};

  if (profile.customAgent) {
    return {
      profile_id: 'custom',
      custom_name: profile.customAgent.name,
      custom_id: profile.customAgent.id,
      custom_prompt: profile.customAgent.systemPrompt,
      custom_tools: profile.customAgent.tools,
      custom_search_context: profile.customAgent.useSearchContext,
      ...(profile.customAgent.temperature !== undefined ? { custom_temperature: profile.customAgent.temperature } : {}),
      ...(profile.customAgent.skills.length > 0 ? { custom_skills: profile.customAgent.skills } : {}),
      ...(profile.customAgent.mcpServers.length > 0 ? { mcp_servers: profile.customAgent.mcpServers } : {}),
      ...(profile.customAgent.agentsAsTools.length > 0
        ? { agentsAsTools: profile.customAgent.agentsAsTools.map((entry) => ({ agentRef: entry.agentRef })) }
        : {}),
      ...resumePayload,
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
        ...(profile.builtInOverride.agentsAsTools.length > 0
          ? { agentsAsTools: profile.builtInOverride.agentsAsTools.map((entry) => ({ agentRef: entry.agentRef })) }
          : {}),
        override_updated_at: profile.builtInOverride.updatedAt,
      },
      ...resumePayload,
    };
  }

  return {
    profile_id: profile.id,
    ...resumePayload,
  };
}
