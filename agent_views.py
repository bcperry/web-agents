"""Agent-authored UI views: storage, limits, and the view data broker.

A view is HTML the agent writes with the ``render_agent_view`` tool. It renders in
a sandboxed, opaque-origin iframe on the client, so it can neither reach the host
application nor the network. When a view needs data it calls back through the
broker in this module, which executes only the tool callables already instantiated
for that agent's live session — the broker keeps no allow-list of its own, so the
agent's permissions cannot drift from what a view can reach.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r; using default=%s", name, raw, default)
        return default


MAX_AGENT_VIEW_CHARS = _env_int("MAX_AGENT_VIEW_CHARS", 250_000)
MAX_AGENT_VIEWS_PER_CONVERSATION = _env_int("MAX_AGENT_VIEWS_PER_CONVERSATION", 50)
MAX_VIEW_DATA_RESPONSE_CHARS = _env_int("MAX_VIEW_DATA_RESPONSE_CHARS", 20_000)
MAX_VIEW_DATA_REQUESTS_PER_MINUTE = _env_int("MAX_VIEW_DATA_REQUESTS_PER_MINUTE", 60)
MAX_VIEW_TITLE_CHARS = 120


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Autonomous cycles create sessions as ``autonomous-{directive_id}`` (see autonomous.py),
# which is the only signal available at render time that nobody is watching.
AUTONOMOUS_SESSION_PREFIX = "autonomous-"


def view_source(conversation_id: str) -> str:
    return "autonomous" if conversation_id.startswith(AUTONOMOUS_SESSION_PREFIX) else "chat"


@dataclass(frozen=True)
class AgentViewRecord:
    """One agent-authored view. Immutable once written — a revision is a new view."""

    id: str
    user_id: str
    conversation_id: str
    title: str
    html: str
    profile_id: str
    created_at: str
    chars: int
    source: str

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> "AgentViewRecord":
        return cls(
            id=str(doc.get("id", "")),
            user_id=str(doc.get("user_id", "")),
            conversation_id=str(doc.get("conversation_id", "")),
            title=str(doc.get("title", "")),
            html=str(doc.get("html", "")),
            profile_id=str(doc.get("profile_id", "")),
            created_at=str(doc.get("created_at", "")),
            chars=int(doc.get("chars", 0) or 0),
            source=str(doc.get("source", "chat")),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "title": self.title,
            "html": self.html,
            "profile_id": self.profile_id,
            "created_at": self.created_at,
            "chars": self.chars,
            "source": self.source,
        }

    def to_summary(self) -> dict[str, Any]:
        return {
            "viewId": self.id,
            "title": self.title,
            "createdAt": self.created_at,
            "chars": self.chars,
            "source": self.source,
        }

    def to_wire(self) -> dict[str, Any]:
        return {**self.to_summary(), "html": self.html}


def validate_view(title: str, html: str) -> dict[str, Any] | None:
    """Return a rejection payload for the model, or None when the view is acceptable.

    Rejection messages are phrased so the agent can correct and retry without
    further instruction.
    """
    clean_title = (title or "").strip()
    if not clean_title:
        return {
            "status": "rejected",
            "reason": "empty_title",
            "message": "The view needs a short, descriptive title.",
        }
    if len(clean_title) > MAX_VIEW_TITLE_CHARS:
        return {
            "status": "rejected",
            "reason": "title_too_long",
            "limit": MAX_VIEW_TITLE_CHARS,
            "chars": len(clean_title),
            "message": f"Shorten the title to {MAX_VIEW_TITLE_CHARS} characters or fewer.",
        }
    if not (html or "").strip():
        return {
            "status": "rejected",
            "reason": "empty_html",
            "message": "The view has no content. Provide self-contained HTML markup.",
        }
    if len(html) > MAX_AGENT_VIEW_CHARS:
        return {
            "status": "rejected",
            "reason": "too_large",
            "limit": MAX_AGENT_VIEW_CHARS,
            "chars": len(html),
            "message": (
                "View exceeds the size limit. Reduce inline data or split it into a smaller view."
            ),
        }
    return None


async def save_view(
    *,
    user_id: str,
    conversation_id: str,
    title: str,
    html: str,
    profile_id: str = "",
    source: str | None = None,
) -> AgentViewRecord:
    """Persist a validated view, evicting the oldest views past the per-conversation cap."""
    from user_data import get_agent_views_repository

    record = AgentViewRecord(
        id=str(uuid.uuid4()),
        user_id=user_id,
        conversation_id=conversation_id,
        title=title.strip(),
        html=html,
        profile_id=profile_id,
        created_at=_utcnow_iso(),
        chars=len(html),
        source=source or view_source(conversation_id),
    )
    repo = get_agent_views_repository()
    await repo.create(record.to_document())
    await _evict_oldest(repo, user_id, conversation_id)
    return record


async def _evict_oldest(repo: Any, user_id: str, conversation_id: str) -> None:
    existing = await repo.list_for_conversation(user_id, conversation_id)
    overflow = len(existing) - MAX_AGENT_VIEWS_PER_CONVERSATION
    for doc in existing[:overflow] if overflow > 0 else []:
        await repo.delete(user_id, str(doc.get("id", "")))


async def list_views(user_id: str, conversation_id: str) -> list[AgentViewRecord]:
    from user_data import get_agent_views_repository

    docs = await get_agent_views_repository().list_for_conversation(user_id, conversation_id)
    return [AgentViewRecord.from_document(doc) for doc in docs]


async def get_view(user_id: str, conversation_id: str, view_id: str) -> AgentViewRecord | None:
    """Return the view only when it belongs to this user *and* this conversation."""
    from user_data import get_agent_views_repository

    doc = await get_agent_views_repository().get(user_id, view_id)
    if doc is None:
        return None
    record = AgentViewRecord.from_document(doc)
    return record if record.conversation_id == conversation_id else None


async def delete_views_for_conversation(user_id: str, conversation_id: str) -> int:
    from user_data import get_agent_views_repository

    repo = get_agent_views_repository()
    docs = await repo.list_for_conversation(user_id, conversation_id)
    deleted = 0
    for doc in docs:
        if await repo.delete(user_id, str(doc.get("id", ""))):
            deleted += 1
    return deleted


# ---------------------------------------------------------------------------
# View data broker
# ---------------------------------------------------------------------------

# A view must not re-render itself; that is the one tool grant it cannot use.
BROKER_EXCLUDED_TOOLS = {"render_agent_view"}


class ViewDataRefused(Exception):
    """A view-originated request that must not execute."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", None) or getattr(tool, "__name__", "") or "")


