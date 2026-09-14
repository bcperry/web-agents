"""Failing-first tests for the provider-neutral database tool contract.

Covers the ``DatabaseProvider`` shape, normalized serialization, result
bounding/truncation reporting, and the sanitized error contract.
"""

import datetime as dt
import inspect
from decimal import Decimal

import pytest

from database import (
    MAX_QUERY_RESULT_CHARS,
    MAX_QUERY_RESULT_ROWS,
    MAX_SQL_CELL_CHARS,
    TIMEZONE_NAIVE_WARNING,
    UNORDERED_RESULT_WARNING,
    AgentDatabaseGrant,
    AuthenticationError,
    AuthorizationError,
    Capability,
    ColumnMetadata,
    ConfigurationError,
    DatabaseError,
    DatabaseProvider,
    DatabaseProviderConfig,
    Environment,
    NormalizedType,
    ProviderId,
    QueryError,
    QueryRequest,
    QueryResult,
    QueryStatus,
    SchemaDiscoveryResult,
    SchemaObjectMetadata,
    SchemaRequest,
    TransientError,
    TrustError,
    TruncationLimit,
    ValidationError,
    bound_result_rows,
    new_correlation_id,
    normalize_value,
)


def make_config(**overrides) -> DatabaseProviderConfig:
    base = dict(
        provider_id=ProviderId.HANA,
        enabled=False,
        host="hana.internal.example",
        port=30015,
        database="HDB",
    )
    base.update(overrides)
    return DatabaseProviderConfig(**base)


class FakeProvider:
    """Minimal provider-neutral double used to pin the protocol shape."""

    provider_id = ProviderId.SYNAPSE

    def __init__(self) -> None:
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.connected = False

    async def discover_schema(self, request: SchemaRequest) -> SchemaDiscoveryResult:
        return SchemaDiscoveryResult(
            provider=self.provider_id,
            objects=[
                SchemaObjectMetadata(
                    schema="sales",
                    name="orders",
                    kind="table",
                    columns=[ColumnMetadata(name="id", type_label=NormalizedType.INTEGER)],
                )
            ],
            correlation_id=new_correlation_id(),
        )

    async def execute_query(self, request: QueryRequest) -> QueryResult:
        return QueryResult(
            provider=self.provider_id,
            columns=[ColumnMetadata(name="id", type_label=NormalizedType.INTEGER)],
            rows=[[1]],
            correlation_id=new_correlation_id(),
        )


class IncompleteProvider:
    provider_id = ProviderId.SYNAPSE


# --------------------------------------------------------------------------
# Provider contract shape
# --------------------------------------------------------------------------


def test_fake_provider_satisfies_protocol():
    assert isinstance(FakeProvider(), DatabaseProvider)


def test_incomplete_provider_does_not_satisfy_protocol():
    assert not isinstance(IncompleteProvider(), DatabaseProvider)


def test_provider_protocol_is_vendor_neutral():
    names = " ".join(dir(DatabaseProvider)).lower()
    for vendor_token in ("hana", "synapse", "hdbcli", "pyodbc", "odbc"):
        assert vendor_token not in names


def test_provider_lifecycle_methods_are_async():
    for name in ("connect", "close", "discover_schema", "execute_query"):
        assert inspect.iscoroutinefunction(getattr(FakeProvider, name))


def test_provider_returns_declared_result_types():
    import asyncio

    provider = FakeProvider()

    async def run():
        await provider.connect()
        schema = await provider.discover_schema(SchemaRequest())
        result = await provider.execute_query(QueryRequest(sql="SELECT 1"))
        await provider.close()
        return schema, result

    schema, result = asyncio.run(run())
    assert isinstance(schema, SchemaDiscoveryResult)
    assert isinstance(result, QueryResult)
    assert result.status is QueryStatus.SUCCESS
    assert result.row_count == 1
    assert provider.connected is False


# --------------------------------------------------------------------------
# Configuration and grants
# --------------------------------------------------------------------------


