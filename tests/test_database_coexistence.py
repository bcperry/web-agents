"""Offline tests for independent provider registration and model-facing tools."""

import asyncio

import pytest

from app_context import (
    DatabaseProviderRegistry,
    build_tool_instances,
    configure_sap_emulator_runtime,
)
from database import (
    AgentDatabaseGrant,
    Capability,
    ColumnMetadata,
    DatabaseProvider,
    ConfigurationError,
    Environment,
    NormalizedType,
    ProviderId,
    QueryRequest,
    QueryResult,
    SchemaDiscoveryResult,
    SchemaObjectMetadata,
    SchemaRequest,
    new_correlation_id,
)
from tools import build_database_tools


class FakeProvider:
    def __init__(self, provider_id: ProviderId, marker: str) -> None:
        self.provider_id = provider_id
        self.marker = marker
        self.query_calls = 0
        self.schema_calls = 0

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def discover_schema(self, request: SchemaRequest) -> SchemaDiscoveryResult:
        self.schema_calls += 1
        return SchemaDiscoveryResult(
            provider=self.provider_id,
            correlation_id=new_correlation_id(),
            objects=[
                SchemaObjectMetadata(
                    schema=self.marker,
                    name="orders",
                    kind="view",
                    columns=[ColumnMetadata("id", NormalizedType.INTEGER)],
                )
            ],
        )

    async def execute_query(self, request: QueryRequest) -> QueryResult:
        self.query_calls += 1
        return QueryResult(
            provider=self.provider_id,
            correlation_id=new_correlation_id(),
            columns=[ColumnMetadata("source", NormalizedType.STRING)],
            rows=[[self.marker]],
        )


def grant(provider_id: ProviderId, *capabilities: Capability) -> AgentDatabaseGrant:
    return AgentDatabaseGrant(
        provider_id=provider_id,
        capabilities=capabilities,
        entitled_groups=["test-group"],
        environment=Environment.LOCAL,
    )


def by_name(tools):
    return {tool.__name__: tool for tool in tools}


def test_fake_hana_and_synapse_satisfy_same_protocol():
    assert isinstance(FakeProvider(ProviderId.SYNAPSE, "synapse"), DatabaseProvider)
    assert isinstance(FakeProvider(ProviderId.HANA, "hana"), DatabaseProvider)


def test_registry_selects_each_provider_independently_without_leakage():
    synapse = FakeProvider(ProviderId.SYNAPSE, "synapse")
    hana = FakeProvider(ProviderId.HANA, "hana")
    registry = DatabaseProviderRegistry([synapse, hana])

    synapse_tools = by_name(
        build_tool_instances(
            set(),
            session_id="synapse-session",
            database_grant=grant(ProviderId.SYNAPSE, Capability.DATABASE_QUERY),
            database_registry=registry,
        )
    )
    hana_tools = by_name(
        build_tool_instances(
            set(),
            session_id="hana-session",
            database_grant=grant(ProviderId.HANA, Capability.DATABASE_QUERY),
            database_registry=registry,
        )
    )

    synapse_result = asyncio.run(synapse_tools["database_query"]("SELECT 1"))
    hana_result = asyncio.run(hana_tools["database_query"]("SELECT 1"))
    assert synapse_result["provider"] == "synapse"
    assert synapse_result["rows"] == [["synapse"]]
    assert hana_result["provider"] == "hana"
    assert hana_result["rows"] == [["hana"]]
    assert (synapse.query_calls, hana.query_calls) == (1, 1)


def test_capability_grant_exposes_only_the_allowed_database_tool():
    provider = FakeProvider(ProviderId.SYNAPSE, "synapse")
    query_tools = build_database_tools(
        provider, grant(ProviderId.SYNAPSE, Capability.DATABASE_QUERY)
    )
    schema_tools = build_database_tools(
        provider, grant(ProviderId.SYNAPSE, Capability.DATABASE_SCHEMA)
    )
    assert set(query_tools) == {"database_query"}
    assert set(schema_tools) == {"database_schema"}


def test_absent_grant_or_missing_provider_registers_no_database_tools():
    registry = DatabaseProviderRegistry(
        [FakeProvider(ProviderId.SYNAPSE, "synapse")]
    )
    assert build_tool_instances(set(), session_id="ordinary", database_registry=registry) == []
    assert build_tool_instances(
        set(),
        session_id="missing-hana",
        database_grant=grant(ProviderId.HANA, Capability.DATABASE_QUERY),
        database_registry=registry,
    ) == []


def test_sap_emulator_runtime_registers_only_for_its_agent_profile():
    registry = DatabaseProviderRegistry()
    authorizer, resolver = configure_sap_emulator_runtime(
        environ={
            "SAP_EMULATOR_ENABLED": "true",
            "AZURE_SQL_CONNECTIONSTRING": "Driver=fake;Server=sql.test;Database=sap",
            "SAP_EMULATOR_SERVER_FQDN": "sql.test",
            "SAP_EMULATOR_DATABASE_NAME": "sap",
            "OAUTH_AZURE_GOV_AD_TENANT_ID": "tenant-1",
            "SAP_EMULATOR_ENTITLED_GROUP_IDS": "group-1, group-2",
        },
        registry=registry,
    )

    assert authorizer is not None
    assert resolver is not None
    grant = resolver(None, "sap_force_equipment")
    assert grant is not None
    assert grant.provider_id is ProviderId.SAP_EMULATOR
    assert grant.entitled_groups == ("group-1", "group-2")
    assert set(registry.tools_for_grant(grant)) == {"database_query", "database_schema"}
    assert resolver(None, "sql") is None


def test_sap_emulator_runtime_rejects_incomplete_enabled_configuration():
    with pytest.raises(ConfigurationError, match="SAP_EMULATOR_SERVER_FQDN"):
        configure_sap_emulator_runtime(
            environ={
                "SAP_EMULATOR_ENABLED": "true",
                "AZURE_SQL_CONNECTIONSTRING": "Driver=fake",
            },
            registry=DatabaseProviderRegistry(),
        )


def test_database_tool_result_shape_matches_contract():
    provider = FakeProvider(ProviderId.HANA, "hana")
    tools = build_database_tools(
        provider,
        grant(
            ProviderId.HANA,
            Capability.DATABASE_QUERY,
            Capability.DATABASE_SCHEMA,
        ),
    )

    query = asyncio.run(tools["database_query"]("SELECT 1", parameters=[1]))
    schema = asyncio.run(tools["database_schema"](schema="hana"))

    assert set(query) == {
        "status",
        "provider",
        "columns",
        "rows",
        "row_count",
        "truncated",
        "truncated_by",
        "continuation",
        "warnings",
        "correlation_id",
    }
    assert set(schema) == {
        "status",
        "provider",
        "objects",
        "truncated",
        "continuation",
        "warnings",
        "correlation_id",
    }
