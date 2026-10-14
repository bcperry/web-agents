from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, Union

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter


@dataclass(frozen=True)
class BuiltinAgentRef:
    """Reference to a built-in agent profile defined in agents.yaml."""
    profile_id: str
    kind: Literal["builtin"] = "builtin"


@dataclass(frozen=True)
class CustomAgentRef:
    """Reference to a custom agent.

    ``definition`` is hydrated from owner-scoped storage before runtime
    construction. Its id must match ``custom_agent_id``.
    """
    custom_agent_id: str
    definition: dict[str, Any]
    kind: Literal["custom"] = "custom"


AgentRef = Union[BuiltinAgentRef, CustomAgentRef]


@dataclass(frozen=True)
class SubAgentToolRef:
    """A reference from a parent agent to a sub-agent exposed as a tool.

    Only ``agent_ref`` is stored. The LLM-visible ``tool_name`` /
    ``tool_description`` / ``arg_description`` are derived from the target
    agent at runtime via ``sub_agent_tools.derive_sub_agent_tool_surface``.
    """
    agent_ref: AgentRef


class BuiltinAgentRefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["builtin"]
    profileId: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        validation_alias=AliasChoices("profileId", "profile_id"), serialization_alias="profile_id",
    )


class CustomAgentRefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["custom"]
    customAgentId: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        validation_alias=AliasChoices("customAgentId", "custom_agent_id"), serialization_alias="custom_agent_id",
    )
    definition: dict[str, Any] | None = None


AgentRefRequest = Annotated[BuiltinAgentRefRequest | CustomAgentRefRequest, Field(discriminator="kind")]


class AgentToolRefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agentRef: AgentRefRequest = Field(
        validation_alias=AliasChoices("agentRef", "agent_ref"), serialization_alias="agent_ref",
    )


_AGENT_REF_ADAPTER = TypeAdapter(AgentRefRequest)
SUB_AGENT_TOOL_REFS = TypeAdapter(list[AgentToolRefRequest])


@dataclass(frozen=True)
class AgentProfile:
    """Resolved agent profile from agents.yaml."""
    name: str
    logical_profile: str
    system_prompt: str
    description: str
    tool_names: list[str]
    temperature: Optional[float] = None
    skills: list[str] = field(default_factory=list)
    search_context: bool = False
    agents_as_tools: list[SubAgentToolRef] = field(default_factory=list)


def _parse_agent_ref(raw: Any) -> AgentRef:
    """Adapt a validated reference to the hydrated runtime dataclasses."""
    reference = _AGENT_REF_ADAPTER.validate_python(raw)
    if isinstance(reference, BuiltinAgentRefRequest):
        return BuiltinAgentRef(profile_id=reference.profileId)
    if reference.definition is None:
        raise ValueError("agent_ref.definition must be a mapping for kind=custom")
    return CustomAgentRef(custom_agent_id=reference.customAgentId, definition=reference.definition)


def _parse_sub_agent_tool_refs(raw: Any) -> list[SubAgentToolRef]:
    """Parse a raw ``agents_as_tools`` list into ``SubAgentToolRef`` objects.

    Returns an empty list when the optional field is absent. Raises
    ``ValueError`` on malformed input so loading fails loudly rather than
    silently dropping configuration.
    """
    return [
        SubAgentToolRef(agent_ref=_parse_agent_ref(entry.agentRef))
        for entry in SUB_AGENT_TOOL_REFS.validate_python([] if raw is None else raw)
    ]


def _normalize_profile_name(name: Optional[str]) -> str:
    if not name:
        return ""
    return " ".join(name.strip().lower().split())


def resolve_logical_profile(
    chat_profile: Optional[str], *, workspace_root: Optional[Path] = None,
    profiles: dict[str, Any] | None = None,
) -> str:
    if profiles is None:
        profiles = load_agents_yaml(workspace_root).get("profiles") or {}
    if chat_profile in profiles:
        return chat_profile
    if not chat_profile:
        return "hybrid"
    normalized = _normalize_profile_name(chat_profile)
    for key, entry in profiles.items():
        if isinstance(entry, dict) and entry.get("name") and _normalize_profile_name(entry["name"]) == normalized:
            return key
    raise ValueError(f"Unknown profile: {chat_profile}")


def get_profile_display_name(logical_profile: str, *, fallback: Optional[str] = None, workspace_root: Optional[Path] = None) -> str:
    """Return the display name for a profile key, loaded from agents.yaml."""
    agents_doc = load_agents_yaml(workspace_root)
    profiles = agents_doc.get("profiles") or {}
    entry = profiles.get(logical_profile)
    if isinstance(entry, dict) and entry.get("name"):
        return str(entry["name"])
    return fallback or logical_profile


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Config file must contain a YAML object: {path}")
    return loaded


def load_agents_yaml(workspace_root: Optional[Path] = None) -> dict[str, Any]:
    """Load and return the raw agents.yaml document."""
    root = workspace_root or Path(__file__).resolve().parent
    return _read_yaml(root / "config" / "agents.yaml")


def load_agent_profile(
    chat_profile: Optional[str],
    workspace_root: Optional[Path] = None,
    *,
    profiles: dict[str, Any] | None = None,
) -> AgentProfile:
    """Load a single agent profile from agents.yaml."""
    if profiles is None:
        profiles = load_agents_yaml(workspace_root).get("profiles") or {}
    logical_profile = resolve_logical_profile(chat_profile, profiles=profiles)

    if logical_profile not in profiles:
        raise ValueError(f"No agent profile found for '{logical_profile}' in agents.yaml")

    entry = profiles[logical_profile]
    if not isinstance(entry, dict) or not entry.get("system_prompt"):
        raise ValueError(f"Invalid agent profile entry for '{logical_profile}'")

    tool_names = entry.get("tools") or []
    if not isinstance(tool_names, list):
        raise ValueError(f"Profile '{logical_profile}' tools must be a list")

    raw_temperature = entry.get("temperature")
    temperature: Optional[float] = None
    if raw_temperature is not None:
        temperature = float(raw_temperature)

    raw_skills = entry.get("skills") or []
    if not isinstance(raw_skills, list):
        raw_skills = []

    return AgentProfile(
        name=str(entry.get("name", chat_profile or logical_profile)),
        logical_profile=logical_profile,
        system_prompt=str(entry["system_prompt"]).strip(),
        description=str(entry.get("description", f"{logical_profile} agent")),
        tool_names=[str(t) for t in tool_names],
        temperature=temperature,
        skills=[str(s) for s in raw_skills],
        search_context=bool(entry.get("search_context", False)),
        agents_as_tools=_parse_sub_agent_tool_refs(entry.get("agents_as_tools")),
    )
