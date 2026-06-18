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
  url?: string;
  authenticated?: boolean;
  authScope?: string;
  description?: string;
}

export interface McpConnectionResult {
  name: string;
  transport: string;
  status: 'connected' | 'failed';
  tool_count: number;
  error?: string;
}

// Agents-as-Tools (feature 008) ---------------------------------------------
//
// Tagged union — `kind` discriminates built-in (references a YAML profile by
// id) from custom (inlines the full local CustomAgentDefinition because the
// backend has no custom-agent persistence layer).
export interface BuiltinAgentRefWire {
  kind: 'builtin';
  profileId: string;
}

export interface CustomAgentRefWire {
  kind: 'custom';
  customAgentId: string;
  /** Full inlined custom-agent definition; required on the wire. */
  definition: CustomAgentDefinition;
}

export type AgentRef = BuiltinAgentRefWire | CustomAgentRefWire;

/**
 * Reference from one agent to another agent that should be exposed as a tool.
 * `toolName` / `toolDescription` / `argDescription` are SERVER-DERIVED and
 * MUST NOT be sent on the wire — the backend recomputes them on every load.
 */
export interface SubAgentToolRef {
  agentRef: AgentRef;
  /** Server-supplied (read-only); slugified from the target agent's name. */
  toolName?: string;
  /** Server-supplied (read-only); copied from the target agent's description. */
  toolDescription?: string;
  argDescription?: string;
}

export interface CustomAgentDefinition {
  id: string;
  name: string;
  description: string;
  group?: string;
  systemPrompt: string;
  tools: string[];
  skills: string[];
  mcpServers: McpServerEntry[];
  useSearchContext: boolean;
  icon: string;
  starters: StarterQuestion[];
  temperature?: number;
  agentsAsTools?: SubAgentToolRef[];
  createdAt: string;
  updatedAt: string;
}

export interface AgentCustomizationOverride {
  id: string;
  description: string;
  group?: string;
  systemPrompt: string;
  tools: string[];
  skills: string[];
  mcpServers: McpServerEntry[];
  useSearchContext: boolean;
  icon: string;
  starters: StarterQuestion[];
  temperature?: number;
  agentsAsTools?: SubAgentToolRef[];
  source: 'builtin-override';
  createdAt: string;
  updatedAt: string;
  baseProfileId: string;
  baseProfileName?: string;
}

export interface BuiltInAgentDefinition {
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
  agentsAsTools?: SubAgentToolRef[];
  source: 'builtin';
}

export interface StandardAgentCandidate {
  profileId: string;
  yaml: string;
  profile: Record<string, unknown>;
  generatedAt: string;
  sourceOverrideUpdatedAt: string;
}

export interface AgentProfile {
  id: string;
  name: string;
  description: string;
  icon: string;
  group?: string;
  starters: StarterQuestion[];
  isCustom?: boolean;
  isCustomized?: boolean;
  customAgent?: CustomAgentDefinition;
  builtInOverride?: AgentCustomizationOverride;
  baseProfileId?: string;
  usedBuiltInOverride?: boolean;
  overrideUpdatedAt?: string;
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
  agents_loaded?: string[];
  search_context?: boolean;
  mcp_results?: McpConnectionResult[];
  used_profile_override?: boolean;
  override_updated_at?: string | null;
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
  usedBuiltInOverride?: boolean;
  baseProfileId?: string;
  overrideUpdatedAt?: string;
}

export interface SkillDefinition {
  name: string;
  description: string;
  content: string;
}

export interface SkillSummary {
  name: string;
  description: string;
}

export interface SkillCreatePayload {
  name: string;
  description: string;
  content: string;
}

export interface SkillUpdatePayload {
  description: string;
  content: string;
}
