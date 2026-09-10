import type {
  AgentProfile,
  AgentCustomizationOverride,
  AgentView,
  AgentViewDataResponse,
  AgentViewSummary,
  AutonomousDirective,
  AutonomousDirectiveCreate,
  AutonomousDirectiveUpdate,
  AutonomousDirectivesResponse,
  AutonomousRun,
  AutonomousRunsResponse,
  BuiltInAgentDefinition,
  ChatMessage,
  ConversationIndexEntry,
  CustomAgentDefinition,
  McpConnectionResult,
  McpServerEntry,
  SessionCreateResponse,
  SkillDefinition,
  SkillCreatePayload,
  SkillUpdatePayload,
  ToolInfo,
  ToolsResponse,
  UnavailableAgent,
  SSEEventType,
  SSETextEvent,
  SSEFunctionCallEvent,
  SSEFunctionResultEvent,
  SSEUsageEvent,
  SSEErrorEvent,
  SSEAgentViewEvent,
} from '../types/api';
import { createParser } from 'eventsource-parser';
import {
  API_BASE,
  request,
  fetchAuthenticated,
  requestJson,
} from './helpers';

export { AuthError } from './helpers';

export async function fetchTools(): Promise<ToolsResponse> {
  return requestJson(`${API_BASE}/tools`, {}, 'Failed to fetch tools');
}

export async function fetchSkills(): Promise<ToolInfo[]> {
  const data = await requestJson<{ skills: ToolInfo[] }>(`${API_BASE}/skills`, {}, 'Failed to fetch skills');
  return data.skills;
}

export async function fetchSkill(name: string): Promise<SkillDefinition> {
  return requestJson(`${API_BASE}/skills/${encodeURIComponent(name)}`, {}, 'Failed to fetch skill');
}

export async function createSkill(skill: SkillCreatePayload): Promise<SkillDefinition> {
  return requestJson(`${API_BASE}/skills`, {
    method: 'POST',
    body: JSON.stringify(skill),
  }, 'Failed to create skill');
}

export async function updateSkill(name: string, payload: SkillUpdatePayload): Promise<SkillDefinition> {
  return requestJson(`${API_BASE}/skills/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }, 'Failed to update skill');
}

export async function deleteSkill(name: string): Promise<void> {
  await request(`${API_BASE}/skills/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  }, 'Failed to delete skill');
}

export async function generateSkillContent(
  description: string,
  name?: string,
): Promise<string> {
  const data = await requestJson<{ content: string }>(`${API_BASE}/skills/generate`, {
    method: 'POST',
    body: JSON.stringify({ description, ...(name ? { name } : {}) }),
  }, 'Failed to generate skill content');
  return data.content;
}

export async function testMcpConnections(servers: McpServerEntry[]): Promise<McpConnectionResult[]> {
  const data = await requestJson<{ results: McpConnectionResult[] }>(`${API_BASE}/mcp/test`, {
    method: 'POST',
    body: JSON.stringify({ mcp_servers: servers }),
  }, 'Failed to test MCP connections');
  return data.results;
}

export interface SessionProfileOverridePayload {
  description: string;
  custom_prompt: string;
  custom_tools: string[];
  custom_search_context: boolean;
  custom_temperature?: number;
  custom_skills?: string[];
  mcp_servers?: McpServerEntry[];
  agentsAsTools?: SubAgentToolWirePayload[];
  override_updated_at: string;
}

/**
 * Wire format for a single sub-agent tool reference. Backend recomputes
 * `toolName`/`toolDescription`/`argDescription` so we never send those.
 */
export interface SubAgentToolWirePayload {
  agentRef:
    | { kind: 'builtin'; profileId: string }
    | { kind: 'custom'; customAgentId: string };
}

export interface SessionRequestPayload {
  profile_id: string;
  custom_name?: string;
  custom_id?: string;
  custom_prompt?: string;
  custom_tools?: string[];
  custom_search_context?: boolean;
  custom_temperature?: number;
  custom_skills?: string[];
  mcp_servers?: McpServerEntry[];
  agentsAsTools?: SubAgentToolWirePayload[];
  profile_override?: SessionProfileOverridePayload;
  conversation_id?: string;
}

