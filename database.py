"""Provider-neutral database contract.

This module owns everything that must behave identically for every database
provider: configuration and grants, request/result models, bounded result
serialization, and the sanitized error contract. The read-only SQL grammar gate
lives in ``database_sql``; vendor specifics live in the per-provider modules.

Nothing here logs SQL text, parameter values, result cells, or credentials.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from text_limits import env_int, truncate_text

logger = logging.getLogger("database")


# ---------------------------------------------------------------------------
# Limits (contract: contracts/database-tools.md)
# ---------------------------------------------------------------------------

MAX_QUERY_RESULT_ROWS = env_int("MAX_QUERY_RESULT_ROWS", 100)
MAX_QUERY_RESULT_CHARS = env_int("MAX_QUERY_RESULT_CHARS", 12000)
MAX_SQL_CELL_CHARS = env_int("MAX_SQL_CELL_CHARS", 1200)

MIN_SQL_CHARS = 1
MAX_SQL_CHARS = 20_000
MAX_PARAMETERS = 100
MAX_PARAMETER_STRING_CHARS = 4_096
MAX_PARAMETERS_CANONICAL_BYTES = 16_384
MAX_IDENTIFIER_CHARS = 127
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1

UNORDERED_RESULT_WARNING = (
    "Partial result from a query without an explicit ORDER BY: the omitted rows are "
    "arbitrary and are not evidence of absence. Reissue a narrower query with ORDER BY."
)
TIMEZONE_NAIVE_WARNING = (
    "One or more timestamp values are timezone-naive as supplied by the provider."
)
BINARY_OMITTED_WARNING = (
    "Binary or large-object values are reported as metadata only and are not returned."
)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ProviderId(str, Enum):
    SYNAPSE = "synapse"
    SAP_EMULATOR = "sap_emulator"
    HANA = "hana"


class Environment(str, Enum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Capability(str, Enum):
    DATABASE_SCHEMA = "database_schema"
    DATABASE_QUERY = "database_query"


DATABASE_TOOL_NAMES = frozenset(capability.value for capability in Capability)


class QueryStatus(str, Enum):
    SUCCESS = "success"
    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    TRUST_ERROR = "trust_error"
    CONFIGURATION_ERROR = "configuration_error"
    TRANSIENT_ERROR = "transient_error"
    QUERY_ERROR = "query_error"


class NormalizedType(str, Enum):
    NULL = "null"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    DECIMAL = "decimal"
    FLOAT = "float"
    STRING = "string"
    DATETIME = "datetime"
    BINARY = "binary"
    FALLBACK = "fallback"


class TruncationLimit(str, Enum):
    ROW_LIMIT = "row_limit"
    TOTAL_CHAR_LIMIT = "total_char_limit"
    CELL_CHAR_LIMIT = "cell_char_limit"


# ---------------------------------------------------------------------------
# Sanitized error contract
# ---------------------------------------------------------------------------


def new_correlation_id() -> str:
    """Opaque, log-safe identifier for server-side diagnostics."""
    return uuid.uuid4().hex


class DatabaseError(Exception):
    """Base class for sanitized, category-mapped database failures.

    ``message`` is operator-authored and safe to return to the model. ``cause``
    stays server-side and is never serialized.
    """

    status: QueryStatus = QueryStatus.QUERY_ERROR

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.cause = cause

    def to_result(
        self, *, provider: ProviderId, correlation_id: str | None = None
    ) -> "QueryResult":
        return QueryResult(
            provider=provider,
            status=self.status,
            correlation_id=correlation_id or new_correlation_id(),
            message=self.message,
        )

    def to_schema_result(
        self, *, provider: ProviderId, correlation_id: str | None = None
    ) -> "SchemaDiscoveryResult":
        return SchemaDiscoveryResult(
            provider=provider,
            status=self.status,
            correlation_id=correlation_id or new_correlation_id(),
            message=self.message,
        )


class ValidationError(DatabaseError):
    status = QueryStatus.VALIDATION_ERROR


class AuthenticationError(DatabaseError):
    status = QueryStatus.AUTHENTICATION_ERROR


class AuthorizationError(DatabaseError):
    status = QueryStatus.AUTHORIZATION_ERROR


class TrustError(DatabaseError):
    status = QueryStatus.TRUST_ERROR


class ConfigurationError(DatabaseError):
    status = QueryStatus.CONFIGURATION_ERROR


class TransientError(DatabaseError):
    status = QueryStatus.TRANSIENT_ERROR


class QueryError(DatabaseError):
    status = QueryStatus.QUERY_ERROR


# ---------------------------------------------------------------------------
# Canonical digests (server-internal only; never crosses a trust boundary)
# ---------------------------------------------------------------------------


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Scalar / parameter validation
# ---------------------------------------------------------------------------


def _validate_scalar(value: Any, *, context: str) -> Any:
    """Accept only null, bool, signed 64-bit int, finite float, or bounded string."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if not (INT64_MIN <= value <= INT64_MAX):
            raise ValidationError(f"{context} integers must fit in a signed 64-bit range.")
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValidationError(f"{context} numbers must be finite.")
        return value
    if isinstance(value, str):
        if len(value) > MAX_PARAMETER_STRING_CHARS:
            raise ValidationError(
                f"{context} strings are limited to {MAX_PARAMETER_STRING_CHARS} characters."
            )
        return value
    raise ValidationError(
        f"{context} must be null, boolean, integer, finite number, or string; "
        f"got {type(value).__name__}."
    )


