"""SQL Server family provider (Azure Synapse and Azure SQL) over ``pyodbc``.

One class serves every SQL Server-shaped provider; the concrete ``ProviderId``
comes from the configuration rather than from a subclass.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from decimal import Decimal
from typing import Any, Callable

from sqlglot import exp

from database import (
    AuthenticationError,
    AuthorizationError,
    ColumnMetadata,
    ConfigurationError,
    DatabaseError,
    DatabaseProviderConfig,
    NormalizedType,
    ProviderId,
    QueryError,
    QueryRequest,
    QueryResult,
    SchemaDiscoveryResult,
    SchemaObjectMetadata,
    SchemaRequest,
    TransientError,
    TrustError,
    ValidationError,
    bound_result_rows,
    new_correlation_id,
)
from database_odbc import OdbcConnector
from database_sql import SqlGlotValidator, SqlValidator, ValidatedSql

logger = logging.getLogger("database.sqlserver")

SCHEMA_TRUNCATED_WARNING = (
    "Schema discovery was bounded; omitted objects are not evidence of absence."
)

_CATALOG_TYPES: dict[str, NormalizedType] = {
    "bigint": NormalizedType.INTEGER,
    "int": NormalizedType.INTEGER,
    "smallint": NormalizedType.INTEGER,
    "tinyint": NormalizedType.INTEGER,
    "decimal": NormalizedType.DECIMAL,
    "money": NormalizedType.DECIMAL,
    "numeric": NormalizedType.DECIMAL,
    "smallmoney": NormalizedType.DECIMAL,
    "float": NormalizedType.FLOAT,
    "real": NormalizedType.FLOAT,
    "bit": NormalizedType.BOOLEAN,
    "date": NormalizedType.DATETIME,
    "datetime": NormalizedType.DATETIME,
    "datetime2": NormalizedType.DATETIME,
    "datetimeoffset": NormalizedType.DATETIME,
    "smalldatetime": NormalizedType.DATETIME,
    "time": NormalizedType.DATETIME,
    "binary": NormalizedType.BINARY,
    "image": NormalizedType.BINARY,
    "timestamp": NormalizedType.BINARY,
    "varbinary": NormalizedType.BINARY,
}

# pyodbc reports each column's Python type in ``cursor.description[i][1]``.
_DESCRIPTION_TYPES: dict[type, NormalizedType] = {
    bool: NormalizedType.BOOLEAN,
    int: NormalizedType.INTEGER,
    Decimal: NormalizedType.DECIMAL,
    float: NormalizedType.FLOAT,
    str: NormalizedType.STRING,
    dt.datetime: NormalizedType.DATETIME,
    dt.date: NormalizedType.DATETIME,
    dt.time: NormalizedType.DATETIME,
    bytes: NormalizedType.BINARY,
    bytearray: NormalizedType.BINARY,
}


def _column_metadata(description: Sequence[Any] | None) -> list[ColumnMetadata]:
    """Column types come from the driver, so they stay correct for an empty result."""
    return [
        ColumnMetadata(
            name=str(column[0]),
            type_label=_DESCRIPTION_TYPES.get(column[1], NormalizedType.FALLBACK),
        )
        for column in (description or ())
    ]

_SCHEMA_DISCOVERY_SQL = """
WITH bounded_objects AS (
    SELECT t.TABLE_SCHEMA, t.TABLE_NAME, t.TABLE_TYPE
    FROM INFORMATION_SCHEMA.TABLES AS t
    {where}
    ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME
    OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
)
SELECT o.TABLE_SCHEMA, o.TABLE_NAME, o.TABLE_TYPE,
       c.COLUMN_NAME, c.DATA_TYPE, c.ORDINAL_POSITION
FROM bounded_objects AS o
JOIN INFORMATION_SCHEMA.COLUMNS AS c
  ON c.TABLE_SCHEMA = o.TABLE_SCHEMA AND c.TABLE_NAME = o.TABLE_NAME