export async function createSessionRequest(
  payload: SessionRequestPayload,
  failureMessage = 'Failed to create session',
): Promise<SessionCreateResponse> {
  return requestJson(`${API_BASE}/sessions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }, failureMessage);
}

export async function fetchBuiltInProfileDefinition(profileId: string): Promise<BuiltInAgentDefinition> {
  return requestJson(`${API_BASE}/profiles/${encodeURIComponent(profileId)}/definition`, {}, 'Failed to fetch profile definition');
}

export interface ProfilesResponse {
  profiles: AgentProfile[];
  unavailable: UnavailableAgent[];
}

export async function fetchProfiles(): Promise<ProfilesResponse> {
  return requestJson(`${API_BASE}/profiles`, {}, 'Failed to fetch profiles');
}

// --- Autonomous mode (Duty Officer) ---

/** List the configured autonomous directives (visible to all authenticated users). */
export async function fetchAutonomousDirectives(): Promise<AutonomousDirectivesResponse> {
  return requestJson(`${API_BASE}/autonomous/directives`, {}, 'Failed to fetch autonomous directives');
}

/** List autonomous run history (most-recent-first), shared across all users. */
export async function fetchAutonomousRuns(
  limit = 50,
  directiveId?: string,
): Promise<AutonomousRunsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (directiveId) params.set('directive_id', directiveId);
  return requestJson(`${API_BASE}/autonomous/runs?${params}`, {}, 'Failed to fetch autonomous runs');
}

/** Trigger one autonomous cycle on demand (same behavior as the scheduled timer). */
export async function triggerAutonomousRun(directiveId?: string): Promise<AutonomousRun> {
  return requestJson(`${API_BASE}/autonomous/run-now`, {
    method: 'POST',
    body: JSON.stringify(directiveId ? { directive_id: directiveId } : {}),
  }, 'Failed to trigger autonomous run');
}

/** Create a new automation (directive). */
export async function createAutonomousDirective(
  body: AutonomousDirectiveCreate,
): Promise<AutonomousDirective> {
  return requestJson(`${API_BASE}/autonomous/directives`, {
    method: 'POST',
    body: JSON.stringify(body),
  }, 'Failed to create automation');
}

/** Update an automation (enable/disable, schedule, instruction, …). */
export async function updateAutonomousDirective(
  id: string,
  body: AutonomousDirectiveUpdate,
): Promise<AutonomousDirective> {
  return requestJson(`${API_BASE}/autonomous/directives/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  }, 'Failed to update automation');
}

/** Delete an automation. */
export async function deleteAutonomousDirective(id: string): Promise<void> {
  await request(`${API_BASE}/autonomous/directives/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  }, 'Failed to delete automation', [404]);
}

export async function deleteSession(sessionId: string): Promise<void> {
  await request(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  }, 'Failed to delete session', [404]);
}

// --- Conversations (durable per-user chat history, Cosmos-backed) ---

export interface ConversationMessagesResponse {
  id: string;
  profileId: string;
  profileName: string;
  messages: ChatMessage[];
}

export async function listConversations(limit = 50): Promise<ConversationIndexEntry[]> {
  const conversations: ConversationIndexEntry[] = [];
  let cursor: string | null = null;
  do {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set('cursor', cursor);
    const page: { conversations: ConversationIndexEntry[]; nextCursor: string | null } = await requestJson(
      `${API_BASE}/conversations?${params}`, {}, 'Failed to load conversations',
    );
    conversations.push(...page.conversations);
    cursor = page.nextCursor;
  } while (cursor);
  return conversations;
}

export async function getConversationMessages(id: string): Promise<ConversationMessagesResponse> {
  return requestJson(`${API_BASE}/conversations/${encodeURIComponent(id)}/messages`, {}, 'Failed to load conversation');
}

export async function deleteConversation(id: string): Promise<void> {
  await request(`${API_BASE}/conversations/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  }, 'Failed to delete conversation', [404]);
}

// --- Agent views (dynamic UI pane) ---

export async function listAgentViews(sessionId: string): Promise<AgentViewSummary[]> {
  const data = await requestJson<{ views: AgentViewSummary[] }>(
    `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/views`,
    {},
    'Failed to load agent views',
  );
  return data.views;
}

export async function getAgentView(sessionId: string, viewId: string): Promise<AgentView> {
  return requestJson<AgentView>(
    `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/views/${encodeURIComponent(viewId)}`,
    {},
    'Failed to load agent view',
  );
}

/**
 * Broker one data request on behalf of a rendered view.
 *
 * Returns the structured outcome instead of throwing: refusals are a normal,
 * expected result that the view itself has to render.
 */
export async function requestAgentViewData(
  sessionId: string,
  viewId: string,
  tool: string,
  args: Record<string, unknown>,
): Promise<AgentViewDataResponse> {
  try {
    const resp = await fetchAuthenticated(
      `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/views/${encodeURIComponent(viewId)}/data`,
      {
        method: 'POST',
        body: JSON.stringify({ tool, arguments: args }),
      },
    );
    if (resp.ok) return (await resp.json()) as AgentViewDataResponse;
    const body = await resp.json().catch(() => null);
    if (body?.error?.code) return { ok: false, error: body.error };
    return {
      ok: false,
      error: {
        code: 'tool_failed',
        message: resp.status === 401 ? 'Your session has expired.' : 'That request could not be completed.',
      },
    };
  } catch {
    return { ok: false, error: { code: 'tool_failed', message: 'That request could not be completed.' } };
  }
}

