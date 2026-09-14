import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from azure.identity import AzureAuthorityHosts, DefaultAzureCredential
from agent_framework import MCPStdioTool
from agent_framework import MCPStreamableHTTPTool
from agent_framework.azure import AzureAISearchContextProvider
from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)


# ── MCP Server Configuration ────────────────────────────────────────────────

_SECRET_QUERY_KEYS = {"api_key", "apikey", "code", "token", "access_token", "client_secret", "password"}
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|client[_-]?secret|password|connectionstring|connection_string)\s*=\s*[^\s&]+"
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")


def _sanitize_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.scheme or not parsed.netloc:
        return value
    safe_query = urlencode([
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _SECRET_QUERY_KEYS
    ])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, safe_query, parsed.fragment))


def sanitize_mcp_result_error(error: str | None) -> str | None:
    if error is None:
        return None
    sanitized = re.sub(r"https?://[^\s)]+", lambda match: _sanitize_url(match.group(0)), str(error))
    sanitized = _BEARER_RE.sub("[REDACTED_TOKEN]", sanitized)
    sanitized = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)} [REDACTED]", sanitized)
    return sanitized


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
    auth: bool = False
    auth_scope: str | None = None


@dataclass
class MCPConnectionResult:
    """Per-server connection outcome returned by connect_mcp_servers()."""
    name: str
    transport: str
    status: str  # "connected" | "failed"
    tool_count: int = 0
    error: str | None = None


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


def parse_mcp_server_configs(profile_entry: dict[str, Any], *, interpolate_env: bool = False) -> list[MCPServerConfig]:
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
        if interpolate_env and isinstance(url, str):
            url = _interpolate_env_vars(url)

        command = entry.get("command")
        if interpolate_env and isinstance(command, str):
            command = _interpolate_env_vars(command)

        if transport == "http" and not url:
            logger.warning("MCP server '%s' (http) requires 'url'", name)
            continue
        if transport == "stdio" and not command:
            logger.warning("MCP server '%s' (stdio) requires 'command'", name)
            continue

        raw_args = entry.get("args") or []
        args = [_interpolate_env_vars(arg) if interpolate_env and isinstance(arg, str) else str(arg) for arg in raw_args]

        raw_env = entry.get("env")
        env = {key: _interpolate_env_vars(value) if interpolate_env else value for key, value in raw_env.items()} if isinstance(raw_env, dict) else None

        allowed_tools = entry.get("allowed_tools")
        if allowed_tools is not None and (
            not isinstance(allowed_tools, list) or any(not isinstance(tool, str) for tool in allowed_tools)
        ):
            raise ValueError("allowed_tools must be a list of tool name strings")

        request_timeout = entry.get("request_timeout")
        if request_timeout is not None:
            try:
                request_timeout = int(request_timeout)
                if request_timeout <= 0:
                    request_timeout = None
            except (TypeError, ValueError):
                request_timeout = None

        auth = bool(entry.get("auth", False) or entry.get("authenticated", False))
        auth_scope = entry.get("auth_scope") or entry.get("authScope") or None
        if isinstance(auth_scope, str):
            auth_scope = auth_scope.strip() or None

        if (auth or auth_scope) and transport != "http":
            logger.warning("MCP server '%s': auth fields are only supported for http transport, ignoring", name)
            auth = False
            auth_scope = None

        configs.append(MCPServerConfig(
            name=str(name),
            transport=str(transport),
            url=url,
            command=command,
            args=args,
            env=env,
            allowed_tools=allowed_tools,
            request_timeout=request_timeout,
            description=entry.get("description"),
            auth=auth,
            auth_scope=auth_scope,
        ))

    return configs


