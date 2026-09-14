import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from agent_framework import CompactionProvider, Message, SkillsProvider, SkillsSource
from agent_framework import Agent as RuntimeAgent
from agent_framework._compaction import (
    CharacterEstimatorTokenizer,
    SlidingWindowStrategy,
    SummarizationStrategy,
    TokenBudgetComposedStrategy,
    ToolResultCompactionStrategy,
)
from agent_framework.openai import OpenAIChatClient as _OpenAIChatClient

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


class OpenAIChatClient(_OpenAIChatClient):
    """Use application-owned history and coalesce Responses reasoning fragments."""

    STORES_BY_DEFAULT = False

    async def _prepare_options(
        self, messages: Sequence[Message], options: Mapping[str, Any]
    ) -> dict[str, Any]:
        local_options = dict(options)
        for key in ("conversation_id", "previous_response_id", "conversation"):
            local_options.pop(key, None)
        local_options["store"] = False
        included = list(local_options.get("include") or [])
        if "reasoning.encrypted_content" not in included:
            included.append("reasoning.encrypted_content")
        local_options["include"] = included
        return await super()._prepare_options(messages, local_options)

    def _get_conversation_id(self, response: Any, store: bool | None) -> None:
        return None

    def _prepare_messages_for_openai(self, chat_messages: Sequence[Message]) -> list[dict[str, Any]]:
        prepared = super()._prepare_messages_for_openai(chat_messages)
        reasoning_items: dict[str, dict[str, Any]] = {}
        result: list[dict[str, Any]] = []
        for item in prepared:
            item_id = item.get("id")
            if item.get("type") != "reasoning" or not item_id:
                result.append(item)
                continue
            existing = reasoning_items.get(item_id)
            if existing is None:
                reasoning_items[item_id] = item
                result.append(item)
                continue
            for key, value in item.items():
                if key in ("summary", "content"):
                    parts = existing.setdefault(key, [])
                    for part in value:
                        if part not in parts:
                            parts.append(part)
                elif value is not None:
                    existing[key] = value
        return result


@dataclass(frozen=True)
class ChatRuntime:
    agent: RuntimeAgent
    session: Any
    tools: list[Any]
    prompt_logical_profile: str
    sub_agent_tool_names: list[str] = field(default_factory=list)


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

class CosmosSkillsSource(SkillsSource):
    """Agent Framework skills source backed by the durable Cosmos skill store.

    ``get_skills()`` is awaited lazily by ``SkillsProvider`` during an agent run
    (an async context), so the Cosmos fetch happens then — not at provider
    construction (which stays synchronous). Each Cosmos skill document becomes an
    ``InlineSkill`` whose instructions are the stored ``content`` (the SKILL.md
    body); invalid documents are skipped rather than failing the run.
    """

    def __init__(self, user_id: str | None = None) -> None:
        self._user_id = user_id

    async def get_skills(self) -> list[Any]:
        from agent_framework import InlineSkill, SkillFrontmatter
        from skills_manager import SkillManager

        docs = await SkillManager(user_id=self._user_id).list_documents()
        skills: list[Any] = []
        for doc in docs:
            try:
                skills.append(
                    InlineSkill(
                        frontmatter=SkillFrontmatter(
                            name=str(doc.get("name") or doc["id"]),
                            description=str(doc.get("description") or ""),
                        ),
                        instructions=str(doc.get("content") or ""),
                    )
                )
            except ValueError:
                logger.warning("Skipping invalid skill document id=%r", doc.get("id"))
        return skills


