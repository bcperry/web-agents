"""Application dependency wiring shared by API routes and background work."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from session_data import SessionData, _sessions
from session_orchestration import SessionContext
from tools import (
    build_create_agent_tool,
    build_create_skill_tool,
    build_edit_agent_tool,
    build_edit_skill_tool,
    build_user_profile_tools,
)

load_dotenv()

DEFAULT_MAX_USER_INPUT_CHARS = int(os.getenv("MAX_USER_INPUT_CHARS", "8000"))


@dataclass(frozen=True)
class FunctionToolRegistration:
    description: str
    factory: Callable[[str], Any]


def function_tool_registry() -> dict[str, FunctionToolRegistration]:
    def profile_factory(name: str) -> Callable[[str], Any]:
        return lambda user_id: build_user_profile_tools(user_id)[name]

    return {
        "get_user_profile": FunctionToolRegistration(
            "Return the authenticated user's saved profile.", profile_factory("get_user_profile")
        ),
        "save_user_profile": FunctionToolRegistration(
            "Save the authenticated user's profile for later sessions.", profile_factory("save_user_profile")
        ),
        "create_skill": FunctionToolRegistration(
            "Create a durable user-owned skill without overwriting existing work.",
            build_create_skill_tool,
        ),
        "create_agent": FunctionToolRegistration(
            "Create a durable user-owned custom agent without overwriting existing work.",
            build_create_agent_tool,
        ),
        "edit_skill": FunctionToolRegistration(
            "Edit an existing user-owned skill.",
            build_edit_skill_tool,
        ),
        "edit_agent": FunctionToolRegistration(
            "Edit an existing user-owned custom agent using its complete definition.",
            build_edit_agent_tool,
        ),
    }


def build_tool_instances(
    tool_names: set[str],
    *,
    session_id: str,
    user_id: str | None = None,
) -> list[Any]:
    """Instantiate the selected backend tools for a session or inventory call."""
    registry = function_tool_registry()
    return [
        registration.factory(user_id or "")
        for name, registration in registry.items()
        if name in tool_names
    ]


def build_user_profile_context(user_profile_data: dict[str, str] | None) -> str:
    """Return a system-prompt snippet with user profile info, or empty string."""
    if not user_profile_data or not isinstance(user_profile_data, dict):
        return ""

    parts = [
        f"- {key}: {value}"
        for key, value in user_profile_data.items()
        if value and str(value).strip()
    ]
    if not parts:
        return ""
    return "\n\n## Known User Profile\n" + "\n".join(parts)


def get_skills_dir() -> Path:
    return Path(__file__).resolve().parent / "skills"


session_context = SessionContext(
    sessions=_sessions,
    session_data_cls=SessionData,
    build_tool_instances=build_tool_instances,
    build_user_profile_context=build_user_profile_context,
)