def resolve_mcp_auth_token(config: MCPServerConfig, user_token: str | None) -> str | None:
    """Resolve the auth token for an MCP server based on its config.

    - auth_scope set: OBO exchange via MSAL ConfidentialClientApplication
    - auth=True: passthrough the user's token as-is
    - Neither: return None (no auth)
    """
    if not config.auth and not config.auth_scope:
        return None

    if not user_token:
        logger.warning("MCP server '%s' requires auth but no user token available", config.name)
        return None

    if config.auth_scope:
        # OBO token exchange
        client_id = os.environ.get("AZURE_AD_CLIENT_ID")
        client_secret = os.environ.get("AZURE_AD_CLIENT_SECRET")
        authority = os.environ.get("AZURE_AD_AUTHORITY")

        if not client_secret:
            logger.warning(
                "MCP server '%s' requires OBO (auth_scope=%s) but AZURE_AD_CLIENT_SECRET is not set%s",
                config.name,
                config.auth_scope,
                "; falling back to passthrough" if config.auth else "",
            )
            return user_token if config.auth else None

        if not client_id or not authority:
            logger.warning("MCP server '%s': AZURE_AD_CLIENT_ID or AZURE_AD_AUTHORITY not set, cannot perform OBO", config.name)
            return user_token if config.auth else None

        try:
            import msal
            cca = msal.ConfidentialClientApplication(
                client_id,
                authority=authority,
                client_credential=client_secret,
            )
            result = cca.acquire_token_on_behalf_of(
                user_assertion=user_token,
                scopes=[config.auth_scope],
            )
            if "access_token" in result:
                return result["access_token"]
            error_desc = result.get("error_description", result.get("error", "Unknown OBO error"))
            logger.warning("OBO token exchange failed for MCP server '%s': %s", config.name, error_desc)
            return None
        except Exception as e:
            logger.warning("OBO token exchange error for MCP server '%s': %s", config.name, e)
            return None

    # Passthrough mode
    return user_token


def create_mcp_tool(config: MCPServerConfig, *, auth_token: str | None = None) -> MCPStdioTool | MCPStreamableHTTPTool:
    """Instantiate the correct MCPTool subclass based on transport type."""
    common_kwargs: dict[str, Any] = {
        "name": config.name,
        "load_prompts": False,
    }
    if config.description:
        common_kwargs["description"] = config.description
    if config.allowed_tools is not None:
        common_kwargs["allowed_tools"] = config.allowed_tools
    if config.request_timeout:
        common_kwargs["request_timeout"] = config.request_timeout

    if config.transport == "http":
        if auth_token:
            import httpx
            http_client = httpx.AsyncClient(headers={"Authorization": f"Bearer {auth_token}"})
            common_kwargs["http_client"] = http_client
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


async def connect_mcp_servers(
    configs: list[MCPServerConfig],
    *,
    user_token: str | None = None,
) -> tuple[list[Any], list[MCPConnectionResult]]:
    """Connect to MCP servers from configs.

    Returns (connected_tools, connection_results) where connection_results
    contains a per-server outcome regardless of success or failure.
    """
    connected: list[Any] = []
    results: list[MCPConnectionResult] = []
    for config in configs:
        tool = None
        try:
            resolved_token = resolve_mcp_auth_token(config, user_token)
            tool = create_mcp_tool(config, auth_token=resolved_token)
            await tool.connect()
            tool_count = len(tool.functions) if hasattr(tool, "functions") else 0
            logger.info("Connected MCP server '%s' (%s) — loaded %d tools", config.name, config.transport, tool_count)
            connected.append(tool)
            results.append(MCPConnectionResult(
                name=config.name,
                transport=config.transport,
                status="connected",
                tool_count=tool_count,
            ))
        except asyncio.CancelledError:
            await cleanup_mcp_servers([*connected, *([tool] if tool is not None else [])])
            raise
        except Exception as e:
            if tool is not None:
                await cleanup_mcp_servers([tool])
            logger.warning("MCP server '%s' (%s) failed to connect: %s", config.name, config.transport, e)
            results.append(MCPConnectionResult(
                name=config.name,
                transport=config.transport,
                status="failed",
                error=str(e),
            ))
    return connected, results


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
        top_k=_env_positive_int("SEARCH_TOP_K", 5),
        semantic_configuration_name=_clean_env("SEARCH_SEMANTIC_CONFIGURATION_NAME"),
    )


class SearchTokenCredential:
    def __init__(self, endpoint: str):
        government = (urlsplit(endpoint).hostname or "").endswith(".us")
        self.scope = "https://search.azure.us/.default" if government else "https://search.azure.com/.default"
        self.credential = DefaultAzureCredential(
            authority=AzureAuthorityHosts.AZURE_GOVERNMENT if government else AzureAuthorityHosts.AZURE_PUBLIC_CLOUD
        )

    def get_token(self, *scopes, **kwargs):
        return self.credential.get_token(self.scope, **kwargs)

    def close(self):
        self.credential.close()


@lru_cache(maxsize=1)
def get_search_credential() -> SearchTokenCredential:
    return SearchTokenCredential(get_search_service_config().endpoint or "")


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
    "get_search_credential",
    "get_search_context_provider",
    "get_search_service_config",
]