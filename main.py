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
from cosmos_memory import close_cosmos, cosmos_config_summary, get_autonomous_directive_repository, get_autonomous_run_repository, get_conversation_repository, get_history_provider, require_cosmos_configured
from autonomous import (
    Directive,
    directive_to_wire,
    get_autonomous_config,
    run_autonomous_cycle,
    seed_autonomous_directives,
    validate_directive_id,
    validate_notify_webhook,
    validate_profile_id,
    validate_schedule,
)
from autonomous_scheduler import AutonomousScheduler, scheduler_enabled
from user_data import (
    get_agent_customizations_repository,
    get_custom_agents_repository,
)
from skills_manager import SkillManager, seed_skills
from streaming import (
    USAGE_INPUT_KEY,
    USAGE_OUTPUT_KEY,
    USAGE_TOTAL_KEY,
    create_usage,
    is_context_length_error,
    is_retryable_error,
    merge_usage,
    messages_to_wire,
    sse_event,
    stream_agent_response,
    usage_value,
    with_user_time,
)
from tools import build_user_profile_tools
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
        "created_at", "context_usage",
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
    user_id: str | None = None,
) -> list[Any]:
    """Instantiate the selected backend tools for a session or tool inventory call."""
    function_tools: list[Any] = []

    profile_tool_names = {"get_user_profile", "save_user_profile"} & tool_names
    if profile_tool_names:
        profile_tools = build_user_profile_tools(user_id or "")
        for name in ("get_user_profile", "save_user_profile"):
            if name in profile_tool_names:
                function_tools.append(profile_tools[name])

    return function_tools


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
    build_tool_instances=_build_tool_instances,
    build_user_profile_context=_build_user_profile_context,
)


# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler — runs on startup and shutdown."""
    # Fail fast: Cosmos is required (emulator locally, real account when deployed).
    # There is no non-durable in-memory fallback.
    require_cosmos_configured()
    cfg = cosmos_config_summary()
    logger.info(
        "Cosmos memory enabled — endpoint=%s database=%s messages=%s conversations=%s auth=%s",
        cfg["endpoint"],
        cfg["database"],
        cfg["messages_container"],
        cfg["conversations_container"],
        cfg["auth"],
    )

    # Autonomous mode startup summary (no secrets). Seed the durable directive store
    # from the YAML defaults (idempotent) so the runtime config is Cosmos-backed.
    try:
        seeded = await seed_autonomous_directives()
        autonomous_config = await get_autonomous_config()
        logger.info(
            "Autonomous mode — enabled=%s directives=%d (seeded %d) system_identity=%s",
            autonomous_config.enabled,
            len(autonomous_config.directives),
            seeded,
            autonomous_config.system_user_id,
        )
    except Exception:
        logger.warning("Failed to load/seed autonomous config at startup", exc_info=True)

    # Seed the durable skill store from the filesystem defaults (idempotent) so the
    # skill catalog is Cosmos-backed and survives restarts/redeploys.
    try:
        skills_seeded = await seed_skills(_get_skills_dir())
        logger.info("Skills — seeded %d default skill(s) from ./skills into Cosmos", skills_seeded)
    except Exception:
        logger.warning("Failed to seed skills at startup", exc_info=True)

    # In-process autonomous scheduler — gated, never blocks startup.
    autonomous_scheduler = None
    if scheduler_enabled():
        try:
            autonomous_scheduler = AutonomousScheduler(_session_context, logger=logger)
            await autonomous_scheduler.start()
            logger.info("Autonomous scheduler started (in-process, Cosmos lease)")
        except Exception:
            logger.error("Failed to start autonomous scheduler", exc_info=True)
            autonomous_scheduler = None

    yield

    # Shutdown: stop the scheduler, then clean up sessions and Cosmos resources
    if autonomous_scheduler is not None:
        try:
            await autonomous_scheduler.stop()
        except Exception:
            logger.debug("Error stopping autonomous scheduler", exc_info=True)
    session_count = len(_sessions)
    _sessions.clear()
    await close_cosmos()
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
            tool_objects = _build_tool_instances({tool_name}, session_id="discovery")
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
    return {"skills": await SkillManager().list_summaries()}


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
    return SkillResponse(**await SkillManager().get(name))


# POST /api/skills — create a new skill
@app.post("/api/skills", response_model=SkillResponse, status_code=201)
async def create_skill(body: SkillCreateRequest, user: AuthenticatedUser = Depends(get_current_user)):
    return SkillResponse(**await SkillManager().create(body.name, body.description, body.content))


