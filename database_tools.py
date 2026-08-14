"""Model-facing database tools and the session access boundary.

``DatabaseAccess`` is the only way a chat session obtains database tools. It
takes the capabilities a *server-defined* profile declares, confirms the caller
is entitled to each one, and returns guarded tools keyed by their model-facing
name. Nothing here trusts a client-supplied identifier.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from database import (
    DATABASE_TOOL_NAMES,
    AgentDatabaseGrant,
    Capability,
    ConfigurationError,
    DatabaseError,
    DatabaseProvider,
    DatabaseProviderConfig,
    Environment,
    ProviderId,
    QueryRequest,
    SchemaRequest,
)
from database_authorization import (
    DatabaseAuthorizer,
    guard_database_tools,
    subject_from_user,
)
from database_sqlserver import SqlServerProvider

logger = logging.getLogger(__name__)

SAP_EMULATOR_PORT = 1433
SAP_EMULATOR_SCHEMAS = ("reporting",)


def build_database_tools(
    provider: DatabaseProvider, capabilities: Iterable[Capability]
) -> dict[Capability, Any]:
    """Build one async tool per capability, bound to a single provider."""
    builders = {
        Capability.DATABASE_SCHEMA: _build_schema_tool,
        Capability.DATABASE_QUERY: _build_query_tool,
    }
    return {capability: builders[capability](provider) for capability in capabilities}


def _build_schema_tool(provider: DatabaseProvider) -> Any:
    async def database_schema(
        schema: str | None = None, object_name: str | None = None
    ) -> dict[str, Any]:
        """Return bounded metadata from the database configured for this agent."""
        try:
            request = SchemaRequest(schema=schema, object_name=object_name)
            return (await provider.discover_schema(request)).to_dict()
        except DatabaseError as error:
            return error.to_schema_result(provider=provider.provider_id).to_dict()

    return database_schema


def _build_query_tool(provider: DatabaseProvider) -> Any:
    async def database_query(sql: str, parameters: list[Any] | None = None) -> dict[str, Any]:
        """Execute one bounded read query against the database configured for this agent."""
        try:
            request = QueryRequest(sql=sql, parameters=parameters)
            return (await provider.execute_query(request)).to_dict()
        except DatabaseError as error:
            return error.to_result(provider=provider.provider_id).to_dict()

    return database_query


class DatabaseAccess:
    """Turns a profile's declared database tools into guarded, entitled tools."""

    def __init__(
        self,
        *,
        provider: DatabaseProvider,
        authorizer: DatabaseAuthorizer,
        grant: AgentDatabaseGrant,
    ) -> None:
        if provider.provider_id is not grant.provider_id:
            raise ConfigurationError("The grant does not match the registered provider.")
        self.provider = provider
        self.authorizer = authorizer
        self.grant = grant

    async def tools_for(
        self, *, user: Any, agent_id: str, tool_names: Iterable[str]
    ) -> dict[str, Any]:
        """Return the guarded tools ``user`` may use, keyed by model-facing name.

        ``agent_id`` is recorded for auditing only; it never widens access.
        """
        requested = sorted(
            {Capability(name) for name in tool_names if name in DATABASE_TOOL_NAMES}
            & set(self.grant.capabilities),
            key=lambda capability: capability.value,
        )
        if not requested:
            return {}

        subject = subject_from_user(user, agent_id=agent_id, grant=self.grant)
        # Sequential on purpose: the first check warms the membership cache the rest reuse.
        allowed = [
            capability
            for capability in requested
            if (await self.authorizer.authorize(subject, capability)).allowed
        ]
        if not allowed:
            return {}
        return guard_database_tools(
            build_database_tools(self.provider, allowed),
            authorizer=self.authorizer,
            subject=subject,
        )


def _csv_values(value: str | None) -> tuple[str, ...]:
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


def sap_emulator_access(environ: Mapping[str, str]) -> DatabaseAccess | None:
    """Build the SAP emulator access boundary, or ``None`` when it is switched off.

    Raises ``ConfigurationError`` when the feature is on but under-configured, so
    a half-set environment is reported rather than silently ignored.
    """
    if environ.get("SAP_EMULATOR_ENABLED", "").strip().lower() not in {"1", "true", "yes"}:
        return None

    settings = {
        "SAP_EMULATOR_CONNECTIONSTRING": (
            environ.get("SAP_EMULATOR_CONNECTIONSTRING", "").strip()
            or environ.get("AZURE_SQL_CONNECTIONSTRING", "").strip()
        ),
        "SAP_EMULATOR_SERVER_FQDN": environ.get("SAP_EMULATOR_SERVER_FQDN", "").strip(),
        "SAP_EMULATOR_DATABASE_NAME": environ.get("SAP_EMULATOR_DATABASE_NAME", "").strip(),
        "OAUTH_AZURE_GOV_AD_TENANT_ID": (
            environ.get("OAUTH_AZURE_GOV_AD_TENANT_ID", "").strip()
            or environ.get("AZURE_AD_TENANT_ID", "").strip()
        ),
        "SAP_EMULATOR_ENTITLED_GROUP_IDS": _csv_values(
            environ.get("SAP_EMULATOR_ENTITLED_GROUP_IDS")
        ),
    }
    missing = sorted(name for name, value in settings.items() if not value)
    if missing:
        raise ConfigurationError(
            f"SAP emulator configuration is incomplete: {', '.join(missing)}."
        )

    tenant_id = settings["OAUTH_AZURE_GOV_AD_TENANT_ID"]
    entitled_groups = settings["SAP_EMULATOR_ENTITLED_GROUP_IDS"]
    provider = SqlServerProvider(
        DatabaseProviderConfig(
            provider_id=ProviderId.SAP_EMULATOR,
            host=settings["SAP_EMULATOR_SERVER_FQDN"],
            port=SAP_EMULATOR_PORT,
            database=settings["SAP_EMULATOR_DATABASE_NAME"],
            enabled=True,
            approved_schemas=SAP_EMULATOR_SCHEMAS,
            environment=Environment.PRODUCTION,
        ),
        settings["SAP_EMULATOR_CONNECTIONSTRING"],
    )
    logger.info(
        "SAP emulator database access enabled for %d entitled group(s)", len(entitled_groups)
    )
    return DatabaseAccess(
        provider=provider,
        authorizer=DatabaseAuthorizer(allowed_tenant_ids=(tenant_id,)),
        grant=AgentDatabaseGrant(
            provider_id=ProviderId.SAP_EMULATOR,
            capabilities=(Capability.DATABASE_SCHEMA, Capability.DATABASE_QUERY),
            entitled_groups=entitled_groups,
            environment=Environment.PRODUCTION,
        ),
    )


__all__ = [
    "DatabaseAccess",
    "build_database_tools",
    "sap_emulator_access",
]
