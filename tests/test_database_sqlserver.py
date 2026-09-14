"""Offline compatibility tests for the Azure Synapse provider."""

import asyncio
import logging
from decimal import Decimal

import pyodbc
import pytest

from database import (
    DatabaseProviderConfig,
    Environment,
    ProviderId,
    QueryRequest,
    QueryStatus,
    SchemaRequest,
)
from database_sqlserver import SqlServerProvider


class FakeToken:
    token = "token-value-that-must-not-be-logged"


class FakeCredential:
    def __init__(self) -> None:
        self.scopes: list[str] = []

    def get_token(self, scope: str) -> FakeToken:
        self.scopes.append(scope)
        return FakeToken()


class FakeCursor:
    def __init__(self, responses=None, error: Exception | None = None) -> None:
        self.responses = list(responses or [])
        self.error = error
        self.executions: list[tuple[str, tuple | None]] = []
        self.description = []
        self.timeout = 0

    def execute(self, sql: str, parameters=None):
        self.executions.append((sql, parameters))
        if self.error is not None:
            raise self.error
        if self.responses:
            response = self.responses.pop(0)
            self.description = response[0]
            self._rows = response[1]
        else:
            self._rows = []
        return self

    def fetchmany(self, size: int):
        return list(self._rows[:size])

    def close(self) -> None:
        pass


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.closed = False
        self.timeout = 0

    def cursor(self) -> FakeCursor:
        return self._cursor

    def close(self) -> None:
        self.closed = True


def make_config(**overrides) -> DatabaseProviderConfig:
    values = {
        "provider_id": ProviderId.SYNAPSE,
        "enabled": True,
        "host": "synapse.example.test",
        "port": 1433,
        "database": "warehouse",
        "environment": Environment.LOCAL,
        "max_rows": 2,
    }
    values.update(overrides)
    return DatabaseProviderConfig(**values)


def test_default_validator_accepts_tsql_bracket_identifiers():
    provider = SqlServerProvider(
        make_config(approved_schemas=["reporting"]),
        "Driver=fake",
    )

    validated = provider.validator.validate(
        "SELECT * FROM [reporting].[FORCE_EQUIPMENT]",
        approved_schemas=provider.config.normalized_approved_schemas,
    )

    assert validated.referenced_schemas == frozenset({"reporting"})


def test_provider_id_comes_from_configuration():
    emulator = SqlServerProvider(
        make_config(provider_id=ProviderId.SAP_EMULATOR), "Driver=fake"
    )
    assert emulator.provider_id is ProviderId.SAP_EMULATOR
    assert SqlServerProvider(make_config(), "Driver=fake").provider_id is ProviderId.SYNAPSE


def test_bounded_sql_preserves_stricter_explicit_limit():
    provider = SqlServerProvider(make_config(), "Driver=fake")
    validated = provider.validator.validate(
        "SELECT TOP (10) [FORCE_ID] FROM [reporting].[FORCE_EQUIPMENT] ORDER BY [FORCE_ID]"
    )

    bounded = provider._bounded_sql(validated, 101)

    assert "TOP 10" in bounded.upper()
    assert "TOP 101" not in bounded.upper()


def test_azure_ad_connection_uses_government_scope_and_token_attribute(monkeypatch, caplog):
    credential = FakeCredential()
    cursor = FakeCursor()
    calls = []

    def fake_connect(connection_string, **kwargs):
        calls.append((connection_string, kwargs))
        return FakeConnection(cursor)

    monkeypatch.setattr("database_odbc.pyodbc.connect", fake_connect)
    connection_string = (
        "Driver={ODBC Driver 18 for SQL Server};Server=secret-host;"
        "Authentication=ActiveDirectoryMsi;Uid=secret-user;Database=warehouse"
    )
    provider = SqlServerProvider(make_config(), connection_string, credential=credential)

    with caplog.at_level(logging.DEBUG):
        asyncio.run(provider.connect())
        asyncio.run(provider.close())

    used_connection_string, kwargs = calls[0]
    assert "Authentication=" not in used_connection_string
    assert "Uid=" not in used_connection_string
    assert kwargs["attrs_before"][1256]
    assert kwargs["timeout"] == 10
    assert credential.scopes == ["https://database.usgovcloudapi.net/.default"]
    logs = caplog.text
    assert connection_string not in logs
    assert "secret-host" not in logs
    assert "secret-user" not in logs
    assert FakeToken.token not in logs


def test_query_validates_binds_parameters_applies_top_and_bounds_rows(monkeypatch, caplog):
    secret_sql = "SELECT amount FROM sales.orders WHERE customer_id = ? ORDER BY amount"
    cursor = FakeCursor(
        responses=[
            (
                [("amount", Decimal, None, None, None, None, None)],
                [(Decimal("1.25"),), (Decimal("2.50"),), (Decimal("3.75"),)],
            )
        ]
    )
    connection = FakeConnection(cursor)
    monkeypatch.setattr("database_odbc.pyodbc.connect", lambda *args, **kwargs: connection)
    provider = SqlServerProvider(make_config(), "Driver=fake;Server=not-logged")

    with caplog.at_level(logging.DEBUG):
        result = asyncio.run(
            provider.execute_query(QueryRequest(sql=secret_sql, parameters=["private-value"]))
        )

    executed_sql, parameters = cursor.executions[0]
    assert "TOP 3" in executed_sql.upper()
    assert parameters == ("private-value",)
    assert connection.timeout == 30
    assert result.to_dict() == {
        "status": "success",
        "provider": "synapse",
        "columns": [{"name": "amount", "type": "decimal"}],
        "rows": [["1.25"], ["2.50"]],
        "row_count": 2,
        "truncated": True,
        "truncated_by": "row_limit",
        "warnings": [
            "Result was bounded by the row_limit; omitted values are not evidence of absence."
        ],
        "correlation_id": result.correlation_id,
    }
    assert secret_sql not in caplog.text
    assert "private-value" not in caplog.text
    assert "1.25" not in caplog.text


