import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence, overload

from agent_framework import CompactionProvider, InMemoryHistoryProvider, SkillsProvider
from agent_framework import Agent as RuntimeAgent
from agent_framework._compaction import (
    CharacterEstimatorTokenizer,
    SlidingWindowStrategy,
    SummarizationStrategy,
    TokenBudgetComposedStrategy,
    ToolResultCompactionStrategy,
)
from agent_framework.openai import OpenAIChatClient

from dotenv import load_dotenv


from pydantic import BaseModel

from prompt_config import load_agent_profile
from mcp_servers import get_search_context_provider


class AgentBase(BaseModel):
    name: str
    instructions: str
    description: str
    token_budget: int = 16_000
    tools: list[str] | None = None


@dataclass(frozen=True)
class ChatRuntime:
    agent: RuntimeAgent
    session: Any
    tools: list[Any]
    prompt_manifest: dict[str, str]
    prompt_logical_profile: str


load_dotenv()
logger = logging.getLogger(__name__)


def _sanitize_agent_name(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_")
    return sanitized or "agent"


def _resolve_enabled_tools(
    profile_tool_names: list[str],
    function_tools: Sequence[Any],
) -> list[Any]:
    """Filter function_tools to only those named in the agent profile."""
    enabled = set(profile_tool_names)
    return [
        t for t in function_tools
        if getattr(t, "name", None) in enabled
        or getattr(t, "__name__", None) in enabled
    ]


_DEFAULT_TEMPERATURE = 0.2

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def _build_skills_provider(
    skill_names: list[str] | None = None,
) -> SkillsProvider | None:
    """Build a SkillsProvider filtered to the requested skill names.

    Returns None if no skills are requested or the skills directory does not exist.
    """
    if not skill_names or not _SKILLS_DIR.is_dir():
        return None

    provider = SkillsProvider(skill_paths=_SKILLS_DIR)

    # Filter to only the requested skills
    discovered = set(provider._skills.keys())
    requested = set(skill_names)
    missing = requested - discovered
    if missing:
        logger.warning("Requested skills not found in %s: %s", _SKILLS_DIR, missing)

    # Remove skills that weren't requested
    to_remove = discovered - requested
    for name in to_remove:
        del provider._skills[name]

    if not provider._skills:
        return None

    return provider


def _get_default_temperature() -> float:
    """Read LLM_TEMPERATURE env var, clamped to [0.0, 2.0]. Defaults to 0.2."""
    raw = os.getenv("LLM_TEMPERATURE")
    if raw is None:
        return _DEFAULT_TEMPERATURE
    try:
        val = float(raw)
    except (ValueError, TypeError):
        logger.warning("Invalid LLM_TEMPERATURE=%r, using default %.1f", raw, _DEFAULT_TEMPERATURE)
        return _DEFAULT_TEMPERATURE
    return max(0.0, min(2.0, val))


def _build_context_providers(
    token_budget: int,
    summarizer_client: OpenAIChatClient | None = None,
    logical_profile: str | None = None,
    enable_search_context: bool = False,
    skill_names: list[str] | None = None,
) -> list[Any]:
    summarizer = summarizer_client or OpenAIChatClient()
    tokenizer = CharacterEstimatorTokenizer()

    pipeline = TokenBudgetComposedStrategy(
        token_budget=token_budget,
        tokenizer=tokenizer,
        strategies=[
            ToolResultCompactionStrategy(keep_last_tool_call_groups=1),
            SummarizationStrategy(client=summarizer, target_count=4, threshold=2),
            SlidingWindowStrategy(keep_last_groups=20),
        ],
    )

    history = InMemoryHistoryProvider(skip_excluded=True)
    compaction = CompactionProvider(
        before_strategy=pipeline,
        after_strategy=pipeline,
        tokenizer=tokenizer,
        history_source_id=history.source_id,
    )

    providers: list[Any] = [history, compaction]
    if enable_search_context:
        providers.append(get_search_context_provider())

    skills_provider = _build_skills_provider(skill_names)
    if skills_provider is not None:
        providers.append(skills_provider)

    return providers


def _create_agent(
    *,
    name: str,
    instructions: str,
    description: str,
    token_budget: int,
    temperature: float,
    tools: Sequence[Any] | None = None,
    client: OpenAIChatClient | None = None,
    summarizer_client: OpenAIChatClient | None = None,
    logical_profile: str | None = None,
    enable_search_context: bool = False,
    skill_names: list[str] | None = None,
) -> RuntimeAgent:
    runtime_client = client or OpenAIChatClient()

    return runtime_client.as_agent(
        name=_sanitize_agent_name(name),
        instructions=instructions,
        description=description,
        tools=tools,
        default_options={"temperature": temperature},
        context_providers=_build_context_providers(
            token_budget=token_budget,
            summarizer_client=summarizer_client,
            logical_profile=logical_profile,
            enable_search_context=enable_search_context,
            skill_names=skill_names,
        ),
    )


@overload
def spawn_agent(agent: AgentBase, /) -> RuntimeAgent: ...


@overload
def spawn_agent(
    *,
    name: str,
    instructions: str,
    description: str,
    token_budget: int = 16_000,
    temperature: float | None = None,
    tools: Sequence[Any] | None = None,
    client: OpenAIChatClient | None = None,
    summarizer_client: OpenAIChatClient | None = None,
    logical_profile: str | None = None,
    enable_search_context: bool = False,
    skill_names: list[str] | None = None,
) -> RuntimeAgent: ...


def spawn_agent(
    agent: AgentBase | None = None,
    /,
    *,
    name: str | None = None,
    instructions: str | None = None,
    description: str | None = None,
    token_budget: int = 16_000,
    temperature: float | None = None,
    tools: Sequence[Any] | None = None,
    client: OpenAIChatClient | None = None,
    summarizer_client: OpenAIChatClient | None = None,
    logical_profile: str | None = None,
    enable_search_context: bool = False,
    skill_names: list[str] | None = None,
) -> RuntimeAgent:
    if agent is not None:
        if any(value is not None for value in (name, instructions, description)):
            raise TypeError("Pass either an agent model or expanded agent fields, not both.")

        return _create_agent(
            name=agent.name,
            instructions=agent.instructions,
            description=agent.description,
            token_budget=agent.token_budget,
            temperature=temperature if temperature is not None else _get_default_temperature(),
            tools=tools,
            client=client,
            summarizer_client=summarizer_client,
            logical_profile=logical_profile,
            enable_search_context=enable_search_context,
            skill_names=skill_names,
        )

    if name is None or instructions is None or description is None:
        raise TypeError(
            "spawn_agent() requires either an agent model or name, instructions, and description keywords."
        )

    return _create_agent(
        name=name,
        instructions=instructions,
        description=description,
        token_budget=token_budget,
        temperature=temperature if temperature is not None else _get_default_temperature(),
        tools=tools,
        client=client,
        summarizer_client=summarizer_client,
        logical_profile=logical_profile,
        enable_search_context=enable_search_context,
        skill_names=skill_names,
    )


def _build_openai_clients() -> tuple[OpenAIChatClient, OpenAIChatClient]:
    """Create primary and summarizer OpenAI clients from environment variables.

    The primary client uses zero-arg construction so the SDK auto-detects the
    provider from environment variables (AZURE_OPENAI_* → Azure, OPENAI_* → OpenAI-compatible).

    The secondary/summarizer client checks for AZURE_OPENAI_SECONDARY_* vars
    (which the SDK does not auto-detect) and falls back to the primary client.
    """
    primary = OpenAIChatClient()

    secondary_endpoint = (os.getenv("AZURE_OPENAI_SECONDARY_ENDPOINT") or "").strip()
    if secondary_endpoint:
        try:
            summarizer = OpenAIChatClient(
                azure_endpoint=secondary_endpoint,
                model=(os.getenv("AZURE_OPENAI_SECONDARY_MODEL") or "").strip() or None,
                api_key=(os.getenv("AZURE_OPENAI_SECONDARY_API_KEY") or "").strip() or None,
                api_version=(
                    (os.getenv("AZURE_OPENAI_SECONDARY_API_VERSION") or "").strip()
                    or (os.getenv("AZURE_OPENAI_API_VERSION") or "").strip()
                    or "2024-02-15-preview"
                ),
            )
        except Exception:
            summarizer = primary
    else:
        summarizer = primary

    logger.info(
        "LLM provider: %s (primary), %s (summarizer)",
        "Azure OpenAI" if os.getenv("AZURE_OPENAI_ENDPOINT") else "OpenAI-compatible",
        "dedicated Azure" if secondary_endpoint else "same as primary",
    )
    return primary, summarizer


def create_chat_runtime(
    *,
    chat_profile: str | None = None,
    function_tools: Sequence[Any] = (),
    mcp_servers: Sequence[Any] = (),
    token_budget: int = 16_000,
    temperature: float | None = None,
    custom_name: str | None = None,
    custom_instructions: str | None = None,
    enable_search_context: bool = False,
    custom_skills: list[str] | None = None,
    extra_instructions: str | None = None,
) -> ChatRuntime:
    is_custom = custom_name is not None and custom_instructions is not None

    if is_custom:
        agent_name = custom_name
        runtime_instructions = custom_instructions
        description = f"Custom agent: {custom_name}"
        logical_profile = "custom"
        all_tools: list[Any] = [*function_tools, *mcp_servers]
        skill_names = custom_skills
    else:
        agent_profile = load_agent_profile(chat_profile=chat_profile)
        runtime_instructions = agent_profile.system_prompt
        if not runtime_instructions:
            raise ValueError("Loaded agent profile but system prompt text is empty")

        bound_function_tools = _resolve_enabled_tools(
            profile_tool_names=agent_profile.tool_names,
            function_tools=function_tools,
        )
        all_tools = [*bound_function_tools, *mcp_servers]
        agent_name = chat_profile or agent_profile.name
        description = agent_profile.description
        logical_profile = agent_profile.logical_profile
        if not enable_search_context:
            enable_search_context = agent_profile.search_context
        if temperature is None and agent_profile.temperature is not None:
            temperature = agent_profile.temperature
        skill_names = agent_profile.skills or None

    if extra_instructions:
        runtime_instructions = runtime_instructions + extra_instructions

    primary_client, summarizer_client = _build_openai_clients()

    resolved_temperature = temperature if temperature is not None else _get_default_temperature()

    agent = spawn_agent(
        client=primary_client,
        name=agent_name,
        instructions=runtime_instructions,
        description=description,
        token_budget=token_budget,
        temperature=resolved_temperature,
        tools=all_tools,
        summarizer_client=summarizer_client,
        logical_profile=logical_profile,
        enable_search_context=enable_search_context,
        skill_names=skill_names,
    )

    logger.info(
        "Created chat runtime profile=%s logical_profile=%s temperature=%s tools=%s context_providers=%s summarizer=%s",
        custom_name or chat_profile,
        logical_profile,
        resolved_temperature,
        [getattr(t, "name", None) or getattr(t, "__name__", str(t)) for t in all_tools],
        [type(p).__name__ for p in agent.context_providers],
        summarizer_client is not primary_client,
    )

    return ChatRuntime(
        agent=agent,
        session=agent.create_session(),
        tools=all_tools,
        prompt_manifest={},
        prompt_logical_profile=logical_profile,
    )

