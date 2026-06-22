"""Runtime state for currently active chat sessions."""

from datetime import datetime, timezone
from typing import Any, Optional

from agent_framework import Agent as RuntimeAgent
from agent_framework import AgentSession
from agent_framework._types import UsageDetails
from fastapi import HTTPException

from eval_trace import EvalTraceLogger
from streaming import create_usage


class SessionData:
    """Server-side state for an active chat session."""

    __slots__ = (
        "session_id", "user_id", "profile_id", "profile_name",
        "agent", "agent_session", "tools", "usage",
        "eval_trace_logger", "prompt_manifest", "prompt_logical_profile",
        "created_at", "context_usage", "mcp_tools",
    )

    def __init__(
        self,
        *,
        session_id: str,
        user_id: str,
        profile_id: str,
        profile_name: str,
        agent: RuntimeAgent,
        agent_session: AgentSession,
        tools: list[Any],
        eval_trace_logger: EvalTraceLogger,
        prompt_manifest: dict[str, str],
        prompt_logical_profile: str,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.profile_id = profile_id
        self.profile_name = profile_name
        self.agent = agent
        self.agent_session = agent_session
        self.tools = tools
        self.usage: Optional[UsageDetails] = create_usage()
        self.eval_trace_logger = eval_trace_logger
        self.prompt_manifest = prompt_manifest
        self.prompt_logical_profile = prompt_logical_profile
        self.created_at = datetime.now(timezone.utc)
        self.context_usage: dict[str, int] = {
            "request_count": 0,
            "sum_context_chars": 0,
            "max_context_chars": 0,
            "last_context_chars": 0,
        }
        self.mcp_tools: list[Any] = []


_sessions: dict[str, SessionData] = {}


def get_session(session_id: str) -> SessionData:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session