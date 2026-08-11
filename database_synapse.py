"""Azure Synapse/SQL Server implementation of the database provider contract."""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import closing
from typing import Any, Callable

import pyodbc
import sqlglot
from azure.identity import DefaultAzureCredential

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
    SqlGlotValidator,
    SqlValidator,
    TransientError,
    TrustError,
    ValidationError,
    bound_result_rows,
    new_correlation_id,
)
from tools import _get_token_struct

logger = logging.getLogger("database.synapse")

SQL_COPT_SS_ACCESS_TOKEN = 1256
AZURE_GOVERNMENT_SQL_SCOPE = "https://database.usgovcloudapi.net/.default"

_AUTHENTICATION_ATTRIBUTE = re.compile(
    r";?\s*Authentication=[^;]+", flags=re.IGNORECASE
)
_USER_ATTRIBUTE = re.compile(r";?\s*(?:Uid|User ID)=[^;]+", flags=re.IGNORECASE)

_INTEGER_TYPES = frozenset(
    {"bigint", "int", "smallint", "tinyint"}
)
_DECIMAL_TYPES = frozenset(
    {"decimal", "money", "numeric", "smallmoney"}
)
_FLOAT_TYPES = frozenset({"float", "real"})
_DATETIME_TYPES = frozenset(
    {"date", "datetime", "datetime2", "datetimeoffset", "smalldatetime", "time"}
)
_BINARY_TYPES = frozenset({"binary", "image", "timestamp", "varbinary"})


