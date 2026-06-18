import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from agent_framework import CompactionProvider, SkillsProvider
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


from prompt_config import (
    AgentProfile,
    BuiltinAgentRef,
    CustomAgentRef,
    SubAgentToolRef,
    load_agent_profile,
)
from mcp_servers import get_search_context_provider
from sub_agent_tools import derive_sub_agent_tool_surface, disambiguate_tool_names
from cosmos_memory import get_history_provider


@dataclass(frozen=True)
class ChatRuntime:
    agent: RuntimeAgent
    session: Any
    tools: list[Any]
    prompt_manifest: dict[str, str]
    prompt_logical_profile: str
    sub_agent_tool_names: list[str] = field(default_factory=list)
    sub_agent_mcp_tools: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class SubAgentResources:
    """Pre-resolved tools/MCPs/skills for a builtin sub-agent.

    Pre-resolved by the async session-orchestration layer so that
    ``create_chat_runtime`` can stay synchronous while still wiring
    each sub-agent with its own function tools, MCP tools, and skills.
    """
    function_tools: list[Any] = field(default_factory=list)
    mcp_tools: list[Any] = field(default_factory=list)
    skill_names: list[str] = field(default_factory=list)
    enable_search_context: bool = False


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

    from agent_framework import FileSkillsSource, FilteringSkillsSource

    selected = set(skill_names)
    source = FilteringSkillsSource(
        FileSkillsSource(_SKILLS_DIR),
        predicate=lambda skill: skill.frontmatter.name in selected,
    )
    return SkillsProvider(source)


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

    history = get_history_provider()
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


def _resolve_sub_agent_definition(
    ref: SubAgentToolRef,
) -> tuple[str, str, str, float | None] | None:
    """Resolve a SubAgentToolRef to ``(name, description, instructions, temperature)``.

    Returns ``None`` if the reference cannot be resolved (e.g., a built-in
    profile id no longer exists, a custom-agent definition is malformed).
    Callers should treat ``None`` as an orphaned reference per FR-008.
    """
    agent_ref = ref.agent_ref
    try:
        if isinstance(agent_ref, BuiltinAgentRef):
            profile = load_agent_profile(agent_ref.profile_id)
            return (
                profile.name,
                profile.description,
                profile.system_prompt,
                profile.temperature,
            )
        if isinstance(agent_ref, CustomAgentRef):
            definition = agent_ref.definition or {}
            name = str(definition.get("name") or "").strip()
            instructions = str(definition.get("systemPrompt") or definition.get("system_prompt") or "").strip()
            if not instructions:
                logger.warning("Sub-agent custom ref %r has no system prompt; skipping", agent_ref.custom_agent_id)
                return None
            description = str(definition.get("description") or "").strip()
            raw_temp = definition.get("temperature")
            temperature: float | None = None
            if raw_temp is not None:
                try:
                    temperature = float(raw_temp)
                except (TypeError, ValueError):
                    temperature = None
            return name, description, instructions, temperature
    except Exception as exc:  # noqa: BLE001 — broad: orphans must not crash parent
        logger.warning("Failed to resolve sub-agent ref %r: %s", agent_ref, exc)
        return None
    return None


