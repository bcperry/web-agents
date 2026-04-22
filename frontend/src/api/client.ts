import type {
  AgentProfile,
  ChatSession,
  McpServerEntry,
  ToolInfo,
  ToolsResponse,
  UnavailableAgent,
  UserMemoryProfile,
  SSEEventType,
  SSETextEvent,
  SSEFunctionCallEvent,
  SSEFunctionResultEvent,
  SSEUsageEvent,
  SSEErrorEvent,
} from '../types/api';
import { emitToast } from '../hooks/useToast';

const API_BASE = '/api';

/** Thrown when the backend returns 401 Unauthorized. */
export class AuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AuthError';
  }
}

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('auth_token');
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

/** Check response for 401 and throw AuthError so callers can trigger re-auth. */
function assertNotUnauthorized(resp: Response, context: string): void {
  if (resp.status === 401) {
    throw new AuthError(`Unauthorized: ${context}`);
  }
}

/** Try to extract a user-friendly detail string from an error response body. */
async function extractErrorDetail(resp: Response, fallback: string): Promise<string> {
  try {
    const body = await resp.json();
    if (body.detail && typeof body.detail === 'string') return body.detail;
  } catch { /* not JSON or no detail field */ }
  return fallback;
}

/** Classify an HTTP error into user-friendly message and severity. */
function classifyError(status: number, detail: string): {
  userMessage: string;
  type: 'error' | 'warning';
  retryable: boolean;
} {
  const lowerDetail = detail.toLowerCase();

  if (status === 429 || lowerDetail.includes('rate limit') || lowerDetail.includes('too many requests')) {
    return { userMessage: detail || 'Rate limit exceeded. Please wait and try again.', type: 'warning', retryable: true };
  }
  if (status === 400) {
    return { userMessage: detail || 'Invalid request.', type: 'error', retryable: false };
  }
  if (status >= 500) {
    return { userMessage: detail || 'A server error occurred. Please try again later.', type: 'error', retryable: false };
  }
  return { userMessage: detail || `Request failed (${status})`, type: 'error', retryable: false };
}

/** Extract detail, classify, emit toast, and throw — shared by all API functions. */
async function handleHttpError(resp: Response, context: string): Promise<never> {
  const detail = await extractErrorDetail(resp, `${context}: ${resp.status}`);
  const classified = classifyError(resp.status, detail);
  emitToast({ message: classified.userMessage, type: classified.type });
  throw new Error(detail);
}

export interface HistoryResponse {
  session_id: string;
  profile_id: string;
  profile_name: string;
  session_data: Record<string, unknown>;
}

export async function fetchTools(): Promise<ToolsResponse> {
  const resp = await fetch(`${API_BASE}/tools`, {
    headers: getAuthHeaders(),
  });
  assertNotUnauthorized(resp, 'Failed to fetch tools');
  if (!resp.ok) await handleHttpError(resp, 'Failed to fetch tools');
  const data = await resp.json();
  return {
    tools: data.tools,
    unavailable: data.unavailable || [],
    search_context_available: data.search_context_available ?? true,
    search_context_reason: data.search_context_reason ?? null,
  };
}

export async function fetchSkills(): Promise<ToolInfo[]> {
  const resp = await fetch(`${API_BASE}/skills`, {
    headers: getAuthHeaders(),
  });
  assertNotUnauthorized(resp, 'Failed to fetch skills');
  if (!resp.ok) await handleHttpError(resp, 'Failed to fetch skills');
  const data = await resp.json();
  return data.skills;
}

export async function createCustomSession(params: {
  custom_name: string;
  custom_prompt: string;
  custom_tools: string[];
  custom_search_context: boolean;
  custom_temperature?: number;
  custom_skills?: string[];
  mcp_servers?: McpServerEntry[];
  history?: Record<string, unknown>;
  user_profile?: { name: string; preferences: string; notes: string };
  [key: string]: unknown;
}): Promise<ChatSession> {
  const { custom_name, custom_prompt, custom_tools, custom_search_context, custom_temperature, custom_skills, mcp_servers, history, user_profile } = params;
  const resp = await fetch(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({
      profile_id: 'custom',
      custom_name,
      custom_prompt,
      custom_tools,
      custom_search_context,
      ...(custom_temperature !== undefined ? { custom_temperature } : {}),
      ...(custom_skills && custom_skills.length > 0 ? { custom_skills } : {}),
      ...(mcp_servers && mcp_servers.length > 0 ? { mcp_servers } : {}),
      ...(history ? { history } : {}),
      ...(user_profile ? { user_profile } : {}),
    }),
  });
  assertNotUnauthorized(resp, 'Failed to create custom session');
  if (!resp.ok) await handleHttpError(resp, 'Failed to create custom session');
  return resp.json();
}

