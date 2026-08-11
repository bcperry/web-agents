"""Provider-neutral database contract for feature 015 (SAP HANA private connectivity).

This module owns everything that must behave identically for every database
provider: configuration and grants, request/result models, the read-only SQL
grammar gate, RFC 8785 canonicalization, signed keyset continuation, bounded
result serialization, and the sanitized error contract.

Vendor specifics (drivers, catalogs, quoting, TLS handshakes) live in the
per-provider modules and must not leak into this file. Nothing here logs SQL
text, parameter values, result cells, or credentials.
"""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import hashlib
import hmac
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol, runtime_checkable

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.tokens import TokenType

from tools import (
    MAX_QUERY_RESULT_CHARS,
    MAX_QUERY_RESULT_ROWS,
    MAX_SQL_CELL_CHARS,
    _sanitize_cell_value,
    _truncate_text,
)

logger = logging.getLogger("database")


# ---------------------------------------------------------------------------
# Limits (contract: contracts/database-tools.md)
# ---------------------------------------------------------------------------

MIN_SQL_CHARS = 1
MAX_SQL_CHARS = 20_000
MAX_PARAMETERS = 100
MAX_PARAMETER_STRING_CHARS = 4_096
MAX_PARAMETERS_CANONICAL_BYTES = 16_384
MAX_IDENTIFIER_CHARS = 127
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1

CONTINUATION_VERSION = 1
DEFAULT_CONTINUATION_TTL_SECONDS = 300
CONTINUATION_CLOCK_SKEW_SECONDS = 60
CONTINUATION_GUIDANCE = (
    "Resend this continuation object unchanged with the identical query, "
    "parameters, and limits to fetch the next page."
)

