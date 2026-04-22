import logging
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from agent_framework import MCPStdioTool
from agent_framework import MCPStreamableHTTPTool
from agent_framework.azure import AzureAISearchContextProvider
from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)


# ── MCP Server Configuration ────────────────────────────────────────────────

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


@dataclass
class MCPServerConfig:
    """Parsed MCP server entry from agents.yaml or inline custom agent request."""
    name: str
    transport: str  # "http" or "stdio"
    url: str | None = None
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    allowed_tools: list[str] | None = None
    request_timeout: int | None = None
    description: str | None = None


def _interpolate_env_vars(value: str) -> str:
    """Replace ${ENV_VAR} placeholders with os.environ values."""
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        env_value = os.environ.get(var_name)
        if env_value is None:
            logger.warning("Environment variable %s not set (referenced in MCP server config)", var_name)
            return match.group(0)  # leave placeholder as-is
        return env_value
    return _ENV_VAR_PATTERN.sub(_replace, value)


def parse_mcp_server_configs(profile_entry: dict[str, Any]) -> list[MCPServerConfig]:
    """Parse and validate the mcp_servers list from an agents.yaml profile entry or request body."""
    raw_servers = profile_entry.get("mcp_servers")
    if not raw_servers:
        return []
    if not isinstance(raw_servers, list):
        logger.warning("mcp_servers must be a list, got %s", type(raw_servers).__name__)
        return []

    configs: list[MCPServerConfig] = []
    for entry in raw_servers:
        if not isinstance(entry, dict):
            logger.warning("Skipping non-dict mcp_servers entry: %s", entry)
            continue

        name = entry.get("name")
        transport = entry.get("transport")
        if not name or not transport:
            logger.warning("MCP server entry missing required 'name' or 'transport': %s", entry)
            continue

        if transport not in ("http", "stdio"):
            logger.warning("MCP server '%s' has invalid transport '%s' (must be 'http' or 'stdio')", name, transport)
            continue

        url = entry.get("url")
        if isinstance(url, str):
            url = _interpolate_env_vars(url)

        command = entry.get("command")
        if isinstance(command, str):
            command = _interpolate_env_vars(command)

        if transport == "http" and not url:
            logger.warning("MCP server '%s' (http) requires 'url'", name)
            continue
        if transport == "stdio" and not command:
            logger.warning("MCP server '%s' (stdio) requires 'command'", name)
            continue

        raw_args = entry.get("args") or []
        args = [_interpolate_env_vars(a) if isinstance(a, str) else str(a) for a in raw_args]

        raw_env = entry.get("env")
        env = {k: _interpolate_env_vars(v) for k, v in raw_env.items()} if isinstance(raw_env, dict) else None

        allowed_tools = entry.get("allowed_tools")
        if allowed_tools is not None and not isinstance(allowed_tools, list):
            allowed_tools = None

        request_timeout = entry.get("request_timeout")
        if request_timeout is not None:
            try:
                request_timeout = int(request_timeout)
                if request_timeout <= 0:
                    request_timeout = None
            except (TypeError, ValueError):
                request_timeout = None

        configs.append(MCPServerConfig(
            name=str(name),
            transport=str(transport),
            url=url,
            command=command,
            args=args,
            env=env,
            allowed_tools=[str(t) for t in allowed_tools] if allowed_tools else None,
            request_timeout=request_timeout,
            description=entry.get("description"),
        ))

    return configs


def create_mcp_tool(config: MCPServerConfig) -> MCPStdioTool | MCPStreamableHTTPTool:
    """Instantiate the correct MCPTool subclass based on transport type."""
    common_kwargs: dict[str, Any] = {
        "name": config.name,
        "load_prompts": False,
    }
    if config.description:
        common_kwargs["description"] = config.description
    if config.allowed_tools:
        common_kwargs["allowed_tools"] = config.allowed_tools
    if config.request_timeout:
        common_kwargs["request_timeout"] = config.request_timeout

    if config.transport == "http":
        return MCPStreamableHTTPTool(url=config.url, **common_kwargs)
    elif config.transport == "stdio":
        kwargs = {**common_kwargs, "command": config.command}
        if config.args:
            kwargs["args"] = config.args
        if config.env:
            kwargs["env"] = config.env
        return MCPStdioTool(**kwargs)
    else:
        raise ValueError(f"Unsupported MCP transport: {config.transport}")


