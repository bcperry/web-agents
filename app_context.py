"""Application dependency wiring shared by API routes and background work."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable, Mapping
from typing import Any, Callable

from dotenv import load_dotenv

from database import (
    AgentDatabaseGrant,
    Capability,
    ConfigurationError,
    DatabaseProviderConfig,
    Environment,
    ProviderId,
)
from database_authorization import DatabaseAuthorizer
from database_synapse import AzureSqlProvider
from session_data import SessionData, _sessions
from session_orchestration import SessionContext
from tools import (
    build_database_tools,
    build_create_agent_tool,
    build_create_skill_tool,
    build_edit_agent_tool,
    build_edit_skill_tool,
    build_user_profile_tools,
)

load_dotenv()

logger = logging.getLogger(__name__)
DEFAULT_MAX_USER_INPUT_CHARS = int(os.getenv("MAX_USER_INPUT_CHARS", "8000"))


@dataclass(frozen=True)
class FunctionToolRegistration:
    description: str
    factory: Callable[[str], Any]


class DatabaseProviderRegistry:
    """Holds optional provider instances without opening connections."""

    def __init__(self, providers: Iterable[Any] = ()) -> None:
        self._providers: dict[Any, Any] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: Any) -> None:
        self._providers[provider.provider_id] = provider

    def tools_for_grant(self, grant: Any | None) -> dict[str, Any]:
        if grant is None:
            return {}
        provider = self._providers.get(grant.provider_id)
        if provider is None:
            return {}
        return build_database_tools(provider, grant)


_database_provider_registry = DatabaseProviderRegistry()


def register_database_provider(provider: Any) -> None:
    """Register an already configured provider for later grant selection."""
    _database_provider_registry.register(provider)


def _csv_values(value: str | None) -> tuple[str, ...]:
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


def configure_sap_emulator_runtime(
    *,
    environ: Mapping[str, str] | None = None,
    registry: DatabaseProviderRegistry | None = None,
) -> tuple[DatabaseAuthorizer | None, Callable[[Any, str], AgentDatabaseGrant | None] | None]:
    """Register the emulator and return its fail-closed session authorization wiring."""
    settings = environ or os.environ
    if settings.get("SAP_EMULATOR_ENABLED", "").strip().lower() not in {"1", "true", "yes"}:
        return None, None

    connection_string = settings.get("AZURE_SQL_CONNECTIONSTRING", "").strip()
    server_fqdn = settings.get("SAP_EMULATOR_SERVER_FQDN", "").strip()
    database_name = settings.get("SAP_EMULATOR_DATABASE_NAME", "").strip()
    tenant_id = (
        settings.get("OAUTH_AZURE_GOV_AD_TENANT_ID", "").strip()
        or settings.get("AZURE_AD_TENANT_ID", "").strip()
    )
    entitled_groups = _csv_values(settings.get("SAP_EMULATOR_ENTITLED_GROUP_IDS"))
    required = {
        "AZURE_SQL_CONNECTIONSTRING": connection_string,
        "SAP_EMULATOR_SERVER_FQDN": server_fqdn,
        "SAP_EMULATOR_DATABASE_NAME": database_name,
        "OAUTH_AZURE_GOV_AD_TENANT_ID": tenant_id,
        "SAP_EMULATOR_ENTITLED_GROUP_IDS": entitled_groups,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ConfigurationError(
            f"SAP emulator runtime configuration is incomplete: {', '.join(missing)}."
        )

    provider = AzureSqlProvider(
        DatabaseProviderConfig(
            provider_id=ProviderId.SAP_EMULATOR,
            host=server_fqdn,
            port=1433,
            database=database_name,
            enabled=True,
            approved_schemas=("reporting",),
            environment=Environment.PRODUCTION,
        ),
        connection_string,
    )
    (registry or _database_provider_registry).register(provider)

    grant = AgentDatabaseGrant(
        provider_id=ProviderId.SAP_EMULATOR,
        capabilities=(Capability.DATABASE_SCHEMA, Capability.DATABASE_QUERY),
        entitled_groups=entitled_groups,
        environment=Environment.PRODUCTION,
    )
    agent_ids = frozenset(
        _csv_values(settings.get("SAP_EMULATOR_AGENT_IDS", "sap_force_equipment"))
    )

    def resolve_grant(_user: Any, agent_id: str) -> AgentDatabaseGrant | None:
        return grant if agent_id in agent_ids else None

    logger.info(
        "SAP emulator provider registered for %d agent profile(s) and %d entitled group(s)",
        len(agent_ids),
        len(entitled_groups),
    )
    return DatabaseAuthorizer(allowed_tenant_ids=(tenant_id,)), resolve_grant


def function_tool_registry() -> dict[str, FunctionToolRegistration]:
    def profile_factory(name: str) -> Callable[[str], Any]:
        return lambda user_id: build_user_profile_tools(user_id)[name]

    return {
        "get_user_profile": FunctionToolRegistration(
            "Return the authenticated user's saved profile.", profile_factory("get_user_profile")
        ),
        "save_user_profile": FunctionToolRegistration(
            "Save the authenticated user's profile for later sessions.", profile_factory("save_user_profile")
        ),
        "create_skill": FunctionToolRegistration(
            "Create a durable user-owned skill without overwriting existing work.",
            build_create_skill_tool,
        ),
        "create_agent": FunctionToolRegistration(
            "Create a durable user-owned custom agent without overwriting existing work.",
            build_create_agent_tool,
        ),
        "edit_skill": FunctionToolRegistration(
            "Edit an existing user-owned skill.",
            build_edit_skill_tool,
        ),
        "edit_agent": FunctionToolRegistration(
            "Edit an existing user-owned custom agent using its complete definition.",
            build_edit_agent_tool,
        ),
    }


def build_tool_instances(
    tool_names: set[str],
    *,
    session_id: str,
    user_id: str | None = None,
    database_grant: Any | None = None,
    database_registry: DatabaseProviderRegistry | None = None,
) -> list[Any]:
    """Instantiate the selected backend tools for a session or inventory call."""
    registry = function_tool_registry()
    tools = [
        registration.factory(user_id or "")
        for name, registration in registry.items()
        if name in tool_names
    ]
    provider_registry = database_registry or _database_provider_registry
    tools.extend(provider_registry.tools_for_grant(database_grant).values())
    return tools


def build_user_profile_context(user_profile_data: dict[str, str] | None) -> str:
    """Return a system-prompt snippet with user profile info, or empty string."""
    if not user_profile_data or not isinstance(user_profile_data, dict):
        return ""

    parts = [
        f"- {key}: {value}"
        for key, value in user_profile_data.items()
        if value and str(value).strip()
    ]
    if not parts:
        return ""
    return "\n\n## Known User Profile\n" + "\n".join(parts)


def get_skills_dir() -> Path:
    return Path(__file__).resolve().parent / "skills"


_database_authorizer, _database_grant_resolver = configure_sap_emulator_runtime()

session_context = SessionContext(
    sessions=_sessions,
    session_data_cls=SessionData,
    build_tool_instances=build_tool_instances,
    build_user_profile_context=build_user_profile_context,
    database_authorizer=_database_authorizer,
    database_grant_resolver=_database_grant_resolver,
)