// --- Custom agents, agent customizations, user profile (durable per-user, Cosmos) ---

export async function listCustomAgents(): Promise<CustomAgentDefinition[]> {
  const data = await requestJson<{ agents: CustomAgentDefinition[] }>(`${API_BASE}/custom-agents`, {}, 'Failed to load custom agents');
  return data.agents;
}

export async function saveCustomAgent(agent: CustomAgentDefinition): Promise<CustomAgentDefinition> {
  return requestJson(`${API_BASE}/custom-agents/${encodeURIComponent(agent.id)}`, {
    method: 'PUT',
    body: JSON.stringify(agent),
  }, 'Failed to save custom agent');
}

export async function deleteCustomAgent(id: string): Promise<void> {
  await request(`${API_BASE}/custom-agents/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  }, 'Failed to delete custom agent', [404]);
}

export async function listAgentCustomizations(): Promise<AgentCustomizationOverride[]> {
  const data = await requestJson<{ overrides: AgentCustomizationOverride[] }>(`${API_BASE}/agent-customizations`, {}, 'Failed to load agent customizations');
  return data.overrides;
}

export async function saveAgentCustomization(override: AgentCustomizationOverride): Promise<void> {
  await request(`${API_BASE}/agent-customizations/${encodeURIComponent(override.baseProfileId)}`, {
    method: 'PUT',
    body: JSON.stringify(override),
  }, 'Failed to save agent customization');
}

export async function deleteAgentCustomization(baseProfileId: string): Promise<void> {
  await request(`${API_BASE}/agent-customizations/${encodeURIComponent(baseProfileId)}`, {
    method: 'DELETE',
  }, 'Failed to delete agent customization', [404]);
}

export interface SSECallback {
  onText?: (data: SSETextEvent) => void;
  onFunctionCall?: (data: SSEFunctionCallEvent) => void;
  onFunctionResult?: (data: SSEFunctionResultEvent) => void;
  onUsage?: (data: SSEUsageEvent) => void;
  onError?: (data: SSEErrorEvent) => void;
  onAgentView?: (data: SSEAgentViewEvent) => void;
  onDone?: () => void;
}

export async function sendMessage(
  sessionId: string,
  content: string,
  images: File[] | null,
  callbacks: SSECallback,
  signal?: AbortSignal,
): Promise<void> {
  let body: BodyInit;
  // Send the user's local date/time so the backend can give the model temporal
  // context. It is added to the model/session history only — never shown in the UI.
  const clientTime = new Date().toString();

  if (images && images.length > 0) {
    const formData = new FormData();
    formData.append('content', content);
    formData.append('client_time', clientTime);
    for (const img of images) {
      formData.append('images', img);
    }
    body = formData;
    // Let browser set Content-Type with boundary for multipart
  } else {
    body = JSON.stringify({ content, client_time: clientTime });
  }

  const resp = await request(
    `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: 'POST',
      body,
      signal,
    },
    'Failed to send message',
  );

  if (!resp.body) {
    throw new Error('No response body for SSE stream');
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let completed = false;
  const parser = createParser({
    onEvent: ({ event, data }) => {
      if (signal?.aborted || completed) return;
      const payload: unknown = JSON.parse(data);
      if (event === 'done') completed = true;
      dispatchSSEEvent(event as SSEEventType, payload, callbacks);
    },
  });

  try {
    while (!completed) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.feed(decoder.decode(value, { stream: true }));
    }
    if (!completed && !signal?.aborted) throw new Error('The response ended before completion. Please try again.');
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

function dispatchSSEEvent(
  event: SSEEventType,
  data: unknown,
  callbacks: SSECallback,
): void {
  switch (event) {
    case 'text':
      callbacks.onText?.(data as SSETextEvent);
      break;
    case 'function_call':
      callbacks.onFunctionCall?.(data as SSEFunctionCallEvent);
      break;
    case 'function_result':
      callbacks.onFunctionResult?.(data as SSEFunctionResultEvent);
      break;
    case 'usage':
      callbacks.onUsage?.(data as SSEUsageEvent);
      break;
    case 'error':
      callbacks.onError?.(data as SSEErrorEvent);
      break;
    case 'agent_view':
      callbacks.onAgentView?.(data as SSEAgentViewEvent);
      break;
    case 'done':
      callbacks.onDone?.();
      break;
  }
}
