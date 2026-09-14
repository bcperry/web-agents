"""Session creation helpers for FastAPI routes."""

import logging
import os
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from agent_framework import AgentSession
from fastapi import HTTPException
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import BaseModel, Field

from agent_factory import ChatRuntime, SubAgentResources, create_chat_runtime
from cosmos_memory import get_conversation_repository
from database import DATABASE_TOOL_NAMES
from eval_trace import EvalTraceLogger
from mcp_servers import MCPServerConfig, cleanup_mcp_servers, connect_mcp_servers, parse_mcp_server_configs, sanitize_mcp_result_error
from session_data import SessionData, replace_session
from user_data import get_custom_agents_repository, get_user_profile_repository
from prompt_config import (
    AgentRef,
    AgentProfile,
    BuiltinAgentRef,
    SubAgentToolRef,
    _parse_sub_agent_tool_refs,
    load_agent_profile,
    load_agents_yaml,
    resolve_logical_profile,
)
from validators import (
    available_skill_names,
    filter_known_skill_names,
    validate_custom_name,
    validate_http_mcp_servers,
    validate_prompt,
    validate_sub_agent_tool_refs,
    validate_temperature,
    validate_tool_names,
)

logger = logging.getLogger(__name__)

MAX_USER_INPUT_CHARS = int(os.getenv("MAX_USER_INPUT_CHARS", "8000"))

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

    Built once by `app_context.py` so route handlers don't have to thread these
    callbacks/objects through every call.
    """
    sessions: dict[str, SessionData]
    session_data_cls: type[SessionData]
    build_tool_instances: Callable[..., list[Any]]
    build_user_profile_context: Callable[[dict[str, str] | None], str]
    database_access: Any | None = None


@dataclass(frozen=True)
class RuntimeDependencies:
    """Runtime inputs plus cleanup-only MCP tools for one chat session."""

    function_tools: list[Any]
    tool_names: list[str]
    mcp_tools: list[Any]
    session_mcp_tools: list[Any]
    mcp_results: list[Any]
    profile_context: str
    sub_agent_resources: dict[str, SubAgentResources]


@dataclass(frozen=True)
class SessionDefinition:
    profile_id: str
    profile: AgentProfile
    mcp_configs: list[MCPServerConfig]
    custom_agent_id: str | None = None
    used_builtin_override: bool = False
    override_updated_at: str | None = None


def _resolve_profile(profile_id: str, profiles_data: dict[str, Any]) -> str:
    if not isinstance(profile_id, str) or not profile_id:
        raise HTTPException(status_code=400, detail="profile_id is required")
    try:
        return resolve_logical_profile(profile_id, profiles=profiles_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


def _resolve_for_validation(agent_ref: AgentRef) -> AgentProfile | dict[str, Any] | None:
    """Resolve a SubAgentToolRef target for cycle/orphan detection."""
    if isinstance(agent_ref, BuiltinAgentRef):
        try:
            return load_agent_profile(agent_ref.profile_id)
        except Exception:
            return None
    definition = agent_ref.definition
    if str(definition.get("systemPrompt") or definition.get("system_prompt") or "").strip():
        return definition
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

    def resolver(ref_kind: str, target_id: str) -> AgentProfile | dict[str, Any] | None:
        for reference in refs:
            agent_ref = reference.agent_ref
            if agent_ref.kind != ref_kind:
                continue
            ref_target = (
                agent_ref.profile_id if isinstance(agent_ref, BuiltinAgentRef)
                else agent_ref.custom_agent_id
            )
            if ref_target == target_id:
                return _resolve_for_validation(agent_ref)
        return None

    errors = validate_sub_agent_tool_refs(parent_id, refs, resolver)
    if errors:
        logger.warning("agents_as_tools validation failed for %s: %s", parent_id, [e.code for e in errors])
        raise HTTPException(
            status_code=400,
            detail={"message": "agents_as_tools validation failed", "errors": [e.to_dict() for e in errors]},
        )
    return refs


async def _resolve_builtin_sub_agent_resources(
    refs: list[SubAgentToolRef],
    *,
    ctx: SessionContext,
    user_bearer_token: str | None,
    user_id: str,
    session_id: str,
    logger: logging.Logger,
    owned_mcp_tools: list[Any],
) -> dict[str, SubAgentResources]:
    """Resolve builtin resources, registering connected tools for caller cleanup."""
    profiles_doc = load_agents_yaml().get("profiles") or {}
    resources_by_profile: dict[str, SubAgentResources] = {}
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
            mcp_configs = parse_mcp_server_configs(entry, interpolate_env=True)
            mcp_tools, mcp_results = await connect_mcp_servers(mcp_configs, user_token=user_bearer_token)
        except Exception as exc:  # noqa: BLE001 — orphan/connection errors must not crash parent
            logger.warning("Sub-agent '%s' MCP connect failed: %s", profile_id, exc)
            mcp_tools, mcp_results = [], []
        for r in mcp_results:
            if r.status == "failed":
                logger.warning("Sub-agent '%s' MCP server '%s' failed: %s", profile_id, r.name, r.error)
        owned_mcp_tools.extend(mcp_tools)
        skills = entry.get("skills") or []
        skill_names = [str(s) for s in skills if isinstance(s, str)]
        resources_by_profile[profile_id] = SubAgentResources(
            function_tools=function_tools,
            mcp_tools=mcp_tools,
            skill_names=skill_names,
            enable_search_context=bool(entry.get("search_context", False)),
        )
    return resources_by_profile


async def _resolve_runtime_dependencies(
    ctx: SessionContext,
    *,
    tool_names: Iterable[str],
    mcp_configs: list[MCPServerConfig],
    sub_agent_refs: list[SubAgentToolRef],
    user_bearer_token: str | None,
    user: Any,
    session_id: str,
    logger: logging.Logger,
    agent_id: str = "",
) -> RuntimeDependencies:
    requested_tool_names = list(tool_names)
    tool_name_set = set(requested_tool_names)
    function_tools = ctx.build_tool_instances(
        tool_name_set,
        session_id=session_id,
        user_id=user.user_id,
    )
    database_tools = await _database_tools(
        ctx, user=user, agent_id=agent_id, tool_names=tool_name_set, logger=logger
    )
    function_tools.extend(database_tools.values())
    loaded_tool_names = [
        name for name in requested_tool_names if name not in DATABASE_TOOL_NAMES
    ] + list(database_tools)
    profile_context = (
        ctx.build_user_profile_context(await get_user_profile_repository().get(user.user_id, user.user_id))
        if "get_user_profile" in tool_name_set
        else ""
    )
    mcp_tools, mcp_results = await connect_mcp_servers(mcp_configs, user_token=user_bearer_token)
    owned_mcp_tools = list(mcp_tools)
    resolved = False
    try:
        sub_agent_resources = await _resolve_builtin_sub_agent_resources(
            sub_agent_refs, ctx=ctx, user_bearer_token=user_bearer_token,
            user_id=user.user_id, session_id=session_id, logger=logger,
            owned_mcp_tools=owned_mcp_tools,
        )
        resolved = True
    finally:
        if not resolved:
            await cleanup_mcp_servers(owned_mcp_tools)
    return RuntimeDependencies(
        function_tools=function_tools,
        tool_names=loaded_tool_names,
        mcp_tools=mcp_tools,
        session_mcp_tools=owned_mcp_tools,
        mcp_results=mcp_results,
        profile_context=profile_context,
        sub_agent_resources=sub_agent_resources,
    )


async def _database_tools(
    ctx: SessionContext,
    *,
    user: Any,
    agent_id: str,
    tool_names: set[str],
    logger: logging.Logger,
) -> dict[str, Any]:
    """Resolve the guarded database tools this session's declared tools earn."""
    if ctx.database_access is None or not (tool_names & DATABASE_TOOL_NAMES):
        return {}
    try:
        return await ctx.database_access.tools_for(
            user=user, agent_id=agent_id, tool_names=tool_names
        )
    except Exception:  # noqa: BLE001 — an unresolvable grant means no database tools
        logger.exception("Database tool resolution failed for agent '%s'", agent_id)
        return {}


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


