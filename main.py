"""
FastAPI application entry point.

Two-tier architecture: FastAPI backend serving REST API at /api/ and
React SPA static files from frontend/dist/.
"""

import json
import logging
import os
import re
import shutil
import uuid
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

from agent_factory import create_chat_runtime
from auth import AuthenticatedUser, get_current_user
from eval_trace import EvalTraceLogger
from mcp_servers import parse_mcp_server_configs, connect_mcp_servers, cleanup_mcp_servers, get_search_service_config
from prompt_config import get_profile_display_name, load_agents_yaml, resolve_logical_profile
from tools import UserProfileStore

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_MAX_USER_INPUT_CHARS = int(os.getenv("MAX_USER_INPUT_CHARS", "8000"))

USAGE_INPUT_KEY = "input_token_count"
USAGE_OUTPUT_KEY = "output_token_count"
USAGE_TOTAL_KEY = "total_token_count"

ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

_MAGIC_BYTES: dict[str, list[bytes]] = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/gif": [b"GIF87a", b"GIF89a"],
    "image/webp": [],  # handled specially: RIFF....WEBP
}

MAX_IMAGE_SIZE_BYTES = 400 * 1024 * 1024  # 400 MB
MAX_IMAGES_PER_MESSAGE = 5

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
        self.usage: Optional[UsageDetails] = _create_usage()
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


# ---------------------------------------------------------------------------
# Usage helpers (ported from original main.py)
# ---------------------------------------------------------------------------

def _create_usage(
    input_token_count: Optional[int] = None,
    output_token_count: Optional[int] = None,
    total_token_count: Optional[int] = None,
) -> UsageDetails:
    return UsageDetails(
        input_token_count=input_token_count,
        output_token_count=output_token_count,
        total_token_count=total_token_count,
    )


def _usage_value(usage: Optional[UsageDetails], key: str) -> int:
    if not usage:
        return 0
    if isinstance(usage, dict):
        return int(usage.get(key) or 0)
    return int(getattr(usage, key, 0) or 0)


def _merge_usage(
    current: Optional[UsageDetails],
    incoming: Optional[UsageDetails],
) -> Optional[UsageDetails]:
    if not incoming:
        return current
    if not current:
        return incoming
    return _create_usage(
        input_token_count=_usage_value(current, USAGE_INPUT_KEY) + _usage_value(incoming, USAGE_INPUT_KEY),
        output_token_count=_usage_value(current, USAGE_OUTPUT_KEY) + _usage_value(incoming, USAGE_OUTPUT_KEY),
        total_token_count=_usage_value(current, USAGE_TOTAL_KEY) + _usage_value(incoming, USAGE_TOTAL_KEY),
    )


def _extract_usage_from_payload(payload: dict) -> Optional[UsageDetails]:
    usage_data = payload.get("usage") or {}
    if not usage_data:
        return None
    return _create_usage(
        input_token_count=usage_data.get(USAGE_INPUT_KEY),
        output_token_count=usage_data.get(USAGE_OUTPUT_KEY),
        total_token_count=usage_data.get(USAGE_TOTAL_KEY),
    )


# ---------------------------------------------------------------------------
# Image validation helpers (ported from original main.py)
# ---------------------------------------------------------------------------

def _validate_image_magic_bytes(data: bytes, claimed_mime: str) -> bool:
    if not data:
        return False
    if claimed_mime == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    signatures = _MAGIC_BYTES.get(claimed_mime, [])
    return any(data[: len(sig)] == sig for sig in signatures)


def _validate_uploaded_images(
    files: list[UploadFile], file_data: list[bytes]
) -> Optional[str]:
    """Validate uploaded image files. Returns error message or None."""
    if len(files) > MAX_IMAGES_PER_MESSAGE:
        return f"Maximum of {MAX_IMAGES_PER_MESSAGE} images per message. Please reduce the number of images."

    for f, data in zip(files, file_data):
        mime = f.content_type or ""
        name = f.filename or "uploaded file"

        if mime not in ALLOWED_IMAGE_MIMES:
            return (
                f"Only image files are accepted (JPEG, PNG, GIF, WebP). "
                f"'{name}' is not a supported image type."
            )

        if len(data) > MAX_IMAGE_SIZE_BYTES:
            return f"'{name}' exceeds the maximum file size of 400 MB."

        if not _validate_image_magic_bytes(data, mime):
            return f"'{name}' could not be processed. The file may be corrupt or unreadable."

    return None


# ---------------------------------------------------------------------------
# Error classification helpers (ported from original main.py)
# ---------------------------------------------------------------------------

