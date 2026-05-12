"""
FastAPI application entry point.

Two-tier architecture: FastAPI backend serving REST API at /api/ and
React SPA static files from frontend/dist/.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from pydantic import BaseModel

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent_framework import Agent as RuntimeAgent
from agent_framework import AgentSession
from agent_framework._types import Content, Message as ChatMessage, UsageDetails

from auth import AuthenticatedUser, get_current_user
from eval_trace import EvalTraceLogger
from mcp_servers import parse_mcp_server_configs, connect_mcp_servers, cleanup_mcp_servers, get_search_service_config
from prompt_config import get_profile_display_name, load_agents_yaml
from session_orchestration import SessionContext, create_chat_session
from skills_manager import SkillManager
from streaming import (
    USAGE_INPUT_KEY,
    USAGE_OUTPUT_KEY,
    USAGE_TOTAL_KEY,
    create_usage,
    is_context_length_error,
    is_retryable_error,
    merge_usage,
    sse_event,
    stream_agent_response,
    usage_value,
)
from tools import UserProfileStore
from validators import (
    ALLOWED_IMAGE_MIMES,
    MAX_IMAGE_SIZE_BYTES,
    MAX_IMAGES_PER_MESSAGE,
    validate_uploaded_images,
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_MAX_USER_INPUT_CHARS = int(os.getenv("MAX_USER_INPUT_CHARS", "8000"))

# Default profile icon (used when no icon specified in agents.yaml)
_DEFAULT_PROFILE_ICON = "/favicon.png"

# ---------------------------------------------------------------------------
# In-memory session store
# ---------------------------------------------------------------------------

class SessionData:
    """Server-side state for an active chat session."""

    __slots__ = (
        "session_id", "user_id", "profile_id", "profile_name",
        "agent", "agent_session", "tools", "usage",
        "eval_trace_logger", "prompt_manifest", "prompt_logical_profile",
        "created_at", "context_usage", "user_profile_store",
        "mcp_tools", "used_profile_override", "override_updated_at",
    )

    def __init__(
        self,
        *,
        session_id: str,
        user_id: str,
        profile_id: str,
        profile_name: str,
        agent: RuntimeAgent,
        agent_session: AgentSession,
        tools: list[Any],
        eval_trace_logger: EvalTraceLogger,
        prompt_manifest: dict[str, str],
        prompt_logical_profile: str,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.profile_id = profile_id
        self.profile_name = profile_name
        self.agent = agent
        self.agent_session = agent_session
        self.tools = tools
        self.usage: Optional[UsageDetails] = create_usage()
        self.eval_trace_logger = eval_trace_logger
        self.prompt_manifest = prompt_manifest
        self.prompt_logical_profile = prompt_logical_profile
        self.created_at = datetime.now(timezone.utc)
        self.context_usage: dict[str, int] = {
            "request_count": 0,
            "sum_context_chars": 0,
            "max_context_chars": 0,
            "last_context_chars": 0,
        }
        self.user_profile_store = None
        self.mcp_tools: list[Any] = []
        self.used_profile_override = False
        self.override_updated_at: str | None = None


_sessions: dict[str, SessionData] = {}


def _check_profile_health(profile_id: str, profile_entry: dict) -> str | None:
    """Pre-flight check: return None if healthy, or a reason string if not.

    Attempts to instantiate the profile's declared tools and checks search
    context requirements for search-enabled profiles. No duplicate registry
    — the real tool constructors are the single source of truth.
    """
    tool_names = set(profile_entry.get("tools") or [])
    try:
        _build_tool_instances(tool_names, session_id="healthcheck")
    except HTTPException as e:
        return e.detail
    except Exception as e:
        return str(e)

    # Profiles with search_context: true also need AI Search config for context providers
    if profile_entry.get("search_context"):
        cfg = get_search_service_config()
        if not cfg.endpoint or not cfg.index_name:
            return "missing SEARCH_SERVICE_ENDPOINT and/or SEARCH_INDEX_NAME"

    return None


def _get_session(session_id: str) -> SessionData:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _build_tool_instances(
    tool_names: set[str],
    *,
    session_id: str,
    user_profile_data: dict[str, str] | None = None,
) -> tuple[list[Any], UserProfileStore | None]:
    """Instantiate the selected backend tools for a session or tool inventory call."""
    function_tools: list[Any] = []
    user_profile_store = None

    if {"get_user_profile", "save_user_profile"} & tool_names:
        user_profile_store = UserProfileStore(user_profile_data if isinstance(user_profile_data, dict) else None)
        if "get_user_profile" in tool_names:
            function_tools.append(user_profile_store.get_user_profile)
        if "save_user_profile" in tool_names:
            function_tools.append(user_profile_store.save_user_profile)

    return function_tools, user_profile_store


def _build_user_profile_context(user_profile_data: dict[str, str] | None) -> str:
    """Return a system-prompt snippet with user profile info, or empty string."""
    if not user_profile_data or not isinstance(user_profile_data, dict):
        return ""
    parts = []
    for key, val in user_profile_data.items():
        if val and str(val).strip():
            parts.append(f"- {key}: {val}")
    if not parts:
        return ""
    return "\n\n## Known User Profile\n" + "\n".join(parts)


def _get_skills_dir() -> Path:
    return Path(__file__).resolve().parent / "skills"


_session_context = SessionContext(
    sessions=_sessions,
    session_data_cls=SessionData,
    get_skills_dir=_get_skills_dir,
    build_tool_instances=_build_tool_instances,
    build_user_profile_context=_build_user_profile_context,
)


# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler — runs on startup and shutdown."""

    yield

    # Shutdown: clean up sessions
    session_count = len(_sessions)
    _sessions.clear()
    logger.info("Cleaned up %d sessions on shutdown", session_count)


# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Agent Framework API",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS — localhost-only for dev; same-origin in prod (no CORS needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8000",  # Self
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BuiltInProfileDefinitionResponse(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    systemPrompt: str
    tools: list[str]
    skills: list[str]
    mcpServers: list[dict[str, Any]]
    useSearchContext: bool
    starters: list[dict[str, str]]
    temperature: float | None = None
    agentsAsTools: list[dict[str, Any]] = []
    source: str = "builtin"


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

# T013 — Health endpoint
@app.get("/api/health")
async def health():
    return {"status": "healthy"}


# GET /api/auth/config — public endpoint for frontend OAuth config
@app.get("/api/auth/config")
async def auth_config():
    """Return OAuth configuration so the frontend can build MSAL config at runtime."""
    return {
        "authDisabled": os.getenv("AUTH_DISABLED", "").lower() in ("true", "1", "yes"),
        "tenantId": os.getenv("OAUTH_AZURE_GOV_AD_TENANT_ID", "") or os.getenv("AZURE_AD_TENANT_ID", ""),
        "clientId": os.getenv("OAUTH_AZURE_GOV_AD_CLIENT_ID", "") or os.getenv("AZURE_AD_CLIENT_ID", ""),
        "authority": os.getenv("AZURE_AD_AUTHORITY", "https://login.microsoftonline.us"),
        "classificationBanner": os.getenv("CLASSIFICATION_BANNER", "UNCLASSIFIED"),
        "appName": os.getenv("APP_NAME", "Web-Agents"),
        "appTagline": os.getenv("APP_TAGLINE", "AI Agent Framework"),
        "appLogo": os.getenv("APP_LOGO", "/Microsoft.png"),
    }


# GET /api/tools — available tools for custom agent builder
@app.get("/api/tools")
async def get_tools(user: AuthenticatedUser = Depends(get_current_user)):
    agents_doc = load_agents_yaml()
    profiles_data = agents_doc.get("profiles") or {}

    # Collect unique tool names across all profiles
    tool_names: set[str] = set()
    for entry in profiles_data.values():
        if isinstance(entry, dict):
            for t in (entry.get("tools") or []):
                if isinstance(t, str):
                    tool_names.add(t)

    desc_map: dict[str, str] = {}
    unavailable_tools: list[dict[str, str]] = []
    available_names: set[str] = set()
    for tool_name in sorted(tool_names):
        try:
            tool_objects, _ = _build_tool_instances({tool_name}, session_id="discovery")
        except HTTPException as e:
            unavailable_tools.append({"name": tool_name, "reason": e.detail})
            continue

        available_names.add(tool_name)

        for t in tool_objects:
            name = getattr(t, "name", None) or getattr(t, "__name__", None)
            doc = getattr(t, "description", None) or getattr(t, "__doc__", None) or ""
            if name:
                # Use first line of docstring as description
                desc_map[name] = doc.strip().split("\n")[0]

    tools = [
        {"name": name, "description": desc_map.get(name, "")}
        for name in sorted(available_names)
    ]

    # Check AI Search context provider availability
    cfg = get_search_service_config()
    search_available = bool(cfg.endpoint and cfg.index_name)
    search_reason: str | None = None
    if not search_available:
        missing = [v for v in ("SEARCH_SERVICE_ENDPOINT", "SEARCH_INDEX_NAME")
                   if not (os.environ.get(v) or "").strip()]
        search_reason = f"missing {' and '.join(missing)}" if missing else "missing SEARCH_SERVICE_ENDPOINT and/or SEARCH_INDEX_NAME"

    return {
        "tools": tools,
        "unavailable": unavailable_tools,
        "search_context_available": search_available,
        "search_context_reason": search_reason,
    }


# T015 — GET /api/profiles
@app.get("/api/profiles")
async def get_profiles(user: AuthenticatedUser = Depends(get_current_user)):
    agents_doc = load_agents_yaml()
    profiles_data = agents_doc.get("profiles") or {}

    profiles = []
    unavailable = []
    for profile_id, entry in profiles_data.items():
        if not isinstance(entry, dict):
            continue

        name = entry.get("name", profile_id)

        # Pre-flight health check
        reason = _check_profile_health(profile_id, entry)
        if reason is not None:
            logger.warning("Profile '%s' (%s) unavailable: %s", profile_id, name, reason)
            unavailable.append({"id": profile_id, "name": name, "reason": reason})
            continue

        # Load starters from agents.yaml, falling back to empty list
        raw_starters = entry.get("starters") or []
        starters = [
            {"label": s.get("label", ""), "message": s.get("message", "")}
            for s in raw_starters
            if isinstance(s, dict)
        ]

        profiles.append({
            "id": profile_id,
            "name": name,
            "description": entry.get("description", ""),
            "icon": entry.get("icon", _DEFAULT_PROFILE_ICON),
            "group": entry.get("group", "") if isinstance(entry.get("group", ""), str) else "",
            "starters": starters,
            "skills": [str(s) for s in (entry.get("skills") or []) if isinstance(s, str)],
            "mcp_server_count": len(entry.get("mcp_servers") or []),
        })

    return {"profiles": profiles, "unavailable": unavailable}


@app.get("/api/profiles/{profile_id}/definition", response_model=BuiltInProfileDefinitionResponse)
async def get_profile_definition(
    profile_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    return _get_builtin_profile_definition(profile_id)


# POST /api/mcp/test — test MCP server connections without creating a session
@app.post("/api/mcp/test")
async def test_mcp_connections(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    body = await request.json()
    raw_servers = body.get("mcp_servers", [])
    if not isinstance(raw_servers, list) or not raw_servers:
        raise HTTPException(status_code=400, detail="mcp_servers must be a non-empty list")

    for entry in raw_servers:
        if not isinstance(entry, dict):
            raise HTTPException(status_code=400, detail="Each mcp_servers entry must be an object")
        if entry.get("transport", "http") != "http":
            raise HTTPException(status_code=400, detail="Only http MCP servers can be tested")

    auth_header = request.headers.get("authorization", "")
    user_token = auth_header.removeprefix("Bearer ").strip() if auth_header.lower().startswith("bearer ") else None

    configs = parse_mcp_server_configs({"mcp_servers": raw_servers})
    _tools, results = await connect_mcp_servers(configs, user_token=user_token)

    # Clean up the test connections immediately
    await cleanup_mcp_servers(_tools)

    return {
        "results": [
            {"name": r.name, "transport": r.transport, "status": r.status, "tool_count": r.tool_count, "error": r.error}
            for r in results
        ],
    }


# GET /api/skills — list available skills for custom agent builder
@app.get("/api/skills")
async def get_skills(user: AuthenticatedUser = Depends(get_current_user)):
    return {"skills": SkillManager(_get_skills_dir()).list_summaries()}


# ---------------------------------------------------------------------------
# Skills CRUD — Pydantic models
# ---------------------------------------------------------------------------

class SkillCreateRequest(BaseModel):
    name: str
    description: str
    content: str


class SkillUpdateRequest(BaseModel):
    description: str
    content: str


class SkillResponse(BaseModel):
    name: str
    description: str
    content: str


class SkillGenerateRequest(BaseModel):
    name: str | None = None
    description: str


class SkillGenerateResponse(BaseModel):
    content: str


def _starter_definitions(raw_starters: Any) -> list[dict[str, str]]:
    return [
        {"label": str(s.get("label", "")), "message": str(s.get("message", ""))}
        for s in (raw_starters or [])
        if isinstance(s, dict)
    ]


def _safe_mcp_server_definitions(raw_servers: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_servers, list):
        return []

    safe_servers: list[dict[str, Any]] = []
    for entry in raw_servers:
        if not isinstance(entry, dict):
            continue

        name = entry.get("name")
        transport = entry.get("transport", "http")
        if not name or transport not in ("http", "stdio"):
            continue

        safe_entry: dict[str, Any] = {
            "name": str(name),
            "transport": str(transport),
        }
        for source_key, target_key in (
            ("url", "url"),
            ("description", "description"),
            ("auth", "authenticated"),
            ("authenticated", "authenticated"),
            ("auth_scope", "authScope"),
            ("authScope", "authScope"),
        ):
            value = entry.get(source_key)
            if value is not None:
                safe_entry[target_key] = value

        safe_servers.append(safe_entry)

    return safe_servers


def _serialize_agents_as_tools(raw: Any) -> list[dict[str, Any]]:
    """Convert YAML-shaped agents_as_tools entries to camelCase wire format.

    Always returns a list (empty when no entries) so the response field is
    consistently present.\
    """
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        ref = entry.get("agent_ref") or entry.get("agentRef")
        if not isinstance(ref, dict):
            continue
        kind = ref.get("kind")
        if kind == "builtin":
            profile_id = ref.get("profile_id") or ref.get("profileId")
            if not profile_id:
                continue
            out.append({"agentRef": {"kind": "builtin", "profileId": str(profile_id)}})
        elif kind == "custom":
            custom_id = ref.get("custom_agent_id") or ref.get("customAgentId")
            definition = ref.get("definition")
            if not custom_id:
                continue
            wire_ref: dict[str, Any] = {"kind": "custom", "customAgentId": str(custom_id)}
            if isinstance(definition, dict):
                wire_ref["definition"] = definition
            out.append({"agentRef": wire_ref})
    return out


def _get_builtin_profile_definition(profile_id: str) -> BuiltInProfileDefinitionResponse:
    agents_doc = load_agents_yaml()
    profiles_data = agents_doc.get("profiles") or {}
    entry = profiles_data.get(profile_id)
    if not isinstance(entry, dict):
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_id}")

    raw_temperature = entry.get("temperature")
    temperature: float | None = None
    if raw_temperature is not None:
        try:
            temperature = float(raw_temperature)
        except (TypeError, ValueError):
            temperature = None

    return BuiltInProfileDefinitionResponse(
        id=profile_id,
        name=str(entry.get("name", profile_id)),
        description=str(entry.get("description", "")),
        icon=str(entry.get("icon", _DEFAULT_PROFILE_ICON)),
        systemPrompt=str(entry.get("system_prompt", "")).strip(),
        tools=[str(t) for t in (entry.get("tools") or []) if isinstance(t, str)],
        skills=[str(s) for s in (entry.get("skills") or []) if isinstance(s, str)],
        mcpServers=_safe_mcp_server_definitions(entry.get("mcp_servers")),
        useSearchContext=bool(entry.get("search_context", False)),
        starters=_starter_definitions(entry.get("starters")),
        temperature=temperature,
        agentsAsTools=_serialize_agents_as_tools(entry.get("agents_as_tools")),
    )


# POST /api/skills/generate — generate skill markdown content from a description using the LLM
@app.post("/api/skills/generate", response_model=SkillGenerateResponse)
async def generate_skill_content(
    body: SkillGenerateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    description = (body.description or "").strip()
    if not description:
        raise HTTPException(status_code=422, detail="description is required")
    if len(description) > 2048:
        raise HTTPException(status_code=422, detail="description must be ≤ 2048 characters")
    skill_name = (body.name or "new-skill").strip() or "new-skill"

    from agent_framework.openai import OpenAIChatClient

    system_prompt = (
        "You are an expert at writing concise, well-structured Markdown skill "
        "instructions for AI agents. Given a short skill description, produce "
        "the BODY of a SKILL.md file (Markdown only, no YAML frontmatter, no "
        "code fences wrapping the whole document). Use clear headings, bullet "
        "points, and short examples where helpful. Be practical and "
        "actionable. Do not include any preamble or commentary — output the "
        "Markdown body directly."
    )
    user_prompt = (
        f"Skill name: {skill_name}\n"
        f"Skill description: {description}\n\n"
        "Write the SKILL.md body now."
    )

    try:
        client = OpenAIChatClient()
        response = await client.get_response(
            messages=[
                ChatMessage(role="system", contents=[Content(type="text", text=system_prompt)]),
                ChatMessage(role="user", contents=[Content(type="text", text=user_prompt)]),
            ],
        )
    except Exception as exc:
        logger.exception("Skill content generation failed")
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {exc}") from exc

    text = (getattr(response, "text", "") or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="LLM returned empty content")

    # Strip an outer ```markdown ... ``` fence if the model wrapped its output.
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1 and text.rstrip().endswith("```"):
            text = text[first_nl + 1 : text.rstrip().rfind("```")].strip()

    if len(text) > 65536:
        text = text[:65536]

    return SkillGenerateResponse(content=text)


# GET /api/skills/{name} — fetch a single skill by name
@app.get("/api/skills/{name}", response_model=SkillResponse)
async def get_skill(name: str, user: AuthenticatedUser = Depends(get_current_user)):
    return SkillResponse(**SkillManager(_get_skills_dir()).get(name))


# POST /api/skills — create a new skill
@app.post("/api/skills", response_model=SkillResponse, status_code=201)
async def create_skill(body: SkillCreateRequest, user: AuthenticatedUser = Depends(get_current_user)):
    return SkillResponse(**SkillManager(_get_skills_dir()).create(body.name, body.description, body.content))


# PUT /api/skills/{name} — update an existing skill
@app.put("/api/skills/{name}", response_model=SkillResponse)
async def update_skill(name: str, body: SkillUpdateRequest, user: AuthenticatedUser = Depends(get_current_user)):
    return SkillResponse(**SkillManager(_get_skills_dir()).update(name, body.description, body.content))


# DELETE /api/skills/{name} — remove a skill directory
@app.delete("/api/skills/{name}", status_code=204)
async def delete_skill(name: str, user: AuthenticatedUser = Depends(get_current_user)):
    SkillManager(_get_skills_dir()).delete(name)
    return Response(status_code=204)


# GET /api/sessions/{session_id}/history — export serialized session state
@app.get("/api/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    session_data = _get_session(session_id)
    return {
        "session_id": session_data.session_id,
        "profile_id": session_data.profile_id,
        "profile_name": session_data.profile_name,
        "session_data": session_data.agent_session.to_dict(),
        "used_profile_override": session_data.used_profile_override,
        "override_updated_at": session_data.override_updated_at,
    }


# T016 — POST /api/sessions
@app.post("/api/sessions", status_code=201)
async def create_session(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    body = await request.json()
    return await create_chat_session(
        _session_context,
        body=body,
        auth_header=request.headers.get("authorization", ""),
        user=user,
        logger=logger,
    )

# T017 + T029 — POST /api/sessions/{session_id}/messages (text + multipart)
@app.post("/api/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    session_data = _get_session(session_id)

    content_type = request.headers.get("content-type", "")
    text_content = ""
    image_files: list[UploadFile] = []
    image_data_list: list[bytes] = []

    if "multipart/form-data" in content_type:
        form = await request.form()
        text_content = str(form.get("content", ""))
        for item in form.getlist("images"):
            if hasattr(item, "read"):
                data = await item.read()
                image_files.append(item)
                image_data_list.append(data)
    else:
        body = await request.json()
        text_content = body.get("content", "")

    # Validate input length (T020)
    if len(text_content) > DEFAULT_MAX_USER_INPUT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Input exceeds maximum length of {DEFAULT_MAX_USER_INPUT_CHARS:,} characters.",
        )

    # Validate images if present (T029)
    if image_files:
        error = validate_uploaded_images(image_files, image_data_list)
        if error:
            raise HTTPException(status_code=400, detail=error)

    # Build content objects
    contents: list[Content] = [Content.from_text(text_content)]
    for f, data in zip(image_files, image_data_list):
        mime = f.content_type or "image/jpeg"
        contents.append(Content.from_data(data=data, media_type=mime))

    # Update context usage tracking
    current_context_chars = len(text_content)
    ctx = session_data.context_usage
    ctx["request_count"] += 1
    ctx["sum_context_chars"] += current_context_chars
    ctx["max_context_chars"] = max(ctx["max_context_chars"], current_context_chars)
    ctx["last_context_chars"] = current_context_chars

    # Stream the response
    async def generate() -> AsyncGenerator[str, None]:
        try:
            async for event in stream_agent_response(
                session_data.agent, contents, session_data.agent_session,
            ):
                yield event
        except Exception as e:
            # T020 — error handling
            if is_retryable_error(e):
                logger.error("Rate limit error: %s", e)
                yield sse_event("error", {
                    "message": "The AI service is currently experiencing high demand. Please try again in a moment.",
                    "retry_after": 30,
                })
            elif is_context_length_error(e):
                logger.error("Context length exceeded: %s", e)
                yield sse_event("error", {
                    "message": "The request exceeded model context limits. Please shorten your prompt or start a new chat.",
                    "retry_after": None,
                })
            elif image_files and not is_context_length_error(e) and not is_retryable_error(e):
                logger.error("Error processing image message: %s", e, exc_info=True)
                yield sse_event("error", {
                    "message": "One or more images could not be processed. Please try again or use a different image.",
                    "retry_after": None,
                })
            else:
                logger.error("Error processing message: %s", e, exc_info=True)
                yield sse_event("error", {
                    "message": f"An error occurred while processing your request: {str(e)}",
                    "retry_after": None,
                })
            yield sse_event("done", {})
            return

        # After successful streaming, update session usage and log trace (T019)
        result = getattr(stream_agent_response, "_last_result", None)
        if result:
            request_usage = result.get("usage")
            if request_usage:
                session_data.usage = merge_usage(session_data.usage, request_usage)
                logger.info(
                    "Request token usage - Input: %s, Output: %s, Total: %s",
                    usage_value(request_usage, USAGE_INPUT_KEY),
                    usage_value(request_usage, USAGE_OUTPUT_KEY),
                    usage_value(request_usage, USAGE_TOTAL_KEY),
                )

            # Eval trace logging
            if session_data.eval_trace_logger.enabled:
                session_data.eval_trace_logger.log({
                    "session_id": session_id,
                    "chat_profile": session_data.profile_id,
                    "prompt_logical_profile": session_data.prompt_logical_profile,
                    "prompt_manifest": session_data.prompt_manifest,
                    "input": text_content,
                    "output": result.get("text", ""),
                    "tool_events": result.get("tool_events", []),
                    "tool_names_available": [
                        getattr(t, "name", str(t)) for t in session_data.tools
                    ],
                    "usage": {
                        USAGE_INPUT_KEY: usage_value(request_usage, USAGE_INPUT_KEY),
                        USAGE_OUTPUT_KEY: usage_value(request_usage, USAGE_OUTPUT_KEY),
                        USAGE_TOTAL_KEY: usage_value(request_usage, USAGE_TOTAL_KEY),
                    } if request_usage else {},
                    "context_usage": session_data.context_usage,
                })

    return StreamingResponse(generate(), media_type="text/event-stream")


# T018 — DELETE /api/sessions/{session_id}
@app.delete("/api/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    session_data = _sessions.pop(session_id, None)
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session not found or already ended")

    # Clean up MCP server connections
    if session_data.mcp_tools:
        await cleanup_mcp_servers(session_data.mcp_tools)

    # Log final token usage
    if session_data.usage:
        logger.info(
            "Session %s ended — Token usage - Input: %s, Output: %s, Total: %s",
            session_id,
            usage_value(session_data.usage, USAGE_INPUT_KEY),
            usage_value(session_data.usage, USAGE_OUTPUT_KEY),
            usage_value(session_data.usage, USAGE_TOTAL_KEY),
        )

    return None


# ---------------------------------------------------------------------------
# T012 — Static file serving + SPA catch-all
# ---------------------------------------------------------------------------

_FRONTEND_DIR = Path(__file__).resolve().parent / "frontend" / "dist"


def _mount_static_files(application: FastAPI) -> None:
    """Mount frontend static files if the dist directory exists."""
    if not _FRONTEND_DIR.is_dir():
        logger.warning("frontend/dist/ not found — static file serving disabled. Run 'cd frontend && npm run build'")
        return

    assets_dir = _FRONTEND_DIR / "assets"
    if assets_dir.is_dir():
        application.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    application.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR)), name="static")

    @application.get("/{full_path:path}", include_in_schema=False)
    async def spa_catch_all(full_path: str):
        """Serve index.html for all non-API, non-static routes (SPA client-side routing)."""
        # Don't intercept API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        # Try to serve the exact file first
        file_path = _FRONTEND_DIR / full_path
        if full_path and file_path.is_file() and _FRONTEND_DIR in file_path.resolve().parents:
            return FileResponse(str(file_path))

        # Fall back to index.html for SPA routing
        index_file = _FRONTEND_DIR / "index.html"
        if index_file.is_file():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

        raise HTTPException(status_code=404, detail="Frontend not built. Run: cd frontend && npm run build")


_mount_static_files(app)