def test_empty_result_still_reports_driver_column_types(monkeypatch):
    import datetime as dt

    cursor = FakeCursor(
        responses=[
            (
                [
                    ("FORCE_ID", str, None, None, None, None, None),
                    ("FL_LEVEL", int, None, None, None, None, None),
                    ("BEGDA", dt.date, None, None, None, None, None),
                ],
                [],
            )
        ]
    )
    monkeypatch.setattr(
        "database_odbc.pyodbc.connect", lambda *args, **kwargs: FakeConnection(cursor)
    )
    provider = SqlServerProvider(make_config(), "Driver=fake")

    payload = asyncio.run(
        provider.execute_query(QueryRequest(sql="SELECT a FROM sales.t WHERE a = ?", parameters=["x"]))
    ).to_dict()

    assert payload["rows"] == []
    assert payload["columns"] == [
        {"name": "FORCE_ID", "type": "string"},
        {"name": "FL_LEVEL", "type": "integer"},
        {"name": "BEGDA", "type": "datetime"},
    ]


def test_unknown_driver_type_is_reported_as_fallback(monkeypatch):
    cursor = FakeCursor(responses=[([("odd", object, None, None, None, None, None)], [])])
    monkeypatch.setattr(
        "database_odbc.pyodbc.connect", lambda *args, **kwargs: FakeConnection(cursor)
    )
    provider = SqlServerProvider(make_config(), "Driver=fake")

    result = asyncio.run(provider.execute_query(QueryRequest(sql="SELECT 1")))

    assert result.to_dict()["columns"] == [{"name": "odd", "type": "fallback"}]


def test_schema_discovery_uses_information_schema_filters_and_groups_columns(monkeypatch):
    cursor = FakeCursor(
        responses=[
            (
                [],
                [
                    ("sales", "orders", "BASE TABLE", "id", "int", 1),
                    ("sales", "orders", "BASE TABLE", "amount", "decimal", 2),
                    ("sales", "summary", "VIEW", "total", "decimal", 1),
                ],
            )
        ]
    )
    monkeypatch.setattr(
        "database_odbc.pyodbc.connect",
        lambda *args, **kwargs: FakeConnection(cursor),
    )
    provider = SqlServerProvider(make_config(max_rows=10), "Driver=fake")

    result = asyncio.run(
        provider.discover_schema(SchemaRequest(schema="sales", object_name="orders"))
    )

    sql, parameters = cursor.executions[0]
    assert "INFORMATION_SCHEMA.TABLES" in sql
    assert "INFORMATION_SCHEMA.COLUMNS" in sql
    assert "OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY" in sql
    assert parameters == ("sales", "orders", 11)
    assert result.to_dict()["objects"] == [
        {
            "schema": "sales",
            "name": "orders",
            "kind": "table",
            "columns": [
                {"name": "id", "type": "integer"},
                {"name": "amount", "type": "decimal"},
            ],
        },
        {
            "schema": "sales",
            "name": "summary",
            "kind": "view",
            "columns": [{"name": "total", "type": "decimal"}],
        },
    ]


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (pyodbc.Error("28000", "login rejected secret detail"), QueryStatus.AUTHENTICATION_ERROR),
        (pyodbc.Error("42501", "permission rejected secret detail"), QueryStatus.AUTHORIZATION_ERROR),
        (pyodbc.Error("08001", "route host secret detail"), QueryStatus.TRANSIENT_ERROR),
        (pyodbc.Error("HYT00", "timeout secret detail"), QueryStatus.TRANSIENT_ERROR),
        (pyodbc.Error("IM002", "driver secret detail"), QueryStatus.CONFIGURATION_ERROR),
        (pyodbc.Error("42000", "syntax secret detail"), QueryStatus.QUERY_ERROR),
    ],
)
def test_driver_errors_map_to_sanitized_results(monkeypatch, caplog, error, expected_status):
    cursor = FakeCursor(error=error)
    monkeypatch.setattr(
        "database_odbc.pyodbc.connect",
        lambda *args, **kwargs: FakeConnection(cursor),
    )
    provider = SqlServerProvider(make_config(), "Driver=fake;Pwd=secret-password")

    with caplog.at_level(logging.DEBUG):
        result = asyncio.run(provider.execute_query(QueryRequest(sql="SELECT 1")))

    assert result.status is expected_status
    assert result.rows == []
    assert "secret detail" not in result.message
    assert "secret detail" not in caplog.text
    assert "secret-password" not in caplog.text


def test_invalid_sql_is_rejected_before_opening_connection(monkeypatch):
    monkeypatch.setattr(
        "database_odbc.pyodbc.connect",
        lambda *args, **kwargs: pytest.fail("connection must not be opened"),
    )
    provider = SqlServerProvider(make_config(), "Driver=fake")

    result = asyncio.run(provider.execute_query(QueryRequest(sql="DELETE FROM sales.orders")))

    assert result.status is QueryStatus.VALIDATION_ERROR