def _is_retryable_error(e: Exception) -> bool:
    error_message = str(e)
    error_type = str(type(e))
    error_lower = error_message.lower()
    return (
        "429" in error_message
        or "Too Many Requests" in error_message
        or "RateLimitError" in error_type
        or "rate_limit" in error_lower
        or "rate limit" in error_lower
        or "capacity" in error_lower
    )


def _is_context_length_error(e: Exception) -> bool:
    error_text = str(e).lower()
    return any(
        phrase in error_text
        for phrase in [
            "context length",
            "maximum context length",
            "token limit",
            "too many tokens",
            "prompt is too long",
            "maximum prompt",
        ]
    )


# ---------------------------------------------------------------------------
# SSE streaming helper (T011 - adapted from original _run_agent_stream)
# ---------------------------------------------------------------------------

def _sse_event(event: str, data: dict) -> str:
    """Format a single SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_agent_response(
    agent: RuntimeAgent,
    contents: list[Content],
    session: AgentSession,
) -> AsyncGenerator[str, None]:
    """Run the agent and yield SSE-formatted events.

    Event types: text, function_call, function_result, usage, error, done
    """
    request_usage: Optional[UsageDetails] = None
    final_text_parts: list[str] = []
    tool_events: list[dict[str, Any]] = []
    tool_event_by_call_id: dict[str, dict[str, Any]] = {}
    # Track the active call_id for accumulating streamed argument chunks
    active_call_id: Optional[str] = None
    args_accumulator: dict[str, str] = {}

    user_message = ChatMessage(role="user", contents=contents)
    stream = agent.run(user_message, session=session, stream=True)

    async for msg in stream:
        msg_dict = msg.to_dict()

        update_usage = _extract_usage_from_payload(msg_dict)
        request_usage = _merge_usage(request_usage, update_usage)

        for content in msg_dict.get("contents", []) or []:
            content_type = content.get("type")

            if content_type == "function_call":
                call_id = content.get("call_id") or None
                name = content.get("name") or None
                arguments = content.get("arguments", "")
                rendered_arguments = (
                    json.dumps(arguments, ensure_ascii=False)
                    if isinstance(arguments, (dict, list))
                    else str(arguments)
                )

                if name and call_id and call_id not in tool_event_by_call_id:
                    # First chunk of a new tool call — call_id not seen before
                    active_call_id = call_id
                    args_accumulator[call_id] = rendered_arguments

                    event_payload = {
                        "call_id": call_id,
                        "name": name,
                        "arguments": rendered_arguments,
                        "result": None,
                    }
                    tool_events.append(event_payload)
                    tool_event_by_call_id[call_id] = event_payload

                    yield _sse_event("function_call", {
                        "call_id": call_id,
                        "name": name,
                        "arguments": rendered_arguments,
                    })
                elif call_id and call_id in tool_event_by_call_id:
                    # Continuation chunk for an existing call (Responses API sends
                    # name+call_id on every delta, not just the first)
                    active_call_id = call_id
                    if rendered_arguments:
                        args_accumulator[call_id] = args_accumulator.get(call_id, "") + rendered_arguments
                        tool_event_by_call_id[call_id]["arguments"] = args_accumulator[call_id]
                        yield _sse_event("function_call", {
                            "call_id": call_id,
                            "name": tool_event_by_call_id[call_id].get("name"),
                            "arguments": args_accumulator[call_id],
                        })
                elif active_call_id:
                    # Continuation chunk — append arguments to the active call
                    if rendered_arguments:
                        args_accumulator[active_call_id] = args_accumulator.get(active_call_id, "") + rendered_arguments
                        if active_call_id in tool_event_by_call_id:
                            tool_event_by_call_id[active_call_id]["arguments"] = args_accumulator[active_call_id]
                            yield _sse_event("function_call", {
                                "call_id": active_call_id,
                                "name": tool_event_by_call_id[active_call_id].get("name"),
                                "arguments": args_accumulator[active_call_id],
                            })

            elif content_type == "mcp_server_tool_call":
                # MCP tools use a different content type with tool_name instead of name
                call_id = content.get("call_id") or None
                name = content.get("tool_name") or content.get("name") or None
                arguments = content.get("arguments", "")
                rendered_arguments = (
                    json.dumps(arguments, ensure_ascii=False)
                    if isinstance(arguments, (dict, list))
                    else str(arguments)
                )

                if name and call_id and call_id not in tool_event_by_call_id:
                    args_accumulator[call_id] = rendered_arguments

                    event_payload = {
                        "call_id": call_id,
                        "name": name,
                        "arguments": rendered_arguments,
                        "result": None,
                    }
                    tool_events.append(event_payload)
                    tool_event_by_call_id[call_id] = event_payload

                    yield _sse_event("function_call", {
                        "call_id": call_id,
                        "name": name,
                        "arguments": rendered_arguments,
                    })

            elif content_type in ("function_result", "mcp_server_tool_result"):
                call_id = content.get("call_id")
                # function_result uses "result"; mcp_server_tool_result uses "output"
                result = content.get("result") if content_type == "function_result" else content.get("output")

                # Extract structured content items from the framework's "items" list.
                # MCP servers return image content which the framework wraps as Content objects
                # with {type:'data', uri:'data:image/jpeg;base64,...'}. Convert to frontend format.
                content_items = None
                items = content.get("items")
                if isinstance(items, list):
                    converted = []
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        item_type = item.get("type")
                        if item_type == "text":
                            converted.append({"type": "text", "text": item.get("text", "")})
                        elif item_type == "data":
                            uri = item.get("uri", "")
                            if uri.startswith("data:image/"):
                                # Parse data URI: data:image/jpeg;base64,<data>
                                header, _, b64data = uri.partition(",")
                                mime_type = header.split(";")[0].replace("data:", "")
                                if b64data and mime_type:
                                    converted.append({"type": "image", "data": b64data, "mimeType": mime_type})
                        elif item_type == "image":
                            # Direct image content (mcp_server_tool_result style)
                            if item.get("data") and item.get("mimeType"):
                                converted.append(item)
                    if any(ci["type"] == "image" for ci in converted):
                        content_items = converted

                # Render text for display
                if isinstance(result, list):
                    text_parts = [
                        item.get("text", "") for item in result
                        if isinstance(item, dict) and item.get("type") == "text"
                    ]
                    rendered_result = "\n".join(text_parts) if text_parts else json.dumps(result, ensure_ascii=False)
                elif isinstance(result, dict):
                    rendered_result = json.dumps(result, ensure_ascii=False)
                else:
                    rendered_result = str(result or "")
                accumulated_args = args_accumulator.get(call_id, "") if call_id else ""
                if call_id in tool_event_by_call_id:
                    tool_event_by_call_id[call_id]["result"] = rendered_result
                    tool_event_by_call_id[call_id]["arguments"] = accumulated_args

                # Reset active call tracking
                active_call_id = None

                yield _sse_event("function_result", {
                    k: v for k, v in {
                        "call_id": call_id,
                        "result": rendered_result,
                        "arguments": accumulated_args,
                        "content_items": content_items,
                    }.items() if v is not None
                })

            elif content_type == "usage":
                usage = _extract_usage_from_payload(content)
                request_usage = _merge_usage(request_usage, usage)

        if getattr(msg, "text", None):
            final_text_parts.append(msg.text)
            yield _sse_event("text", {"content": msg.text})

    # Get usage from the final response (usage_details is only on AgentResponse,
    # not on individual stream updates)
    try:
        final_response = await stream.get_final_response()
        if final_response and getattr(final_response, "usage_details", None):
            request_usage = _merge_usage(request_usage, final_response.usage_details)
    except Exception:
        pass  # Usage is best-effort; don't break the stream

    # Emit final usage event
    if request_usage:
        in_tokens = _usage_value(request_usage, USAGE_INPUT_KEY)
        out_tokens = _usage_value(request_usage, USAGE_OUTPUT_KEY)
        total_tokens = _usage_value(request_usage, USAGE_TOTAL_KEY)
        logger.info("Token usage — IN: %d | OUT: %d | TOTAL: %d", in_tokens, out_tokens, total_tokens)
        yield _sse_event("usage", {
            USAGE_INPUT_KEY: in_tokens,
            USAGE_OUTPUT_KEY: out_tokens,
            USAGE_TOTAL_KEY: total_tokens,
        })

    yield _sse_event("done", {})

    # Stash results for caller to pick up via a mutable container
    # We use generator attributes for this
    _stream_agent_response._last_result = {  # type: ignore[attr-defined]
        "text": "".join(final_text_parts).strip(),
        "tool_events": tool_events,
        "usage": request_usage,
    }


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


class McpServerEntryRequest(BaseModel):
    name: str
    transport: str = "http"
    url: str | None = None
    authenticated: bool | None = None
    auth: bool | None = None
    authScope: str | None = None
    auth_scope: str | None = None
    description: str | None = None


class ProfileOverrideRequest(BaseModel):
    description: str | None = None
    custom_prompt: str
    custom_tools: list[str] = []
    custom_search_context: bool = False
    custom_temperature: float | None = None
    custom_skills: list[str] = []
    mcp_servers: list[McpServerEntryRequest] = []
    override_updated_at: str | None = None


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
    from agent_framework import SkillsProvider
    skills_dir = _get_skills_dir()
    if not skills_dir.is_dir():
        return {"skills": []}

    provider = SkillsProvider(skill_paths=skills_dir)
    skills = [
        {"name": skill.name, "description": skill.description}
        for skill in provider._skills.values()
    ]
    return {"skills": skills}


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


_SKILL_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9-]*$')
_SKILL_MD_TEMPLATE = '---\nname: {name}\ndescription: "{description}"\n---\n\n{content}\n'


def _get_skills_dir() -> Path:
    return Path(__file__).resolve().parent / "skills"


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
    )


def _parse_skill_md(skill_dir: Path) -> dict:
    """Parse a SKILL.md file; return {name, description, content}. Raises HTTPException(404) if missing."""
    skill_file = skill_dir / "SKILL.md"
    if not skill_dir.is_dir() or not skill_file.is_file():
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_dir.name}")
    raw = skill_file.read_text(encoding="utf-8")
    # Parse YAML frontmatter between --- delimiters
    name = skill_dir.name
    description = ""
    content = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            frontmatter = raw[3:end].strip()
            content = raw[end + 4:].lstrip("\n")
            for line in frontmatter.splitlines():
                if line.startswith("description:"):
                    description = line[len("description:"):].strip().strip('"').strip("'")
                elif line.startswith("name:"):
                    name = line[len("name:"):].strip()
    return {"name": name, "description": description, "content": content}


def _validate_skill_name(name: str, status_on_error: int = 400) -> str:
    """Validate that name contains only safe characters; raise HTTP error if not.

    This check runs *before* any path operation so that static analysis tools
    can see the user-supplied value is sanitised prior to filesystem access.
    Accepts the same alphabet as the creation regex (lowercase alphanumeric +
    hyphens, starting with alphanumeric, max 64 chars).
    """
    if not name or not _SKILL_NAME_RE.match(name) or len(name) > 64:
        raise HTTPException(status_code=status_on_error, detail="Invalid skill name")
    return name


def _prevent_path_traversal(name: str, skills_dir: Path) -> Path:
    """Resolve skill path and ensure it stays inside skills_dir.

    `name` must already have been validated by ``_validate_skill_name`` before
    this function is called.  ``os.path.basename`` is applied as an additional
    sanitization step so that static-analysis tools can identify the path-
    traversal mitigation at the point of path construction.
    """
    # os.path.basename strips any leading directory components (e.g. "../")
    # so that even if an unexpected character slips past the regex the
    # resulting path cannot escape the skills directory.
    base_name = os.path.basename(name)
    skill_path = (skills_dir / base_name).resolve()
    # Belt-and-suspenders: reject anything that escaped the skills directory.
    # is_relative_to is used (Python 3.9+) for cross-platform correctness
    # instead of string prefix matching.
    if not skill_path.is_relative_to(skills_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid skill name")
    return skill_path


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
    safe_name = _validate_skill_name(name)
    skills_dir = _get_skills_dir()
    skill_path = _prevent_path_traversal(safe_name, skills_dir)
    data = _parse_skill_md(skill_path)
    return SkillResponse(**data)


# POST /api/skills — create a new skill
@app.post("/api/skills", response_model=SkillResponse, status_code=201)
async def create_skill(body: SkillCreateRequest, user: AuthenticatedUser = Depends(get_current_user)):
    safe_name = _validate_skill_name(body.name, status_on_error=422)
    if not body.description or len(body.description) > 256:
        raise HTTPException(status_code=422, detail="Description must be non-empty (max 256 chars)")
    if not body.content or len(body.content) > 65536:
        raise HTTPException(status_code=422, detail="Content must be non-empty (max 65536 chars)")
    skills_dir = _get_skills_dir()
    skill_path = _prevent_path_traversal(safe_name, skills_dir)
    if skill_path.exists():
        raise HTTPException(status_code=409, detail=f"Skill already exists: {safe_name}")
    skill_path.mkdir(parents=True, exist_ok=False)
    skill_file = skill_path / "SKILL.md"
    # Escape double quotes in description for YAML frontmatter
    safe_description = body.description.replace('"', '\\"')
    skill_file.write_text(
        _SKILL_MD_TEMPLATE.format(name=safe_name, description=safe_description, content=body.content),
        encoding="utf-8",
    )
    return SkillResponse(name=safe_name, description=body.description, content=body.content)


# PUT /api/skills/{name} — update an existing skill
@app.put("/api/skills/{name}", response_model=SkillResponse)
async def update_skill(name: str, body: SkillUpdateRequest, user: AuthenticatedUser = Depends(get_current_user)):
    safe_name = _validate_skill_name(name)
    if not body.description or len(body.description) > 256:
        raise HTTPException(status_code=422, detail="Description must be non-empty (max 256 chars)")
    if not body.content or len(body.content) > 65536:
        raise HTTPException(status_code=422, detail="Content must be non-empty (max 65536 chars)")
    skills_dir = _get_skills_dir()
    skill_path = _prevent_path_traversal(safe_name, skills_dir)
    if not skill_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Skill not found: {safe_name}")
    skill_file = skill_path / "SKILL.md"
    safe_description = body.description.replace('"', '\\"')
    skill_file.write_text(
        _SKILL_MD_TEMPLATE.format(name=safe_name, description=safe_description, content=body.content),
        encoding="utf-8",
    )
    return SkillResponse(name=safe_name, description=body.description, content=body.content)


# DELETE /api/skills/{name} — remove a skill directory
@app.delete("/api/skills/{name}", status_code=204)
async def delete_skill(name: str, user: AuthenticatedUser = Depends(get_current_user)):
    safe_name = _validate_skill_name(name)
    skills_dir = _get_skills_dir()
    skill_path = _prevent_path_traversal(safe_name, skills_dir)
    if not skill_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Skill not found: {safe_name}")
    shutil.rmtree(skill_path)
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
    profile_id = body.get("profile_id", "")

    # Extract bearer token for authenticated MCP servers
    auth_header = request.headers.get("authorization", "")
    user_bearer_token = auth_header.removeprefix("Bearer ").strip() if auth_header.lower().startswith("bearer ") else None

    # --- Custom agent branch ---
    if profile_id == "custom":
        custom_name = body.get("custom_name", "").strip()
        custom_prompt = body.get("custom_prompt", "").strip()
        custom_tools = body.get("custom_tools", [])
        custom_search_context = bool(body.get("custom_search_context", False))

        # Parse optional custom temperature
        raw_temperature = body.get("custom_temperature")
        custom_temperature: float | None = None
        if raw_temperature is not None:
            try:
                custom_temperature = float(raw_temperature)
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="custom_temperature must be a number")
            if not (0.0 <= custom_temperature <= 2.0):
                raise HTTPException(status_code=400, detail="custom_temperature must be between 0.0 and 2.0")

        if not custom_name or len(custom_name) > 100:
            raise HTTPException(status_code=400, detail="custom_name is required and must be ≤ 100 characters")
        if not custom_prompt or len(custom_prompt) > DEFAULT_MAX_USER_INPUT_CHARS:
            raise HTTPException(
                status_code=400,
                detail=f"custom_prompt is required and must be ≤ {DEFAULT_MAX_USER_INPUT_CHARS} characters",
            )
        if not isinstance(custom_tools, list):
            raise HTTPException(status_code=400, detail="custom_tools must be a list of tool name strings")

        # Validate custom_tools against registered tool names from agents.yaml
        agents_doc = load_agents_yaml()
        profiles_data = agents_doc.get("profiles") or {}
        known_tools: set[str] = {"get_user_profile", "save_user_profile"}
        for entry in profiles_data.values():
            if isinstance(entry, dict):
                for t in (entry.get("tools") or []):
                    if isinstance(t, str):
                        known_tools.add(t)

        invalid_tools = [t for t in custom_tools if t not in known_tools]
        if invalid_tools:
            raise HTTPException(status_code=400, detail=f"Unknown tools: {', '.join(invalid_tools)}")

        # Parse and validate custom_skills
        custom_skills = body.get("custom_skills", [])
        if not isinstance(custom_skills, list):
            raise HTTPException(status_code=400, detail="custom_skills must be a list of skill name strings")
        if custom_skills:
            from agent_framework import SkillsProvider
            skills_dir = _get_skills_dir()
            if skills_dir.is_dir():
                sp = SkillsProvider(skill_paths=skills_dir)
                available_skills = set(sp._skills.keys())
            else:
                available_skills = set()
            invalid_skills = [s for s in custom_skills if s not in available_skills]
            if invalid_skills:
                raise HTTPException(status_code=400, detail=f"Unknown skills: {', '.join(invalid_skills)}")

        session_id = str(uuid.uuid4())
        try:
            function_tools, user_profile_store = _build_tool_instances(
                set(custom_tools),
                session_id=session_id,
                user_profile_data=body.get("user_profile"),
            )

            # Connect inline MCP servers from request body
            raw_mcp_servers = body.get("mcp_servers", [])
            if not isinstance(raw_mcp_servers, list):
                raise HTTPException(status_code=400, detail="mcp_servers must be a list")

            # Validate each MCP server entry (only http allowed via custom agents;
            # stdio is restricted to built-in profiles in agents.yaml)
            for entry in raw_mcp_servers:
                if not isinstance(entry, dict):
                    raise HTTPException(status_code=400, detail="Each mcp_servers entry must be an object")
                if not entry.get("name"):
                    raise HTTPException(status_code=400, detail="Each mcp_servers entry requires a 'name'")
                transport = entry.get("transport")
                if transport != "http":
                    raise HTTPException(
                        status_code=400,
                        detail="Custom agents only support 'http' MCP servers. Local (stdio) servers must be configured in agents.yaml.",
                    )
                if not entry.get("url"):
                    raise HTTPException(status_code=400, detail=f"MCP server '{entry['name']}' (http) requires a 'url'")

            mcp_configs = parse_mcp_server_configs({"mcp_servers": raw_mcp_servers})
            mcp_tools, mcp_results = await connect_mcp_servers(mcp_configs, user_token=user_bearer_token)

            # Auto-inject user profile into system prompt if agent has get_user_profile
            profile_context = ""
            if "get_user_profile" in set(custom_tools):
                profile_context = _build_user_profile_context(body.get("user_profile"))

            chat_runtime = create_chat_runtime(
                custom_name=custom_name,
                custom_instructions=custom_prompt,
                function_tools=function_tools,
                mcp_servers=mcp_tools,
                temperature=custom_temperature,
                enable_search_context=custom_search_context,
                custom_skills=custom_skills or None,
                extra_instructions=profile_context or None,
            )
        except HTTPException as e:
            logger.error("Session creation failed for custom agent '%s': %s", custom_name, e.detail)
            raise
        except Exception as e:
            logger.exception("Unexpected error creating session for custom agent '%s'", custom_name)
            raise HTTPException(status_code=500, detail=str(e))

        # Restore session history if provided
        history = body.get("history")
        if history and isinstance(history, dict):
            try:
                agent_session = AgentSession.from_dict(history)
                agent_session._session_id = session_id
                logger.info("Restored custom session history for session %s", session_id)
            except Exception:
                logger.warning("Failed to restore custom session history for %s, using fresh session", session_id)
                agent_session = chat_runtime.session
        else:
            agent_session = chat_runtime.session

        session_data = SessionData(
            session_id=session_id,
            user_id=user.user_id,
            profile_id="custom",
            profile_name=custom_name,
            agent=chat_runtime.agent,
            agent_session=agent_session,
            tools=chat_runtime.tools,
            eval_trace_logger=EvalTraceLogger.from_env(),
            prompt_manifest=chat_runtime.prompt_manifest,
            prompt_logical_profile=chat_runtime.prompt_logical_profile,
        )
        session_data.user_profile_store = user_profile_store
        session_data.mcp_tools = mcp_tools
        _sessions[session_id] = session_data

        logger.info("Created custom session %s for user %s agent=%s", session_id, user.user_id, custom_name)

        return {
            "session_id": session_id,
            "profile_id": "custom",
            "profile_name": custom_name,
            "tools_loaded": list(custom_tools),
            "skills_loaded": list(custom_skills),
            "search_context": custom_search_context,
            "mcp_results": [
                {"name": r.name, "transport": r.transport, "status": r.status, "tool_count": r.tool_count, "error": r.error}
                for r in mcp_results
            ],
        }

    # --- Standard profile branch (unchanged) ---

    # Validate profile exists
    agents_doc = load_agents_yaml()
    profiles_data = agents_doc.get("profiles") or {}

    # Accept either a direct profile key (e.g. "sql") or an exact display name.
    if profile_id in profiles_data:
        logical_profile = profile_id
    else:
        normalized_profile_id = " ".join(str(profile_id).strip().lower().split())
        logical_profile = ""
        for key, entry in profiles_data.items():
            if not isinstance(entry, dict):
                continue
            normalized_name = " ".join(str(entry.get("name", "")).strip().lower().split())
            if normalized_name and normalized_name == normalized_profile_id:
                logical_profile = key
                break

    if logical_profile not in profiles_data:
        raise HTTPException(status_code=400, detail=f"Unknown profile: {profile_id}")

    profile_entry = profiles_data[logical_profile]
    profile_name = str(profile_entry.get("name", logical_profile))
    raw_profile_override = body.get("profile_override")
    profile_override: ProfileOverrideRequest | None = None
    if raw_profile_override is not None:
        if not isinstance(raw_profile_override, dict):
            raise HTTPException(status_code=400, detail="profile_override must be an object")
        if "name" in raw_profile_override or "custom_name" in raw_profile_override:
            raise HTTPException(status_code=400, detail="Built-in profile overrides cannot change the agent name")
        try:
            profile_override = ProfileOverrideRequest(**raw_profile_override)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid profile_override: {e}")

        if not profile_override.custom_prompt.strip() or len(profile_override.custom_prompt) > DEFAULT_MAX_USER_INPUT_CHARS:
            raise HTTPException(
                status_code=400,
                detail=f"custom_prompt is required and must be ≤ {DEFAULT_MAX_USER_INPUT_CHARS} characters",
            )
        if profile_override.custom_temperature is not None and not (0.0 <= profile_override.custom_temperature <= 2.0):
            raise HTTPException(status_code=400, detail="custom_temperature must be between 0.0 and 2.0")

    session_id = str(uuid.uuid4())

    profile_tool_names = (
        list(profile_override.custom_tools)
        if profile_override is not None
        else (profile_entry.get("tools") or [])
    )
    try:
        function_tools, user_profile_store = _build_tool_instances(
            set(profile_tool_names),
            session_id=session_id,
            user_profile_data=body.get("user_profile"),
        )

        if profile_override is not None:
            known_tools: set[str] = {"get_user_profile", "save_user_profile"}
            for entry in profiles_data.values():
                if isinstance(entry, dict):
                    for t in (entry.get("tools") or []):
                        if isinstance(t, str):
                            known_tools.add(t)
            invalid_tools = [t for t in profile_override.custom_tools if t not in known_tools]
            if invalid_tools:
                raise HTTPException(status_code=400, detail=f"Unknown tools: {', '.join(invalid_tools)}")

            if profile_override.custom_skills:
                from agent_framework import SkillsProvider
                skills_dir = _get_skills_dir()
                if skills_dir.is_dir():
                    sp = SkillsProvider(skill_paths=skills_dir)
                    available_skills = set(sp._skills.keys())
                else:
                    available_skills = set()
                invalid_skills = [s for s in profile_override.custom_skills if s not in available_skills]
                if invalid_skills:
                    raise HTTPException(status_code=400, detail=f"Unknown skills: {', '.join(invalid_skills)}")

            raw_mcp_servers = [server.model_dump(exclude_none=True) for server in profile_override.mcp_servers]
            for entry in raw_mcp_servers:
                if entry.get("transport") != "http":
                    raise HTTPException(status_code=400, detail="Built-in profile overrides only support 'http' MCP servers")
                if not entry.get("url"):
                    raise HTTPException(status_code=400, detail=f"MCP server '{entry['name']}' (http) requires a 'url'")
            mcp_configs = parse_mcp_server_configs({"mcp_servers": raw_mcp_servers})
        else:
            mcp_configs = parse_mcp_server_configs(profile_entry)
        mcp_tools, mcp_results = await connect_mcp_servers(mcp_configs, user_token=user_bearer_token)

        # Auto-inject user profile into system prompt if agent has get_user_profile
        profile_context = ""
        if "get_user_profile" in profile_tool_names:
            profile_context = _build_user_profile_context(body.get("user_profile"))

        if profile_override is not None:
            chat_runtime = create_chat_runtime(
                custom_name=profile_name,
                custom_instructions=profile_override.custom_prompt.strip(),
                function_tools=function_tools,
                mcp_servers=mcp_tools,
                temperature=profile_override.custom_temperature,
                enable_search_context=profile_override.custom_search_context,
                custom_skills=profile_override.custom_skills or None,
                extra_instructions=profile_context or None,
            )
        else:
            chat_runtime = create_chat_runtime(
                chat_profile=get_profile_display_name(logical_profile, fallback=profile_id),
                function_tools=function_tools,
                mcp_servers=mcp_tools,
                extra_instructions=profile_context or None,
            )
    except HTTPException as e:
        logger.error("Session creation failed for profile '%s': %s", logical_profile, e.detail)
        raise
    except Exception as e:
        logger.exception("Unexpected error creating session for profile '%s'", logical_profile)
        raise HTTPException(status_code=500, detail=str(e))

    # Restore session history if provided
    history = body.get("history")
    if history and isinstance(history, dict):
        try:
            agent_session = AgentSession.from_dict(history)
            agent_session._session_id = session_id
            logger.info("Restored session history for session %s", session_id)
        except Exception:
            logger.warning("Failed to restore session history for session %s, using fresh session", session_id)
            agent_session = chat_runtime.session
    else:
        agent_session = chat_runtime.session

    session_data = SessionData(
        session_id=session_id,
        user_id=user.user_id,
        profile_id=logical_profile,
        profile_name=profile_name,
        agent=chat_runtime.agent,
        agent_session=agent_session,
        tools=chat_runtime.tools,
        eval_trace_logger=EvalTraceLogger.from_env(),
        prompt_manifest=chat_runtime.prompt_manifest,
        prompt_logical_profile=chat_runtime.prompt_logical_profile,
    )
    session_data.user_profile_store = user_profile_store
    session_data.mcp_tools = mcp_tools
    session_data.used_profile_override = profile_override is not None
    session_data.override_updated_at = profile_override.override_updated_at if profile_override else None

    _sessions[session_id] = session_data

    logger.info("Created session %s for user %s profile %s", session_id, user.user_id, logical_profile)

    profile_skills = (
        list(profile_override.custom_skills)
        if profile_override is not None
        else [str(s) for s in (profile_entry.get("skills") or []) if isinstance(s, str)]
    )
    profile_search_context = (
        bool(profile_override.custom_search_context)
        if profile_override is not None
        else bool(profile_entry.get("search_context", False))
    )

    return {
        "session_id": session_id,
        "profile_id": logical_profile,
        "profile_name": profile_name,
        "tools_loaded": list(profile_tool_names),
        "skills_loaded": profile_skills,
        "search_context": profile_search_context,
        "mcp_results": [
            {"name": r.name, "transport": r.transport, "status": r.status, "tool_count": r.tool_count, "error": r.error}
            for r in mcp_results
        ],
        "used_profile_override": profile_override is not None,
        "override_updated_at": profile_override.override_updated_at if profile_override else None,
    }


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
        error = _validate_uploaded_images(image_files, image_data_list)
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
            async for event in _stream_agent_response(
                session_data.agent, contents, session_data.agent_session,
            ):
                yield event
        except Exception as e:
            # T020 — error handling
            if _is_retryable_error(e):
                logger.error("Rate limit error: %s", e)
                yield _sse_event("error", {
                    "message": "The AI service is currently experiencing high demand. Please try again in a moment.",
                    "retry_after": 30,
                })
            elif _is_context_length_error(e):
                logger.error("Context length exceeded: %s", e)
                yield _sse_event("error", {
                    "message": "The request exceeded model context limits. Please shorten your prompt or start a new chat.",
                    "retry_after": None,
                })
            elif image_files and not _is_context_length_error(e) and not _is_retryable_error(e):
                logger.error("Error processing image message: %s", e, exc_info=True)
                yield _sse_event("error", {
                    "message": "One or more images could not be processed. Please try again or use a different image.",
                    "retry_after": None,
                })
            else:
                logger.error("Error processing message: %s", e, exc_info=True)
                yield _sse_event("error", {
                    "message": f"An error occurred while processing your request: {str(e)}",
                    "retry_after": None,
                })
            yield _sse_event("done", {})
            return

        # After successful streaming, update session usage and log trace (T019)
        result = getattr(_stream_agent_response, "_last_result", None)
        if result:
            request_usage = result.get("usage")
            if request_usage:
                session_data.usage = _merge_usage(session_data.usage, request_usage)
                logger.info(
                    "Request token usage - Input: %s, Output: %s, Total: %s",
                    _usage_value(request_usage, USAGE_INPUT_KEY),
                    _usage_value(request_usage, USAGE_OUTPUT_KEY),
                    _usage_value(request_usage, USAGE_TOTAL_KEY),
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
                        USAGE_INPUT_KEY: _usage_value(request_usage, USAGE_INPUT_KEY),
                        USAGE_OUTPUT_KEY: _usage_value(request_usage, USAGE_OUTPUT_KEY),
                        USAGE_TOTAL_KEY: _usage_value(request_usage, USAGE_TOTAL_KEY),
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
            _usage_value(session_data.usage, USAGE_INPUT_KEY),
            _usage_value(session_data.usage, USAGE_OUTPUT_KEY),
            _usage_value(session_data.usage, USAGE_TOTAL_KEY),
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