def validate_parameters(parameters: Any) -> tuple[Any, ...] | None:
    """Validate positional bound parameters. Values are never echoed in errors."""
    if parameters is None:
        return None
    if isinstance(parameters, (str, bytes, bytearray, Mapping)) or not isinstance(
        parameters, Sequence
    ):
        raise ValidationError("Parameters must be a positional list of scalars.")
    if len(parameters) > MAX_PARAMETERS:
        raise ValidationError(f"At most {MAX_PARAMETERS} positional parameters are allowed.")
    validated = tuple(_validate_scalar(value, context="Parameter") for value in parameters)
    if len(canonical_bytes(list(validated))) > MAX_PARAMETERS_CANONICAL_BYTES:
        raise ValidationError(
            "Canonical parameter encoding exceeds "
            f"{MAX_PARAMETERS_CANONICAL_BYTES} UTF-8 bytes."
        )
    return validated


def validate_sql_text(sql: Any) -> str:
    if not isinstance(sql, str):
        raise ValidationError("SQL must be a string.")
    if len(sql) > MAX_SQL_CHARS:
        raise ValidationError(f"SQL exceeds the {MAX_SQL_CHARS} character limit.")
    if len(sql.strip()) < MIN_SQL_CHARS:
        raise ValidationError("SQL must contain exactly one read query.")
    return sql


_IDENTIFIER_DENIED_CHARS = frozenset('.;"\'`%*[]{}()\\/,?')


