"""Built-in profile definition serialization for the API boundary."""

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from prompt_config import load_agents_yaml


DEFAULT_PROFILE_ICON = "/favicon.png"


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
    agentsAsTools: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "builtin"


def starter_definitions(raw_starters: Any) -> list[dict[str, str]]:
    return [
        {"label": str(starter.get("label", "")), "message": str(starter.get("message", ""))}
        for starter in (raw_starters or [])
        if isinstance(starter, dict)
    ]


def safe_mcp_server_definitions(raw_servers: Any) -> list[dict[str, Any]]:
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


def serialize_agents_as_tools(raw: Any) -> list[dict[str, Any]]:
    """Convert YAML-shaped agents_as_tools entries to camelCase wire format."""
    if not isinstance(raw, list):
        return []

    serialized: list[dict[str, Any]] = []
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
            serialized.append({"agentRef": {"kind": "builtin", "profileId": str(profile_id)}})
        elif kind == "custom":
            custom_id = ref.get("custom_agent_id") or ref.get("customAgentId")
            definition = ref.get("definition")
            if not custom_id:
                continue
            wire_ref: dict[str, Any] = {"kind": "custom", "customAgentId": str(custom_id)}
            if isinstance(definition, dict):
                wire_ref["definition"] = definition
            serialized.append({"agentRef": wire_ref})

    return serialized


def get_builtin_profile_definition(profile_id: str) -> BuiltInProfileDefinitionResponse:
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
        icon=str(entry.get("icon", DEFAULT_PROFILE_ICON)),
        systemPrompt=str(entry.get("system_prompt", "")).strip(),
        tools=[str(tool) for tool in (entry.get("tools") or []) if isinstance(tool, str)],
        skills=[str(skill) for skill in (entry.get("skills") or []) if isinstance(skill, str)],
        mcpServers=safe_mcp_server_definitions(entry.get("mcp_servers")),
        useSearchContext=bool(entry.get("search_context", False)),
        starters=starter_definitions(entry.get("starters")),
        temperature=temperature,
        agentsAsTools=serialize_agents_as_tools(entry.get("agents_as_tools")),
    )