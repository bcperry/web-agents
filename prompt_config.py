from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional, Union

import yaml


@dataclass(frozen=True)
class BuiltinAgentRef:
    """Reference to a built-in agent profile defined in agents.yaml."""
    profile_id: str
    kind: Literal["builtin"] = "builtin"


@dataclass(frozen=True)
class CustomAgentRef:
    """Reference to a custom agent.

    The full ``definition`` payload is inlined by the frontend at request
    time so the backend can build the sub-agent without needing a custom-
    agent persistence layer. ``definition["id"]`` MUST equal
    ``custom_agent_id`` (V5 in contracts/validation-rules.md).
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
    """Parse a raw ``agent_ref`` mapping into a tagged ``AgentRef``.

    Built-in YAML normally uses ``kind: builtin``; custom references are only
    valid when a full inline definition is supplied by the agent-builder flow.
    """
    if not isinstance(raw, dict):
        raise ValueError("agent_ref must be a mapping")
    kind = raw.get("kind")
    if kind == "builtin":
        profile_id = raw.get("profile_id")
        if not isinstance(profile_id, str) or not profile_id.strip():
            raise ValueError("agent_ref.profile_id is required for kind=builtin")
        return BuiltinAgentRef(profile_id=profile_id.strip())
    if kind == "custom":
        custom_agent_id = raw.get("custom_agent_id")
        definition = raw.get("definition")
        if not isinstance(custom_agent_id, str) or not custom_agent_id.strip():
            raise ValueError("agent_ref.custom_agent_id is required for kind=custom")
        if not isinstance(definition, dict):
            raise ValueError("agent_ref.definition must be a mapping for kind=custom")
        return CustomAgentRef(custom_agent_id=custom_agent_id.strip(), definition=definition)
    raise ValueError(f"agent_ref.kind must be 'builtin' or 'custom', got {kind!r}")


def _parse_sub_agent_tool_refs(raw: Any) -> list[SubAgentToolRef]:
    """Parse a raw ``agents_as_tools`` list into ``SubAgentToolRef`` objects.

    Returns an empty list when the optional field is absent. Raises
    ``ValueError`` on malformed input so loading fails loudly rather than
    silently dropping configuration.
    """
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValueError("agents_as_tools must be a list")
    refs: list[SubAgentToolRef] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Each agents_as_tools entry must be a mapping")
        agent_ref_raw = entry.get("agent_ref")
        if agent_ref_raw is None:
            raise ValueError("Each agents_as_tools entry requires 'agent_ref'")
        refs.append(SubAgentToolRef(agent_ref=_parse_agent_ref(agent_ref_raw)))
    return refs


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
