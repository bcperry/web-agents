"""Durable per-user custom agent and customization endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from auth import AuthenticatedUser, get_current_user
from definition_creation import AgentCreationRequest, AgentCreationService
from user_data import get_agent_customizations_repository, get_custom_agents_repository

logger = logging.getLogger(__name__)
router = APIRouter()

_USER_DATA_UNAVAILABLE = "User data store is temporarily unavailable. Please try again."


@router.get("/api/custom-agents")
async def list_custom_agents(user: AuthenticatedUser = Depends(get_current_user)):
    try:
        agents = await get_custom_agents_repository().list_for_user(user.user_id)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Failed to list custom agents: %s", exc)
        raise HTTPException(status_code=503, detail=_USER_DATA_UNAVAILABLE) from exc
    return {"agents": agents}


@router.put("/api/custom-agents/{agent_id}")
async def save_custom_agent(agent_id: str, request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")
    if str(body.get("id") or "") != agent_id:
        raise HTTPException(status_code=400, detail="Path agent_id must match body id")
    try:
        definition = AgentCreationRequest.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=[{
            "field": ".".join(str(part) for part in error["loc"]),
            "reason": error["msg"],
        } for error in exc.errors()]) from exc
    try:
        saved, issues = await AgentCreationService(user.user_id).upsert(definition)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Failed to save custom agent %s exception=%s", agent_id, exc.__class__.__name__)
        raise HTTPException(status_code=503, detail=_USER_DATA_UNAVAILABLE) from exc
    if issues:
        raise HTTPException(
            status_code=422,
            detail=[issue.model_dump() for issue in issues],
        )
    assert saved is not None
    return saved


@router.delete("/api/custom-agents/{agent_id}", status_code=204)
async def delete_custom_agent(agent_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    try:
        await get_custom_agents_repository().delete(user.user_id, agent_id)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Failed to delete custom agent %s: %s", agent_id, exc)
        raise HTTPException(status_code=503, detail=_USER_DATA_UNAVAILABLE) from exc
    return None


@router.get("/api/agent-customizations")
async def list_agent_customizations(user: AuthenticatedUser = Depends(get_current_user)):
    try:
        overrides = await get_agent_customizations_repository().list_for_user(user.user_id)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Failed to list agent customizations: %s", exc)
        raise HTTPException(status_code=503, detail=_USER_DATA_UNAVAILABLE) from exc
    return {"overrides": overrides}


@router.put("/api/agent-customizations/{base_profile_id}")
async def save_agent_customization(base_profile_id: str, request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")
    try:
        saved = await get_agent_customizations_repository().upsert(user.user_id, base_profile_id, body)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Failed to save agent customization %s: %s", base_profile_id, exc)
        raise HTTPException(status_code=503, detail=_USER_DATA_UNAVAILABLE) from exc
    return saved


@router.delete("/api/agent-customizations/{base_profile_id}", status_code=204)
async def delete_agent_customization(base_profile_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    try:
        await get_agent_customizations_repository().delete(user.user_id, base_profile_id)
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Failed to delete agent customization %s: %s", base_profile_id, exc)
        raise HTTPException(status_code=503, detail=_USER_DATA_UNAVAILABLE) from exc
    return None