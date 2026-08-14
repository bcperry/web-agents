"""Offline tests for independent provider selection and model-facing tool shape."""

import asyncio

import pytest

from database import (
    AgentDatabaseGrant,
    Capability,
    ColumnMetadata,
    ConfigurationError,
    DatabaseProvider,
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
from database_authorization import DatabaseAuthorizer
from database_tools import DatabaseAccess, build_database_tools, sap_emulator_access

TENANT = "tenant-1"
ENTITLED_GROUP = "group-1"

EMULATOR_ENV = {
    "SAP_EMULATOR_ENABLED": "true",
    "SAP_EMULATOR_CONNECTIONSTRING": "Driver=fake;Server=sql.test;Database=sap",
    "SAP_EMULATOR_SERVER_FQDN": "sql.test",
    "SAP_EMULATOR_DATABASE_NAME": "sap",
    "OAUTH_AZURE_GOV_AD_TENANT_ID": TENANT,
    "SAP_EMULATOR_ENTITLED_GROUP_IDS": "group-1, group-2",
}


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


class AllowAllResolver:
    def resolve_transitive_group_ids(self, *, user_id: str, tenant_id: str):
        return [ENTITLED_GROUP]


class FakeUser:
    user_id = "user-1"
    tenant_id = TENANT
    group_ids = (ENTITLED_GROUP,)


def make_grant(provider_id: ProviderId, *capabilities: Capability) -> AgentDatabaseGrant:
    return AgentDatabaseGrant(
        provider_id=provider_id,
        capabilities=capabilities,
        entitled_groups=[ENTITLED_GROUP],
        environment=Environment.LOCAL,
    )


def make_access(provider: FakeProvider, *capabilities: Capability) -> DatabaseAccess:
    return DatabaseAccess(
        provider=provider,
        authorizer=DatabaseAuthorizer(allowed_tenant_ids=(TENANT,), resolver=AllowAllResolver()),
        grant=make_grant(provider.provider_id, *capabilities),
    )


def resolve(access: DatabaseAccess, *tool_names: str) -> dict:
    return asyncio.run(
        access.tools_for(user=FakeUser(), agent_id="agent-1", tool_names=tool_names)
    )


def test_fake_hana_and_synapse_satisfy_same_protocol():
    assert isinstance(FakeProvider(ProviderId.SYNAPSE, "synapse"), DatabaseProvider)
    assert isinstance(FakeProvider(ProviderId.HANA, "hana"), DatabaseProvider)


def test_each_provider_serves_its_own_session_without_leakage():
    synapse = FakeProvider(ProviderId.SYNAPSE, "synapse")
    hana = FakeProvider(ProviderId.HANA, "hana")

    synapse_tools = resolve(make_access(synapse, Capability.DATABASE_QUERY), "database_query")
    hana_tools = resolve(make_access(hana, Capability.DATABASE_QUERY), "database_query")

    synapse_result = asyncio.run(synapse_tools["database_query"]("SELECT 1"))
    hana_result = asyncio.run(hana_tools["database_query"]("SELECT 1"))
    assert synapse_result["provider"] == "synapse"
    assert synapse_result["rows"] == [["synapse"]]
    assert hana_result["provider"] == "hana"
    assert hana_result["rows"] == [["hana"]]
    assert (synapse.query_calls, hana.query_calls) == (1, 1)


def test_capability_grant_exposes_only_the_allowed_database_tool():
    provider = FakeProvider(ProviderId.SYNAPSE, "synapse")
    assert set(build_database_tools(provider, [Capability.DATABASE_QUERY])) == {
        Capability.DATABASE_QUERY
    }
    assert set(build_database_tools(provider, [Capability.DATABASE_SCHEMA])) == {
        Capability.DATABASE_SCHEMA
    }


def test_undeclared_and_ungranted_tools_are_never_exposed():
    access = make_access(FakeProvider(ProviderId.SYNAPSE, "synapse"), Capability.DATABASE_SCHEMA)
    assert resolve(access) == {}
    assert resolve(access, "get_user_profile") == {}
    assert resolve(access, "database_query") == {}
    assert set(resolve(access, "database_schema")) == {"database_schema"}


def test_access_rejects_a_grant_for_a_different_provider():
    with pytest.raises(ConfigurationError):
        DatabaseAccess(
            provider=FakeProvider(ProviderId.SYNAPSE, "synapse"),
            authorizer=DatabaseAuthorizer(allowed_tenant_ids=(TENANT,)),
            grant=make_grant(ProviderId.HANA, Capability.DATABASE_QUERY),
        )


def test_emulator_access_is_absent_when_disabled():
    assert sap_emulator_access({}) is None
    assert sap_emulator_access({"SAP_EMULATOR_ENABLED": "false"}) is None


def test_emulator_access_binds_the_configured_tenant_and_groups():
    access = sap_emulator_access(EMULATOR_ENV)

    assert access is not None
    assert access.provider.provider_id is ProviderId.SAP_EMULATOR
    assert access.grant.entitled_groups == ("group-1", "group-2")
    assert access.authorizer.allowed_tenant_ids == frozenset({TENANT})


def test_emulator_access_falls_back_to_the_shared_azure_sql_dsn():
    environ = dict(EMULATOR_ENV)
    del environ["SAP_EMULATOR_CONNECTIONSTRING"]
    environ["AZURE_SQL_CONNECTIONSTRING"] = "Driver=fake;Server=sql.test;Database=sap"

    assert sap_emulator_access(environ) is not None


@pytest.mark.parametrize("missing", ["SAP_EMULATOR_SERVER_FQDN", "SAP_EMULATOR_ENTITLED_GROUP_IDS"])
def test_emulator_access_rejects_incomplete_enabled_configuration(missing: str):
    environ = dict(EMULATOR_ENV)
    del environ[missing]

    with pytest.raises(ConfigurationError, match=missing):
        sap_emulator_access(environ)


def test_incomplete_configuration_never_stops_the_app_from_starting(monkeypatch):
    from app_context import configured_database_access

    monkeypatch.setenv("SAP_EMULATOR_ENABLED", "true")
    monkeypatch.delenv("SAP_EMULATOR_SERVER_FQDN", raising=False)

    assert configured_database_access() is None


def test_database_tool_result_shape_matches_contract():
    provider = FakeProvider(ProviderId.HANA, "hana")
    tools = build_database_tools(provider, [Capability.DATABASE_QUERY, Capability.DATABASE_SCHEMA])

    query = asyncio.run(tools[Capability.DATABASE_QUERY]("SELECT 1", parameters=[1]))
    schema = asyncio.run(tools[Capability.DATABASE_SCHEMA](schema="hana"))

    assert set(query) == {
        "status",
        "provider",
        "columns",
        "rows",
        "row_count",
        "truncated",
        "truncated_by",
        "warnings",
        "correlation_id",
    }
    assert set(schema) == {
        "status",
        "provider",
        "objects",
        "truncated",
        "warnings",
        "correlation_id",
    }
