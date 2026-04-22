from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


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


def _normalize_profile_name(name: Optional[str]) -> str:
    if not name:
        return ""
    return " ".join(name.strip().lower().split())


def _build_profile_alias_map(workspace_root: Optional[Path] = None) -> dict[str, str]:
    """Build a {normalised display-name → profile-key} map from agents.yaml."""
    agents_doc = load_agents_yaml(workspace_root)
    profiles = agents_doc.get("profiles") or {}
    alias_map: dict[str, str] = {}
    for key, entry in profiles.items():
        if isinstance(entry, dict):
            name = entry.get("name")
            if name:
                alias_map[_normalize_profile_name(name)] = key
    return alias_map


def resolve_logical_profile(chat_profile: Optional[str], *, workspace_root: Optional[Path] = None) -> str:
    normalized = _normalize_profile_name(chat_profile)
    alias_map = _build_profile_alias_map(workspace_root)
    if normalized in alias_map:
        return alias_map[normalized]
    return "hybrid"


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
) -> AgentProfile:
    """Load a single agent profile from agents.yaml."""
    agents_doc = load_agents_yaml(workspace_root)
    logical_profile = resolve_logical_profile(chat_profile, workspace_root=workspace_root)

    profiles = agents_doc.get("profiles") or {}
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
    )