# PUT /api/skills/{name} — update an existing skill
@app.put("/api/skills/{name}", response_model=SkillResponse)
async def update_skill(name: str, body: SkillUpdateRequest, user: AuthenticatedUser = Depends(get_current_user)):
    return SkillResponse(**await SkillManager().update(name, body.description, body.content))


# DELETE /api/skills/{name} — remove a skill
@app.delete("/api/skills/{name}", status_code=204)
async def delete_skill(name: str, user: AuthenticatedUser = Depends(get_current_user)):
    await SkillManager().delete(name)
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
    client_time = ""
    image_files: list[UploadFile] = []
    image_data_list: list[bytes] = []

    if "multipart/form-data" in content_type:
        form = await request.form()
        text_content = str(form.get("content", ""))
        client_time = str(form.get("client_time", ""))
        for item in form.getlist("images"):
            if hasattr(item, "read"):
                data = await item.read()
                image_files.append(item)
                image_data_list.append(data)
    else:
        body = await request.json()
        text_content = body.get("content", "")
        client_time = str(body.get("client_time", "") or "")

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

    # Build content objects. The user's local date/time is prepended to the text the
    # model sees (and to the persisted session history) but is stripped from the wire
    # form by messages_to_wire, so it stays invisible in the UI.
    when = client_time.strip() or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    model_text = with_user_time(text_content, when) if text_content.strip() else text_content
    contents: list[Content] = [Content.from_text(model_text)]
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
        # Persist the conversation index (title on first turn + last activity) BEFORE
        # streaming, so the sidebar's refresh on the "done" event reliably reflects the
        # title. Doing it after streaming races the client's refresh, so the title would
        # only appear after a manual page reload.
        try:
            conversations = get_conversation_repository()
            candidate_title = " ".join((text_content or "").split())[:60]
            await conversations.touch(session_data.user_id, session_id, title=candidate_title or None)
        except Exception:
            logger.warning("Failed to update conversation index for %s", session_id, exc_info=True)

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
# Conversations — durable per-user chat history (Cosmos-backed)
# ---------------------------------------------------------------------------

# GET /api/conversations — list the authenticated user's conversations (US2)
@app.get("/api/conversations")
async def list_conversations(
    user: AuthenticatedUser = Depends(get_current_user),
    limit: int = 50,
    cursor: str | None = None,
):
    repo = get_conversation_repository()
    bounded = max(1, min(int(limit or 50), 200))
    try:
        records, next_cursor = await repo.list_for_user(user.user_id, limit=bounded, cursor=cursor)
    except Exception as e:
        logger.error("Failed to list conversations: %s", e)
        raise HTTPException(status_code=503, detail="Conversation store is temporarily unavailable. Please try again.")
    return {"conversations": [r.to_wire() for r in records], "nextCursor": next_cursor}