def _build_session_data(
    ctx: SessionContext,
    *,
    session_id: str,
    user: Any,
    profile_id: str,
    profile_name: str,
    chat_runtime: ChatRuntime,
    agent_session: AgentSession,
    mcp_tools: list[Any],
) -> SessionData:
    session_data = ctx.session_data_cls(
        session_id=session_id,
        user_id=user.user_id,
        profile_id=profile_id,
        profile_name=profile_name,
        agent=chat_runtime.agent,
        agent_session=agent_session,
        tools=chat_runtime.tools,
        eval_trace_logger=EvalTraceLogger.from_env(),
        prompt_logical_profile=chat_runtime.prompt_logical_profile,
    )
    session_data.mcp_tools = mcp_tools
    return session_data


async def create_chat_session(
    ctx: SessionContext,
    *,
    body: dict[str, Any],
    auth_header: str,
    user: Any,
    logger: logging.Logger,
) -> dict[str, Any]:
    profile_id = body.get("profile_id", "")
    scheme, token = get_authorization_scheme_param(auth_header)
    user_bearer_token = token.strip() if scheme.lower() == "bearer" else None
    agents_doc = load_agents_yaml()
    profiles_data = agents_doc.get("profiles") or {}

    if profile_id == "custom":
        return await _create_custom_chat_session(
            ctx,
            body=body,
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
    user_bearer_token: str | None,
    user: Any,
    logger: logging.Logger,
) -> dict[str, Any]:
    from app_context import function_tool_registry

    custom_name = validate_custom_name(body.get("custom_name", ""))
    custom_prompt = validate_prompt(body.get("custom_prompt", ""), max_chars=MAX_USER_INPUT_CHARS)
    custom_search_context = bool(body.get("custom_search_context", False))
    custom_temperature = validate_temperature(body.get("custom_temperature"))
    custom_tools = validate_tool_names(body.get("custom_tools", []), set(function_tool_registry()))
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

    return await _start_session(
        ctx, body=body, user=user, logger=logger,
        user_bearer_token=user_bearer_token,
        definition=SessionDefinition(
            profile_id="custom",
            profile=AgentProfile(
                name=custom_name, logical_profile="custom", system_prompt=custom_prompt,
                description=f"Custom agent: {custom_name}", tool_names=custom_tools,
                temperature=custom_temperature, skills=custom_skills,
                search_context=custom_search_context, agents_as_tools=sub_agent_refs,
            ),
            mcp_configs=parse_mcp_server_configs({"mcp_servers": raw_mcp_servers}),
            custom_agent_id=str(body.get("custom_id") or custom_name),
        ),
    )


