export interface StarterQuestion {
  label: string;
  message: string;
}

export interface ToolInfo {
  name: string;
  description: string;
}

export interface UnavailableToolInfo {
  name: string;
  reason: string;
}

export interface ToolsResponse {
  tools: ToolInfo[];
  unavailable: UnavailableToolInfo[];
  search_context_available: boolean;
  search_context_reason: string | null;
}

export interface McpServerEntry {
  name: string;
  transport: 'http' | 'stdio';
  url: string;
  authenticated?: boolean;
  authScope?: string;
}

export interface McpConnectionResult {
  name: string;
  transport: string;
  status: 'connected' | 'failed';
  tool_count: number;
  error?: string;
}

export interface CustomAgentDefinition {
  id: string;
  name: string;
  description: string;
  systemPrompt: string;
  tools: string[];
  skills: string[];
  mcpServers: McpServerEntry[];
  useSearchContext: boolean;
  icon: string;
  starters: StarterQuestion[];
  temperature?: number;
  createdAt: string;
  updatedAt: string;
}

export interface AgentProfile {
  id: string;
  name: string;
  description: string;
  icon: string;
  starters: StarterQuestion[];
  isCustom?: boolean;
  mcp_server_count?: number;
}

export interface UnavailableAgent {
  id: string;
  name: string;
  reason: string;
}

export interface ChatSession {
  session_id: string;
  profile_id: string;
  profile_name: string;
}

export interface SessionCreateResponse {
  session_id: string;
  profile_id: string;
  profile_name: string;
  tools_loaded?: string[];
  skills_loaded?: string[];
  search_context?: boolean;
  mcp_results?: McpConnectionResult[];
}

export interface ImageData {
  filename: string;
  media_type: string;
  data: string;
}

export interface ToolInvocation {
  call_id: string;
  name: string;
  arguments: string;
  result: string;
  content_items?: ContentItem[];
}

export type ContentItem =
  | { type: 'text'; text: string }
  | { type: 'image'; data: string; mimeType: string };

export interface UsageDetails {
  input_token_count: number;
  output_token_count: number;
  total_token_count: number;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  images?: ImageData[];
  tool_invocations?: ToolInvocation[];
  usage?: UsageDetails | null;
}

export type SSEEventType = 'text' | 'function_call' | 'function_result' | 'usage' | 'error' | 'done';

export interface SSETextEvent {
  content: string;
}

export interface SSEFunctionCallEvent {
  call_id: string;
  name: string;
  arguments: string;
}

export interface SSEFunctionResultEvent {
  call_id: string;
  result: string;
  arguments?: string;
  content_items?: ContentItem[];
}

export interface SSEUsageEvent {
  input_token_count: number;
  output_token_count: number;
  total_token_count: number;
}

export interface SSEErrorEvent {
  message: string;
  retry_after: number | null;
}

export interface ConversationIndexEntry {
  id: string;
  profileId: string;
  profileName: string;
  description: string;
  createdAt: string;
  lastActivityAt: string;
  customAgentId?: string;
}

export interface StoredConversation {
  id: string;
  profileId: string;
  profileName: string;
  description: string;
  createdAt: string;
  lastActivityAt: string;
  sessionData: Record<string, unknown>;
  customAgentId?: string;
}

export interface UserMemoryProfile {
  name: string;
  preferences: string;
  notes: string;
  updatedAt: string;
}