def validate_identifier_filter(value: Any, *, field: str) -> str | None:
    """Validate an optional schema/object discovery filter."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} filter must be a string or null.")
    trimmed = value.strip()
    if not trimmed:
        raise ValidationError(f"{field} filter must not be blank.")
    if len(trimmed) > MAX_IDENTIFIER_CHARS:
        raise ValidationError(f"{field} filter is limited to {MAX_IDENTIFIER_CHARS} characters.")
    if any(char < "\x20" or char == "\x7f" for char in trimmed):
        raise ValidationError(f"{field} filter must not contain control characters.")
    if any(char in _IDENTIFIER_DENIED_CHARS for char in trimmed):
        raise ValidationError(f"{field} filter must not contain separator or wildcard syntax.")
    return trimmed


# ---------------------------------------------------------------------------
# Configuration and grants
# ---------------------------------------------------------------------------


@dataclass
class DatabaseProviderConfig:
    provider_id: ProviderId
    host: str
    port: int
    database: str
    enabled: bool = False
    approved_schemas: Sequence[str] | None = None
    allowed_table_functions: Sequence[str] | None = None
    connect_timeout_seconds: int = 10
    query_timeout_seconds: int = 30
    max_rows: int = MAX_QUERY_RESULT_ROWS
    max_result_chars: int = MAX_QUERY_RESULT_CHARS
    max_cell_chars: int = MAX_SQL_CELL_CHARS
    environment: Environment = Environment.LOCAL

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise ValidationError("provider_id must be a known provider.")
        if not isinstance(self.environment, Environment):
            raise ValidationError("environment must be a known environment.")
        if not str(self.host).strip():
            raise ValidationError("host is required.")
        if (
            not isinstance(self.port, int)
            or isinstance(self.port, bool)
            or not (1 <= self.port <= 65535)
        ):
            raise ValidationError("port must be between 1 and 65535.")
        if not str(self.database).strip():
            raise ValidationError("database is required.")
        for name in (
            "connect_timeout_seconds",
            "query_timeout_seconds",
            "max_rows",
            "max_result_chars",
            "max_cell_chars",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValidationError(f"{name} must be a positive integer.")

    @property
    def normalized_approved_schemas(self) -> frozenset[str]:
        return frozenset(
            name.strip().lower() for name in (self.approved_schemas or ()) if name.strip()
        )

    @property
    def normalized_table_functions(self) -> frozenset[str]:
        return frozenset(
            name.strip().lower() for name in (self.allowed_table_functions or ()) if name.strip()
        )

    @property
    def config_fingerprint(self) -> str:
        """SHA-256 over the canonical non-secret settings."""
        return sha256_hex(
            canonical_bytes(
                {
                    "provider": self.provider_id.value,
                    "environment": self.environment.value,
                    "enabled": self.enabled,
                    "host": self.host,
                    "port": self.port,
                    "database": self.database,
                    "approved_schemas": sorted(self.normalized_approved_schemas),
                    "allowed_table_functions": sorted(self.normalized_table_functions),
                    "connect_timeout_seconds": self.connect_timeout_seconds,
                    "query_timeout_seconds": self.query_timeout_seconds,
                    "limits": [self.max_rows, self.max_result_chars, self.max_cell_chars],
                }
            )
        )


@dataclass
class AgentDatabaseGrant:
    provider_id: ProviderId
    capabilities: Iterable[Capability]
    entitled_groups: Sequence[str]
    environment: Environment

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise ValidationError("provider_id must be a known provider.")
        if not isinstance(self.environment, Environment):
            raise ValidationError("environment must be a known environment.")
        self.capabilities = frozenset(self.capabilities)
        self.entitled_groups = tuple(str(group) for group in self.entitled_groups)

    def allows(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def entitles_groups(self, user_group_ids: Iterable[str]) -> bool:
        """Empty entitlement means nobody, never everyone."""
        if not self.entitled_groups:
            return False
        return bool(set(self.entitled_groups) & {str(group) for group in user_group_ids})


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


@dataclass
class QueryRequest:
    sql: str
    parameters: Sequence[Any] | None = None

    def __post_init__(self) -> None:
        self.sql = validate_sql_text(self.sql)
        self.parameters = validate_parameters(self.parameters)

    @property
    def canonical_parameters(self) -> bytes:
        return canonical_bytes(None if self.parameters is None else list(self.parameters))

    @property
    def parameters_hash(self) -> str:
        return sha256_hex(self.canonical_parameters)


@dataclass
class SchemaRequest:
    schema: str | None = None
    object_name: str | None = None

    def __post_init__(self) -> None:
        self.schema = validate_identifier_filter(self.schema, field="schema")
        self.object_name = validate_identifier_filter(self.object_name, field="object_name")


# ---------------------------------------------------------------------------
# Normalized serialization
# ---------------------------------------------------------------------------


def normalize_value(value: Any) -> tuple[Any, NormalizedType, bool | None]:
    """Return ``(json_safe_value, normalized_type, timezone_aware)``."""
    if value is None:
        return None, NormalizedType.NULL, None
    if isinstance(value, bool):
        return value, NormalizedType.BOOLEAN, None
    if isinstance(value, int):
        return value, NormalizedType.INTEGER, None
    if isinstance(value, Decimal):
        return str(value), NormalizedType.DECIMAL, None
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return repr(value), NormalizedType.FALLBACK, None
        return value, NormalizedType.FLOAT, None
    if isinstance(value, str):
        return value, NormalizedType.STRING, None
    if isinstance(value, dt.datetime):
        return value.isoformat(), NormalizedType.DATETIME, value.tzinfo is not None
    if isinstance(value, dt.date):
        return value.isoformat(), NormalizedType.DATETIME, None
    if isinstance(value, dt.time):
        return value.isoformat(), NormalizedType.DATETIME, value.tzinfo is not None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return (
            {"kind": "binary", "byte_length": len(bytes(value)), "returned": False},
            NormalizedType.BINARY,
            None,
        )
    return str(value), NormalizedType.FALLBACK, None


@dataclass(frozen=True)
class NormalizedRow:
    values: list[Any]
    cell_truncated: bool
    timezone_naive: bool
    binary: bool

    @property
    def cost(self) -> int:
        return len(json.dumps(self.values, ensure_ascii=False, default=str))


def normalize_row(raw_row: Sequence[Any], *, max_cell_chars: int) -> NormalizedRow:
    values: list[Any] = []
    cell_truncated = False
    timezone_naive = False
    binary = False
    for raw_value in raw_row:
        value, type_label, tz_aware = normalize_value(raw_value)
        timezone_naive = timezone_naive or (
            type_label is NormalizedType.DATETIME and tz_aware is False
        )
        binary = binary or type_label is NormalizedType.BINARY
        if isinstance(value, str):
            bounded = truncate_text(value, max_cell_chars, "SQL CELL")
            cell_truncated = cell_truncated or bounded != value
            value = bounded
        values.append(value)
    return NormalizedRow(values, cell_truncated, timezone_naive, binary)


@dataclass
class BoundedRows:
    rows: list[list[Any]]
    truncated_by: TruncationLimit | None
    limits_reached: frozenset[TruncationLimit]
    has_more: bool
    warnings: list[str]
    applied_limits: tuple[int, int, int]

    @property
    def truncated(self) -> bool:
        return self.truncated_by is not None

    @property
    def row_count(self) -> int:
        return len(self.rows)


_TRUNCATION_PRECEDENCE = (
    TruncationLimit.TOTAL_CHAR_LIMIT,
    TruncationLimit.ROW_LIMIT,
    TruncationLimit.CELL_CHAR_LIMIT,
)


def bound_result_rows(
    fetched_rows: Sequence[Sequence[Any]],
    *,
    max_rows: int = MAX_QUERY_RESULT_ROWS,
    max_result_chars: int = MAX_QUERY_RESULT_CHARS,
    max_cell_chars: int = MAX_SQL_CELL_CHARS,
    has_explicit_order: bool,
) -> BoundedRows:
    """Normalize and bound rows fetched with ``max_rows + 1`` semantics."""
    has_more = len(fetched_rows) > max_rows

    limits: set[TruncationLimit] = set()
    rows: list[list[Any]] = []
    remaining_chars = max_result_chars
    timezone_naive_seen = False
    binary_seen = False

    for raw_row in fetched_rows[:max_rows]:
        row = normalize_row(raw_row, max_cell_chars=max_cell_chars)
        timezone_naive_seen = timezone_naive_seen or row.timezone_naive
        binary_seen = binary_seen or row.binary
        if row.cell_truncated:
            limits.add(TruncationLimit.CELL_CHAR_LIMIT)
        if row.cost > remaining_chars:
            limits.add(TruncationLimit.TOTAL_CHAR_LIMIT)
            break
        remaining_chars -= row.cost
        rows.append(row.values)

    if has_more and TruncationLimit.TOTAL_CHAR_LIMIT not in limits:
        limits.add(TruncationLimit.ROW_LIMIT)

    truncated_by = next((limit for limit in _TRUNCATION_PRECEDENCE if limit in limits), None)

    warnings: list[str] = []
    if truncated_by is not None:
        warnings.append(
            f"Result was bounded by the {truncated_by.value}; "
            "omitted values are not evidence of absence."
        )
        if not has_explicit_order:
            warnings.append(UNORDERED_RESULT_WARNING)
    if timezone_naive_seen:
        warnings.append(TIMEZONE_NAIVE_WARNING)
    if binary_seen:
        warnings.append(BINARY_OMITTED_WARNING)

    return BoundedRows(
        rows=rows,
        truncated_by=truncated_by,
        limits_reached=frozenset(limits),
        has_more=has_more,
        warnings=warnings,
        applied_limits=(max_rows, max_result_chars, max_cell_chars),
    )


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class ColumnMetadata:
    name: str
    type_label: NormalizedType
    timezone_aware: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "type": self.type_label.value}
        if self.timezone_aware is not None:
            payload["timezone_aware"] = self.timezone_aware
        return payload


@dataclass
class SchemaObjectMetadata:
    schema: str
    name: str
    kind: str
    columns: list[ColumnMetadata] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "name": self.name,
            "kind": self.kind,
            "columns": [column.to_dict() for column in self.columns],
        }


@dataclass
class QueryResult:
    provider: ProviderId
    correlation_id: str
    status: QueryStatus = QueryStatus.SUCCESS
    columns: Sequence[ColumnMetadata] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False
    truncated_by: TruncationLimit | None = None
    warnings: list[str] = field(default_factory=list)
    message: str | None = None

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status.value,
            "provider": self.provider.value,
            "columns": [column.to_dict() for column in self.columns],
            "rows": self.rows,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "truncated_by": self.truncated_by.value if self.truncated_by else None,
            "warnings": list(self.warnings),
            "correlation_id": self.correlation_id,
        }
        if self.message:
            payload["message"] = self.message
        return payload


@dataclass
class SchemaDiscoveryResult:
    provider: ProviderId
    correlation_id: str
    status: QueryStatus = QueryStatus.SUCCESS
    objects: Sequence[SchemaObjectMetadata] = field(default_factory=list)
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status.value,
            "provider": self.provider.value,
            "objects": [obj.to_dict() for obj in self.objects],
            "truncated": self.truncated,
            "warnings": list(self.warnings),
            "correlation_id": self.correlation_id,
        }
        if self.message:
            payload["message"] = self.message
        return payload


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class DatabaseProvider(Protocol):
    """Provider-neutral connection lifecycle, discovery, and query surface."""

    provider_id: ProviderId

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def discover_schema(self, request: SchemaRequest) -> SchemaDiscoveryResult: ...

    async def execute_query(self, request: QueryRequest) -> QueryResult: ...
