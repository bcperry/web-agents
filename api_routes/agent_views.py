"""Agent view endpoints: read stored views and broker their data requests.

Every endpoint re-verifies that the caller owns the conversation before touching
anything, and returns 404 for both "missing" and "not yours" so the API never
reveals that another user's conversation exists.
"""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from agent_views import (
    ViewDataRefused,
    check_view_data_budget,
    execute_view_data_request,
    get_view,
    list_views,
)
from auth import AuthenticatedUser, get_current_user
from cosmos_memory import get_conversation_repository
from session_data import _sessions
from validators import validate_view_data_request

logger = logging.getLogger(__name__)
router = APIRouter()


async def _require_owned_conversation(user_id: str, session_id: str) -> None:
    repo = get_conversation_repository()
    try:
        owned = await repo.get_owned(user_id, session_id)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Conversation lookup failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Conversation store is temporarily unavailable. Please try again.",
        ) from exc
    if owned is None:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("/api/sessions/{session_id}/views")
async def list_agent_views(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    await _require_owned_conversation(user.user_id, session_id)
    try:
        records = await list_views(user.user_id, session_id)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Failed to list views for %s: %s", session_id, exc)
        raise HTTPException(
            status_code=503,
            detail="View store is temporarily unavailable. Please try again.",
        ) from exc
    return {"views": [record.to_summary() for record in records]}


@router.get("/api/sessions/{session_id}/views/{view_id}")
async def get_agent_view(
    session_id: str,
    view_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    await _require_owned_conversation(user.user_id, session_id)
    try:
        record = await get_view(user.user_id, session_id, view_id)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Failed to load view %s: %s", view_id, exc)
        raise HTTPException(
            status_code=503,
            detail="View store is temporarily unavailable. Please try again.",
        ) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="View not found")
    return record.to_wire()


def _audit(session_data, *, user_id, session_id, view_id, tool, outcome, reason, duration_ms):
    logger.info(
        "View data request session=%s view=%s user=%s tool=%s outcome=%s reason=%s duration_ms=%s",
        session_id, view_id, user_id, tool, outcome, reason or "-", duration_ms,
    )
    trace_logger = getattr(session_data, "eval_trace_logger", None) if session_data else None
    if trace_logger is not None and getattr(trace_logger, "enabled", False):
        trace_logger.log({
            "session_id": session_id,
            "chat_profile": getattr(session_data, "profile_id", ""),
            "source": "agent_view",
            "view_id": view_id,
            "tool_events": [{"name": tool, "outcome": outcome, "reason": reason}],
        })


@router.post("/api/sessions/{session_id}/views/{view_id}/data")
async def request_agent_view_data(
    session_id: str,
    view_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Execute one tool call on behalf of a rendered view.

    The rendering agent's live tool list is the only authority for what may run,
    and the caller's token is the only identity used — nothing in the body can
    change either.
    """
    await _require_owned_conversation(user.user_id, session_id)

    record = await get_view(user.user_id, session_id, view_id)
    if record is None:
        raise HTTPException(status_code=404, detail="View not found")

    body = await request.json()
    tool = body.get("tool")
    arguments = body.get("arguments") or {}
    session_data = _sessions.get(session_id)

    def refuse(code: str, message: str, status_code: int) -> JSONResponse:
        _audit(
            session_data, user_id=user.user_id, session_id=session_id, view_id=view_id,
            tool=tool, outcome="refused", reason=code, duration_ms=0,
        )
        return JSONResponse(
            status_code=status_code,
            content={"ok": False, "error": {"code": code, "message": message}},
        )

    shape_error = validate_view_data_request(tool, arguments)
    if shape_error:
        return refuse("invalid_arguments", shape_error, 400)

    if session_data is None:
        return refuse(
            "session_inactive",
            "This conversation is no longer active. Reopen it and try again.",
            409,
        )

    started = time.monotonic()
    try:
        check_view_data_budget(session_id)
        result = await execute_view_data_request(
            session_data=session_data, tool_name=tool, arguments=arguments
        )
    except ViewDataRefused as refusal:
        response = refuse(refusal.code, refusal.message, refusal.status_code)
        if refusal.code == "rate_limited":
            response.headers["Retry-After"] = "60"
        return response

    duration_ms = int((time.monotonic() - started) * 1000)
    _audit(
        session_data, user_id=user.user_id, session_id=session_id, view_id=view_id,
        tool=tool, outcome="fulfilled", reason=None, duration_ms=duration_ms,
    )
    return {
        "ok": True,
        "data": result["data"],
        "truncated": result["truncated"],
        "durationMs": duration_ms,
    }