def _build_skills_provider(
    skill_names: list[str] | None = None,
    user_id: str | None = None,
) -> SkillsProvider | None:
    """Build a SkillsProvider filtered to the requested skill names.

    Skills are loaded from the durable Cosmos store lazily at agent-run time via
    ``CosmosSkillsSource``; name-based filtering and the silent omission of
    unknown names are preserved. Returns None when no skills are requested.
    """
    if not skill_names:
        return None

    from agent_framework import FilteringSkillsSource

    selected = set(skill_names)
    source = FilteringSkillsSource(
        CosmosSkillsSource(user_id),
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


_azure_credential: Any = None


def _openai_token_scope(endpoint: str) -> str:
    """Azure Government uses a different Entra audience than the commercial cloud."""
    cloud = "us" if (urlsplit(endpoint).hostname or "").endswith(".us") else "com"
    return f"https://cognitiveservices.azure.{cloud}/.default"


def _azure_token_provider(endpoint: str) -> Any:
    """Entra token provider for Azure OpenAI, backed by a shared credential.

    A provider is built here rather than handing the SDK a credential because the
    SDK hardcodes the commercial-cloud scope.
    """
    global _azure_credential
    from azure.identity import AzureAuthorityHosts
    from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider

    if _azure_credential is None:
        authority = (
            AzureAuthorityHosts.AZURE_GOVERNMENT
            if (urlsplit(endpoint).hostname or "").endswith(".us")
            else AzureAuthorityHosts.AZURE_PUBLIC_CLOUD
        )
        _azure_credential = DefaultAzureCredential(authority=authority)
    return get_bearer_token_provider(_azure_credential, _openai_token_scope(endpoint))


async def close_azure_credential() -> None:
    """Close the shared Entra credential (called on app shutdown)."""
    global _azure_credential
    if _azure_credential is not None:
        await _azure_credential.close()
        _azure_credential = None


def build_chat_client(**kwargs: Any) -> OpenAIChatClient:
    """Build an OpenAIChatClient, authenticating with Entra ID when no API key is set.

    Accepts the SDK's own keyword arguments; with none the SDK auto-detects the
    provider from environment variables (AZURE_OPENAI_* → Azure, OPENAI_* →
    OpenAI-compatible).
    """
    endpoint = kwargs.get("azure_endpoint") or (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
    if endpoint:
        kwargs.pop("api_key", None)
        if kwargs.get("credential") is None:
            kwargs["credential"] = _azure_token_provider(endpoint)
    return OpenAIChatClient(**kwargs)


def _temperature_options(client: OpenAIChatClient, temperature: float | None) -> dict[str, float]:
    if client.model == "gpt-5.6" or client.model.startswith("gpt-5.6-") or temperature is None:
        return {}
    return {"temperature": temperature}


def _build_context_providers(
    token_budget: int,
    summarizer_client: OpenAIChatClient | None = None,
    enable_search_context: bool = False,
    skill_names: list[str] | None = None,
    user_id: str | None = None,
) -> list[Any]:
    summarizer = summarizer_client or build_chat_client()
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

    skills_provider = _build_skills_provider(skill_names, user_id)
    if skills_provider is not None:
        providers.append(skills_provider)

    return providers


def _build_openai_clients() -> tuple[OpenAIChatClient, OpenAIChatClient]:
    """Create primary and summarizer OpenAI clients from environment variables.

    The primary client is built from the ambient AZURE_OPENAI_*/OPENAI_* vars;
    an Azure endpoint with no API key authenticates with managed identity.

    The secondary/summarizer client checks for AZURE_OPENAI_SECONDARY_* vars
    (which the SDK does not auto-detect) and falls back to the primary client.
    """
    primary = build_chat_client()

    secondary_endpoint = (os.getenv("AZURE_OPENAI_SECONDARY_ENDPOINT") or "").strip()
    if secondary_endpoint:
        try:
            summarizer = build_chat_client(
                azure_endpoint=secondary_endpoint,
                model=(os.getenv("AZURE_OPENAI_SECONDARY_MODEL") or "").strip() or None,
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

    azure_endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
    logger.info(
        "LLM provider: %s (primary, auth=%s), %s (summarizer)",
        "Azure OpenAI" if azure_endpoint else "OpenAI-compatible",
        "Entra" if azure_endpoint else "provider-default",
        "dedicated Azure" if secondary_endpoint else "same as primary",
    )
    return primary, summarizer


def _resolve_sub_agent_definition(
    ref: SubAgentToolRef,
) -> tuple[str, str, str, float | None, list[str]] | None:
    """Resolve a SubAgentToolRef to runtime identity, behavior, and selected skills.

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
                profile.skills,
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
            skills = [value for value in (definition.get("skills") or []) if isinstance(value, str)]
            temperature: float | None = None
            if raw_temp is not None:
                try:
                    temperature = float(raw_temp)
                except (TypeError, ValueError):
                    temperature = None
            return name, description, instructions, temperature, skills
    except Exception as exc:  # noqa: BLE001 — broad: orphans must not crash parent
        logger.warning("Failed to resolve sub-agent ref %r: %s", agent_ref, exc)
        return None
    return None


def _build_sub_agent_tools(
    refs,
    primary_client,
    sub_agent_resources=None,
    user_id=None,
    reserved_tool_names=(),
):
    """Wrap each resolved sub-agent ref as a FunctionTool via Agent.as_tool.

    Returns (tools, tool_names). For each builtin
    sub-agent ref, if sub_agent_resources contains an entry keyed by the
    target profile_id, that sub-agent is constructed with its own
    function_tools + mcp_tools + skills (and search context provider).
    Otherwise sub-agents fall back to leaf-only behaviour (instructions
    + temperature). Custom sub-agents remain leaf-only.
    """
    if not refs:
        return [], []

    resources_map = sub_agent_resources or {}

    resolved = []
    for ref in refs:
        info = _resolve_sub_agent_definition(ref)
        if info is None:
            continue
        name, description = info[:2]
        agent_ref = ref.agent_ref
        if isinstance(agent_ref, BuiltinAgentRef):
            fallback_id = agent_ref.profile_id
        elif isinstance(agent_ref, CustomAgentRef):
            fallback_id = agent_ref.custom_agent_id
        else:
            fallback_id = ""
        surface = derive_sub_agent_tool_surface(name, description, fallback_id)
        resolved.append((ref, info, surface))

    tool_names = disambiguate_tool_names(
        [surface[0] for _, _, surface in resolved], reserved_names=reserved_tool_names
    )

    tools = []
    for (ref, info, surface), final_tool_name in zip(resolved, tool_names):
        name, description, instructions, sub_temp, sub_skills = info
        sub_tools_extra = []
        try:
            providers = []
            selected_skills = sub_skills
            if isinstance(ref.agent_ref, BuiltinAgentRef):
                selected_skills = []
                resources = resources_map.get(ref.agent_ref.profile_id)
                if resources is not None:
                    sub_tools_extra = [*resources.function_tools, *resources.mcp_tools]
                    selected_skills = resources.skill_names
                    if resources.enable_search_context:
                        providers.append(get_search_context_provider())
            skills_provider = _build_skills_provider(selected_skills or None, user_id)
            if skills_provider is not None:
                providers.append(skills_provider)

            sub_agent = primary_client.as_agent(
                name=_sanitize_agent_name(name or final_tool_name),
                instructions=instructions,
                description=description or f"Delegate to the {name or final_tool_name} agent.",
                default_options=_temperature_options(primary_client, sub_temp),
                tools=sub_tools_extra or None,
                context_providers=providers or None,
            )
            sub_tool = sub_agent.as_tool(
                name=final_tool_name,
                description=surface[1],
                arg_name="request",
                arg_description=f"Request for the {final_tool_name} agent.",
            )
        except Exception as exc:
            logger.warning("Failed to wrap sub-agent %r as tool: %s", ref.agent_ref, exc)
            continue
        tools.append(sub_tool)
        logger.info(
            "Wired sub-agent tool: %s (target=%s, kind=%s, extra_tools=%d)",
            final_tool_name,
            getattr(ref.agent_ref, "profile_id", None) or getattr(ref.agent_ref, "custom_agent_id", None),
            getattr(ref.agent_ref, "kind", "unknown"),
            len(sub_tools_extra),
        )

    return tools, [tool.name for tool in tools]


def create_chat_runtime(
    *,
    profile: AgentProfile,
    function_tools: Sequence[Any] = (),
    mcp_servers: Sequence[Any] = (),
    token_budget: int = 16_000,
    extra_instructions: str | None = None,
    sub_agent_resources: dict[str, SubAgentResources] | None = None,
    user_id: str | None = None,
) -> ChatRuntime:
    runtime_instructions = profile.system_prompt + (extra_instructions or "")
    all_tools = [
        *_resolve_enabled_tools(profile.tool_names, function_tools),
        *mcp_servers,
    ]
    primary_client, summarizer_client = _build_openai_clients()
    resolved_temperature = profile.temperature if profile.temperature is not None else _get_default_temperature()

    sub_agent_tools, sub_agent_tool_names = _build_sub_agent_tools(
        profile.agents_as_tools, primary_client, sub_agent_resources, user_id,
        reserved_tool_names=[
            getattr(tool, "name", None) or getattr(tool, "__name__", "")
            for tool in all_tools
        ],
    )
    all_tools.extend(sub_agent_tools)

    agent = primary_client.as_agent(
        name=_sanitize_agent_name(profile.name),
        instructions=runtime_instructions,
        description=profile.description,
        tools=all_tools,
        default_options=_temperature_options(primary_client, resolved_temperature),
        context_providers=_build_context_providers(
            token_budget=token_budget,
            summarizer_client=summarizer_client,
            enable_search_context=profile.search_context,
            skill_names=profile.skills or None,
            user_id=user_id,
        ),
    )

    logger.info(
        "Created chat runtime profile=%s logical_profile=%s temperature=%s tools=%s context_providers=%s summarizer=%s",
        profile.name,
        profile.logical_profile,
        resolved_temperature,
        [getattr(t, "name", None) or getattr(t, "__name__", str(t)) for t in all_tools],
        [type(p).__name__ for p in agent.context_providers],
        summarizer_client is not primary_client,
    )

    return ChatRuntime(
        agent=agent,
        session=agent.create_session(),
        tools=all_tools,
        prompt_logical_profile=profile.logical_profile,
        sub_agent_tool_names=sub_agent_tool_names,
    )
