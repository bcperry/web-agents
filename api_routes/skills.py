"""Skill catalog endpoints."""

import logging

from agent_framework._types import Content, Message as ChatMessage
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from auth import AuthenticatedUser, get_current_user
from definition_creation import SkillCreationRequest
from skills_manager import SkillManager

logger = logging.getLogger(__name__)
router = APIRouter()


class SkillUpdateRequest(BaseModel):
    description: str
    content: str


class SkillResponse(BaseModel):
    name: str
    description: str
    content: str


class SkillGenerateRequest(BaseModel):
    name: str | None = None
    description: str


class SkillGenerateResponse(BaseModel):
    content: str


@router.get("/api/skills")
async def get_skills(user: AuthenticatedUser = Depends(get_current_user)):
    return {"skills": await SkillManager(user_id=user.user_id).list_summaries()}


@router.post("/api/skills/generate", response_model=SkillGenerateResponse)
async def generate_skill_content(
    body: SkillGenerateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    description = (body.description or "").strip()
    if not description:
        raise HTTPException(status_code=422, detail="description is required")
    if len(description) > 2048:
        raise HTTPException(status_code=422, detail="description must be ≤ 2048 characters")
    skill_name = (body.name or "new-skill").strip() or "new-skill"

    from agent_factory import build_chat_client

    system_prompt = (
        "You are an expert at writing concise, well-structured Markdown skill "
        "instructions for AI agents. Given a short skill description, produce "
        "the BODY of a SKILL.md file (Markdown only, no YAML frontmatter, no "
        "code fences wrapping the whole document). Use clear headings, bullet "
        "points, and short examples where helpful. Be practical and "
        "actionable. Do not include any preamble or commentary — output the "
        "Markdown body directly."
    )
    user_prompt = (
        f"Skill name: {skill_name}\n"
        f"Skill description: {description}\n\n"
        "Write the SKILL.md body now."
    )

    try:
        client = build_chat_client()
        response = await client.get_response(
            messages=[
                ChatMessage(role="system", contents=[Content(type="text", text=system_prompt)]),
                ChatMessage(role="user", contents=[Content(type="text", text=user_prompt)]),
            ],
        )
    except Exception as exc:  # noqa: BLE001 - route maps provider errors to HTTP
        logger.exception("Skill content generation failed")
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {exc}") from exc

    text = (getattr(response, "text", "") or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="LLM returned empty content")

    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1 and text.rstrip().endswith("```"):
            text = text[first_newline + 1 : text.rstrip().rfind("```")].strip()

    if len(text) > 65536:
        text = text[:65536]

    return SkillGenerateResponse(content=text)


@router.get("/api/skills/{name}", response_model=SkillResponse)
async def get_skill(name: str, user: AuthenticatedUser = Depends(get_current_user)):
    return SkillResponse(**await SkillManager(user_id=user.user_id).get(name))


@router.post("/api/skills", response_model=SkillResponse, status_code=201)
async def create_skill(body: SkillCreationRequest, user: AuthenticatedUser = Depends(get_current_user)):
    return SkillResponse(**await SkillManager().create(body.name, body.description, body.content))


@router.put("/api/skills/{name}", response_model=SkillResponse)
async def update_skill(name: str, body: SkillUpdateRequest, user: AuthenticatedUser = Depends(get_current_user)):
    return SkillResponse(**await SkillManager().update(name, body.description, body.content))


@router.delete("/api/skills/{name}", status_code=204)
async def delete_skill(name: str, user: AuthenticatedUser = Depends(get_current_user)):
    await SkillManager().delete(name)
    return Response(status_code=204)