def test_config_defaults_reuse_shared_limits():
    config = make_config()
    assert config.max_rows == MAX_QUERY_RESULT_ROWS
    assert config.max_result_chars == MAX_QUERY_RESULT_CHARS
    assert config.max_cell_chars == MAX_SQL_CELL_CHARS


def test_config_rejects_invalid_port_and_timeouts():
    for kwargs in ({"port": 0}, {"port": 65536}, {"connect_timeout_seconds": 0}, {"query_timeout_seconds": -1}):
        with pytest.raises(ValidationError):
            make_config(**kwargs)


def test_config_fingerprint_is_stable_and_change_sensitive():
    a = make_config()
    b = make_config()
    assert a.config_fingerprint == b.config_fingerprint
    assert a.config_fingerprint != make_config(port=30013).config_fingerprint
    assert a.config_fingerprint != make_config(database="OTHER").config_fingerprint
    assert a.config_fingerprint != make_config(approved_schemas=["sales"]).config_fingerprint


def test_config_rejects_unknown_environment():
    with pytest.raises(ValidationError):
        make_config(environment="production")


def test_approved_schemas_normalized_for_comparison():
    config = make_config(approved_schemas=["Sales", "REPORTING"])
    assert config.normalized_approved_schemas == frozenset({"sales", "reporting"})
    assert make_config().normalized_approved_schemas == frozenset()


def test_grant_binds_provider_and_environment():
    grant = AgentDatabaseGrant(
        provider_id=ProviderId.HANA,
        capabilities={Capability.DATABASE_QUERY},
        entitled_groups=["11111111-1111-1111-1111-111111111111"],
        environment=Environment.DEVELOPMENT,
    )
    assert grant.allows(Capability.DATABASE_QUERY) is True
    assert grant.allows(Capability.DATABASE_SCHEMA) is False


def test_hana_grant_with_no_entitled_groups_allows_nobody():
    grant = AgentDatabaseGrant(
        provider_id=ProviderId.HANA,
        capabilities={Capability.DATABASE_QUERY},
        entitled_groups=[],
        environment=Environment.PRODUCTION,
    )
    assert grant.entitles_groups(set()) is False
    assert grant.entitles_groups({"11111111-1111-1111-1111-111111111111"}) is False


# --------------------------------------------------------------------------
# Normalized serialization
# --------------------------------------------------------------------------


def test_normalize_null_boolean_integer_string():
    assert normalize_value(None)[:2] == (None, NormalizedType.NULL)
    assert normalize_value(True)[:2] == (True, NormalizedType.BOOLEAN)
    assert normalize_value(7)[:2] == (7, NormalizedType.INTEGER)
    assert normalize_value("x")[:2] == ("x", NormalizedType.STRING)


def test_normalize_decimal_is_serialized_as_string():
    value, type_label, _ = normalize_value(Decimal("12345678901234567890.123"))
    assert type_label is NormalizedType.DECIMAL
    assert value == "12345678901234567890.123"
    assert isinstance(value, str)


def test_normalize_float_and_non_finite_float():
    assert normalize_value(1.5)[:2] == (1.5, NormalizedType.FLOAT)
    value, type_label, _ = normalize_value(float("nan"))
    assert type_label is NormalizedType.FALLBACK
    assert isinstance(value, str)


def test_normalize_timezone_aware_timestamp():
    aware = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)
    value, type_label, tz_aware = normalize_value(aware)
    assert type_label is NormalizedType.DATETIME
    assert value.endswith("+00:00")
    assert tz_aware is True


def test_normalize_timezone_naive_timestamp_is_identified():
    naive = dt.datetime(2026, 1, 2, 3, 4, 5)
    value, type_label, tz_aware = normalize_value(naive)
    assert type_label is NormalizedType.DATETIME
    assert value == "2026-01-02T03:04:05"
    assert tz_aware is False


def test_normalize_date_and_time():
    assert normalize_value(dt.date(2026, 1, 2))[:2] == ("2026-01-02", NormalizedType.DATETIME)
    assert normalize_value(dt.time(3, 4, 5))[:2] == ("03:04:05", NormalizedType.DATETIME)


