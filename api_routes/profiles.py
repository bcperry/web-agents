"""Profile, tool inventory, and MCP test endpoints."""

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app_context import build_tool_instances
from auth import AuthenticatedUser, get_current_user
from mcp_servers import cleanup_mcp_servers, connect_mcp_servers, get_search_service_config, parse_mcp_server_configs
from profile_definitions import (
    BuiltInProfileDefinitionResponse,
    DEFAULT_PROFILE_ICON,
    get_builtin_profile_definition,
    starter_definitions,
)
from prompt_config import load_agents_yaml

logger = logging.getLogger(__name__)
router = APIRouter()


def _check_profile_health(profile_id: str, profile_entry: dict) -> str | None:
    """Return None if the profile can be instantiated, or a reason string."""
    tool_names = set(profile_entry.get("tools") or [])
    try:
        build_tool_instances(tool_names, session_id="healthcheck")
    except HTTPException as exc:
        return exc.detail
    except Exception as exc:  # noqa: BLE001 - route reports health as data
        return str(exc)

    if profile_entry.get("search_context"):
        cfg = get_search_service_config()
        if not cfg.endpoint or not cfg.index_name:
            return "missing SEARCH_SERVICE_ENDPOINT and/or SEARCH_INDEX_NAME"

    return None


@router.get("/api/tools")
async def get_tools(user: AuthenticatedUser = Depends(get_current_user)):
    agents_doc = load_agents_yaml()
    profiles_data = agents_doc.get("profiles") or {}

    tool_names: set[str] = set()
    for entry in profiles_data.values():
        if isinstance(entry, dict):
            for tool_name in entry.get("tools") or []:
                if isinstance(tool_name, str):
                    tool_names.add(tool_name)

    desc_map: dict[str, str] = {}
    unavailable_tools: list[dict[str, str]] = []
    available_names: set[str] = set()
    for tool_name in sorted(tool_names):
        try:
            tool_objects = build_tool_instances({tool_name}, session_id="discovery")
        except HTTPException as exc:
            unavailable_tools.append({"name": tool_name, "reason": exc.detail})
            continue

        available_names.add(tool_name)
        for tool_object in tool_objects:
            name = getattr(tool_object, "name", None) or getattr(tool_object, "__name__", None)
            doc = getattr(tool_object, "description", None) or getattr(tool_object, "__doc__", None) or ""
            if name:
                desc_map[name] = doc.strip().split("\n")[0]

    cfg = get_search_service_config()
    search_available = bool(cfg.endpoint and cfg.index_name)
    search_reason: str | None = None
    if not search_available:
        missing = [
            env_name
            for env_name in ("SEARCH_SERVICE_ENDPOINT", "SEARCH_INDEX_NAME")
            if not (os.environ.get(env_name) or "").strip()
        ]
        search_reason = f"missing {' and '.join(missing)}" if missing else "missing SEARCH_SERVICE_ENDPOINT and/or SEARCH_INDEX_NAME"

    return {
        "tools": [
            {"name": name, "description": desc_map.get(name, "")}
            for name in sorted(available_names)
        ],
        "unavailable": unavailable_tools,
        "search_context_available": search_available,
        "search_context_reason": search_reason,
    }


@router.get("/api/profiles")
async def get_profiles(user: AuthenticatedUser = Depends(get_current_user)):
    agents_doc = load_agents_yaml()
    profiles_data = agents_doc.get("profiles") or {}

    profiles = []
    unavailable = []
    for profile_id, entry in profiles_data.items():
        if not isinstance(entry, dict):
            continue

        name = entry.get("name", profile_id)
        reason = _check_profile_health(profile_id, entry)
        if reason is not None:
            logger.warning("Profile '%s' (%s) unavailable: %s", profile_id, name, reason)
            unavailable.append({"id": profile_id, "name": name, "reason": reason})
            continue

        profiles.append({
            "id": profile_id,
            "name": name,
            "description": entry.get("description", ""),
            "icon": entry.get("icon", DEFAULT_PROFILE_ICON),
            "group": entry.get("group", "") if isinstance(entry.get("group", ""), str) else "",
            "starters": starter_definitions(entry.get("starters")),
            "skills": [str(skill) for skill in (entry.get("skills") or []) if isinstance(skill, str)],
            "mcp_server_count": len(entry.get("mcp_servers") or []),
        })

    return {"profiles": profiles, "unavailable": unavailable}


@router.get("/api/profiles/{profile_id}/definition", response_model=BuiltInProfileDefinitionResponse)
async def get_profile_definition(
    profile_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    return get_builtin_profile_definition(profile_id)


@router.post("/api/mcp/test")
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
    tools, results = await connect_mcp_servers(configs, user_token=user_token)
    await cleanup_mcp_servers(tools)

    return {
        "results": [
            {"name": r.name, "transport": r.transport, "status": r.status, "tool_count": r.tool_count, "error": r.error}
            for r in results
        ],
    }