export interface ProfilesResponse {
  profiles: AgentProfile[];
  unavailable: UnavailableAgent[];
}

export async function fetchProfiles(): Promise<ProfilesResponse> {
  const resp = await fetch(`${API_BASE}/profiles`, {
    headers: getAuthHeaders(),
  });
  assertNotUnauthorized(resp, 'Failed to fetch profiles');
  if (!resp.ok) await handleHttpError(resp, 'Failed to fetch profiles');
  const data = await resp.json();
  return { profiles: data.profiles, unavailable: data.unavailable || [] };
}

export async function createSession(profileId: string, userProfile?: UserMemoryProfile | null): Promise<ChatSession> {
  const resp = await fetch(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({
      profile_id: profileId,
      ...(userProfile ? { user_profile: { name: userProfile.name, preferences: userProfile.preferences, notes: userProfile.notes } } : {}),
    }),
  });
  assertNotUnauthorized(resp, 'Failed to create session');
  if (!resp.ok) await handleHttpError(resp, 'Failed to create session');
  return resp.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  assertNotUnauthorized(resp, 'Failed to delete session');
  if (!resp.ok && resp.status !== 404) await handleHttpError(resp, 'Failed to delete session');
}

export async function fetchHistory(sessionId: string): Promise<HistoryResponse> {
  const resp = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/history`, {
    headers: getAuthHeaders(),
  });
  assertNotUnauthorized(resp, 'Failed to fetch history');
  if (!resp.ok) await handleHttpError(resp, 'Failed to fetch history');
  return resp.json();
}

export async function createSessionWithHistory(
  profileId: string,
  history: Record<string, unknown>,
  userProfile?: UserMemoryProfile | null,
): Promise<ChatSession> {
  const resp = await fetch(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({
      profile_id: profileId,
      history,
      ...(userProfile ? { user_profile: { name: userProfile.name, preferences: userProfile.preferences, notes: userProfile.notes } } : {}),
    }),
  });
  assertNotUnauthorized(resp, 'Failed to create session with history');
  if (!resp.ok) await handleHttpError(resp, 'Failed to create session with history');
  return resp.json();
}

export interface SSECallback {
  onText?: (data: SSETextEvent) => void;
  onFunctionCall?: (data: SSEFunctionCallEvent) => void;
  onFunctionResult?: (data: SSEFunctionResultEvent) => void;
  onUsage?: (data: SSEUsageEvent) => void;
  onError?: (data: SSEErrorEvent) => void;
  onDone?: () => void;
}

export async function sendMessage(
  sessionId: string,
  content: string,
  images: File[] | null,
  callbacks: SSECallback,
): Promise<void> {
  let body: BodyInit;
  const headers: Record<string, string> = { ...getAuthHeaders() };

  if (images && images.length > 0) {
    const formData = new FormData();
    formData.append('content', content);
    for (const img of images) {
      formData.append('images', img);
    }
    body = formData;
    // Let browser set Content-Type with boundary for multipart
  } else {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify({ content });
  }

  const resp = await fetch(
    `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: 'POST',
      headers,
      body,
    },
  );

  assertNotUnauthorized(resp, 'Session expired or unauthorized');
  if (!resp.ok) {
    const errText = await resp.text();
    const classified = classifyError(resp.status, errText);
    emitToast({ message: classified.userMessage, type: classified.type });
    throw new Error(`Message request failed (${resp.status}): ${errText}`);
  }

  if (!resp.body) {
    throw new Error('No response body for SSE stream');
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    let currentEvent = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        const rawData = line.slice(6);
        try {
          const data = JSON.parse(rawData);
          dispatchSSEEvent(currentEvent as SSEEventType, data, callbacks);
        } catch {
          // skip malformed data
        }
        currentEvent = '';
      }
    }
  }

  // Process any remaining buffer
  if (buffer.trim()) {
    const remainingLines = buffer.split('\n');
    let currentEvent = '';
    for (const line of remainingLines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          dispatchSSEEvent(currentEvent as SSEEventType, data, callbacks);
        } catch {
          // skip
        }
        currentEvent = '';
      }
    }
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
    case 'done':
      callbacks.onDone?.();
      break;
  }
}