def test_normalize_binary_returns_metadata_only():
    value, type_label, _ = normalize_value(b"\x00\x01secret-bytes")
    assert type_label is NormalizedType.BINARY
    assert value == {"kind": "binary", "byte_length": 14, "returned": False}
    assert "secret" not in str(value)


def test_normalize_unknown_type_falls_back_to_string():
    class Weird:
        def __str__(self) -> str:
            return "weird"

    value, type_label, _ = normalize_value(Weird())
    assert (value, type_label) == ("weird", NormalizedType.FALLBACK)


# --------------------------------------------------------------------------
# Result bounding / truncation
# --------------------------------------------------------------------------


def test_untruncated_result_reports_no_limit():
    bounded = bound_result_rows([[1], [2]], max_rows=10, has_explicit_order=True)
    assert bounded.rows == [[1], [2]]
    assert bounded.truncated is False
    assert bounded.truncated_by is None
    assert bounded.limits_reached == frozenset()
    assert bounded.has_more is False


def test_row_limit_uses_limit_plus_one_semantics():
    fetched = [[i] for i in range(6)]  # provider fetched max_rows + 1
    bounded = bound_result_rows(fetched, max_rows=5, has_explicit_order=True)
    assert len(bounded.rows) == 5
    assert bounded.has_more is True
    assert bounded.truncated is True
    assert bounded.truncated_by is TruncationLimit.ROW_LIMIT
    assert bounded.limits_reached == frozenset({TruncationLimit.ROW_LIMIT})


def test_character_limit_can_trigger_before_row_limit():
    fetched = [["x" * 100] for _ in range(50)]
    bounded = bound_result_rows(
        fetched, max_rows=100, max_result_chars=500, has_explicit_order=True
    )
    assert bounded.has_more is False
    assert bounded.truncated is True
    assert bounded.truncated_by is TruncationLimit.TOTAL_CHAR_LIMIT
    assert TruncationLimit.TOTAL_CHAR_LIMIT in bounded.limits_reached
    assert len(bounded.rows) < 50


def test_cell_limit_reported_and_value_truncated():
    fetched = [["y" * 50]]
    bounded = bound_result_rows(
        fetched, max_rows=10, max_cell_chars=10, has_explicit_order=True
    )
    assert bounded.truncated is True
    assert bounded.truncated_by is TruncationLimit.CELL_CHAR_LIMIT
    assert bounded.limits_reached == frozenset({TruncationLimit.CELL_CHAR_LIMIT})
    assert bounded.rows[0][0].startswith("y" * 10)
    assert "TRUNCATED" in bounded.rows[0][0]


def test_multiple_limits_are_all_reported():
    fetched = [["z" * 50] for _ in range(4)]
    bounded = bound_result_rows(
        fetched, max_rows=3, max_cell_chars=10, has_explicit_order=True
    )
    assert bounded.limits_reached == frozenset(
        {TruncationLimit.ROW_LIMIT, TruncationLimit.CELL_CHAR_LIMIT}
    )
    assert bounded.truncated_by is TruncationLimit.ROW_LIMIT


def test_unordered_truncation_is_marked_partial():
    fetched = [[i] for i in range(6)]
    bounded = bound_result_rows(fetched, max_rows=5, has_explicit_order=False)
    assert bounded.truncated is True
    assert UNORDERED_RESULT_WARNING in bounded.warnings


def test_ordered_truncation_omits_the_unordered_warning():
    fetched = [[i] for i in range(6)]
    bounded = bound_result_rows(fetched, max_rows=5, has_explicit_order=True)
    assert UNORDERED_RESULT_WARNING not in bounded.warnings


def test_unordered_but_complete_result_is_not_warned():
    bounded = bound_result_rows([[1]], max_rows=5, has_explicit_order=False)
    assert bounded.truncated is False
    assert bounded.warnings == []


def test_timezone_naive_values_add_a_warning():
    bounded = bound_result_rows(
        [[dt.datetime(2026, 1, 1, 0, 0, 0)]], max_rows=10, has_explicit_order=True
    )
    assert TIMEZONE_NAIVE_WARNING in bounded.warnings


