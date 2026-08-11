"""Session creation helpers for FastAPI routes."""

import inspect
import logging
import os
import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agent_framework import AgentSession
from fastapi import HTTPException
from pydantic import BaseModel, Field

from agent_factory import SubAgentResources, create_chat_runtime
from cosmos_memory import get_conversation_repository
from eval_trace import EvalTraceLogger
from mcp_servers import connect_mcp_servers, parse_mcp_server_configs
from user_data import get_custom_agents_repository, get_user_profile_repository
from prompt_config import (
    SubAgentToolRef,
    _parse_sub_agent_tool_refs,
    get_profile_display_name,
    load_agent_profile,
    load_agents_yaml,
)
from sub_agent_tools import derive_sub_agent_tool_surface, disambiguate_tool_names
from validators import (
    available_skill_names,
    filter_known_skill_names,
    known_tool_names_from_profiles,
    validate_custom_name,
    validate_http_mcp_servers,
    validate_prompt,
    validate_sub_agent_tool_refs,
    validate_temperature,
    validate_tool_names,
)

logger = logging.getLogger(__name__)

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
    custom_tools: list[str] = Field(default_factory=list)
    custom_search_context: bool = False
    custom_temperature: float | None = None
    custom_skills: list[str] = Field(default_factory=list)
    mcp_servers: list[McpServerEntryRequest] = Field(default_factory=list)
    agentsAsTools: list[dict[str, Any]] = Field(default_factory=list)
    override_updated_at: str | None = None


@dataclass(frozen=True)
class SessionContext:
    """Bundle the FastAPI-app dependencies that session creation needs.

    Built once by `main.py` so route handlers don't have to thread these
    callbacks/objects through every call.
    """
    sessions: dict[str, Any]
    session_data_cls: type
    build_tool_instances: Callable[..., list[Any]]
    build_user_profile_context: Callable[[dict[str, str] | None], str]
    database_authorizer: Any | None = None
    database_grant_resolver: Callable[..., Any] | None = None


@dataclass(frozen=True)
class RuntimeDependencies:
    """Runtime inputs plus cleanup-only MCP tools for one chat session."""

    function_tools: list[Any]
    mcp_tools: list[Any]
    session_mcp_tools: list[Any]
    mcp_results: list[Any]
    profile_context: str
    sub_agent_resources: dict[str, SubAgentResources]


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


def _loaded_tool_names(tools: Iterable[Any]) -> list[str]:
    return [
        str(name)
        for tool in tools
        if (name := getattr(tool, "name", None) or getattr(tool, "__name__", None))
    ]