def resolve_view_tool(session_tools: Iterable[Any], tool_name: str) -> Any | None:
    """Return the callable a view may invoke for ``tool_name``, or None.

    The rendering agent's own live tool list is the only authority here, narrowed
    to registered backend function tools — MCP servers and sub-agent tools also
    live in that list but are not callable from a view.
    """
    from app_context import function_tool_registry

    if tool_name in BROKER_EXCLUDED_TOOLS or tool_name not in function_tool_registry():
        return None
    for tool in session_tools:
        if _tool_name(tool) == tool_name and callable(tool):
            return tool
    return None


def _render_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(result)


async def execute_view_data_request(
    *,
    session_data: Any,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Run one view-originated tool call. Raises ``ViewDataRefused`` when it must not run."""
    tool = resolve_view_tool(getattr(session_data, "tools", []) or [], tool_name)
    if tool is None:
        raise ViewDataRefused(
            "not_permitted", "That data is not available to this view.", 403
        )

    try:
        result = tool(**arguments)
        if inspect.isawaitable(result):
            result = await result
    except TypeError as exc:
        raise ViewDataRefused(
            "invalid_arguments", "That request was not valid for this data source.", 400
        ) from exc
    except Exception as exc:  # noqa: BLE001 - message is sanitized before it leaves the server
        logger.error("View data tool %s failed: %s", tool_name, exc, exc_info=True)
        raise ViewDataRefused(
            "tool_failed", "That data could not be loaded right now.", 500
        ) from exc

    rendered = _render_result(result)
    truncated = len(rendered) > MAX_VIEW_DATA_RESPONSE_CHARS
    return {
        "data": rendered[:MAX_VIEW_DATA_RESPONSE_CHARS] if truncated else rendered,
        "truncated": truncated,
    }


_request_times: dict[str, list[float]] = {}


def check_view_data_budget(session_id: str) -> None:
    """Enforce the per-session request budget. Raises ``ViewDataRefused`` when spent."""
    now = time.monotonic()
    recent = [t for t in _request_times.get(session_id, []) if now - t < 60.0]
    if len(recent) >= MAX_VIEW_DATA_REQUESTS_PER_MINUTE:
        _request_times[session_id] = recent
        raise ViewDataRefused(
            "rate_limited", "This view is requesting data too quickly. Try again shortly.", 429
        )
    recent.append(now)
    _request_times[session_id] = recent


def clear_view_data_budget(session_id: str) -> None:
    _request_times.pop(session_id, None)


__all__ = [
    "MAX_AGENT_VIEWS_PER_CONVERSATION",
    "MAX_AGENT_VIEW_CHARS",
    "MAX_VIEW_DATA_REQUESTS_PER_MINUTE",
    "MAX_VIEW_DATA_RESPONSE_CHARS",
    "MAX_VIEW_TITLE_CHARS",
    "AgentViewRecord",
    "ViewDataRefused",
    "check_view_data_budget",
    "clear_view_data_budget",
    "delete_views_for_conversation",
    "execute_view_data_request",
    "get_view",
    "list_views",
    "resolve_view_tool",
    "save_view",
    "validate_view",
    "view_source",
]