def test_bounding_normalizes_values_without_typing_columns():
    bounded = bound_result_rows(
        [[None, Decimal("1.5")], [1, Decimal("2.5")]], max_rows=10, has_explicit_order=True
    )
    assert bounded.rows == [[None, "1.5"], [1, "2.5"]]
    assert not hasattr(bounded, "column_types")


def test_bounding_defaults_to_shared_limits():
    bounded = bound_result_rows([[1]], has_explicit_order=True)
    assert bounded.applied_limits == (
        MAX_QUERY_RESULT_ROWS,
        MAX_QUERY_RESULT_CHARS,
        MAX_SQL_CELL_CHARS,
    )


# --------------------------------------------------------------------------
# Error contract
# --------------------------------------------------------------------------

ERROR_CASES = [
    (ValidationError, QueryStatus.VALIDATION_ERROR),
    (AuthenticationError, QueryStatus.AUTHENTICATION_ERROR),
    (AuthorizationError, QueryStatus.AUTHORIZATION_ERROR),
    (TrustError, QueryStatus.TRUST_ERROR),
    (ConfigurationError, QueryStatus.CONFIGURATION_ERROR),
    (TransientError, QueryStatus.TRANSIENT_ERROR),
    (QueryError, QueryStatus.QUERY_ERROR),
]


@pytest.mark.parametrize("error_type,status", ERROR_CASES, ids=[c[1].value for c in ERROR_CASES])
def test_error_category_mapping(error_type, status):
    error = error_type("safe message")
    assert isinstance(error, DatabaseError)
    assert error.status is status


def test_error_result_is_sanitized_and_empty():
    cause = RuntimeError("hana.internal.example password=hunter2 SELECT secret_column")
    error = TransientError("temporary provider interruption", cause=cause)
    result = error.to_result(provider=ProviderId.HANA, correlation_id="corr-1")
    assert result.status is QueryStatus.TRANSIENT_ERROR
    assert result.rows == []
    assert result.row_count == 0
    assert result.truncated is False
    assert result.correlation_id == "corr-1"
    payload = result.to_dict()
    serialized = str(payload)
    for leak in ("hunter2", "hana.internal.example", "secret_column"):
        assert leak not in serialized
    assert "cause" not in payload


def test_error_schema_result_is_sanitized_and_empty():
    error = AuthorizationError("denied", cause=RuntimeError("secret detail"))
    payload = error.to_schema_result(provider=ProviderId.HANA, correlation_id="corr-4").to_dict()
    assert payload["status"] == "authorization_error"
    assert payload["objects"] == []
    assert payload["message"] == "denied"
    assert "secret detail" not in str(payload)


def test_success_result_serialization_shape():
    result = QueryResult(
        provider=ProviderId.SYNAPSE,
        columns=[ColumnMetadata(name="id", type_label=NormalizedType.INTEGER)],
        rows=[[1]],
        correlation_id="corr-2",
    )
    payload = result.to_dict()
    assert payload["status"] == "success"
    assert payload["provider"] == "synapse"
    assert payload["columns"] == [{"name": "id", "type": "integer"}]
    assert payload["rows"] == [[1]]
    assert payload["row_count"] == 1
    assert payload["truncated"] is False
    assert payload["warnings"] == []
    assert payload["correlation_id"] == "corr-2"


def test_schema_result_serialization_shape():
    result = SchemaDiscoveryResult(
        provider=ProviderId.HANA,
        objects=[
            SchemaObjectMetadata(
                schema="sales",
                name="orders",
                kind="table",
                columns=[ColumnMetadata(name="id", type_label=NormalizedType.INTEGER)],
            )
        ],
        correlation_id="corr-3",
    )
    payload = result.to_dict()
    assert payload["provider"] == "hana"
    assert payload["objects"][0]["schema"] == "sales"
    assert payload["objects"][0]["columns"] == [{"name": "id", "type": "integer"}]
    assert payload["truncated"] is False
    assert "definition" not in payload["objects"][0]


def test_correlation_ids_are_unique_and_opaque():
    a, b = new_correlation_id(), new_correlation_id()
    assert a != b
    assert a.isalnum()