ORDER BY o.TABLE_SCHEMA, o.TABLE_NAME, c.ORDINAL_POSITION
"""


class SqlServerProvider:
    """Read-only Azure Synapse / Azure SQL provider backed by ``pyodbc``."""

    def __init__(
        self,
        config: DatabaseProviderConfig,
        connection_string: str,
        *,
        credential: Any | None = None,
        validator: SqlValidator | None = None,
        connect_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not config.enabled:
            raise ConfigurationError(f"The {config.provider_id.value} provider is disabled.")
        if not isinstance(connection_string, str) or not connection_string.strip():
            raise ConfigurationError("A connection configuration is required.")

        self.provider_id = config.provider_id
        self.config = config
        self.validator = validator or SqlGlotValidator(dialect="tsql")
        self._connector = OdbcConnector(
            connection_string, credential=credential, connect=connect_factory
        )
        self._connection: Any | None = None

    # -- lifecycle --------------------------------------------------------

    async def connect(self) -> None:
        if self._connection is None:
            self._connection = await asyncio.to_thread(self._open)

    async def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            await asyncio.to_thread(connection.close)

    def _open(self) -> Any:
        try:
            return self._connector.open(timeout=self.config.connect_timeout_seconds)
        except Exception as error:
            raise self._map_error(error, operation="connection") from error

    @contextmanager
    def _cursor(self, *, operation: str) -> Iterator[Any]:
        """Yield a cursor on the pooled connection, or on a short-lived one."""
        connection = self._connection
        owned = connection is None
        try:
            connection = connection or self._open()
            connection.timeout = self.config.query_timeout_seconds
            with closing(connection.cursor()) as cursor:
                yield cursor
        except DatabaseError:
            raise
        except Exception as error:
            raise self._map_error(error, operation=operation) from error
        finally:
            if owned and connection is not None:
                connection.close()

    # -- query ------------------------------------------------------------

    async def execute_query(self, request: QueryRequest) -> QueryResult:
        correlation_id = new_correlation_id()
        try:
            validated = self.validator.validate(
                request.sql,
                approved_schemas=self.config.normalized_approved_schemas,
                allowed_table_functions=self.config.normalized_table_functions,
            )
            return await asyncio.to_thread(
                self._execute_query_sync, request, validated, correlation_id
            )
        except DatabaseError as error:
            return error.to_result(provider=self.provider_id, correlation_id=correlation_id)

    def _execute_query_sync(
        self, request: QueryRequest, validated: ValidatedSql, correlation_id: str
    ) -> QueryResult:
        bounded_sql = self._bounded_sql(validated, self.config.max_rows + 1)
        parameters = tuple(request.parameters or ())
        with self._cursor(operation="query") as cursor:
            if parameters:
                cursor.execute(bounded_sql, parameters)
            else:
                cursor.execute(bounded_sql)
            columns = _column_metadata(cursor.description)
            fetched_rows = cursor.fetchmany(self.config.max_rows + 1)

        bounded = bound_result_rows(
            fetched_rows,
            max_rows=self.config.max_rows,
            max_result_chars=self.config.max_result_chars,
            max_cell_chars=self.config.max_cell_chars,
            has_explicit_order=validated.has_explicit_order,
        )
        return QueryResult(
            provider=self.provider_id,
            correlation_id=correlation_id,
            columns=columns,
            rows=bounded.rows,
            truncated=bounded.truncated,
            truncated_by=bounded.truncated_by,
            warnings=bounded.warnings,
        )

    def _bounded_sql(self, validated: ValidatedSql, row_count: int) -> str:
        """Cap the already-parsed statement at ``row_count``, never loosening it."""
        try:
            expression = validated.expression
            limit = expression.args.get("limit")
            limit_expression = limit.expression if limit is not None else None
            if (
                isinstance(limit_expression, exp.Literal)
                and not limit_expression.is_string
                and limit.args.get("limit_options") is None
            ):
                row_count = min(row_count, max(0, int(limit_expression.this)))
            return expression.limit(row_count).sql(dialect="tsql", comments=False)
        except Exception as error:
            raise ValidationError("SQL could not be bounded for execution.") from error

    # -- schema discovery -------------------------------------------------

    async def discover_schema(self, request: SchemaRequest) -> SchemaDiscoveryResult:
        correlation_id = new_correlation_id()
        try:
            approved = self.config.normalized_approved_schemas
            if request.schema and approved and request.schema.lower() not in approved:
                raise ValidationError("The requested schema is not approved.")
            return await asyncio.to_thread(self._discover_schema_sync, request, correlation_id)
        except DatabaseError as error:
            return error.to_schema_result(
                provider=self.provider_id, correlation_id=correlation_id
            )

    def _discover_schema_sql(self, request: SchemaRequest) -> tuple[str, tuple[Any, ...]]:
        predicates: list[str] = []
        parameters: list[Any] = []
        approved = sorted(self.config.normalized_approved_schemas)
        if request.schema:
            predicates.append("t.TABLE_SCHEMA = ?")
            parameters.append(request.schema)
        elif approved:
            placeholders = ", ".join("?" for _ in approved)
            predicates.append(f"LOWER(t.TABLE_SCHEMA) IN ({placeholders})")
            parameters.extend(approved)
        if request.object_name:
            predicates.append("t.TABLE_NAME = ?")
            parameters.append(request.object_name)
        parameters.append(self.config.max_rows + 1)
        where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        return _SCHEMA_DISCOVERY_SQL.format(where=where).strip(), tuple(parameters)

    def _discover_schema_sync(
        self, request: SchemaRequest, correlation_id: str
    ) -> SchemaDiscoveryResult:
        sql, parameters = self._discover_schema_sql(request)
        with self._cursor(operation="schema discovery") as cursor:
            cursor.execute(sql, parameters)
            rows = cursor.fetchmany(self.config.max_rows * 100 + 100)

        objects: dict[tuple[str, str], SchemaObjectMetadata] = {}
        for schema, name, table_type, column_name, data_type, _ in rows:
            key = (str(schema), str(name))
            metadata = objects.get(key)
            if metadata is None:
                metadata = SchemaObjectMetadata(
                    schema=key[0],
                    name=key[1],
                    kind="view" if str(table_type).upper() == "VIEW" else "table",
                )
                objects[key] = metadata
            metadata.columns.append(
                ColumnMetadata(
                    name=str(column_name),
                    type_label=_CATALOG_TYPES.get(str(data_type).lower(), NormalizedType.STRING),
                )
            )

        discovered = list(objects.values())
        truncated = len(discovered) > self.config.max_rows
        return SchemaDiscoveryResult(
            provider=self.provider_id,
            correlation_id=correlation_id,
            objects=discovered[: self.config.max_rows],
            truncated=truncated,
            warnings=[SCHEMA_TRUNCATED_WARNING] if truncated else [],
        )

    # -- error mapping ----------------------------------------------------

    @staticmethod
    def _map_error(error: BaseException, *, operation: str) -> DatabaseError:
        """Classify by SQLSTATE; the driver message is only consulted where
        SQLSTATE alone cannot separate two categories."""
        arguments: Sequence[Any] = getattr(error, "args", ())
        state = str(arguments[0]).upper() if arguments else ""
        detail = " ".join(str(argument) for argument in arguments[1:]).lower()
        if state.startswith("28"):
            return AuthenticationError("Database authentication failed.", cause=error)
        if state.startswith("IM"):
            return ConfigurationError("The database driver is unavailable.", cause=error)
        if state == "42501" or (state == "42000" and "permission" in detail):
            return AuthorizationError("Database access was denied.", cause=error)
        if state.startswith("08") or state in {"HYT00", "HYT01"}:
            # 08xxx covers both a broken link and a rejected server certificate.
            if any(token in detail for token in ("certificate", "ssl", "tls")):
                return TrustError("Database server trust validation failed.", cause=error)
            return TransientError(
                f"The database {operation} is temporarily unavailable.", cause=error
            )
        return QueryError("The database rejected the read query.", cause=error)
