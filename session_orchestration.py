"""Session creation helpers for FastAPI routes."""

import logging
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agent_framework import AgentSession
from fastapi import HTTPException
from pydantic import BaseModel

from agent_factory import create_chat_runtime
from eval_trace import EvalTraceLogger
from mcp_servers import connect_mcp_servers, parse_mcp_server_configs
from prompt_config import get_profile_display_name, load_agents_yaml
from validators import (
    available_skill_names,
    filter_known_skill_names,
    known_tool_names_from_profiles,
    validate_custom_name,
    validate_http_mcp_servers,
    validate_prompt,
    validate_temperature,
    validate_tool_names,
)

MAX_USER_INPUT_CHARS = int(os.getenv("MAX_USER_INPUT_CHARS", "8000"))

_SECRET_QUERY_KEYS = {"api_key", "apikey", "code", "token", "access_token", "client_secret", "password"}
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|client[_-]?secret|password|connectionstring|connection_string)\s*=\s*[^\s&]+"
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")


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


@dataclass(frozen=True)
class SessionContext:
    """Bundle the FastAPI-app dependencies that session creation needs.

    Built once by `main.py` so route handlers don't have to thread these
    callbacks/objects through every call.
    """
    sessions: dict[str, Any]
    session_data_cls: type
    get_skills_dir: Callable[[], Path]
    build_tool_instances: Callable[..., tuple[list[Any], Any]]
    build_user_profile_context: Callable[[dict[str, str] | None], str]


def _sanitize_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.scheme or not parsed.netloc:
        return value
    safe_query = urlencode([
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _SECRET_QUERY_KEYS
    ])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, safe_query, parsed.fragment))


def sanitize_mcp_result_error(error: str | None) -> str | None:
    if error is None:
        return None
    sanitized = re.sub(r"https?://[^\s)]+", lambda match: _sanitize_url(match.group(0)), str(error))
    sanitized = _BEARER_RE.sub("[REDACTED_TOKEN]", sanitized)
    sanitized = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)} [REDACTED]", sanitized)
    return sanitized


def _resolve_profile(profile_id: str, profiles_data: dict[str, Any]) -> str:
    if profile_id in profiles_data:
        return profile_id

    normalized_profile_id = " ".join(str(profile_id).strip().lower().split())
    for key, entry in profiles_data.items():
        if not isinstance(entry, dict):
            continue
        normalized_name = " ".join(str(entry.get("name", "")).strip().lower().split())
        if normalized_name and normalized_name == normalized_profile_id:
            return key

    raise HTTPException(status_code=400, detail=f"Unknown profile: {profile_id}")


def _serialize_mcp_results(results: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": result.name,
            "transport": result.transport,
            "status": result.status,
            "tool_count": result.tool_count,
            "error": sanitize_mcp_result_error(result.error),
        }
        for result in results
    ]


def _restore_session_history(history: object, session_id: str, fallback_session: AgentSession, logger: logging.Logger) -> AgentSession:
    if history and isinstance(history, dict):
        try:
            agent_session = AgentSession.from_dict(history)
            agent_session._session_id = session_id
            logger.info("Restored session history for session %s", session_id)
            return agent_session
        except Exception:
            logger.warning("Failed to restore session history for %s, using fresh session", session_id)
    return fallback_session


def _parse_profile_override(raw_profile_override: object) -> ProfileOverrideRequest | None:
    if raw_profile_override is None:
        return None
    if not isinstance(raw_profile_override, dict):
        raise HTTPException(status_code=400, detail="profile_override must be an object")
    if "name" in raw_profile_override or "custom_name" in raw_profile_override:
        raise HTTPException(status_code=400, detail="Built-in profile overrides cannot change the agent name")
    try:
        profile_override = ProfileOverrideRequest(**raw_profile_override)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid profile_override: {exc}") from exc

    profile_override.custom_prompt = validate_prompt(profile_override.custom_prompt, max_chars=MAX_USER_INPUT_CHARS)
    if profile_override.custom_temperature is not None:
        validate_temperature(profile_override.custom_temperature)
    return profile_override


