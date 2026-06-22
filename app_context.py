"""Application dependency wiring shared by API routes and background work."""

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from session_data import SessionData, _sessions
from session_orchestration import SessionContext
from tools import build_user_profile_tools

load_dotenv()

DEFAULT_MAX_USER_INPUT_CHARS = int(os.getenv("MAX_USER_INPUT_CHARS", "8000"))


def build_tool_instances(
    tool_names: set[str],
    *,
    session_id: str,
    user_id: str | None = None,
) -> list[Any]:
    """Instantiate the selected backend tools for a session or inventory call."""
    function_tools: list[Any] = []

    profile_tool_names = {"get_user_profile", "save_user_profile"} & tool_names
    if profile_tool_names:
        profile_tools = build_user_profile_tools(user_id or "")
        for name in ("get_user_profile", "save_user_profile"):
            if name in profile_tool_names:
                function_tools.append(profile_tools[name])

    return function_tools


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