PARTIAL_RESULT_WARNING = (
    "Partial result: no stable unique ordering was proven, so omitted rows are "
    "not evidence of absence. Reissue a narrower query with an explicit stable ORDER BY."
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


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class NullOrdering(str, Enum):
    NULLS_FIRST = "nulls_first"
    NULLS_LAST = "nulls_last"


class TruncationLimit(str, Enum):
    ROW_LIMIT = "row_limit"
    TOTAL_CHAR_LIMIT = "total_char_limit"
    CELL_CHAR_LIMIT = "cell_char_limit"


RETRYABLE_STATUSES = frozenset({QueryStatus.TRANSIENT_ERROR})


# ---------------------------------------------------------------------------
# Sanitized error contract
# ---------------------------------------------------------------------------


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

    @property
    def retryable(self) -> bool:
        return self.status in RETRYABLE_STATUSES

    def to_result(
        self,
        *,
        provider: ProviderId,
        correlation_id: str | None = None,
    ) -> "QueryResult":
        return QueryResult(
            provider=provider,
            status=self.status,
            columns=[],
            rows=[],
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


def new_correlation_id() -> str:
    """Opaque, log-safe identifier for server-side diagnostics."""
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# RFC 8785 JSON Canonicalization Scheme
# ---------------------------------------------------------------------------

_JSON_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def _canonical_string(value: str) -> str:
    out = ['"']
    for char in value:
        escape = _JSON_ESCAPES.get(char)
        if escape is not None:
            out.append(escape)
        elif char < "\x20":
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _canonical_number(value: float) -> str:
    """ECMAScript ``Number::toString`` formatting required by RFC 8785."""
    if value != value or value in (float("inf"), float("-inf")):
        raise ValidationError("Non-finite numbers cannot be canonicalized.")
    if value == 0:
        return "0"
    if value.is_integer() and abs(value) < 1e21:
        return str(int(value))
    shortest = repr(value)
    mantissa, separator, exponent = shortest.partition("e")
    if not separator:
        return shortest
    exponent_value = int(exponent)
    if -7 < exponent_value < 21:
        return format(Decimal(shortest), "f")
    sign = "+" if exponent_value > 0 else "-"
    return f"{mantissa}e{sign}{abs(exponent_value)}"


def _canonical_fragment(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _canonical_number(value)
    if isinstance(value, str):
        return _canonical_string(value)
    if isinstance(value, Mapping):
        # RFC 8785 orders members by UTF-16 code unit sequence.
        items = []
        for key in sorted(value, key=lambda k: _utf16_sort_key(k)):
            items.append(f"{_canonical_string(key)}:{_canonical_fragment(value[key])}")
        return "{" + ",".join(items) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical_fragment(item) for item in value) + "]"
    raise ValidationError(f"Value of type {type(value).__name__} cannot be canonicalized.")


def _utf16_sort_key(key: Any) -> bytes:
    if not isinstance(key, str):
        raise ValidationError("Canonical JSON object keys must be strings.")
    return key.encode("utf-16-be", errors="surrogatepass")


def canonicalize_json(value: Any) -> bytes:
    """Return the RFC 8785 JSON Canonicalization Scheme encoding of ``value``."""
    return _canonical_fragment(value).encode("utf-8")


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
    encoded = canonicalize_json(list(validated))
    if len(encoded) > MAX_PARAMETERS_CANONICAL_BYTES:
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
        raise ValidationError(
            f"{field} filter is limited to {MAX_IDENTIFIER_CHARS} characters."
        )
    if any(char < "\x20" or char == "\x7f" for char in trimmed):
        raise ValidationError(f"{field} filter must not contain control characters.")
    if any(char in _IDENTIFIER_DENIED_CHARS for char in trimmed):
        raise ValidationError(
            f"{field} filter must not contain separator or wildcard syntax."
        )
    return trimmed


# ---------------------------------------------------------------------------
# SQL grammar validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidatedSql:
    normalized_sql: str
    normalized_sql_hash: str
    referenced_schemas: frozenset[str]
    referenced_table_functions: frozenset[str]
    has_explicit_order: bool


class SqlValidator(ABC):
    """Abstraction over the parser that proves a statement is a single read."""

    @abstractmethod
    def validate(
        self,
        sql: str,
        *,
        approved_schemas: frozenset[str] | None = None,
        allowed_table_functions: frozenset[str] | None = None,
    ) -> ValidatedSql:
        raise NotImplementedError


_DENIED_EXPRESSION_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Create",
    "Drop",
    "Alter",
    "AlterTable",
    "TruncateTable",
    "Grant",
    "Revoke",
    "Command",
    "Transaction",
    "Commit",
    "Rollback",
    "Set",
    "Use",
    "Copy",
    "Pragma",
    "Analyze",
    "Into",
    "Export",
    "LoadData",
)

_DENIED_KEYWORDS = frozenset(
    {
        "ALTER",
        "BACKUP",
        "BEGIN",
        "CALL",
        "COMMIT",
        "CREATE",
        "DELETE",
        "DO",
        "DROP",
        "EXEC",
        "EXECUTE",
        "EXPORT",
        "GRANT",
        "IMPORT",
        "INSERT",
        "INTO",
        "LOAD",
        "MERGE",
        "REVOKE",
        "ROLLBACK",
        "SAVEPOINT",
        "SET",
        "TRUNCATE",
        "UNLOAD",
        "UPDATE",
        "UPSERT",
        "USE",
    }
)

_LITERAL_TOKEN_TYPES = frozenset(
    {
        TokenType.STRING,
        TokenType.IDENTIFIER,
        TokenType.NATIONAL_STRING,
        TokenType.RAW_STRING,
        TokenType.HEREDOC_STRING,
        TokenType.BYTE_STRING,
    }
)

_TABLE_FUNCTION_NODE_NAMES = ("Lateral", "TableFromRows", "Unnest")


def _denied_expression_types() -> tuple[type, ...]:
    types: list[type] = []
    for name in _DENIED_EXPRESSION_NAMES:
        node_type = getattr(exp, name, None)
        if isinstance(node_type, type):
            types.append(node_type)
    return tuple(types)


def _table_function_types() -> tuple[type, ...]:
    types: list[type] = []
    for name in _TABLE_FUNCTION_NODE_NAMES:
        node_type = getattr(exp, name, None)
        if isinstance(node_type, type):
            types.append(node_type)
    return tuple(types)


def _reject_comments(sql: str) -> None:
    """Reject SQL comments outside string/identifier literals.

    Comments can hide statement or control tokens in model output, so the
    contract bans them outright rather than trying to interpret them.
    """
    index = 0
    length = len(sql)
    quote: str | None = None
    while index < length:
        char = sql[index]
        if quote is not None:
            if char == quote:
                if index + 1 < length and sql[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            index += 1
            continue
        if char == "-" and sql.startswith("--", index):
            raise ValidationError("SQL comments are not permitted.")
        if char == "/" and sql.startswith("/*", index):
            raise ValidationError("SQL comments are not permitted.")
        index += 1
    if quote is not None:
        raise ValidationError("SQL contains an unterminated literal.")


class SqlGlotValidator(SqlValidator):
    """Parser-backed validator.

    The dialect is injectable so the HANA-aware dialect chosen by the driver
    spike can replace the default without changing any caller.
    """

    def __init__(self, dialect: str | None = None) -> None:
        self.dialect = dialect
        self._denied_types = _denied_expression_types()
        self._table_function_types = _table_function_types()

    def validate(
        self,
        sql: str,
        *,
        approved_schemas: frozenset[str] | None = None,
        allowed_table_functions: frozenset[str] | None = None,
    ) -> ValidatedSql:
        validate_sql_text(sql)
        _reject_comments(sql)
        self._reject_denied_keywords(sql)

        try:
            statements = sqlglot.parse(sql, read=self.dialect)
        except SqlglotError as error:  # never echo the statement text
            raise ValidationError("SQL could not be parsed as a single read query.") from error

        parsed = [statement for statement in statements if statement is not None]
        if len(parsed) != 1 or len(statements) != 1:
            raise ValidationError("Exactly one read statement is allowed.")

        root = parsed[0]
        if not isinstance(root, (exp.Select, exp.SetOperation, exp.Subquery)):
            raise ValidationError("Only a single read-only SELECT statement is allowed.")

        for node in root.walk():
            if isinstance(node, self._denied_types):
                raise ValidationError("The statement contains a non-read operation.")

        allowed_functions = frozenset(
            name.lower() for name in (allowed_table_functions or frozenset())
        )
        approved = frozenset(name.lower() for name in (approved_schemas or frozenset()))
        cte_names = {
            cte.alias_or_name.lower() for cte in root.find_all(exp.CTE) if cte.alias_or_name
        }

        for node in root.walk():
            if isinstance(node, self._table_function_types):
                raise ValidationError("Table functions are not permitted by default.")

        schemas: set[str] = set()
        table_functions: set[str] = set()
        for table in root.find_all(exp.Table):
            inner = table.this
            if isinstance(inner, exp.Func):
                name = self._table_function_name(table, inner)
                if name not in allowed_functions:
                    raise ValidationError(
                        "Table functions must be explicitly allowlisted by fully qualified name."
                    )
                table_functions.add(name)
                continue
            schema_name = (table.db or "").lower()
            if not schema_name:
                if table.name.lower() in cte_names:
                    continue
                if approved:
                    raise ValidationError(
                        "Every referenced object must be schema-qualified within the "
                        "approved schemas."
                    )
                continue
            if approved and schema_name not in approved:
                raise ValidationError("The statement references a schema that is not approved.")
            schemas.add(schema_name)

        normalized_sql = root.sql(dialect=self.dialect, comments=False, normalize=True)
        return ValidatedSql(
            normalized_sql=normalized_sql,
            normalized_sql_hash=sha256_hex(normalized_sql.encode("utf-8")),
            referenced_schemas=frozenset(schemas),
            referenced_table_functions=frozenset(table_functions),
            has_explicit_order=root.args.get("order") is not None,
        )

    def _reject_denied_keywords(self, sql: str) -> None:
        try:
            tokens = sqlglot.tokenize(sql, read=self.dialect)
        except SqlglotError as error:
            raise ValidationError("SQL could not be tokenized.") from error
        for token in tokens:
            if token.token_type in _LITERAL_TOKEN_TYPES:
                continue
            if token.text.upper() in _DENIED_KEYWORDS:
                raise ValidationError("The statement contains a non-read keyword.")

    @staticmethod
    def _table_function_name(table: exp.Table, func: exp.Func) -> str:
        name = func.sql_name() if not isinstance(func, exp.Anonymous) else str(func.this)
        parts = [part for part in (table.catalog, table.db, name) if part]
        return ".".join(parts).lower()


_DEFAULT_VALIDATOR = SqlGlotValidator()


def default_sql_validator() -> SqlValidator:
    return _DEFAULT_VALIDATOR


# ---------------------------------------------------------------------------
# Configuration and grants
# ---------------------------------------------------------------------------


@dataclass
class DatabaseProviderConfig:
    provider_id: ProviderId
    host: str
    port: int
    database: str
    tls_server_name: str | None = None
    enabled: bool = False
    tls_required: bool = True
    ca_secret_uri: str | None = None
    credential_secret_uri: str | None = None
    approved_schemas: Sequence[str] | None = None
    allowed_table_functions: Sequence[str] | None = None
    connect_timeout_seconds: int = 10
    query_timeout_seconds: int = 30
    max_rows: int = MAX_QUERY_RESULT_ROWS
    max_result_chars: int = MAX_QUERY_RESULT_CHARS
    max_cell_chars: int = MAX_SQL_CELL_CHARS
    environment: Environment = Environment.LOCAL
    code_revision: str = ""
    driver_version: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise ValidationError("provider_id must be a known provider.")
        if not self.host or not str(self.host).strip():
            raise ValidationError("host is required.")
        if not isinstance(self.port, int) or isinstance(self.port, bool) or not (
            1 <= self.port <= 65535
        ):
            raise ValidationError("port must be between 1 and 65535.")
        if not self.database or not str(self.database).strip():
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
        if self.enabled and self.provider_id is ProviderId.HANA:
            if not self.tls_required:
                raise ValidationError("HANA requires TLS outside isolated tests.")
            if not self.tls_server_name:
                raise ValidationError("HANA requires a validated TLS server name.")
            if not self.credential_secret_uri:
                raise ValidationError("HANA requires a credential secret reference.")

    @property
    def normalized_approved_schemas(self) -> frozenset[str]:
        return frozenset(name.strip().lower() for name in (self.approved_schemas or ()) if name.strip())

    @property
    def normalized_table_functions(self) -> frozenset[str]:
        return frozenset(
            name.strip().lower() for name in (self.allowed_table_functions or ()) if name.strip()
        )

    @property
    def config_fingerprint(self) -> str:
        """SHA-256 over canonical non-secret settings; secret *values* never appear."""
        payload = {
            "provider": self.provider_id.value,
            "environment": self.environment.value,
            "enabled": self.enabled,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "tls_required": self.tls_required,
            "tls_server_name": self.tls_server_name,
            "ca_secret_uri": self.ca_secret_uri,
            "credential_secret_uri": self.credential_secret_uri,
            "approved_schemas": sorted(self.normalized_approved_schemas),
            "allowed_table_functions": sorted(self.normalized_table_functions),
            "connect_timeout_seconds": self.connect_timeout_seconds,
            "query_timeout_seconds": self.query_timeout_seconds,
            "limits": [self.max_rows, self.max_result_chars, self.max_cell_chars],
            "code_revision": self.code_revision,
            "driver_version": self.driver_version,
        }
        return sha256_hex(canonicalize_json(payload))


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


@runtime_checkable
class AcceptancePolicy(Protocol):
    """Gate that proves a provider/environment is currently enableable."""

    def assert_enabled(
        self,
        *,
        provider: ProviderId,
        environment: Environment,
        config_fingerprint: str,
    ) -> None:
        """Raise ``ConfigurationError`` when the acceptance record does not pass."""
        ...


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


@dataclass
class QueryRequest:
    sql: str
    parameters: Sequence[Any] | None = None
    continuation: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        self.sql = validate_sql_text(self.sql)
        self.parameters = validate_parameters(self.parameters)
        if self.continuation is not None and not isinstance(self.continuation, Mapping):
            raise ValidationError("continuation must be the unmodified object previously returned.")

    @property
    def canonical_parameters(self) -> bytes:
        values = None if self.parameters is None else list(self.parameters)
        return canonicalize_json(values)

    @property
    def parameters_hash(self) -> str:
        return sha256_hex(self.canonical_parameters)


@dataclass
class SchemaRequest:
    schema: str | None = None
    object_name: str | None = None
    continuation: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        self.schema = validate_identifier_filter(self.schema, field="schema")
        self.object_name = validate_identifier_filter(self.object_name, field="object_name")
        if self.continuation is not None and not isinstance(self.continuation, Mapping):
            raise ValidationError("continuation must be the unmodified object previously returned.")


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


@dataclass
class BoundedRows:
    rows: list[list[Any]]
    column_types: tuple[NormalizedType, ...]
    truncated: bool
    truncated_by: TruncationLimit | None
    limits_reached: frozenset[TruncationLimit]
    has_more: bool
    continuation_allowed: bool
    warnings: list[str]
    applied_limits: tuple[int, int, int]

    @property
    def row_count(self) -> int:
        return len(self.rows)


def _bound_cell(value: Any, max_cell_chars: int) -> tuple[Any, bool]:
    if not isinstance(value, str):
        return value, False
    if max_cell_chars == MAX_SQL_CELL_CHARS:
        bounded = _sanitize_cell_value(value)
    else:
        bounded = _truncate_text(value, max_cell_chars, "SQL CELL")
    return bounded, bounded != value


def _row_cost(row: Sequence[Any]) -> int:
    return len(json.dumps(row, ensure_ascii=False, default=str))


def bound_result_rows(
    fetched_rows: Sequence[Sequence[Any]],
    *,
    max_rows: int = MAX_QUERY_RESULT_ROWS,
    max_result_chars: int = MAX_QUERY_RESULT_CHARS,
    max_cell_chars: int = MAX_SQL_CELL_CHARS,
    stable_order: bool,
) -> BoundedRows:
    """Normalize and bound rows fetched with ``max_rows + 1`` semantics."""
    has_more = len(fetched_rows) > max_rows
    candidate_rows = list(fetched_rows[:max_rows])

    limits: set[TruncationLimit] = set()
    warnings: list[str] = []
    rows: list[list[Any]] = []
    column_types: list[NormalizedType] = []
    total_chars = 0
    timezone_naive_seen = False
    binary_seen = False
    char_truncated = False

    for raw_row in candidate_rows:
        normalized_row: list[Any] = []
        for index, raw_value in enumerate(raw_row):
            value, type_label, tz_aware = normalize_value(raw_value)
            if type_label is NormalizedType.DATETIME and tz_aware is False:
                timezone_naive_seen = True
            if type_label is NormalizedType.BINARY:
                binary_seen = True
            value, cell_truncated = _bound_cell(value, max_cell_chars)
            if cell_truncated:
                limits.add(TruncationLimit.CELL_CHAR_LIMIT)
            while len(column_types) <= index:
                column_types.append(NormalizedType.NULL)
            if (
                column_types[index] is NormalizedType.NULL
                and type_label is not NormalizedType.NULL
            ):
                column_types[index] = type_label
            normalized_row.append(value)
        cost = _row_cost(normalized_row)
        if rows and total_chars + cost > max_result_chars:
            char_truncated = True
            break
        if not rows and cost > max_result_chars:
            char_truncated = True
            break
        total_chars += cost
        rows.append(normalized_row)

    if char_truncated:
        limits.add(TruncationLimit.TOTAL_CHAR_LIMIT)
    elif has_more:
        limits.add(TruncationLimit.ROW_LIMIT)

    if TruncationLimit.TOTAL_CHAR_LIMIT in limits:
        truncated_by = TruncationLimit.TOTAL_CHAR_LIMIT
    elif TruncationLimit.ROW_LIMIT in limits:
        truncated_by = TruncationLimit.ROW_LIMIT
    elif TruncationLimit.CELL_CHAR_LIMIT in limits:
        truncated_by = TruncationLimit.CELL_CHAR_LIMIT
    else:
        truncated_by = None

    truncated = truncated_by is not None
    if truncated:
        warnings.append(
            "Result was bounded by the "
            f"{truncated_by.value}; omitted values are not evidence of absence."
        )
    if timezone_naive_seen:
        warnings.append(TIMEZONE_NAIVE_WARNING)
    if binary_seen:
        warnings.append(BINARY_OMITTED_WARNING)

    continuation_allowed = stable_order
    if truncated and not stable_order:
        warnings.append(PARTIAL_RESULT_WARNING)

    return BoundedRows(
        rows=rows,
        column_types=tuple(column_types),
        truncated=truncated,
        truncated_by=truncated_by,
        limits_reached=frozenset(limits),
        has_more=has_more,
        continuation_allowed=continuation_allowed,
        warnings=warnings,
        applied_limits=(max_rows, max_result_chars, max_cell_chars),
    )


# ---------------------------------------------------------------------------
# Signed keyset continuation
# ---------------------------------------------------------------------------


@runtime_checkable
class ContinuationSigner(Protocol):
    """Integrity protection for continuation tokens.

    Deliberately separate from the RS256 acceptance-manifest verifier: this
    signer only proves the server minted the paging state.
    """

    def sign(self, payload: bytes) -> str: ...

    def verify(self, payload: bytes, signature: str) -> bool: ...


class HmacContinuationSigner:
    def __init__(self, key: bytes, *, digest: str = "sha256") -> None:
        if not key:
            raise ConfigurationError("A continuation signing key is required.")
        self._key = key
        self._digest = digest

    def sign(self, payload: bytes) -> str:
        mac = hmac.new(self._key, payload, self._digest).digest()
        return base64.urlsafe_b64encode(mac).decode().rstrip("=")

    def verify(self, payload: bytes, signature: str) -> bool:
        if not isinstance(signature, str):
            return False
        return hmac.compare_digest(self.sign(payload), signature)


@dataclass(frozen=True)
class KeyColumn:
    name: str
    direction: SortDirection
    nulls: NullOrdering

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValidationError("Key column names are required.")
        if not isinstance(self.direction, SortDirection):
            raise ValidationError("Key column direction must be asc or desc.")
        if not isinstance(self.nulls, NullOrdering):
            raise ValidationError("Key column null ordering must be explicit.")

    def to_claim(self) -> list[str]:
        return [self.name, self.direction.value, self.nulls.value]

    @staticmethod
    def from_claim(claim: Any) -> "KeyColumn":
        if not isinstance(claim, list) or len(claim) != 3:
            raise ValidationError("Continuation key columns are malformed.")
        name, direction, nulls = claim
        try:
            return KeyColumn(name, SortDirection(direction), NullOrdering(nulls))
        except (ValueError, TypeError) as error:
            raise ValidationError("Continuation key columns are malformed.") from error


@dataclass(frozen=True)
class ContinuationBinding:
    provider: ProviderId
    environment: Environment
    sql_hash: str
    parameters_hash: str
    key_columns: tuple[KeyColumn, ...]
    max_rows: int
    max_result_chars: int
    max_cell_chars: int
    config_fingerprint: str


@dataclass(frozen=True)
class ContinuationToken:
    version: int
    token: str
    expires_at: str
    guidance: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "token": self.token,
            "expires_at": self.expires_at,
            "guidance": self.guidance,
        }


@dataclass(frozen=True)
class ContinuationClaims:
    version: int
    provider: ProviderId
    environment: Environment
    sql_hash: str
    parameters_hash: str
    key_columns: tuple[KeyColumn, ...]
    last_key_values: tuple[Any, ...]
    max_rows: int
    max_result_chars: int
    max_cell_chars: int
    config_fingerprint: str
    issued_at: int
    expires_at: int


_REQUIRED_CLAIMS = ("v", "p", "e", "sh", "ph", "kc", "lk", "lim", "cf", "iat", "exp")


class ContinuationCodec:
    """Issues and verifies integrity-protected keyset continuation tokens."""

    def __init__(
        self,
        signer: ContinuationSigner,
        *,
        ttl_seconds: int = DEFAULT_CONTINUATION_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
        guidance: str = CONTINUATION_GUIDANCE,
    ) -> None:
        if ttl_seconds <= 0:
            raise ConfigurationError("Continuation ttl_seconds must be positive.")
        self.signer = signer
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self.guidance = guidance

    # -- issuing ----------------------------------------------------------

    def issue(
        self,
        binding: ContinuationBinding,
        last_key_values: Sequence[Any],
    ) -> ContinuationToken:
        key_columns = self._validate_key_columns(binding.key_columns)
        values = self._validate_last_key_values(last_key_values, key_columns)
        issued_at = int(self.clock())
        expires_at = issued_at + self.ttl_seconds
        claims = {
            "v": CONTINUATION_VERSION,
            "p": binding.provider.value,
            "e": binding.environment.value,
            "sh": binding.sql_hash,
            "ph": binding.parameters_hash,
            "kc": [column.to_claim() for column in key_columns],
            "lk": list(values),
            "lim": [binding.max_rows, binding.max_result_chars, binding.max_cell_chars],
            "cf": binding.config_fingerprint,
            "iat": issued_at,
            "exp": expires_at,
        }
        payload = canonicalize_json(claims)
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        return ContinuationToken(
            version=CONTINUATION_VERSION,
            token=f"{encoded}.{self.signer.sign(payload)}",
            expires_at=dt.datetime.fromtimestamp(expires_at, tz=dt.timezone.utc).isoformat(),
            guidance=self.guidance,
        )

    def advance(
        self,
        previous: ContinuationToken | Mapping[str, Any],
        binding: ContinuationBinding,
        last_key_values: Sequence[Any],
    ) -> ContinuationToken:
        previous_claims = self.decode(previous, binding)
        key_columns = self._validate_key_columns(binding.key_columns)
        values = self._validate_last_key_values(last_key_values, key_columns)
        if values == previous_claims.last_key_values:
            raise ValidationError("The continuation key did not advance; paging would not progress.")
        return self.issue(binding, values)

    # -- verifying --------------------------------------------------------

    def decode(
        self,
        continuation: ContinuationToken | Mapping[str, Any] | None,
        binding: ContinuationBinding,
    ) -> ContinuationClaims:
        payload_map = self._as_mapping(continuation)
        version = payload_map.get("version")
        if not isinstance(version, int) or isinstance(version, bool):
            raise ValidationError("Continuation version is malformed.")
        if version != CONTINUATION_VERSION:
            raise ValidationError("Continuation version is not supported.")

        token = payload_map.get("token")
        if not isinstance(token, str) or "." not in token:
            raise ValidationError("Continuation token is malformed.")
        encoded, _, signature = token.partition(".")
        if not encoded or not signature:
            raise ValidationError("Continuation token is malformed.")
        try:
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except (binascii.Error, ValueError) as error:
            raise ValidationError("Continuation token is malformed.") from error

        if not self.signer.verify(raw, signature):
            raise ValidationError("Continuation token signature is invalid.")

        try:
            claims = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationError("Continuation token is malformed.") from error
        if not isinstance(claims, dict):
            raise ValidationError("Continuation token is malformed.")
        if canonicalize_json(claims) != raw:
            raise ValidationError("Continuation token is not canonically encoded.")

        for name in _REQUIRED_CLAIMS:
            if name not in claims:
                raise ValidationError("Continuation token is missing required claims.")
        if claims["v"] != CONTINUATION_VERSION:
            raise ValidationError("Continuation version is not supported.")

        issued_at = claims["iat"]
        expires_at = claims["exp"]
        if not isinstance(issued_at, int) or isinstance(issued_at, bool):
            raise ValidationError("Continuation token is malformed.")
        if not isinstance(expires_at, int) or isinstance(expires_at, bool):
            raise ValidationError("Continuation token is malformed.")
        now = int(self.clock())
        if now > expires_at:
            raise ValidationError("Continuation token has expired; reissue the query.")
        if issued_at > now + CONTINUATION_CLOCK_SKEW_SECONDS:
            raise ValidationError("Continuation token was issued in the future.")

        key_columns = self._decode_key_columns(claims["kc"])
        limits = claims["lim"]
        if not isinstance(limits, list) or len(limits) != 3:
            raise ValidationError("Continuation limits are malformed.")
        expected_limits = [binding.max_rows, binding.max_result_chars, binding.max_cell_chars]
        binding_matches = (
            claims["p"] == binding.provider.value
            and claims["e"] == binding.environment.value
            and claims["sh"] == binding.sql_hash
            and claims["ph"] == binding.parameters_hash
            and claims["cf"] == binding.config_fingerprint
            and limits == expected_limits
            and key_columns == tuple(binding.key_columns)
        )
        if not binding_matches:
            raise ValidationError(
                "Continuation token does not match this query, parameters, limits, or "
                "configuration; reissue the query instead of paging."
            )

        values = self._validate_last_key_values(claims["lk"], key_columns)
        return ContinuationClaims(
            version=CONTINUATION_VERSION,
            provider=binding.provider,
            environment=binding.environment,
            sql_hash=binding.sql_hash,
            parameters_hash=binding.parameters_hash,
            key_columns=key_columns,
            last_key_values=values,
            max_rows=binding.max_rows,
            max_result_chars=binding.max_result_chars,
            max_cell_chars=binding.max_cell_chars,
            config_fingerprint=binding.config_fingerprint,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _as_mapping(
        continuation: ContinuationToken | Mapping[str, Any] | None,
    ) -> Mapping[str, Any]:
        if isinstance(continuation, ContinuationToken):
            return continuation.to_dict()
        if not isinstance(continuation, Mapping):
            raise ValidationError("Continuation must be the unmodified object previously returned.")
        return continuation

    @staticmethod
    def _validate_key_columns(key_columns: Sequence[KeyColumn]) -> tuple[KeyColumn, ...]:
        columns = tuple(key_columns or ())
        if not columns:
            raise ValidationError(
                "Deterministic continuation requires a proven unique ordering key."
            )
        for column in columns:
            if not isinstance(column, KeyColumn):
                raise ValidationError("Continuation key columns are malformed.")
        return columns

    @staticmethod
    def _decode_key_columns(claim: Any) -> tuple[KeyColumn, ...]:
        if not isinstance(claim, list) or not claim:
            raise ValidationError("Continuation key columns are malformed.")
        return tuple(KeyColumn.from_claim(entry) for entry in claim)

    @staticmethod
    def _validate_last_key_values(
        values: Any,
        key_columns: Sequence[KeyColumn],
    ) -> tuple[Any, ...]:
        if not isinstance(values, (list, tuple)):
            raise ValidationError("Continuation key values are malformed.")
        if len(values) != len(key_columns):
            raise ValidationError("Continuation key values do not match the ordering key.")
        validated: list[Any] = []
        for value in values:
            if value is None:
                raise ValidationError("Continuation key values must not be null.")
            validated.append(_validate_scalar(value, context="Continuation key"))
        return tuple(validated)


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
    columns: Sequence[ColumnMetadata] = field(default_factory=list)

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
    row_count: int | None = None
    truncated: bool = False
    truncated_by: TruncationLimit | None = None
    continuation: ContinuationToken | Mapping[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    message: str | None = None

    def __post_init__(self) -> None:
        if self.row_count is None:
            self.row_count = len(self.rows)

    def to_dict(self) -> dict[str, Any]:
        continuation = self.continuation
        if isinstance(continuation, ContinuationToken):
            continuation = continuation.to_dict()
        payload: dict[str, Any] = {
            "status": self.status.value,
            "provider": self.provider.value,
            "columns": [column.to_dict() for column in self.columns],
            "rows": self.rows,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "truncated_by": self.truncated_by.value if self.truncated_by else None,
            "continuation": continuation,
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
    continuation: ContinuationToken | Mapping[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        continuation = self.continuation
        if isinstance(continuation, ContinuationToken):
            continuation = continuation.to_dict()
        payload: dict[str, Any] = {
            "status": self.status.value,
            "provider": self.provider.value,
            "objects": [obj.to_dict() for obj in self.objects],
            "truncated": self.truncated,
            "continuation": continuation,
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