def _store_session(
    ctx: SessionContext,
    *,
    session_id: str,
    user: Any,
    profile_id: str,
    profile_name: str,
    chat_runtime: Any,
    agent_session: AgentSession,
    user_profile_store: Any,
    mcp_tools: list[Any],
    profile_override: "ProfileOverrideRequest | None" = None,
) -> None:
    session_data = ctx.session_data_cls(
        session_id=session_id,
        user_id=user.user_id,
        profile_id=profile_id,
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
    if profile_override is not None:
        session_data.used_profile_override = True
        session_data.override_updated_at = profile_override.override_updated_at
    ctx.sessions[session_id] = session_data


async def create_chat_session(
    ctx: SessionContext,
    *,
    body: dict[str, Any],
    auth_header: str,
    user: Any,
    logger: logging.Logger,
) -> dict[str, Any]:
    profile_id = body.get("profile_id", "")
    user_bearer_token = (
        auth_header.removeprefix("Bearer ").strip()
        if auth_header.lower().startswith("bearer ")
        else None
    )
    agents_doc = load_agents_yaml()
    profiles_data = agents_doc.get("profiles") or {}

    if profile_id == "custom":
        return await _create_custom_chat_session(
            ctx,
            body=body,
            profiles_data=profiles_data,
            user_bearer_token=user_bearer_token,
            user=user,
            logger=logger,
        )

    return await _create_profile_chat_session(
        ctx,
        body=body,
        profiles_data=profiles_data,
        user_bearer_token=user_bearer_token,
        user=user,
        logger=logger,
    )


async def _create_custom_chat_session(
    ctx: SessionContext,
    *,
    body: dict[str, Any],
    profiles_data: dict[str, Any],
    user_bearer_token: str | None,
    user: Any,
    logger: logging.Logger,
) -> dict[str, Any]:
    custom_name = validate_custom_name(body.get("custom_name", ""))
    custom_prompt = validate_prompt(body.get("custom_prompt", ""), max_chars=MAX_USER_INPUT_CHARS)
    custom_search_context = bool(body.get("custom_search_context", False))
    custom_temperature = validate_temperature(body.get("custom_temperature"))
    custom_tools = validate_tool_names(body.get("custom_tools", []), known_tool_names_from_profiles(profiles_data))
    custom_skills, dropped_skills = filter_known_skill_names(body.get("custom_skills", []), available_skill_names(ctx.get_skills_dir()))
    if dropped_skills:
        logger.warning("Custom agent '%s' references unknown skills, dropping: %s", custom_name, dropped_skills)
    raw_mcp_servers = validate_http_mcp_servers(body.get("mcp_servers", []), override=False)

    session_id = str(uuid.uuid4())
    custom_tool_set = set(custom_tools)
    try:
        function_tools, user_profile_store = ctx.build_tool_instances(
            custom_tool_set,
            session_id=session_id,
            user_profile_data=body.get("user_profile"),
        )
        mcp_configs = parse_mcp_server_configs({"mcp_servers": raw_mcp_servers})
        mcp_tools, mcp_results = await connect_mcp_servers(mcp_configs, user_token=user_bearer_token)
        profile_context = ctx.build_user_profile_context(body.get("user_profile")) if "get_user_profile" in custom_tool_set else ""
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
    except HTTPException as exc:
        logger.error("Session creation failed for custom agent '%s': %s", custom_name, exc.detail)
        raise
    except Exception as exc:
        logger.exception("Unexpected error creating session for custom agent '%s'", custom_name)
        raise HTTPException(status_code=500, detail=sanitize_mcp_result_error(str(exc))) from exc

    agent_session = _restore_session_history(body.get("history"), session_id, chat_runtime.session, logger)
    _store_session(
        ctx,
        session_id=session_id,
        user=user,
        profile_id="custom",
        profile_name=custom_name,
        chat_runtime=chat_runtime,
        agent_session=agent_session,
        user_profile_store=user_profile_store,
        mcp_tools=mcp_tools,
    )

    logger.info("Created custom session %s for user %s agent=%s", session_id, user.user_id, custom_name)
    return {
        "session_id": session_id,
        "profile_id": "custom",
        "profile_name": custom_name,
        "tools_loaded": list(custom_tools),
        "skills_loaded": list(custom_skills),
        "search_context": custom_search_context,
        "mcp_results": _serialize_mcp_results(mcp_results),
    }


async def _create_profile_chat_session(
    ctx: SessionContext,
    *,
    body: dict[str, Any],
    profiles_data: dict[str, Any],
    user_bearer_token: str | None,
    user: Any,
    logger: logging.Logger,
) -> dict[str, Any]:
    profile_id = body.get("profile_id", "")
    logical_profile = _resolve_profile(profile_id, profiles_data)
    profile_entry = profiles_data[logical_profile]
    profile_name = str(profile_entry.get("name", logical_profile))
    profile_override = _parse_profile_override(body.get("profile_override"))
    profile_tool_names = list(profile_override.custom_tools) if profile_override is not None else (profile_entry.get("tools") or [])
    session_id = str(uuid.uuid4())

    try:
        function_tools, user_profile_store = ctx.build_tool_instances(
            set(profile_tool_names),
            session_id=session_id,
            user_profile_data=body.get("user_profile"),
        )

        if profile_override is not None:
            validate_tool_names(profile_override.custom_tools, known_tool_names_from_profiles(profiles_data))
            if profile_override.custom_skills:
                kept, dropped = filter_known_skill_names(profile_override.custom_skills, available_skill_names(ctx.get_skills_dir()))
                if dropped:
                    logger.warning("Profile override for '%s' references unknown skills, dropping: %s", logical_profile, dropped)
                profile_override.custom_skills = kept
            raw_mcp_servers = [server.model_dump(exclude_none=True) for server in profile_override.mcp_servers]
            validate_http_mcp_servers(raw_mcp_servers, override=True)
            mcp_configs = parse_mcp_server_configs({"mcp_servers": raw_mcp_servers})
        else:
            mcp_configs = parse_mcp_server_configs(profile_entry)

        mcp_tools, mcp_results = await connect_mcp_servers(mcp_configs, user_token=user_bearer_token)
        profile_context = ctx.build_user_profile_context(body.get("user_profile")) if "get_user_profile" in profile_tool_names else ""

        if profile_override is not None:
            chat_runtime = create_chat_runtime(
                custom_name=profile_name,
                custom_instructions=profile_override.custom_prompt,
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
    except HTTPException as exc:
        logger.error("Session creation failed for profile '%s': %s", logical_profile, exc.detail)
        raise
    except Exception as exc:
        logger.exception("Unexpected error creating session for profile '%s'", logical_profile)
        raise HTTPException(status_code=500, detail=sanitize_mcp_result_error(str(exc))) from exc

    agent_session = _restore_session_history(body.get("history"), session_id, chat_runtime.session, logger)
    _store_session(
        ctx,
        session_id=session_id,
        user=user,
        profile_id=logical_profile,
        profile_name=profile_name,
        chat_runtime=chat_runtime,
        agent_session=agent_session,
        user_profile_store=user_profile_store,
        mcp_tools=mcp_tools,
        profile_override=profile_override,
    )

    logger.info("Created session %s for user %s profile %s", session_id, user.user_id, logical_profile)
    profile_skills = list(profile_override.custom_skills) if profile_override is not None else [
        str(skill) for skill in (profile_entry.get("skills") or []) if isinstance(skill, str)
    ]
    profile_search_context = bool(profile_override.custom_search_context) if profile_override is not None else bool(profile_entry.get("search_context", False))

    return {
        "session_id": session_id,
        "profile_id": logical_profile,
        "profile_name": profile_name,
        "tools_loaded": list(profile_tool_names),
        "skills_loaded": profile_skills,
        "search_context": profile_search_context,
        "mcp_results": _serialize_mcp_results(mcp_results),
        "used_profile_override": profile_override is not None,
        "override_updated_at": profile_override.override_updated_at if profile_override else None,
    }


__all__ = [
    "McpServerEntryRequest",
    "ProfileOverrideRequest",
    "SessionContext",
    "create_chat_session",
    "sanitize_mcp_result_error",
]