# Implementation Plan: MCP Server UI Improvements

**Branch**: `001-mcp-server-ui-improvements` | **Date**: 2026-04-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-mcp-server-ui-improvements/spec.md`

## Summary

Add MCP server connection visibility to the UI: show per-server connection status indicators (checkmarks/X's), emit toast warnings when default agent MCP servers fail to connect during session creation, and support authenticated MCP servers that forward the user's Azure AD bearer token. This requires backend API changes (session creation response includes MCP connection results, token forwarding to MCP servers) and frontend changes (status indicators in ProfileSelector/session views, toast integration, auth flag in McpServerEntry).

## Technical Context

**Language/Version**: Python 3.12+ (backend), TypeScript (frontend)  
**Primary Dependencies**: FastAPI, React, MSAL (Azure AD auth — frontend @azure/msal-browser + backend msal for OBO), agent-framework (MCPStdioTool, MCPStreamableHTTPTool), httpx  
**Storage**: In-memory session store (backend), localStorage (frontend custom agents)  
**Testing**: pytest (backend), manual + Playwright visual verification (frontend)  
**Target Platform**: Azure Government App Service (Linux)  
**Project Type**: Web service (two-tier: FastAPI backend + React SPA frontend)  
**Performance Goals**: Session creation <5s including MCP connections (parallel where possible)  
**Constraints**: Azure Government endpoints only (.azure.us); no secrets in frontend; MSAL token acquisition for MCP auth  
**Scale/Scope**: ~5 default agent profiles, up to ~10 MCP servers per agent, single-user sessions

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Read-Only Data Access | PASS | No database changes — MCP servers are external tool providers |
| II. Single-File Agent Definitions | PASS | `agents.yaml` gains optional `auth: true` field on mcp_servers entries; no structural change |
| III. Security & Credential Hygiene | PASS | Auth token forwarded server-side only, never exposed in frontend. Must ensure token is not logged. MCP auth restricted to Azure Gov endpoints |
| IV. Evaluation-Driven Quality | PASS | No prompt/model changes — UI and API plumbing only |
| V. Simplicity & Minimalism | PASS | Minimal additions: one new field on McpServerEntry, extended session response, toast on failure, status indicators. New `msal` dependency justified: required for OBO token exchange with MCP servers on separate Azure AD app registrations — no alternative exists in the Python ecosystem for this Azure AD flow |
| VI. Infrastructure as Code | PASS | No infrastructure changes |
| VII. Two-Tier API-First Architecture | PASS | All MCP connection logic stays in backend. Frontend consumes extended API response |
| Visual Verification Protocol | APPLIES | Frontend UI changes require Playwright screenshot verification |

## Project Structure

### Documentation (this feature)

```text
specs/001-mcp-server-ui-improvements/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── session-api.md   # Extended session creation API contract
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
# Backend (Python, repo root)
main.py                    # FastAPI app — session creation endpoint changes
mcp_servers.py             # MCP connection logic — add auth token forwarding, return per-server results
config/agents.yaml         # Add optional auth: true on mcp_servers entries

# Frontend (TypeScript/React)
frontend/src/
├── types/api.ts           # McpServerEntry type + new McpConnectionResult type
├── api/client.ts          # Pass auth token for authenticated MCP sessions
├── hooks/useChat.ts       # Handle MCP results from session response, emit toasts
├── hooks/useAuth.ts       # Expose getToken() for MCP auth header
├── pages/ChatPage.tsx     # Display MCP status, wire toast on session creation
├── pages/AgentBuilder.tsx # Add authenticated toggle + auth scope field to MCP server config
├── components/
│   └── McpStatusIndicator.tsx  # New component: checkmark/X per MCP server

# Tests
tests/test_api.py          # Test extended session creation response
```

**Structure Decision**: Existing two-tier web application structure. No new directories — changes are surgical additions to existing files plus one new component (`McpStatusIndicator.tsx`).

## Complexity Tracking

No constitution violations — no complexity justification needed.

## Post-Design Constitution Re-Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Read-Only Data Access | PASS | No SQL changes |
| II. Single-File Agent Definitions | PASS | `agents.yaml` gains optional `auth` field — no structural change |
| III. Security & Credential Hygiene | PASS | Token forwarded server-side only via `httpx.AsyncClient` default headers. Not logged. Azure Gov endpoints only. |
| IV. Evaluation-Driven Quality | PASS | No prompt/model changes |
| V. Simplicity & Minimalism | PASS | One new component, one new dataclass, extended response — minimal additions. `msal` dependency justified for OBO token exchange (no alternative for Azure AD OBO flow) |
| VI. Infrastructure as Code | PASS | No infra changes |
| VII. Two-Tier API-First Architecture | PASS | MCP connections remain server-side. Frontend consumes extended API response. |
| Visual Verification Protocol | APPLIES | Must verify McpStatusIndicator rendering, toast appearance, AgentBuilder auth toggle |
