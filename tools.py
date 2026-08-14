import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from text_limits import env_int, truncate_text

logger = logging.getLogger("tools")

MAX_LOG_QUERY_CHARS = env_int("MAX_LOG_QUERY_CHARS", 500)
MAX_LOG_TOOL_RESULT_CHARS = env_int("MAX_LOG_TOOL_RESULT_CHARS", 100)
MAX_SEARCH_SNIPPET_CHARS = env_int("MAX_SEARCH_SNIPPET_CHARS", 500)


def _mask_connection_string(connection_string: str) -> str:
    redacted = re.sub(r"(?i)(password|pwd)\s*=\s*[^;]+", r"\1=***", connection_string)
    redacted = re.sub(r"(?i)(user id|uid)\s*=\s*[^;]+", r"\1=***", redacted)
    return redacted


def _compact_sql_for_logs(query: str) -> str:
    compacted = " ".join(query.strip().split())
    return truncate_text(compacted, MAX_LOG_QUERY_CHARS, "SQL LOG")


def _summarize_params_for_logs(params: Any | None) -> str:
    if params is None:
        return "none"
    if isinstance(params, tuple):
        return f"tuple(len={len(params)})"
    if isinstance(params, list):
        return f"list(len={len(params)})"
    if isinstance(params, dict):
        return f"dict(keys={list(params.keys())})"
    return type(params).__name__


def _preview_tool_result_for_logs(value: Any) -> str:
    raw = str(value)
    compact = " ".join(raw.split())
    if len(compact) <= MAX_LOG_TOOL_RESULT_CHARS:
        return compact
    return f"{compact[:MAX_LOG_TOOL_RESULT_CHARS]}..."


