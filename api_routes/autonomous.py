"""Autonomous mode endpoints."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app_context import DEFAULT_MAX_USER_INPUT_CHARS, session_context
from auth import AuthenticatedUser, get_current_user
from autonomous import (
    Directive,
    directive_to_wire,
    get_autonomous_config,
    run_autonomous_cycle,
    validate_directive_id,
    validate_notify_webhook,
    validate_profile_id,
    validate_schedule,
)
from autonomous_scheduler import scheduler_enabled
from cosmos_memory import get_autonomous_directive_repository, get_autonomous_run_repository

logger = logging.getLogger(__name__)
router = APIRouter()


class AutonomousRunNowRequest(BaseModel):
    directive_id: str | None = None


class DirectiveCreateRequest(BaseModel):
    id: str
    profile_id: str
    instruction: str
    schedule: str | None = None
    enabled: bool = True
    notify_webhook: str | None = None


class DirectiveUpdateRequest(BaseModel):
    profile_id: str | None = None
    instruction: str | None = None
    schedule: str | None = None
    enabled: bool | None = None
    notify_webhook: str | None = None


def _validated_schedule(raw: str | None) -> str | None:
    schedule = (raw or "").strip() or None
    if schedule is not None:
        try:
            validate_schedule(schedule)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schedule


def _validated_instruction(raw: str) -> str:
    instruction = (raw or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction is required")
    if len(instruction) > DEFAULT_MAX_USER_INPUT_CHARS:
        raise HTTPException(status_code=400, detail="instruction is too long")
    return instruction


def _validated_notify(raw: str | None) -> dict[str, str] | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return validate_notify_webhook(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/autonomous/run-now")
async def autonomous_run_now(
    body: AutonomousRunNowRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Run one autonomous cycle on demand. The only HTTP trigger."""
    config = await get_autonomous_config()
    if not config.enabled:
        raise HTTPException(status_code=409, detail="Autonomous mode is disabled")

    if body.directive_id:
        directive = config.find_directive(body.directive_id)
        if directive is None or not directive.enabled:
            raise HTTPException(status_code=404, detail="Directive not found or not enabled")
    else:
        enabled = config.enabled_directives()
        if not enabled:
            raise HTTPException(status_code=409, detail="No enabled directives are configured")
        directive = enabled[0]

    record = await run_autonomous_cycle(
        session_context, directive, trigger="manual", logger=logger, config=config
    )
    return record.to_wire()


@router.get("/api/autonomous/runs")
async def list_autonomous_runs(
    user: AuthenticatedUser = Depends(get_current_user),
    limit: int = 50,
    directive_id: str | None = None,
):
    """List autonomous run history, most-recent-first."""
    bounded = max(1, min(int(limit or 50), 200))
    try:
        records = await get_autonomous_run_repository().list_runs(
            limit=bounded, directive_id=directive_id
        )
    except Exception as exc:  # noqa: BLE001 - route maps store errors to HTTP
        logger.error("Failed to list autonomous runs: %s", exc)
        raise HTTPException(status_code=503, detail="Autonomous run store is temporarily unavailable. Please try again.") from exc
    return {"runs": [record.to_wire() for record in records], "count": len(records)}


@router.get("/api/autonomous/directives")
async def list_autonomous_directives(
    user: AuthenticatedUser = Depends(get_current_user),
):
    """List the configured directives (no secrets) for all authenticated users."""
    config = await get_autonomous_config()
    return {
        "enabled": config.enabled,
        "schedulerEnabled": scheduler_enabled(),
        "systemUserId": config.system_user_id,
        "directives": [directive_to_wire(directive) for directive in config.directives],
    }


@router.post("/api/autonomous/directives", status_code=201)
async def create_autonomous_directive(
    body: DirectiveCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a new automation directive."""
    repo = get_autonomous_directive_repository()
    try:
        directive_id = validate_directive_id(body.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        validate_profile_id(body.profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if await repo.get(directive_id) is not None:
        raise HTTPException(status_code=409, detail=f"Directive '{directive_id}' already exists")

    now = datetime.now(timezone.utc).isoformat()
    directive = Directive(
        id=directive_id,
        profile_id=body.profile_id,
        instruction=_validated_instruction(body.instruction),
        schedule=_validated_schedule(body.schedule),
        enabled=bool(body.enabled),
        notify=_validated_notify(body.notify_webhook),
        created_at=now,
        updated_at=now,
    )
    await repo.upsert(directive.to_doc())
    logger.info("Autonomous directive created: %s", directive_id)
    return directive_to_wire(directive)


@router.patch("/api/autonomous/directives/{directive_id}")
async def update_autonomous_directive(
    directive_id: str,
    body: DirectiveUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Update an automation: enable/disable, schedule, instruction, profile, or notify."""
    repo = get_autonomous_directive_repository()
    existing = await repo.get(directive_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Directive not found")
    current = Directive.from_doc(existing)
    fields = body.model_dump(exclude_unset=True)

    profile_id = current.profile_id
    if "profile_id" in fields and fields["profile_id"] is not None:
        try:
            validate_profile_id(fields["profile_id"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        profile_id = fields["profile_id"]

    instruction = current.instruction
    if "instruction" in fields and fields["instruction"] is not None:
        instruction = _validated_instruction(fields["instruction"])

    schedule = current.schedule
    if "schedule" in fields:
        schedule = _validated_schedule(fields["schedule"])

    enabled = current.enabled
    if "enabled" in fields and fields["enabled"] is not None:
        enabled = bool(fields["enabled"])

    notify = current.notify
    if "notify_webhook" in fields:
        notify = _validated_notify(fields["notify_webhook"])

    now = datetime.now(timezone.utc).isoformat()
    updated = Directive(
        id=current.id,
        profile_id=profile_id,
        instruction=instruction,
        schedule=schedule,
        enabled=enabled,
        notify=notify,
        created_at=current.created_at or now,
        updated_at=now,
    )
    await repo.upsert(updated.to_doc())
    logger.info("Autonomous directive updated: %s (enabled=%s)", directive_id, enabled)
    return directive_to_wire(updated)


@router.delete("/api/autonomous/directives/{directive_id}", status_code=204)
async def delete_autonomous_directive(
    directive_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Delete an automation. A YAML-default directive reappears on next startup."""
    deleted = await get_autonomous_directive_repository().delete(directive_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Directive not found")
    logger.info("Autonomous directive deleted: %s", directive_id)
    return None