async def connect_mcp_servers(configs: list[MCPServerConfig]) -> list[Any]:
    """Connect to MCP servers from configs. Returns list of successfully connected MCPTool instances."""
    connected: list[Any] = []
    for config in configs:
        try:
            tool = create_mcp_tool(config)
            await tool.connect()
            tool_count = len(tool.functions) if hasattr(tool, "functions") else 0
            logger.info("Connected MCP server '%s' (%s) — loaded %d tools", config.name, config.transport, tool_count)
            connected.append(tool)
        except Exception as e:
            logger.warning("MCP server '%s' (%s) failed to connect: %s", config.name, config.transport, e)
    return connected


async def cleanup_mcp_servers(tools: list[Any]) -> None:
    """Close all MCP server connections. Errors are logged but not raised."""
    for tool in tools:
        name = getattr(tool, "name", "unknown")
        try:
            await tool.close()
            logger.info("Closed MCP server '%s'", name)
        except Exception as e:
            logger.warning("Failed to close MCP server '%s': %s", name, e)


# ── Context Providers ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SearchServiceConfig:
    endpoint: str | None
    index_name: str | None
    api_key: str | None
    top_k: int
    semantic_configuration_name: str | None


def _clean_env(name: str) -> str | None:
    value = (os.getenv(name) or "").strip()
    return value or None


def _env_positive_int(name: str, default: int) -> int:
    raw = _clean_env(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@lru_cache(maxsize=1)
def get_search_service_config() -> SearchServiceConfig:
    return SearchServiceConfig(
        endpoint=_clean_env("SEARCH_SERVICE_ENDPOINT"),
        index_name=_clean_env("SEARCH_INDEX_NAME"),
        api_key=_clean_env("SEARCH_API_KEY"),
        top_k=_env_positive_int("SEARCH_TOP_K", 5),
        semantic_configuration_name=_clean_env("SEARCH_SEMANTIC_CONFIGURATION_NAME"),
    )


@lru_cache(maxsize=1)
def get_search_credential() -> AzureKeyCredential | DefaultAzureCredential:
    config = get_search_service_config()
    if config.api_key:
        return AzureKeyCredential(config.api_key)
    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def get_search_client() -> SearchClient:
    config = get_search_service_config()
    if not config.endpoint or not config.index_name:
        raise ValueError("SEARCH_SERVICE_ENDPOINT and SEARCH_INDEX_NAME must be configured.")

    return SearchClient(
        endpoint=config.endpoint,
        index_name=config.index_name,
        credential=get_search_credential(),
    )


@lru_cache(maxsize=1)
def get_search_context_provider() -> AzureAISearchContextProvider:
    """Lazily create the Azure AI Search context provider (requires .env to be loaded)."""
    config = get_search_service_config()

    provider_kwargs = {
        "endpoint": config.endpoint,
        "index_name": config.index_name,
        "top_k": config.top_k,
        "semantic_configuration_name": config.semantic_configuration_name,
    }
    if config.api_key:
        provider_kwargs["api_key"] = config.api_key
    else:
        provider_kwargs["credential"] = get_search_credential()

    return AzureAISearchContextProvider(
        **provider_kwargs,
        context_prompt=(
            "[SYSTEM: The following documents were automatically retrieved from "
            "Azure AI Search based on the user's query. This is NOT user-provided "
            "content — it is search-grounded context for you to reference.]"
        ),
    )


__all__ = [
    "MCPServerConfig",
    "create_mcp_tool",
    "parse_mcp_server_configs",
    "connect_mcp_servers",
    "cleanup_mcp_servers",
    "SearchServiceConfig",
    "get_search_client",
    "get_search_credential",
    "get_search_context_provider",
    "get_search_service_config",
]