# GET /api/conversations/{id}/messages — messages for a resumed conversation (US3)
@app.get("/api/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    repo = get_conversation_repository()
    try:
        owned = await repo.get_owned(user.user_id, conversation_id)
    except Exception as e:
        logger.error("Conversation lookup failed: %s", e)
        raise HTTPException(status_code=503, detail="Conversation store is temporarily unavailable. Please try again.")
    if owned is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    history_provider = get_history_provider()
    try:
        stored = await history_provider.get_messages(conversation_id)
    except Exception as e:
        logger.error("Failed to load messages for %s: %s", conversation_id, e)
        raise HTTPException(status_code=503, detail="Conversation store is temporarily unavailable. Please try again.")
    return {
        "id": owned.id,
        "profileId": owned.profile_id,
        "profileName": owned.profile_name,
        "messages": messages_to_wire(stored or []),
    }


# DELETE /api/conversations/{id} — delete index entry + stored messages (US5)
@app.delete("/api/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    repo = get_conversation_repository()
    try:
        owned = await repo.get_owned(user.user_id, conversation_id)
    except Exception as e:
        logger.error("Conversation lookup failed: %s", e)
        raise HTTPException(status_code=503, detail="Conversation store is temporarily unavailable. Please try again.")
    if owned is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    history_provider = get_history_provider()
    try:
        clear = getattr(history_provider, "clear", None)
        if clear is not None:
            await clear(conversation_id)
        await repo.delete(user.user_id, conversation_id)
    except Exception as e:
        logger.error("Failed to delete conversation %s: %s", conversation_id, e)
        raise HTTPException(status_code=503, detail="Conversation store is temporarily unavailable. Please try again.")
    # Drop any in-memory runtime session bound to this conversation
    _sessions.pop(conversation_id, None)
    return None


# ---------------------------------------------------------------------------
# Autonomous mode — the Duty Officer (in-process; user-authenticated API)
# ---------------------------------------------------------------------------

class AutonomousRunNowRequest(BaseModel):
    directive_id: str | None = None


@app.post("/api/autonomous/run-now")
async def autonomous_run_now(
    body: AutonomousRunNowRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Run one autonomous cycle on demand. The ONLY HTTP trigger; user-authenticated.

    Scheduled cycles fire in-process (recorded as ``trigger: "timer"``); this is the
    sole external entry point and selects only a pre-configured directive.
    """
    config = await get_autonomous_config()
    if not config.enabled:
        raise HTTPException(status_code=409, detail="Autonomous mode is disabled")

    if body.directive_id:
        directive = config.find_directive(body.directive_id)
        if directive is None or not directive.enabled:
            raise HTTPException(status_code=404, detail="Directive not found or not enabled")
    else:
        enabled = config.enabled_directives()
        if not enabled:
            raise HTTPException(status_code=409, detail="No enabled directives are configured")
        directive = enabled[0]

    record = await run_autonomous_cycle(
        _session_context, directive, trigger="manual", logger=logger, config=config
    )
    return record.to_wire()


@app.get("/api/autonomous/runs")
async def list_autonomous_runs(
    user: AuthenticatedUser = Depends(get_current_user),
    limit: int = 50,
    directive_id: str | None = None,
):
    """List autonomous run history, most-recent-first (shared across all users)."""
    bounded = max(1, min(int(limit or 50), 200))
    try:
        records = await get_autonomous_run_repository().list_runs(
            limit=bounded, directive_id=directive_id
        )
    except Exception as e:
        logger.error("Failed to list autonomous runs: %s", e)
        raise HTTPException(status_code=503, detail="Autonomous run store is temporarily unavailable. Please try again.")
    return {"runs": [r.to_wire() for r in records], "count": len(records)}


@app.get("/api/autonomous/directives")
async def list_autonomous_directives(
    user: AuthenticatedUser = Depends(get_current_user),
):
    """List the configured directives (no secrets) for all authenticated users."""
    config = await get_autonomous_config()
    return {
        "enabled": config.enabled,
        "schedulerEnabled": scheduler_enabled(),
        "systemUserId": config.system_user_id,
        "directives": [directive_to_wire(d) for d in config.directives],
    }


class DirectiveCreateRequest(BaseModel):
    id: str
    profile_id: str
    instruction: str
    schedule: str | None = None
    enabled: bool = True
    notify_webhook: str | None = None


class DirectiveUpdateRequest(BaseModel):
    profile_id: str | None = None
    instruction: str | None = None
    schedule: str | None = None
    enabled: bool | None = None
    notify_webhook: str | None = None


def _validated_schedule(raw: str | None) -> str | None:
    """Normalize + validate an optional schedule; '' or None clears it."""
    schedule = (raw or "").strip() or None
    if schedule is not None:
        try:
            validate_schedule(schedule)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return schedule


def _validated_instruction(raw: str) -> str:
    instruction = (raw or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction is required")
    if len(instruction) > DEFAULT_MAX_USER_INPUT_CHARS:
        raise HTTPException(status_code=400, detail="instruction is too long")
    return instruction


def _validated_notify(raw: str | None) -> dict[str, str] | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return validate_notify_webhook(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/autonomous/directives", status_code=201)
async def create_autonomous_directive(
    body: DirectiveCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a new automation (directive). Authenticated users only."""
    repo = get_autonomous_directive_repository()
    try:
        directive_id = validate_directive_id(body.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        validate_profile_id(body.profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if await repo.get(directive_id) is not None:
        raise HTTPException(status_code=409, detail=f"Directive '{directive_id}' already exists")

    now = datetime.now(timezone.utc).isoformat()
    directive = Directive(
        id=directive_id,
        profile_id=body.profile_id,
        instruction=_validated_instruction(body.instruction),
        schedule=_validated_schedule(body.schedule),
        enabled=bool(body.enabled),
        notify=_validated_notify(body.notify_webhook),
        created_at=now,
        updated_at=now,
    )
    await repo.upsert(directive.to_doc())
    logger.info("Autonomous directive created: %s", directive_id)
    return directive_to_wire(directive)


@app.patch("/api/autonomous/directives/{directive_id}")
async def update_autonomous_directive(
    directive_id: str,
    body: DirectiveUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Update an automation: enable/disable, schedule, instruction, profile, or notify."""
    repo = get_autonomous_directive_repository()
    existing = await repo.get(directive_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Directive not found")
    current = Directive.from_doc(existing)
    fields = body.model_dump(exclude_unset=True)

    profile_id = current.profile_id
    if "profile_id" in fields and fields["profile_id"] is not None:
        try:
            validate_profile_id(fields["profile_id"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        profile_id = fields["profile_id"]

    instruction = current.instruction
    if "instruction" in fields and fields["instruction"] is not None:
        instruction = _validated_instruction(fields["instruction"])

    schedule = current.schedule
    if "schedule" in fields:
        schedule = _validated_schedule(fields["schedule"])

    enabled = current.enabled
    if "enabled" in fields and fields["enabled"] is not None:
        enabled = bool(fields["enabled"])

    notify = current.notify
    if "notify_webhook" in fields:
        notify = _validated_notify(fields["notify_webhook"])

    now = datetime.now(timezone.utc).isoformat()
    updated = Directive(
        id=current.id,
        profile_id=profile_id,
        instruction=instruction,
        schedule=schedule,
        enabled=enabled,
        notify=notify,
        created_at=current.created_at or now,
        updated_at=now,
    )
    await repo.upsert(updated.to_doc())
    logger.info("Autonomous directive updated: %s (enabled=%s)", directive_id, enabled)
    return directive_to_wire(updated)


@app.delete("/api/autonomous/directives/{directive_id}", status_code=204)
async def delete_autonomous_directive(
    directive_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Delete an automation. (A YAML-default directive reappears on next startup.)"""
    deleted = await get_autonomous_directive_repository().delete(directive_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Directive not found")
    logger.info("Autonomous directive deleted: %s", directive_id)
    return None


# ---------------------------------------------------------------------------
# Custom agents, agent customizations, user profile (durable per-user, Cosmos)
# ---------------------------------------------------------------------------

_USER_DATA_UNAVAILABLE = "User data store is temporarily unavailable. Please try again."


@app.get("/api/custom-agents")
async def list_custom_agents(user: AuthenticatedUser = Depends(get_current_user)):
    try:
        agents = await get_custom_agents_repository().list_for_user(user.user_id)
    except Exception as e:
        logger.error("Failed to list custom agents: %s", e)
        raise HTTPException(status_code=503, detail=_USER_DATA_UNAVAILABLE)
    return {"agents": agents}


@app.put("/api/custom-agents/{agent_id}")
async def save_custom_agent(agent_id: str, request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")
    try:
        saved = await get_custom_agents_repository().upsert(user.user_id, agent_id, body)
    except Exception as e:
        logger.error("Failed to save custom agent %s: %s", agent_id, e)
        raise HTTPException(status_code=503, detail=_USER_DATA_UNAVAILABLE)
    return saved


@app.delete("/api/custom-agents/{agent_id}", status_code=204)
async def delete_custom_agent(agent_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    try:
        await get_custom_agents_repository().delete(user.user_id, agent_id)
    except Exception as e:
        logger.error("Failed to delete custom agent %s: %s", agent_id, e)
        raise HTTPException(status_code=503, detail=_USER_DATA_UNAVAILABLE)
    return None


@app.get("/api/agent-customizations")
async def list_agent_customizations(user: AuthenticatedUser = Depends(get_current_user)):
    try:
        overrides = await get_agent_customizations_repository().list_for_user(user.user_id)
    except Exception as e:
        logger.error("Failed to list agent customizations: %s", e)
        raise HTTPException(status_code=503, detail=_USER_DATA_UNAVAILABLE)
    return {"overrides": overrides}


@app.put("/api/agent-customizations/{base_profile_id}")
async def save_agent_customization(base_profile_id: str, request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")
    try:
        saved = await get_agent_customizations_repository().upsert(user.user_id, base_profile_id, body)
    except Exception as e:
        logger.error("Failed to save agent customization %s: %s", base_profile_id, e)
        raise HTTPException(status_code=503, detail=_USER_DATA_UNAVAILABLE)
    return saved


@app.delete("/api/agent-customizations/{base_profile_id}", status_code=204)
async def delete_agent_customization(base_profile_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    try:
        await get_agent_customizations_repository().delete(user.user_id, base_profile_id)
    except Exception as e:
        logger.error("Failed to delete agent customization %s: %s", base_profile_id, e)
        raise HTTPException(status_code=503, detail=_USER_DATA_UNAVAILABLE)
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