class SynapseProvider:
    """Read-only Azure Synapse provider backed by ``pyodbc``."""

    provider_id = ProviderId.SYNAPSE

    def __init__(
        self,
        config: DatabaseProviderConfig,
        connection_string: str,
        *,
        credential: Any | None = None,
        validator: SqlValidator | None = None,
        connect_factory: Callable[..., Any] | None = None,
    ) -> None:
        if config.provider_id is not self.provider_id:
            raise ConfigurationError(
                f"{type(self).__name__} requires a {self.provider_id.value} configuration."
            )
        if not config.enabled:
            raise ConfigurationError("The Synapse provider is disabled.")
        if not isinstance(connection_string, str) or not connection_string.strip():
            raise ConfigurationError("A Synapse connection configuration is required.")

        self.config = config
        self.validator = validator or SqlGlotValidator(dialect="tsql")
        self._connect_factory = connect_factory
        self._connection: Any | None = None

        uses_active_directory = "authentication=activedirectory" in connection_string.lower()
        self._credential = credential
        if uses_active_directory:
            self._credential = credential or DefaultAzureCredential()
            connection_string = _AUTHENTICATION_ATTRIBUTE.sub("", connection_string)
            connection_string = _USER_ATTRIBUTE.sub("", connection_string)
        self._connection_string = connection_string.strip("; ")

    async def connect(self) -> None:
        if self._connection is None:
            self._connection = await asyncio.to_thread(self._open_connection)

    async def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            await asyncio.to_thread(connection.close)

    async def discover_schema(self, request: SchemaRequest) -> SchemaDiscoveryResult:
        correlation_id = new_correlation_id()
        try:
            self._validate_schema_request(request)
            return await asyncio.to_thread(
                self._discover_schema_sync, request, correlation_id
            )
        except DatabaseError as error:
            return SchemaDiscoveryResult(
                provider=self.provider_id,
                correlation_id=correlation_id,
                status=error.status,
                message=error.message,
            )

    async def execute_query(self, request: QueryRequest) -> QueryResult:
        correlation_id = new_correlation_id()
        try:
            if request.continuation is not None:
                raise ValidationError(
                    "Synapse continuation requires a proven unique ordering key."
                )
            validated = self.validator.validate(
                request.sql,
                approved_schemas=self.config.normalized_approved_schemas,
                allowed_table_functions=self.config.normalized_table_functions,
            )
            return await asyncio.to_thread(
                self._execute_query_sync, request, validated, correlation_id
            )
        except DatabaseError as error:
            return error.to_result(
                provider=self.provider_id, correlation_id=correlation_id
            )

    @staticmethod
    def _apply_top(sql: str, row_count: int) -> str:
        try:
            expression = sqlglot.parse_one(sql, read="tsql")
            limit = expression.args.get("limit")
            limit_expression = limit.expression if limit is not None else None
            if (
                isinstance(limit_expression, sqlglot.exp.Literal)
                and not limit_expression.is_string
                and limit.args.get("limit_options") is None
            ):
                row_count = min(row_count, max(0, int(limit_expression.this)))
            expression = expression.limit(row_count)
            return expression.sql(dialect="tsql", comments=False)
        except Exception as error:
            raise ValidationError("SQL could not be bounded for Synapse execution.") from error

    def _open_connection(self):
        kwargs: dict[str, Any] = {"timeout": self.config.connect_timeout_seconds}
        if self._credential is not None:
            token = self._credential.get_token(AZURE_GOVERNMENT_SQL_SCOPE)
            kwargs["attrs_before"] = {
                SQL_COPT_SS_ACCESS_TOKEN: _get_token_struct(token.token)
            }
        connect = self._connect_factory or pyodbc.connect
        try:
            return connect(self._connection_string, **kwargs)
        except Exception as error:
            raise self._map_error(error, operation="connection") from error

    def _acquire_connection(self) -> tuple[Any, bool]:
        if self._connection is not None:
            return self._connection, False
        return self._open_connection(), True

    def _execute_query_sync(self, request, validated, correlation_id: str) -> QueryResult:
        connection = None
        owned = False
        try:
            connection, owned = self._acquire_connection()
            connection.timeout = self.config.query_timeout_seconds
            with closing(connection.cursor()) as cursor:
                bounded_sql = self._apply_top(
                    validated.normalized_sql, self.config.max_rows + 1
                )
                parameters = tuple(request.parameters or ())
                if parameters:
                    cursor.execute(bounded_sql, parameters)
                else:
                    cursor.execute(bounded_sql)
                column_names = [str(column[0]) for column in (cursor.description or ())]
                fetched_rows = cursor.fetchmany(self.config.max_rows + 1)

            bounded = bound_result_rows(
                fetched_rows,
                max_rows=self.config.max_rows,
                max_result_chars=self.config.max_result_chars,
                max_cell_chars=self.config.max_cell_chars,
                stable_order=validated.has_explicit_order,
            )
            column_types = list(bounded.column_types)
            column_types.extend(
                [NormalizedType.NULL] * (len(column_names) - len(column_types))
            )
            return QueryResult(
                provider=self.provider_id,
                correlation_id=correlation_id,
                columns=[
                    ColumnMetadata(name, column_types[index])
                    for index, name in enumerate(column_names)
                ],
                rows=bounded.rows,
                truncated=bounded.truncated,
                truncated_by=bounded.truncated_by,
                warnings=bounded.warnings,
            )
        except DatabaseError:
            raise
        except Exception as error:
            raise self._map_error(error, operation="query") from error
        finally:
            if owned and connection is not None:
                connection.close()

    def _validate_schema_request(self, request: SchemaRequest) -> None:
        if request.continuation is not None:
            raise ValidationError("Synapse schema continuation is not supported.")
        approved = self.config.normalized_approved_schemas
        if request.schema and approved and request.schema.lower() not in approved:
            raise ValidationError("The requested schema is not approved.")

    def _discover_schema_sync(
        self, request: SchemaRequest, correlation_id: str
    ) -> SchemaDiscoveryResult:
        where = []
        parameters: list[Any] = []
        approved = sorted(self.config.normalized_approved_schemas)
        if request.schema:
            where.append("t.TABLE_SCHEMA = ?")
            parameters.append(request.schema)
        elif approved:
            placeholders = ", ".join("?" for _ in approved)
            where.append(f"LOWER(t.TABLE_SCHEMA) IN ({placeholders})")
            parameters.extend(approved)
        if request.object_name:
            where.append("t.TABLE_NAME = ?")
            parameters.append(request.object_name)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        sql = f"""
WITH bounded_objects AS (
    SELECT t.TABLE_SCHEMA, t.TABLE_NAME, t.TABLE_TYPE
    FROM INFORMATION_SCHEMA.TABLES AS t
    {where_sql}
    ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME
    OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
)
SELECT o.TABLE_SCHEMA, o.TABLE_NAME, o.TABLE_TYPE,
       c.COLUMN_NAME, c.DATA_TYPE, c.ORDINAL_POSITION
FROM bounded_objects AS o
JOIN INFORMATION_SCHEMA.COLUMNS AS c
  ON c.TABLE_SCHEMA = o.TABLE_SCHEMA AND c.TABLE_NAME = o.TABLE_NAME
ORDER BY o.TABLE_SCHEMA, o.TABLE_NAME, c.ORDINAL_POSITION
""".strip()
        parameters.append(self.config.max_rows + 1)

        connection = None
        owned = False
        try:
            connection, owned = self._acquire_connection()
            connection.timeout = self.config.query_timeout_seconds
            with closing(connection.cursor()) as cursor:
                cursor.execute(sql, tuple(parameters))
                rows = cursor.fetchmany(self.config.max_rows * 100 + 100)

            objects: list[SchemaObjectMetadata] = []
            object_index: dict[tuple[str, str], SchemaObjectMetadata] = {}
            for schema, name, table_type, column_name, data_type, _ in rows:
                key = (str(schema), str(name))
                metadata = object_index.get(key)
                if metadata is None:
                    metadata = SchemaObjectMetadata(
                        schema=key[0],
                        name=key[1],
                        kind="view" if str(table_type).upper() == "VIEW" else "table",
                        columns=[],
                    )
                    object_index[key] = metadata
                    objects.append(metadata)
                metadata.columns.append(
                    ColumnMetadata(
                        name=str(column_name),
                        type_label=self._normalize_catalog_type(str(data_type)),
                    )
                )

            truncated = len(objects) > self.config.max_rows
            return SchemaDiscoveryResult(
                provider=self.provider_id,
                correlation_id=correlation_id,
                objects=objects[: self.config.max_rows],
                truncated=truncated,
                warnings=(
                    ["Schema discovery was bounded; omitted objects are not evidence of absence."]
                    if truncated
                    else []
                ),
            )
        except DatabaseError:
            raise
        except Exception as error:
            raise self._map_error(error, operation="schema discovery") from error
        finally:
            if owned and connection is not None:
                connection.close()

    @staticmethod
    def _normalize_catalog_type(data_type: str) -> NormalizedType:
        normalized = data_type.lower()
        if normalized in _INTEGER_TYPES:
            return NormalizedType.INTEGER
        if normalized in _DECIMAL_TYPES:
            return NormalizedType.DECIMAL
        if normalized in _FLOAT_TYPES:
            return NormalizedType.FLOAT
        if normalized == "bit":
            return NormalizedType.BOOLEAN
        if normalized in _DATETIME_TYPES:
            return NormalizedType.DATETIME
        if normalized in _BINARY_TYPES:
            return NormalizedType.BINARY
        return NormalizedType.STRING

    @staticmethod
    def _map_error(error: BaseException, *, operation: str) -> DatabaseError:
        arguments = getattr(error, "args", ())
        state = str(arguments[0]).upper() if arguments else ""
        detail = " ".join(str(argument) for argument in arguments).lower()
        if any(token in detail for token in ("certificate", "ssl", "tls", "trust")):
            return TrustError("Synapse server trust validation failed.", cause=error)
        if state.startswith("28"):
            return AuthenticationError("Synapse authentication failed.", cause=error)
        if state in {"42501", "42001"} or "permission" in detail or "not authorized" in detail:
            return AuthorizationError("Synapse access was denied.", cause=error)
        if state.startswith("08") or state in {"HYT00", "HYT01"}:
            return TransientError(f"Synapse {operation} is temporarily unavailable.", cause=error)
        if state.startswith("IM"):
            return ConfigurationError("Synapse driver configuration is unavailable.", cause=error)
        return QueryError("Synapse rejected the read query.", cause=error)


class AzureSqlProvider(SynapseProvider):
    """Read-only Azure SQL provider used by the SAP emulator."""

    provider_id = ProviderId.SAP_EMULATOR