def _build_sub_agent_tools(
    refs,
    primary_client,
    sub_agent_resources=None,
):
    """Wrap each resolved sub-agent ref as a FunctionTool via Agent.as_tool.

    Returns (tools, tool_names, sub_agent_mcp_tools). For each builtin
    sub-agent ref, if sub_agent_resources contains an entry keyed by the
    target profile_id, that sub-agent is constructed with its own
    function_tools + mcp_tools + skills (and search context provider).
    Otherwise sub-agents fall back to leaf-only behaviour (instructions
    + temperature). Custom sub-agents remain leaf-only.
    """
    if not refs:
        return [], [], []

    resources_map = sub_agent_resources or {}

    resolved = []
    for ref in refs:
        info = _resolve_sub_agent_definition(ref)
        if info is None:
            continue
        resolved.append((ref, info))

    if not resolved:
        return [], [], []

    derivations = []
    for ref, (name, description, _instructions, _temp) in resolved:
        agent_ref = ref.agent_ref
        if isinstance(agent_ref, BuiltinAgentRef):
            fallback_id = agent_ref.profile_id
        elif isinstance(agent_ref, CustomAgentRef):
            fallback_id = agent_ref.custom_agent_id
        else:
            fallback_id = ""
        derivations.append(derive_sub_agent_tool_surface(name, description, fallback_id))

    tool_names = disambiguate_tool_names([tn for tn, _, _ in derivations])

    tools = []
    final_names = []
    aggregated_mcp_tools = []
    for (ref, (name, description, instructions, sub_temp)), (_orig_tool_name, tool_description, _arg_desc), final_tool_name in zip(
        resolved, derivations, tool_names
    ):
        sub_tools_extra = []
        try:
            sub_default_options = {}
            if sub_temp is not None:
                sub_default_options["temperature"] = sub_temp

            sub_context_providers = None
            if isinstance(ref.agent_ref, BuiltinAgentRef):
                resources = resources_map.get(ref.agent_ref.profile_id)
                if resources is not None:
                    sub_tools_extra = [*resources.function_tools, *resources.mcp_tools]
                    aggregated_mcp_tools.extend(resources.mcp_tools)
                    providers = []
                    if resources.enable_search_context:
                        providers.append(get_search_context_provider())
                    skills_provider = _build_skills_provider(resources.skill_names or None)
                    if skills_provider is not None:
                        providers.append(skills_provider)
                    sub_context_providers = providers or None

            as_agent_kwargs = {
                "name": _sanitize_agent_name(name or final_tool_name),
                "instructions": instructions,
                "description": description or f"Delegate to the {name or final_tool_name} agent.",
            }
            if sub_default_options:
                as_agent_kwargs["default_options"] = sub_default_options
            if sub_tools_extra:
                as_agent_kwargs["tools"] = sub_tools_extra
            if sub_context_providers:
                as_agent_kwargs["context_providers"] = sub_context_providers

            sub_agent = primary_client.as_agent(**as_agent_kwargs)
            sub_tool = sub_agent.as_tool(
                name=final_tool_name,
                description=tool_description,
                arg_name="request",
                arg_description=f"Request for the {final_tool_name} agent.",
            )
        except Exception as exc:
            logger.warning("Failed to wrap sub-agent %r as tool: %s", ref.agent_ref, exc)
            continue
        tools.append(sub_tool)
        final_names.append(final_tool_name)
        logger.info(
            "Wired sub-agent tool: %s (target=%s, kind=%s, extra_tools=%d)",
            final_tool_name,
            getattr(ref.agent_ref, "profile_id", None) or getattr(ref.agent_ref, "custom_agent_id", None),
            getattr(ref.agent_ref, "kind", "unknown"),
            len(sub_tools_extra),
        )

    return tools, final_names, aggregated_mcp_tools


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
    agents_as_tools: Sequence[SubAgentToolRef] = (),
    sub_agent_resources: dict[str, SubAgentResources] | None = None,
) -> ChatRuntime:
    is_custom = custom_name is not None and custom_instructions is not None

    if is_custom:
        agent_name = custom_name
        runtime_instructions = custom_instructions
        description = f"Custom agent: {custom_name}"
        logical_profile = "custom"
        all_tools: list[Any] = [*function_tools, *mcp_servers]
        skill_names = custom_skills
        sub_agent_refs: list[SubAgentToolRef] = list(agents_as_tools)
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
        # Caller-supplied refs override profile refs (e.g., session-time overrides);
        # otherwise fall back to whatever the YAML profile declared.
        sub_agent_refs = list(agents_as_tools) if agents_as_tools else list(getattr(agent_profile, "agents_as_tools", ()) or ())

    if extra_instructions:
        runtime_instructions = runtime_instructions + extra_instructions

    primary_client, summarizer_client = _build_openai_clients()

    resolved_temperature = temperature if temperature is not None else _get_default_temperature()

    sub_agent_tools, sub_agent_tool_names, sub_agent_mcp_tools = _build_sub_agent_tools(
        sub_agent_refs, primary_client, sub_agent_resources
    )
    if sub_agent_tools:
        all_tools = [*all_tools, *sub_agent_tools]

    agent = primary_client.as_agent(
        name=_sanitize_agent_name(agent_name),
        instructions=runtime_instructions,
        description=description,
        tools=all_tools,
        default_options={"temperature": resolved_temperature},
        context_providers=_build_context_providers(
            token_budget=token_budget,
            summarizer_client=summarizer_client,
            logical_profile=logical_profile,
            enable_search_context=enable_search_context,
            skill_names=skill_names,
        ),
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
        sub_agent_tool_names=sub_agent_tool_names,
        sub_agent_mcp_tools=sub_agent_mcp_tools,
    )