def _normalize_agent_ref_keys(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept camelCase wire format and emit snake_case keys for the parser."""
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key == "profileId":
            out.setdefault("profile_id", value)
        elif key == "customAgentId":
            out.setdefault("custom_agent_id", value)
        else:
            out[key] = value
    return out


def _normalize_sub_agent_tool_payload(raw_list: object) -> list[dict[str, Any]]:
    if raw_list in (None, ""):
        return []
    if not isinstance(raw_list, list):
        raise HTTPException(status_code=400, detail="agents_as_tools must be a list")
    normalized: list[dict[str, Any]] = []
    for entry in raw_list:
        if not isinstance(entry, dict):
            raise HTTPException(status_code=400, detail="Each agents_as_tools entry must be an object")
        agent_ref_raw = entry.get("agent_ref") or entry.get("agentRef") or {}
        if not isinstance(agent_ref_raw, dict):
            raise HTTPException(status_code=400, detail="agents_as_tools[].agent_ref must be an object")
        normalized.append({"agent_ref": _normalize_agent_ref_keys(agent_ref_raw)})
    return normalized


def _resolve_for_validation(agent_ref: Any) -> dict[str, Any] | None:
    """Resolve a SubAgentToolRef target for cycle/orphan detection."""
    kind = getattr(agent_ref, "kind", None)
    if kind == "builtin":
        profile_id = getattr(agent_ref, "profile_id", None)
        if not profile_id:
            return None
        try:
            profile = load_agent_profile(profile_id)
        except Exception:
            return None
        nested: list[dict[str, Any]] = []
        for r in profile.agents_as_tools:
            ar = r.agent_ref
            nested.append({"agent_ref": {
                "kind": getattr(ar, "kind", None),
                "profile_id": getattr(ar, "profile_id", None),
                "custom_agent_id": getattr(ar, "custom_agent_id", None),
            }})
        return {"id": profile_id, "name": profile.name, "agents_as_tools": nested}
    if kind == "custom":
        custom_id = getattr(agent_ref, "custom_agent_id", None)
        definition = getattr(agent_ref, "definition", None)
        if (
            not custom_id
            or not isinstance(definition, dict)
            or not str(definition.get("systemPrompt") or definition.get("system_prompt") or "").strip()
        ):
            return None
        return {
            "id": custom_id,
            "name": definition.get("name", custom_id),
            "agentsAsTools": definition.get("agentsAsTools") or [],
        }
    return None


async def _owner_scoped_sub_agent_payload(raw_payload: object, user_id: str) -> list[dict[str, Any]]:
    """Replace client-supplied custom definitions with owner-scoped durable records."""
    normalized = _normalize_sub_agent_tool_payload(raw_payload)
    owner_repo = get_custom_agents_repository()
    scoped: list[dict[str, Any]] = []
    for entry in normalized:
        ref = entry["agent_ref"]
        if ref.get("kind") != "custom":
            scoped.append(entry)
            continue
        custom_id = str(ref.get("custom_agent_id") or "")
        definition = await owner_repo.get(user_id, custom_id) if custom_id else None
        supplied = ref.get("definition")
        if (
            isinstance(supplied, dict)
            and supplied.get("id") is not None
            and str(supplied["id"]) != custom_id
        ):
            definition = supplied
        scoped.append({
            "agent_ref": {
                "kind": "custom",
                "custom_agent_id": custom_id,
                "definition": definition or {"id": custom_id},
            }
        })
    return scoped


def _build_validated_sub_agent_refs(
    parent_id: str,
    raw_payload: object,
    logger: logging.Logger,
) -> list[SubAgentToolRef]:
    normalized = _normalize_sub_agent_tool_payload(raw_payload)
    if not normalized:
        return []
    try:
        refs = _parse_sub_agent_tool_refs(normalized)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid agents_as_tools: {exc}") from exc

    def resolver(ref_kind: str, target_id: str) -> dict[str, Any] | None:
        for r in refs:
            ar = r.agent_ref
            if getattr(ar, "kind", None) != ref_kind:
                continue
            ref_target = (
                getattr(ar, "profile_id", None) if ref_kind == "builtin"
                else getattr(ar, "custom_agent_id", None)
            )
            if ref_target == target_id:
                return _resolve_for_validation(ar)
        return None

    errors = validate_sub_agent_tool_refs(parent_id, refs, resolver)
    if errors:
        logger.warning("agents_as_tools validation failed for %s: %s", parent_id, [e.code for e in errors])
        raise HTTPException(
            status_code=400,
            detail={"message": "agents_as_tools validation failed", "errors": [e.to_dict() for e in errors]},
        )
    return refs


def _derive_sub_agent_tool_names(refs: list[SubAgentToolRef]) -> list[str]:
    """Return derived (disambiguated) tool names for a list of sub-agent refs.

    Mirrors the runtime wiring in agent_factory so the UI can show the same
    names the LLM will see.
    """
    profiles_doc = load_agents_yaml().get("profiles") or {}
    base_names: list[str] = []
    for r in refs:
        ar = r.agent_ref
        kind = getattr(ar, "kind", None)
        if kind == "builtin":
            profile_id = getattr(ar, "profile_id", "") or ""
            entry = profiles_doc.get(profile_id) if isinstance(profiles_doc, dict) else None
            if isinstance(entry, dict):
                name = str(entry.get("name", "") or "")
                desc = str(entry.get("description", "") or "")
            else:
                name, desc = "", ""
            fallback = profile_id
        elif kind == "custom":
            custom_id = getattr(ar, "custom_agent_id", "") or ""
            definition = getattr(ar, "definition", None) or {}
            if not isinstance(definition, dict):
                definition = {}
            name = str(definition.get("name", "") or "")
            desc = str(definition.get("description", "") or "")
            fallback = custom_id
        else:
            name, desc, fallback = "", "", ""
        tool_name, _, _ = derive_sub_agent_tool_surface(name, desc, fallback)
        base_names.append(tool_name)
    return disambiguate_tool_names(base_names)


async def _resolve_builtin_sub_agent_resources(
    refs: list[SubAgentToolRef],
    *,
    ctx: SessionContext,
    user_bearer_token: str | None,
    user_id: str,
    session_id: str,
    logger: logging.Logger,
) -> tuple[dict[str, SubAgentResources], list[Any]]:
    """Pre-resolve each *builtin* sub-agent's tools, MCPs, and skills.

    Returns ``(resources_by_profile_id, all_mcp_tools)`` where the second
    element is a flat list of every MCP tool object connected here so the
    caller can register them for cleanup at session-end.
    """
    profiles_doc = load_agents_yaml().get("profiles") or {}
    resources_by_profile: dict[str, SubAgentResources] = {}
    all_mcp_tools: list[Any] = []
    for ref in refs:
        ar = ref.agent_ref
        if getattr(ar, "kind", None) != "builtin":
            continue
        profile_id = getattr(ar, "profile_id", "") or ""
        if not profile_id or profile_id in resources_by_profile:
            continue
        entry = profiles_doc.get(profile_id) if isinstance(profiles_doc, dict) else None
        if not isinstance(entry, dict):
            continue
        tool_names_raw = entry.get("tools") or []
        tool_names = {str(t) for t in tool_names_raw if isinstance(t, str)}
        function_tools = ctx.build_tool_instances(
            tool_names,
            session_id=f"{session_id}:sub:{profile_id}",
            user_id=user_id,
        )
        try:
            mcp_configs = parse_mcp_server_configs(entry)
            mcp_tools, mcp_results = await connect_mcp_servers(mcp_configs, user_token=user_bearer_token)
        except Exception as exc:  # noqa: BLE001 — orphan/connection errors must not crash parent
            logger.warning("Sub-agent '%s' MCP connect failed: %s", profile_id, exc)
            mcp_tools, mcp_results = [], []
        for r in mcp_results:
            if r.status == "failed":
                logger.warning("Sub-agent '%s' MCP server '%s' failed: %s", profile_id, r.name, r.error)
        all_mcp_tools.extend(mcp_tools)
        skills = entry.get("skills") or []
        skill_names = [str(s) for s in skills if isinstance(s, str)]
        resources_by_profile[profile_id] = SubAgentResources(
            function_tools=list(function_tools),
            mcp_tools=list(mcp_tools),
            skill_names=skill_names,
            enable_search_context=bool(entry.get("search_context", False)),
        )
    return resources_by_profile, all_mcp_tools


async def _authorized_database_tools(
    ctx: SessionContext,
    *,
    user: Any,
    agent_id: str,
    session_id: str,
    logger: logging.Logger,
) -> list[Any]:
    """Expose provider-bound database tools only to entitled users.

    Returns an empty list unless the app wired both a grant resolver and an
    authorizer, so sessions without a database grant behave exactly as before.
    Each exposed tool is guarded so membership is re-evaluated per invocation.
    """
    authorizer = ctx.database_authorizer
    grant_resolver = ctx.database_grant_resolver
    if authorizer is None or grant_resolver is None:
        return []

    from database_authorization import guard_database_tools, subject_from_user

    try:
        grant = grant_resolver(user, agent_id)
        if inspect.isawaitable(grant):
            grant = await grant
    except Exception:  # noqa: BLE001 — an unresolvable grant means no database tools
        logger.exception("Database grant resolution failed for agent '%s'", agent_id)
        return []
    if grant is None:
        return []

    subject = subject_from_user(user, agent_id=agent_id, grant=grant)
    if not await authorizer.authorize_grant(subject):
        logger.warning(
            "Database capability denied for user %s on agent '%s'", user.user_id, agent_id
        )
        return []
    tools = ctx.build_tool_instances(
        set(),
        session_id=session_id,
        user_id=user.user_id,
        database_grant=grant,
    )
    return list(guard_database_tools(tools, authorizer=authorizer, subject=subject))


async def _resolve_runtime_dependencies(
    ctx: SessionContext,
    *,
    tool_names: Iterable[str],
    mcp_config_source: dict[str, Any],
    sub_agent_refs: list[SubAgentToolRef],
    user_bearer_token: str | None,
    user: Any,
    session_id: str,
    logger: logging.Logger,
    agent_id: str = "",
) -> RuntimeDependencies:
    tool_name_set = set(tool_names)
    function_tools = ctx.build_tool_instances(
        tool_name_set,
        session_id=session_id,
        user_id=user.user_id,
    )
    function_tools.extend(
        await _authorized_database_tools(
            ctx, user=user, agent_id=agent_id, session_id=session_id, logger=logger
        )
    )
    mcp_configs = parse_mcp_server_configs(mcp_config_source)
    mcp_tools, mcp_results = await connect_mcp_servers(mcp_configs, user_token=user_bearer_token)
    profile_context = (
        ctx.build_user_profile_context(await get_user_profile_repository().get(user.user_id, user.user_id))
        if "get_user_profile" in tool_name_set
        else ""
    )
    sub_agent_resources, sub_mcp_tools = await _resolve_builtin_sub_agent_resources(
        sub_agent_refs,
        ctx=ctx,
        user_bearer_token=user_bearer_token,
        user_id=user.user_id,
        session_id=session_id,
        logger=logger,
    )
    return RuntimeDependencies(
        function_tools=function_tools,
        mcp_tools=mcp_tools,
        session_mcp_tools=[*mcp_tools, *sub_mcp_tools],
        mcp_results=mcp_results,
        profile_context=profile_context,
        sub_agent_resources=sub_agent_resources,
    )


def _bind_session_id(session: AgentSession, session_id: str) -> AgentSession:
    """Bind the runtime session to the conversation id (Cosmos partition key)."""
    session._session_id = session_id
    return session


async def _resolve_session_id(conversations: Any, user: Any, body: dict[str, Any]) -> tuple[str, bool]:
    """Return ``(session_id, is_resume)``.

    When ``conversation_id`` is supplied the caller is resuming an existing
    conversation: ownership is verified against the per-user index (404 if it is
    not owned by the caller). Otherwise a new unguessable session id is generated
    for a fresh conversation.
    """
    conversation_id = body.get("conversation_id")
    if not conversation_id:
        return str(uuid.uuid4()), False
    conversation_id = str(conversation_id)
    try:
        owned = await conversations.get_owned(user.user_id, conversation_id)
    except Exception as exc:  # noqa: BLE001 — surface store errors as retryable
        logger.error("Conversation lookup failed for %s: %s", conversation_id, sanitize_mcp_result_error(str(exc)))
        raise HTTPException(status_code=503, detail="Conversation store is temporarily unavailable. Please try again.") from exc
    if owned is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation_id, True


async def _create_conversation_index(
    conversations: Any,
    *,
    user: Any,
    session_id: str,
    profile_id: str,
    profile_name: str,
    custom_agent_id: str | None = None,
    used_builtin_override: bool = False,
    base_profile_id: str | None = None,
    override_updated_at: str | None = None,
) -> None:
    """Write the per-user conversation index entry (FR-002/FR-004)."""
    try:
        await conversations.create(
            user.user_id,
            session_id,
            profile_id,
            profile_name,
            custom_agent_id=custom_agent_id,
            used_builtin_override=used_builtin_override,
            base_profile_id=base_profile_id,
            override_updated_at=override_updated_at,
        )
    except Exception as exc:  # noqa: BLE001 — surface store errors as retryable
        logger.error("Failed to write conversation index for %s: %s", session_id, sanitize_mcp_result_error(str(exc)))
        raise HTTPException(status_code=503, detail="Conversation store is temporarily unavailable. Please try again.") from exc


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
    mcp_tools: list[Any],
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
    session_data.mcp_tools = mcp_tools
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
    custom_skills, dropped_skills = filter_known_skill_names(
        body.get("custom_skills", []), await available_skill_names(user.user_id)
    )
    if dropped_skills:
        logger.warning("Custom agent '%s' references unknown skills, dropping: %s", custom_name, dropped_skills)
    raw_mcp_servers = validate_http_mcp_servers(body.get("mcp_servers", []), override=False)
    sub_agent_refs = _build_validated_sub_agent_refs(
        parent_id=str(body.get("custom_id") or custom_name),
        raw_payload=await _owner_scoped_sub_agent_payload(
            body.get("agents_as_tools") or body.get("agentsAsTools"), user.user_id
        ),
        logger=logger,
    )

    conversations = get_conversation_repository()
    session_id, is_resume = await _resolve_session_id(conversations, user, body)
    custom_tool_set = set(custom_tools)
    try:
        dependencies = await _resolve_runtime_dependencies(
            ctx=ctx,
            tool_names=custom_tool_set,
            mcp_config_source={"mcp_servers": raw_mcp_servers},
            sub_agent_refs=sub_agent_refs,
            user_bearer_token=user_bearer_token,
            user=user,
            session_id=session_id,
            logger=logger,
            agent_id=str(body.get("custom_id") or custom_name),
        )
        chat_runtime = create_chat_runtime(
            custom_name=custom_name,
            custom_instructions=custom_prompt,
            function_tools=dependencies.function_tools,
            mcp_servers=dependencies.mcp_tools,
            temperature=custom_temperature,
            enable_search_context=custom_search_context,
            custom_skills=custom_skills or None,
            extra_instructions=dependencies.profile_context or None,
            agents_as_tools=sub_agent_refs,
            sub_agent_resources=dependencies.sub_agent_resources,
            user_id=user.user_id,
        )
    except HTTPException as exc:
        logger.error("Session creation failed for custom agent '%s': %s", custom_name, exc.detail)
        raise
    except Exception as exc:
        logger.exception("Unexpected error creating session for custom agent '%s'", custom_name)
        raise HTTPException(status_code=500, detail=sanitize_mcp_result_error(str(exc))) from exc

    agent_session = _bind_session_id(chat_runtime.session, session_id)
    _store_session(
        ctx,
        session_id=session_id,
        user=user,
        profile_id="custom",
        profile_name=custom_name,
        chat_runtime=chat_runtime,
        agent_session=agent_session,
        mcp_tools=dependencies.session_mcp_tools,
    )
    if not is_resume:
        await _create_conversation_index(
            conversations,
            user=user,
            session_id=session_id,
            profile_id="custom",
            profile_name=custom_name,
            custom_agent_id=str(body.get("custom_id") or custom_name) or None,
        )

    logger.info("Created custom session %s for user %s agent=%s", session_id, user.user_id, custom_name)
    return {
        "session_id": session_id,
        "profile_id": "custom",
        "profile_name": custom_name,
        "tools_loaded": _loaded_tool_names(dependencies.function_tools),
        "skills_loaded": list(custom_skills),
        "agents_loaded": _derive_sub_agent_tool_names(sub_agent_refs),
        "search_context": custom_search_context,
        "mcp_results": _serialize_mcp_results(dependencies.mcp_results),
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
    conversations = get_conversation_repository()
    session_id, is_resume = await _resolve_session_id(conversations, user, body)

    try:
        if profile_override is not None:
            validate_tool_names(profile_override.custom_tools, known_tool_names_from_profiles(profiles_data))
            if profile_override.custom_skills:
                kept, dropped = filter_known_skill_names(
                    profile_override.custom_skills, await available_skill_names(user.user_id)
                )
                if dropped:
                    logger.warning("Profile override for '%s' references unknown skills, dropping: %s", logical_profile, dropped)
                profile_override.custom_skills = kept
            raw_mcp_servers = [server.model_dump(exclude_none=True) for server in profile_override.mcp_servers]
            validate_http_mcp_servers(raw_mcp_servers, override=True)
            profile_sub_agent_refs = _build_validated_sub_agent_refs(
                parent_id=logical_profile,
                raw_payload=await _owner_scoped_sub_agent_payload(
                    profile_override.agentsAsTools, user.user_id
                ),
                logger=logger,
            )
            dependencies = await _resolve_runtime_dependencies(
                ctx=ctx,
                tool_names=profile_tool_names,
                mcp_config_source={"mcp_servers": raw_mcp_servers},
                sub_agent_refs=profile_sub_agent_refs,
                user_bearer_token=user_bearer_token,
                user=user,
                session_id=session_id,
                logger=logger,
                agent_id=logical_profile,
            )
            chat_runtime = create_chat_runtime(
                custom_name=profile_name,
                custom_instructions=profile_override.custom_prompt,
                function_tools=dependencies.function_tools,
                mcp_servers=dependencies.mcp_tools,
                temperature=profile_override.custom_temperature,
                enable_search_context=profile_override.custom_search_context,
                custom_skills=profile_override.custom_skills or None,
                extra_instructions=dependencies.profile_context or None,
                agents_as_tools=profile_sub_agent_refs,
                sub_agent_resources=dependencies.sub_agent_resources,
                user_id=user.user_id,
            )
        else:
            profile_sub_agent_refs = list(getattr(load_agent_profile(logical_profile), "agents_as_tools", []) or [])
            dependencies = await _resolve_runtime_dependencies(
                ctx=ctx,
                tool_names=profile_tool_names,
                mcp_config_source=profile_entry,
                sub_agent_refs=profile_sub_agent_refs,
                user_bearer_token=user_bearer_token,
                user=user,
                session_id=session_id,
                logger=logger,
                agent_id=logical_profile,
            )
            chat_runtime = create_chat_runtime(
                chat_profile=get_profile_display_name(logical_profile, fallback=profile_id),
                function_tools=dependencies.function_tools,
                mcp_servers=dependencies.mcp_tools,
                extra_instructions=dependencies.profile_context or None,
                agents_as_tools=profile_sub_agent_refs,
                sub_agent_resources=dependencies.sub_agent_resources,
                user_id=user.user_id,
            )
    except HTTPException as exc:
        logger.error("Session creation failed for profile '%s': %s", logical_profile, exc.detail)
        raise
    except Exception as exc:
        logger.exception("Unexpected error creating session for profile '%s'", logical_profile)
        raise HTTPException(status_code=500, detail=sanitize_mcp_result_error(str(exc))) from exc

    agent_session = _bind_session_id(chat_runtime.session, session_id)
    _store_session(
        ctx,
        session_id=session_id,
        user=user,
        profile_id=logical_profile,
        profile_name=profile_name,
        chat_runtime=chat_runtime,
        agent_session=agent_session,
        mcp_tools=dependencies.session_mcp_tools,
    )
    if not is_resume:
        await _create_conversation_index(
            conversations,
            user=user,
            session_id=session_id,
            profile_id=logical_profile,
            profile_name=profile_name,
            used_builtin_override=profile_override is not None,
            base_profile_id=logical_profile if profile_override is not None else None,
            override_updated_at=profile_override.override_updated_at if profile_override is not None else None,
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
        "tools_loaded": _loaded_tool_names(dependencies.function_tools),
        "skills_loaded": profile_skills,
        "agents_loaded": _derive_sub_agent_tool_names(profile_sub_agent_refs),
        "search_context": profile_search_context,
        "mcp_results": _serialize_mcp_results(dependencies.mcp_results),
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