def build_user_profile_tools(user_id: str) -> dict[str, Any]:
    """Build the user-profile memory tools bound to a specific user.

    The returned async tools read and write the user's profile directly in
    Azure Cosmos DB, so Cosmos is the single source of truth — there is no
    per-session copy and no frontend round-trip to keep in sync. Returned
    keyed by tool name so callers can expose ``get_user_profile`` and/or
    ``save_user_profile`` independently.
    """
    from user_data import get_user_profile_repository

    async def get_user_profile() -> str:
        """Return the user's saved profile (name, preferences, notes) as JSON, or a message if none is stored yet."""
        profile = await get_user_profile_repository().get(user_id, user_id)
        if not profile:
            return (
                "No user profile found. Please ask the user for their name "
                "and any preferences or interests they'd like you to remember."
            )
        return json.dumps(profile)

    async def save_user_profile(name: str, preferences: str = "", notes: str = "") -> str:
        """Save or update the user profile. Returns confirmation or a validation error.

        Args:
            name: The user's display name (e.g. "Alex").
            preferences: Comma-separated list of things the user likes or prefers (e.g. "concise answers, dark mode, Python").
            notes: Any additional notes about the user to remember across sessions.
        """
        if not name or not name.strip():
            return "Error: name must not be empty."
        profile = {
            "name": name.strip(),
            "preferences": preferences.strip(),
            "notes": notes.strip(),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        await get_user_profile_repository().upsert(user_id, user_id, profile)
        return f"User profile saved successfully: {json.dumps(profile)}"

    return {"get_user_profile": get_user_profile, "save_user_profile": save_user_profile}


def build_create_skill_tool(user_id: str) -> Any:
    """Build the skill-creation tool bound to an authenticated owner."""
    from definition_creation import SkillCreationRequest, SkillCreationService

    async def create_skill(name: str, description: str, content: str) -> dict[str, Any]:
        """Create a durable user-owned skill without overwriting an existing definition."""
        result = await SkillCreationService(user_id).create(SkillCreationRequest(
            name=name, description=description, content=content
        ))
        return result.model_dump(exclude_none=True)

    return create_skill


def build_edit_skill_tool(user_id: str) -> Any:
    """Build the skill-editing tool bound to an authenticated owner."""
    from definition_creation import SkillCreationRequest, SkillCreationService

    async def edit_skill(name: str, description: str, content: str) -> dict[str, Any]:
        """Replace an existing user-owned skill's description and instructions."""
        result = await SkillCreationService(user_id).update(SkillCreationRequest(
            name=name, description=description, content=content
        ))
        return result.model_dump(exclude_none=True)

    return edit_skill


def build_create_agent_tool(user_id: str) -> Any:
    """Build the custom-agent creation tool bound to an authenticated owner."""
    from definition_creation import (
        AgentCreationRequest,
        AgentCreationService,
        AgentToolRefRequest,
        HttpMcpServerRequest,
        StarterQuestionRequest,
    )

    async def create_agent(
        id: str,
        name: str,
        systemPrompt: str,
        description: str = "",
        group: str = "",
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        mcpServers: list[HttpMcpServerRequest] | None = None,
        useSearchContext: bool = False,
        icon: str = "/favicon.png",
        starters: list[StarterQuestionRequest] | None = None,
        temperature: float = 0.2,
        agentsAsTools: list[AgentToolRefRequest] | None = None,
    ) -> dict[str, Any]:
        """Create a durable user-owned custom agent without overwriting an existing definition."""
        result = await AgentCreationService(user_id).create(AgentCreationRequest(
            id=id,
            name=name,
            description=description,
            group=group,
            systemPrompt=systemPrompt,
            tools=tools or [],
            skills=skills or [],
            mcpServers=mcpServers or [],
            useSearchContext=useSearchContext,
            icon=icon,
            starters=starters or [],
            temperature=temperature,
            agentsAsTools=agentsAsTools or [],
        ))
        return result.model_dump(exclude_none=True)

    return create_agent


def build_edit_agent_tool(user_id: str) -> Any:
    """Build the custom-agent editing tool bound to an authenticated owner."""
    from definition_creation import (
        AgentCreationRequest,
        AgentCreationService,
        AgentToolRefRequest,
        HttpMcpServerRequest,
        StarterQuestionRequest,
    )

    async def edit_agent(
        id: str,
        name: str,
        systemPrompt: str,
        description: str = "",
        group: str = "",
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        mcpServers: list[HttpMcpServerRequest] | None = None,
        useSearchContext: bool = False,
        icon: str = "/favicon.png",
        starters: list[StarterQuestionRequest] | None = None,
        temperature: float = 0.2,
        agentsAsTools: list[AgentToolRefRequest] | None = None,
    ) -> dict[str, Any]:
        """Replace an existing user-owned custom agent using its complete definition."""
        result = await AgentCreationService(user_id).update(AgentCreationRequest(
            id=id,
            name=name,
            description=description,
            group=group,
            systemPrompt=systemPrompt,
            tools=tools or [],
            skills=skills or [],
            mcpServers=mcpServers or [],
            useSearchContext=useSearchContext,
            icon=icon,
            starters=starters or [],
            temperature=temperature,
            agentsAsTools=agentsAsTools or [],
        ))
        return result.model_dump(exclude_none=True)

    return edit_agent


def build_render_agent_view_tool(user_id: str, session_id: str) -> Any:
    """Build the dynamic-UI rendering tool bound to an owner and conversation.

    Both ids are closed over rather than accepted as parameters so the model can
    neither choose nor forge the partition a view is written to.
    """
    from agent_views import save_view, validate_view

    async def render_agent_view(title: str, html: str) -> dict[str, Any]:
        """Show a rich HTML view in a side pane next to the chat.

        Use this when the answer is easier to read as a view than as prose — a
        comparison table, a dashboard, a grouped list, a form. Keep answering in
        chat as well; the view supplements your reply, it does not replace it.

        you should ALSO use this tool when the user asks for a visualization of 
        the answer, even if the answer is short. The view can contain a chart, 
        diagram, or other visual representation of the answer.

        The view renders isolated from the application, so it MUST be fully
        self-contained: inline <style> and <script> are supported, but external
        scripts, stylesheets, fonts, and images will NOT load. Use inline SVG and
        data: URIs for graphics. Do not use emoji — they render inconsistently.

        Style with the host theme variables so the view matches the app in both
        light and dark mode: var(--text), var(--muted), var(--border),
        var(--accent), var(--panel). Avoid hard-coded text or background colors.

        To show live data, call the async bridge from inside your markup:

            const rows = await window.agentData("get_user_profile", {});

        It resolves with that tool's result and rejects with {code, message}. Only
        the tools you already have can be requested; anything else is refused.

        Args:
            title: Short descriptive title for the pane header (120 chars max).
            html: Self-contained markup for the view.
        """
        rejection = validate_view(title, html)
        if rejection is not None:
            return rejection

        record = await save_view(
            user_id=user_id,
            conversation_id=session_id,
            title=title,
            html=html,
        )
        return {
            "status": "rendered",
            "view_id": record.id,
            "title": record.title,
            "chars": record.chars,
            "created_at": record.created_at,
        }

    return render_agent_view

