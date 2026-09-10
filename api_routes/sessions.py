"""Chat session and conversation endpoints."""

import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from agent_framework._types import Content
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from agent_views import clear_view_data_budget, delete_views_for_conversation
from app_context import DEFAULT_MAX_USER_INPUT_CHARS, session_context
from auth import AuthenticatedUser, get_current_user
from cosmos_memory import get_conversation_repository, get_history_provider
from session_data import close_session, get_session
from session_orchestration import create_chat_session
from streaming import (
    USAGE_INPUT_KEY,
    USAGE_OUTPUT_KEY,
    USAGE_TOTAL_KEY,
    is_context_length_error,
    is_retryable_error,
    merge_usage,
    messages_to_wire,
    sse_event,
    stream_agent_response,
    usage_value,
    with_user_time,
)
from validators import validate_uploaded_images

logger = logging.getLogger(__name__)
session_cleanup_logger = logging.getLogger("main")
router = APIRouter()


@router.post("/api/sessions", status_code=201)
async def create_session(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        body = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Body must be valid JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")
    return await create_chat_session(
        session_context,
        body=body,
        auth_header=request.headers.get("authorization", ""),
        user=user,
        logger=logger,
    )


@router.post("/api/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    session_data = get_session(session_id, user.user_id)

    content_type = request.headers.get("content-type", "")
    text_content = ""
    client_time = ""
    image_files: list[UploadFile] = []
    image_data_list: list[bytes] = []

    if "multipart/form-data" in content_type:
        form = await request.form()
        text_content = str(form.get("content", ""))
        client_time = str(form.get("client_time", ""))
        for item in form.getlist("images"):
            if hasattr(item, "read"):
                data = await item.read()
                image_files.append(item)
                image_data_list.append(data)
    else:
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Body must be valid JSON") from exc
        if not isinstance(body, dict) or not isinstance(body.get("content", ""), str):
            raise HTTPException(status_code=400, detail="Body must be an object with string content")
        text_content = body.get("content", "")
        client_time = str(body.get("client_time", "") or "")

    if len(text_content) > DEFAULT_MAX_USER_INPUT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Input exceeds maximum length of {DEFAULT_MAX_USER_INPUT_CHARS:,} characters.",
        )

    if image_files:
        error = validate_uploaded_images(image_files, image_data_list)
        if error:
            raise HTTPException(status_code=400, detail=error)

    when = client_time.strip() or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    model_text = with_user_time(text_content, when) if text_content.strip() else text_content
    contents: list[Content] = [Content.from_text(model_text)]
    for file, data in zip(image_files, image_data_list):
        mime = file.content_type or "image/jpeg"
        contents.append(Content.from_data(data=data, media_type=mime))

    current_context_chars = len(text_content)
    ctx = session_data.context_usage
    ctx["request_count"] += 1
    ctx["sum_context_chars"] += current_context_chars
    ctx["max_context_chars"] = max(ctx["max_context_chars"], current_context_chars)
    ctx["last_context_chars"] = current_context_chars

    async def generate() -> AsyncGenerator[str, None]:
        try:
            conversations = get_conversation_repository()
            candidate_title = " ".join((text_content or "").split())[:60]
            await conversations.touch(session_data.user_id, session_id, title=candidate_title or None)
        except Exception:  # noqa: BLE001 - title update should not interrupt streaming
            logger.warning("Failed to update conversation index for %s", session_id, exc_info=True)

        result = {}
        try:
            async for event in stream_agent_response(session_data.agent, contents, session_data.agent_session, result=result):
                yield event
        except Exception as exc:  # noqa: BLE001 - route translates stream errors to SSE
            if is_retryable_error(exc):
                logger.error("Rate limit error: %s", exc)
                yield sse_event("error", {
                    "message": "The AI service is currently experiencing high demand. Please try again in a moment.",
                    "retry_after": 30,
                })
            elif is_context_length_error(exc):
                logger.error("Context length exceeded: %s", exc)
                yield sse_event("error", {
                    "message": "The request exceeded model context limits. Please shorten your prompt or start a new chat.",
                    "retry_after": None,
                })
            elif image_files:
                logger.error("Error processing image message: %s", exc, exc_info=True)
                yield sse_event("error", {
                    "message": "One or more images could not be processed. Please try again or use a different image.",
                    "retry_after": None,
                })
            else:
                logger.error("Error processing message: %s", exc, exc_info=True)
                yield sse_event("error", {
                    "message": "An error occurred while processing your request. Please try again.",
                    "retry_after": None,
                })
            yield sse_event("done", {})
            return

        if result:
            request_usage = result.get("usage")
            if request_usage:
                session_data.usage = merge_usage(session_data.usage, request_usage)
                logger.info(
                    "Request token usage - Input: %s, Output: %s, Total: %s",
                    usage_value(request_usage, USAGE_INPUT_KEY),
                    usage_value(request_usage, USAGE_OUTPUT_KEY),
                    usage_value(request_usage, USAGE_TOTAL_KEY),
                )

            if session_data.eval_trace_logger.enabled:
                session_data.eval_trace_logger.log({
                    "session_id": session_id,
                    "chat_profile": session_data.profile_id,
                    "prompt_logical_profile": session_data.prompt_logical_profile,
                    "prompt_manifest": {},
                    "input": text_content,
                    "output": result.get("text", ""),
                    "tool_events": result.get("tool_events", []),
                    "tool_names_available": [getattr(tool, "name", str(tool)) for tool in session_data.tools],
                    "usage": {
                        USAGE_INPUT_KEY: usage_value(request_usage, USAGE_INPUT_KEY),
                        USAGE_OUTPUT_KEY: usage_value(request_usage, USAGE_OUTPUT_KEY),
                        USAGE_TOTAL_KEY: usage_value(request_usage, USAGE_TOTAL_KEY),
                    } if request_usage else {},
                    "context_usage": session_data.context_usage,
                })

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.delete("/api/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    session_data = get_session(session_id, user.user_id)
    await close_session(session_id, expected=session_data)

    if session_data.usage:
        session_cleanup_logger.info(
            "Session %s ended — Token usage - Input: %s, Output: %s, Total: %s",
            session_id,
            usage_value(session_data.usage, USAGE_INPUT_KEY),
            usage_value(session_data.usage, USAGE_OUTPUT_KEY),
            usage_value(session_data.usage, USAGE_TOTAL_KEY),
        )

    return None


@router.get("/api/conversations")
async def list_conversations(
    user: AuthenticatedUser = Depends(get_current_user),
    limit: int = 50,
    cursor: str | None = None,
):
    repo = get_conversation_repository()
    bounded = max(1, min(int(limit or 50), 200))
    try:
        records, next_cursor = await repo.list_for_user(user.user_id, limit=bounded, cursor=cursor)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Failed to list conversations: %s", exc)
        raise HTTPException(status_code=503, detail="Conversation store is temporarily unavailable. Please try again.") from exc
    return {"conversations": [record.to_wire() for record in records], "nextCursor": next_cursor}


@router.get("/api/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    repo = get_conversation_repository()
    try:
        owned = await repo.get_owned(user.user_id, conversation_id)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Conversation lookup failed: %s", exc)
        raise HTTPException(status_code=503, detail="Conversation store is temporarily unavailable. Please try again.") from exc
    if owned is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    history_provider = get_history_provider()
    try:
        stored = await history_provider.get_messages(conversation_id)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Failed to load messages for %s: %s", conversation_id, exc)
        raise HTTPException(status_code=503, detail="Conversation store is temporarily unavailable. Please try again.") from exc
    return {
        "id": owned.id,
        "profileId": owned.profile_id,
        "profileName": owned.profile_name,
        "messages": messages_to_wire(stored or []),
    }


@router.delete("/api/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    repo = get_conversation_repository()
    try:
        owned = await repo.get_owned(user.user_id, conversation_id)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Conversation lookup failed: %s", exc)
        raise HTTPException(status_code=503, detail="Conversation store is temporarily unavailable. Please try again.") from exc
    if owned is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    history_provider = get_history_provider()
    try:
        await history_provider.clear(conversation_id)
        await delete_views_for_conversation(user.user_id, conversation_id)
        await repo.delete(user.user_id, conversation_id)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Failed to delete conversation %s: %s", conversation_id, exc)
        raise HTTPException(status_code=503, detail="Conversation store is temporarily unavailable. Please try again.") from exc

    clear_view_data_budget(conversation_id)
    await close_session(conversation_id)
    return None