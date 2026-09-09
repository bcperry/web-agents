"""Read-only end-to-end checks against a live, configured SAP emulator database.

Skipped unless the running environment resolves a real ``DatabaseAccess``. These
exercise the one path unit tests cannot: the ODBC driver, the Entra handshake,
and the real catalog.
"""

import asyncio

import pytest

from app_context import configured_database_access
from database import DATABASE_TOOL_NAMES
from prompt_config import load_agents_yaml

pytestmark = pytest.mark.sqlserver_integration

REPORTING_VIEW = "[reporting].[FORCE_EQUIPMENT]"
FINANCE_REPORTING_VIEW = "[reporting].[FINANCIAL_EXECUTION]"
UNENTITLED_GROUP = "00000000-0000-0000-0000-000000000000"


@pytest.fixture(scope="module")
def access():
    resolved = configured_database_access()
    if resolved is None:
        pytest.skip("No SAP emulator database is configured in this environment.")
    return resolved


class User:
    def __init__(self, access, group_ids=None) -> None:
        self.user_id = "integration-check"
        self.tenant_id = next(iter(access.authorizer.allowed_tenant_ids))
        self.group_ids = (
            access.grant.entitled_groups if group_ids is None else tuple(group_ids)
        )


def resolve(access, user=None, tool_names=DATABASE_TOOL_NAMES, agent_id="sap_force_equipment"):
    return asyncio.run(
        access.tools_for(
            user=user or User(access), agent_id=agent_id, tool_names=tool_names
        )
    )


def test_declared_profile_tools_resolve_against_the_live_database(access):
    profiles = load_agents_yaml()["profiles"]

    for agent_id in ("sap_force_equipment", "sap_financial_execution"):
        declared = profiles[agent_id]["tools"]
        assert set(resolve(access, tool_names=declared, agent_id=agent_id)) == {
            "database_schema",
            "database_query",
        }


def test_schema_discovery_returns_the_reporting_contract(access):
    result = asyncio.run(
        resolve(access)["database_schema"](schema="reporting", object_name="FORCE_EQUIPMENT")
    )

    assert result["status"] == "success"
    assert [obj["name"] for obj in result["objects"]] == ["FORCE_EQUIPMENT"]
    assert len(result["objects"][0]["columns"]) == 21


def test_finance_schema_and_query_return_the_reporting_contract(access):
    tools = resolve(access, agent_id="sap_financial_execution")
    schema = asyncio.run(
        tools["database_schema"](schema="reporting", object_name="FINANCIAL_EXECUTION")
    )
    result = asyncio.run(
        tools["database_query"](
            f"SELECT COUNT(*) AS N FROM {FINANCE_REPORTING_VIEW} WHERE [FISCAL_YEAR] = ?",
            [2026],
        )
    )

    assert schema["status"] == "success"
    assert [obj["name"] for obj in schema["objects"]] == ["FINANCIAL_EXECUTION"]
    assert len(schema["objects"][0]["columns"]) == 20
    assert result["status"] == "success"
    assert result["rows"] == [[500]]


def test_query_binds_parameters_and_types_columns(access):
    result = asyncio.run(
        resolve(access)["database_query"](
            f"SELECT COUNT(*) AS N FROM {REPORTING_VIEW} WHERE [FE_SHORT] = ?",
            ["no-such-force"],
        )
    )

    assert result["status"] == "success"
    assert result["rows"] == [[0]]
    assert [column["type"] for column in result["columns"]] == ["integer"]


def test_unordered_truncation_warns_that_omitted_rows_are_arbitrary(access):
    tools = resolve(access)

    unordered = asyncio.run(tools["database_query"](f"SELECT [EQUNR] FROM {REPORTING_VIEW}"))
    ordered = asyncio.run(
        tools["database_query"](f"SELECT [EQUNR] FROM {REPORTING_VIEW} ORDER BY [EQUNR]")
    )

    assert unordered["truncated_by"] == ordered["truncated_by"] == "row_limit"
    assert len(unordered["warnings"]) == 2
    assert len(ordered["warnings"]) == 1


@pytest.mark.parametrize(
    "sql",
    [
        f"DELETE FROM {REPORTING_VIEW}",
        f"UPDATE {REPORTING_VIEW} SET [EQUNR] = '1'",
        "SELECT TOP 1 * FROM [dbo].[EQUI]",
    ],
)
def test_writes_and_off_schema_reads_never_reach_the_database(access, sql):
    result = asyncio.run(resolve(access)["database_query"](sql))

    assert result["status"] == "validation_error"
    assert result["rows"] == []


def test_unentitled_user_receives_no_tools(access):
    assert resolve(access, User(access, group_ids=[UNENTITLED_GROUP])) == {}
