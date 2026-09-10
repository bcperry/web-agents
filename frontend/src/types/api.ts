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
// Tagged union — `kind` discriminates built-in references from custom agents.
// Custom refs inline the definition so the parent can call the exact draft the
// user selected, even before it is promoted into the shared built-in catalog.
export interface BuiltinAgentRefWire {
  kind: 'builtin';
  profileId: string;
}

export interface CustomAgentRefWire {
  kind: 'custom';
  customAgentId: string;
  definition?: CustomAgentDefinition;
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
  agentsAsTools: SubAgentToolRef[];
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
  agentsAsTools: SubAgentToolRef[];
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
  agentsAsTools: SubAgentToolRef[];
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

export type SSEEventType = 'text' | 'function_call' | 'function_result' | 'usage' | 'error' | 'done' | 'agent_view';

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

export interface SSEAgentViewEvent {
  view_id: string;
  title: string;
  call_id: string;
  created_at: string;
}

export interface AgentViewSummary {
  viewId: string;
  title: string;
  createdAt: string;
  chars: number;
  source: 'chat' | 'autonomous';
}

export interface AgentView extends AgentViewSummary {
  html: string;
}

export interface AgentViewDataResponse {
  ok: boolean;
  data?: unknown;
  truncated?: boolean;
  durationMs?: number;
  error?: AgentViewBridgeError;
}

export type AgentViewErrorCode =
  | 'not_permitted'
  | 'invalid_arguments'
  | 'session_inactive'
  | 'rate_limited'
  | 'tool_failed';

export interface AgentViewBridgeError {
  code: AgentViewErrorCode;
  message: string;
}

/** view -> host. See specs/016-agent-ui-pane/contracts/view-bridge.md */
export type AgentViewBridgeRequest =
  | { v: 1; type: 'agentui.ready' }
  | { v: 1; type: 'agentui.request'; requestId: string; tool: string; args: Record<string, unknown> };

/** host -> view. */
export type AgentViewBridgeResponse =
  | { v: 1; type: 'agentui.response'; requestId: string; ok: true; data: unknown; truncated: boolean }
  | { v: 1; type: 'agentui.response'; requestId: string; ok: false; error: AgentViewBridgeError };

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

// --- Autonomous mode (Duty Officer) ---

/** A configured standing order the autonomous agent runs on a schedule. */
export interface AutonomousDirective {
  id: string;
  profileId: string;
  /** Full standing-order instruction (used by the edit form). */
  instruction: string;
  /** First ~160 chars of the directive instruction (no secrets). */
  instructionSummary: string;
  schedule: string | null;
  /** Next scheduled fire time (UTC ISO-8601) when running autonomously, else null. */
  nextRun: string | null;
  enabled: boolean;
  /** Non-secret notification descriptor: 'webhook' or 'log'. */
  notify: string;
  /** Configured webhook ENV-VAR NAME for editing (never a literal URL), else null. */
  notifyWebhook: string | null;
  /** Last edit time (UTC ISO-8601), else null. */
  updatedAt: string | null;
}

export interface AutonomousDirectivesResponse {
  enabled: boolean;
  /** Whether the unattended in-process scheduler is running (else runs are manual-only). */
  schedulerEnabled: boolean;
  systemUserId: string;
  directives: AutonomousDirective[];
}

/** Create payload for a new automation (snake_case to match the backend). */
export interface AutonomousDirectiveCreate {
  id: string;
  profile_id: string;
  instruction: string;
  schedule?: string | null;
  enabled?: boolean;
  notify_webhook?: string | null;
}

/** Partial update for an automation; omitted fields are left unchanged. */
export interface AutonomousDirectiveUpdate {
  profile_id?: string;
  instruction?: string;
  schedule?: string | null;
  enabled?: boolean;
  notify_webhook?: string | null;
}

/** An audit record for one autonomous cycle (camelCase, no secrets). */
export interface AutonomousRun {
  id: string;
  directiveId: string;
  profileId: string;
  sessionId: string;
  status: string;
  startedAt: string;
  finishedAt: string;
  responseText: string;
  toolEvents: Array<Record<string, unknown>>;
  usage: Partial<UsageDetails>;
  error: string | null;
  notifyStatus: string;
  notifyError: string | null;
  trigger: string;
}

export interface AutonomousRunsResponse {
  runs: AutonomousRun[];
  count: number;
}