async def _create_profile_chat_session(
    ctx: SessionContext,
    *,
    body: dict[str, Any],
    profiles_data: dict[str, Any],
    user_bearer_token: str | None,
    user: Any,
    logger: logging.Logger,
) -> dict[str, Any]:
    from app_context import function_tool_registry

    profile_id = body.get("profile_id", "")
    logical_profile = _resolve_profile(profile_id, profiles_data)
    profile_entry = profiles_data[logical_profile]
    profile_name = str(profile_entry.get("name", logical_profile))
    profile_override = _parse_profile_override(body.get("profile_override"))
    if profile_override is not None:
        validate_tool_names(profile_override.custom_tools, set(function_tool_registry()))
        profile_override.custom_skills, dropped = filter_known_skill_names(
            profile_override.custom_skills, await available_skill_names(user.user_id)
        )
        if dropped:
            logger.warning("Profile override '%s' references unknown skills, dropping: %s", logical_profile, dropped)
        raw_mcp_servers = [server.model_dump(exclude_none=True) for server in profile_override.mcp_servers]
        raw_mcp_servers = validate_http_mcp_servers(raw_mcp_servers, override=True)
        mcp_configs = parse_mcp_server_configs({"mcp_servers": raw_mcp_servers})
        profile_sub_agent_refs = _build_validated_sub_agent_refs(
            logical_profile, await _owner_scoped_sub_agent_payload(profile_override.agentsAsTools, user.user_id), logger
        )
        profile = AgentProfile(
            name=profile_name, logical_profile="custom", system_prompt=profile_override.custom_prompt,
            description=f"Custom agent: {profile_name}", tool_names=profile_override.custom_tools,
            temperature=profile_override.custom_temperature, skills=profile_override.custom_skills,
            search_context=profile_override.custom_search_context, agents_as_tools=profile_sub_agent_refs,
        )
    else:
        profile = load_agent_profile(logical_profile, profiles=profiles_data)
        mcp_configs = parse_mcp_server_configs(profile_entry, interpolate_env=True)

    response = await _start_session(
        ctx, body=body, user=user, logger=logger, user_bearer_token=user_bearer_token,
        definition=SessionDefinition(
            profile_id=logical_profile, profile=profile, mcp_configs=mcp_configs,
            used_builtin_override=profile_override is not None,
            override_updated_at=profile_override.override_updated_at if profile_override else None,
        ),
    )
    return {**response,
        "used_profile_override": profile_override is not None,
        "override_updated_at": profile_override.override_updated_at if profile_override else None,
    }


