"""Shared strict validation and persistence for agent-authored definitions."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from azure.cosmos.exceptions import CosmosResourceExistsError
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

import cosmos_memory
import user_data
from prompt_config import load_agents_yaml
from skills_manager import SkillManager
from validators import validate_http_mcp_servers

logger = logging.getLogger(__name__)
_AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_MAX_PROMPT_CHARS = int(os.getenv("MAX_USER_INPUT_CHARS", "8000"))


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ValidationIssue(BaseModel):
    field: str
    reason: str


class CreatedResult(BaseModel):
    status: Literal["created"] = "created"
    kind: Literal["skill", "agent"]
    id: str
    name: str
    message: str


class UpdatedResult(BaseModel):
    status: Literal["updated"] = "updated"
    kind: Literal["skill", "agent"]
    id: str
    name: str
    message: str


class ErrorResult(BaseModel):
    status: Literal["error"] = "error"
    kind: Literal["skill", "agent"]
    code: Literal["validation_error", "duplicate", "not_found", "unauthorized", "temporarily_unavailable"]
    message: str
    retryable: bool
    issues: list[ValidationIssue] | None = None


CreationResult = CreatedResult | UpdatedResult | ErrorResult


class SkillCreationRequest(BaseModel):
    name: str
    description: str
    content: str


class StarterQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=100, description="Short button label shown to the user.")
    message: str = Field(min_length=1, max_length=2000, description="Complete user message sent when selected.")


class HttpMcpServerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    transport: Literal["http"] = "http"
    url: str = Field(min_length=1, max_length=500)
    description: str | None = None
    authenticated: bool | None = None
    authScope: str | None = None


class BuiltinAgentRefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["builtin"]
    profileId: str = Field(min_length=1)


class CustomAgentRefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["custom"]
    customAgentId: str = Field(min_length=1)
    definition: dict[str, Any] | None = None


AgentRefRequest = Annotated[
    BuiltinAgentRefRequest | CustomAgentRefRequest,
    Field(discriminator="kind"),
]


class AgentToolRefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agentRef: AgentRefRequest


class AgentCreationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Unique lowercase slug for the agent.")
    name: str = Field(description="Display name for the agent.")
    description: str = Field(default="", description="Short description of the agent's purpose.")
    group: str = Field(default="", description="Optional group shown in the agent selector.")
    systemPrompt: str = Field(description="Complete system instructions that control the agent's behavior.")
    tools: list[str] = Field(default_factory=list, description="Exact registered tool names to enable.")
    skills: list[str] = Field(default_factory=list, description="Exact available skill names to load.")
    mcpServers: list[HttpMcpServerRequest] = Field(default_factory=list, description="HTTP MCP server definitions.")
    useSearchContext: bool = Field(default=False, description="Whether to load configured AI Search context.")
    icon: str = Field(default="/favicon.png", description="Icon URL shown in the agent selector.")
    starters: list[StarterQuestionRequest] = Field(
        default_factory=list,
        description="Suggested queries, each with a visible label and the message to send.",
    )
    temperature: float = Field(default=0.2, description="Model temperature from 0.0 to 2.0.")
    agentsAsTools: list[AgentToolRefRequest] = Field(
        default_factory=list,
        description="Other agents this agent may invoke, expressed as agentRef objects.",
    )
    source: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


def _validation_error(kind: Literal["skill", "agent"], issues: list[ValidationIssue]) -> ErrorResult:
    return ErrorResult(
        kind=kind,
        code="validation_error",
        message=f"The {kind} definition is invalid.",
        retryable=False,
        issues=issues,
    )


def _unauthorized(kind: Literal["skill", "agent"], action: str = "create") -> ErrorResult:
    return ErrorResult(
        kind=kind,
        code="unauthorized",
        message=f"An authenticated user is required to {action} a {kind}.",
        retryable=False,
    )


def _duplicate(kind: Literal["skill", "agent"], identity: str) -> ErrorResult:
    return ErrorResult(
        kind=kind,
        code="duplicate",
        message=f"A {kind} named '{identity}' already exists.",
        retryable=False,
    )


def _not_found(kind: Literal["skill", "agent"], identity: str) -> ErrorResult:
    return ErrorResult(
        kind=kind,
        code="not_found",
        message=f"No user-owned {kind} named '{identity}' exists.",
        retryable=False,
    )


def _unavailable(kind: Literal["skill", "agent"]) -> ErrorResult:
    return ErrorResult(
        kind=kind,
        code="temporarily_unavailable",
        message=f"The {kind} store is temporarily unavailable. Please try again.",
        retryable=True,
    )


class SkillCreationService:
    def __init__(self, user_id: str, global_repo: Any = None, user_repo: Any = None) -> None:
        self.user_id = user_id.strip()
        self.global_repo = global_repo or cosmos_memory.get_skill_repository()
        self.user_repo = user_repo or user_data.get_user_skills_repository()

    async def create(self, request: SkillCreationRequest) -> CreationResult:
        if not self.user_id:
            return _unauthorized("skill")
        try:
            await SkillManager(
                self.global_repo,
                user_id=self.user_id,
                user_repo=self.user_repo,
            ).create(request.name, request.description, request.content)
        except HTTPException as exc:
            if exc.status_code == 422 and isinstance(exc.detail, list):
                return _validation_error(
                    "skill",
                    [ValidationIssue.model_validate(issue) for issue in exc.detail],
                )
            if exc.status_code == 409:
                return _duplicate("skill", request.name)
            raise
        except Exception as exc:  # provider details must never reach the caller
            logger.error(
                "Definition creation failed kind=skill id=%s code=temporarily_unavailable exception=%s",
                request.name,
                exc.__class__.__name__,
            )
            return _unavailable("skill")
        return CreatedResult(
            kind="skill",
            id=request.name,
            name=request.name,
            message=f"Created skill '{request.name}'.",
        )

    async def update(self, request: SkillCreationRequest) -> CreationResult:
        if not self.user_id:
            return _unauthorized("skill", "edit")
        try:
            await SkillManager(
                self.global_repo,
                user_id=self.user_id,
                user_repo=self.user_repo,
            ).update(request.name, request.description, request.content)
        except HTTPException as exc:
            if exc.status_code == 422 and isinstance(exc.detail, list):
                return _validation_error(
                    "skill",
                    [ValidationIssue.model_validate(issue) for issue in exc.detail],
                )
            if exc.status_code == 404:
                return _not_found("skill", request.name)
            raise
        except Exception as exc:
            logger.error(
                "Definition update failed kind=skill id=%s code=temporarily_unavailable exception=%s",
                request.name,
                exc.__class__.__name__,
            )
            return _unavailable("skill")
        return UpdatedResult(
            kind="skill",
            id=request.name,
            name=request.name,
            message=f"Updated skill '{request.name}'.",
        )


class AgentCreationService:
    def __init__(
        self,
        user_id: str,
        *,
        custom_repo: Any = None,
        global_skills_repo: Any = None,
        user_skills_repo: Any = None,
    ) -> None:
        self.user_id = user_id.strip()
        self.custom_repo = custom_repo or user_data.get_custom_agents_repository()
        self.global_skills_repo = global_skills_repo or cosmos_memory.get_skill_repository()
        self.user_skills_repo = user_skills_repo or user_data.get_user_skills_repository()

    async def validate_and_normalize(
        self,
        request: AgentCreationRequest,
        *,
        existing: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[ValidationIssue]]:
        issues: list[ValidationIssue] = []
        agent_id = request.id.strip()
        name = request.name.strip()
        prompt = request.systemPrompt.strip()
        if not agent_id or not _AGENT_ID_RE.fullmatch(agent_id) or len(agent_id) > 100:
            issues.append(ValidationIssue(field="id", reason="Use a lowercase slug of at most 100 characters."))
        if not name or len(name) > 100:
            issues.append(ValidationIssue(field="name", reason="Name is required and must be at most 100 characters."))
        if not prompt or len(prompt) > _MAX_PROMPT_CHARS:
            issues.append(ValidationIssue(
                field="systemPrompt",
                reason=f"System prompt is required and must be at most {_MAX_PROMPT_CHARS} characters.",
            ))
        if not 0.0 <= request.temperature <= 2.0:
            issues.append(ValidationIssue(field="temperature", reason="Temperature must be between 0.0 and 2.0."))

        from app_context import function_tool_registry

        known_tools = set(function_tool_registry())
        for index, tool_name in enumerate(request.tools):
            if tool_name not in known_tools:
                issues.append(ValidationIssue(field=f"tools[{index}]", reason="Tool is not available."))

        skill_manager = SkillManager(
            self.global_skills_repo, user_id=self.user_id, user_repo=self.user_skills_repo
        )
        available_skills = {
            str(doc.get("name") or doc.get("id")) for doc in await skill_manager.list_documents()
        }
        for index, skill_name in enumerate(request.skills):
            if skill_name not in available_skills:
                issues.append(ValidationIssue(field=f"skills[{index}]", reason="Skill could not be resolved."))

        try:
            mcp_servers = validate_http_mcp_servers(
                [server.model_dump(exclude_none=True) for server in request.mcpServers],
                override=False,
            )
        except HTTPException as exc:
            issues.append(ValidationIssue(field="mcpServers", reason=str(exc.detail)))
            mcp_servers = []

        hydrated_refs: list[dict[str, Any]] = []
        profiles = load_agents_yaml().get("profiles") or {}
        seen_targets: set[tuple[str, str]] = set()
        for index, entry_model in enumerate(request.agentsAsTools):
            entry = entry_model.model_dump(exclude_none=True)
            field = f"agentsAsTools[{index}].agentRef"
            ref = entry.get("agentRef") if isinstance(entry, dict) else None
            if not isinstance(ref, dict):
                issues.append(ValidationIssue(field=field, reason="Sub-agent reference is required."))
                continue
            kind = ref.get("kind")
            target_id = ref.get("profileId") if kind == "builtin" else ref.get("customAgentId")
            target_id = str(target_id or "")
            key = (str(kind), target_id)
            if not target_id or kind not in {"builtin", "custom"}:
                issues.append(ValidationIssue(field=field, reason="Sub-agent could not be resolved."))
                continue
            if target_id == agent_id:
                issues.append(ValidationIssue(field=field, reason="An agent cannot reference itself."))
                continue
            if key in seen_targets:
                issues.append(ValidationIssue(field=field, reason="Sub-agent is referenced more than once."))
                continue
            seen_targets.add(key)
            if kind == "builtin":
                if target_id not in profiles:
                    issues.append(ValidationIssue(field=field, reason="Sub-agent could not be resolved."))
                    continue
                hydrated_refs.append({"agentRef": {"kind": "builtin", "profileId": target_id}})
                continue
            target = await self.custom_repo.get(self.user_id, target_id)
            if not target:
                issues.append(ValidationIssue(field=field, reason="Sub-agent could not be resolved."))
                continue
            nested = target.get("agentsAsTools") or []
            if any(
                isinstance(item, dict)
                and isinstance(item.get("agentRef"), dict)
                and (item["agentRef"].get("customAgentId") or item["agentRef"].get("profileId")) == agent_id
                for item in nested
            ):
                issues.append(ValidationIssue(field=field, reason="Direct delegated-agent cycles are not allowed."))
                continue
            hydrated_refs.append({
                "agentRef": {"kind": "custom", "customAgentId": target_id, "definition": target}
            })

        if issues:
            return None, issues
        now = _utcnow_iso()
        created_at = str((existing or {}).get("createdAt") or now)
        return {
            "id": agent_id,
            "name": name,
            "description": request.description.strip(),
            **({"group": request.group.strip()} if request.group.strip() else {}),
            "systemPrompt": prompt,
            "tools": list(request.tools),
            "skills": list(request.skills),
            "mcpServers": list(mcp_servers),
            "useSearchContext": request.useSearchContext,
            "icon": request.icon or "/favicon.png",
            "starters": [starter.model_dump() for starter in request.starters],
            "temperature": float(request.temperature),
            "agentsAsTools": hydrated_refs,
            "source": "custom",
            "createdAt": created_at,
            "updatedAt": now,
        }, []

    async def _save(
        self,
        request: AgentCreationRequest,
        *,
        overwrite: bool,
    ) -> tuple[dict[str, Any] | None, list[ValidationIssue]]:
        if not self.user_id:
            return None, [ValidationIssue(field="authorization", reason="Authentication is required.")]
        existing = (
            await self.custom_repo.get(self.user_id, request.id.strip())
            if overwrite
            else None
        )
        data, issues = await self.validate_and_normalize(request, existing=existing)
        if issues or data is None:
            return None, issues
        if overwrite:
            await self.custom_repo.upsert(self.user_id, data["id"], data)
        else:
            await self.custom_repo.create(self.user_id, data["id"], data)
        return data, []

    async def create(self, request: AgentCreationRequest) -> CreationResult:
        if not self.user_id:
            return _unauthorized("agent")
        try:
            data, issues = await self._save(request, overwrite=False)
            if issues:
                return _validation_error("agent", issues)
            assert data is not None
        except CosmosResourceExistsError:
            return _duplicate("agent", request.id)
        except Exception as exc:
            logger.error(
                "Definition creation failed kind=agent id=%s code=temporarily_unavailable exception=%s",
                request.id,
                exc.__class__.__name__,
            )
            return _unavailable("agent")
        return CreatedResult(
            kind="agent", id=data["id"], name=data["name"], message=f"Created agent '{data['name']}'."
        )

    async def upsert(self, request: AgentCreationRequest) -> tuple[dict[str, Any] | None, list[ValidationIssue]]:
        return await self._save(request, overwrite=True)

    async def update(self, request: AgentCreationRequest) -> CreationResult:
        if not self.user_id:
            return _unauthorized("agent", "edit")
        try:
            existing = await self.custom_repo.get(self.user_id, request.id.strip())
            if not existing:
                return _not_found("agent", request.id)
            data, issues = await self.validate_and_normalize(request, existing=existing)
            if issues:
                return _validation_error("agent", issues)
            assert data is not None
            await self.custom_repo.upsert(self.user_id, data["id"], data)
        except Exception as exc:
            logger.error(
                "Definition update failed kind=agent id=%s code=temporarily_unavailable exception=%s",
                request.id,
                exc.__class__.__name__,
            )
            return _unavailable("agent")
        return UpdatedResult(
            kind="agent", id=data["id"], name=data["name"], message=f"Updated agent '{data['name']}'."
        )


__all__ = [
    "AgentCreationRequest",
    "AgentCreationService",
    "AgentToolRefRequest",
    "CreatedResult",
    "ErrorResult",
    "HttpMcpServerRequest",
    "SkillCreationRequest",
    "SkillCreationService",
    "StarterQuestionRequest",
    "UpdatedResult",
    "ValidationIssue",
]