async def _start_session(
    ctx: SessionContext, *, body: dict[str, Any], user: Any, logger: logging.Logger,
    definition: SessionDefinition, user_bearer_token: str | None,
) -> dict[str, Any]:
    profile = definition.profile
    conversations = get_conversation_repository()
    session_id, is_resume = await _resolve_session_id(conversations, user, body)
    dependencies = None
    registered = False
    try:
        dependencies = await _resolve_runtime_dependencies(
            ctx, tool_names=profile.tool_names, mcp_configs=definition.mcp_configs,
            sub_agent_refs=profile.agents_as_tools,
            user_bearer_token=user_bearer_token, user=user, session_id=session_id,
            logger=logger, agent_id=definition.profile_id,
        )
        runtime = create_chat_runtime(
            profile=profile, function_tools=dependencies.function_tools,
            mcp_servers=dependencies.mcp_tools, extra_instructions=dependencies.profile_context or None,
            sub_agent_resources=dependencies.sub_agent_resources,
            user_id=user.user_id,
        )
        response = {
            "session_id": session_id, "profile_id": definition.profile_id, "profile_name": profile.name,
            "tools_loaded": dependencies.tool_names, "skills_loaded": profile.skills,
            "agents_loaded": runtime.sub_agent_tool_names, "search_context": profile.search_context,
            "mcp_results": _serialize_mcp_results(dependencies.mcp_results),
        }
        if not is_resume:
            await _create_conversation_index(
                conversations, user=user, session_id=session_id, profile_id=definition.profile_id,
                profile_name=profile.name, custom_agent_id=definition.custom_agent_id,
                used_builtin_override=definition.used_builtin_override,
                base_profile_id=definition.profile_id if definition.used_builtin_override else None,
                override_updated_at=definition.override_updated_at,
            )
        session_data = _build_session_data(ctx, session_id=session_id, user=user, profile_id=definition.profile_id,
                       profile_name=profile.name, chat_runtime=runtime,
                       agent_session=_bind_session_id(runtime.session, session_id),
                       mcp_tools=dependencies.session_mcp_tools)
        registered = True
        await replace_session(session_data, sessions=ctx.sessions)
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Session creation failed for profile %s", definition.profile_id)
        raise HTTPException(status_code=500, detail="Session creation failed. Please try again.") from exc
    finally:
        if dependencies is not None and not registered:
            await cleanup_mcp_servers(dependencies.session_mcp_tools)


__all__ = [
    "McpServerEntryRequest",
    "ProfileOverrideRequest",
    "SessionContext",
    "create_chat_session",
]