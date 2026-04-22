import json
import logging
import os
import re
import struct
import time
from contextlib import closing
from typing import Any

from pydantic import Field
import pyodbc

from azure.identity import DefaultAzureCredential


logger = logging.getLogger("tools")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r; using default=%s", name, raw, default)
        return default


MAX_QUERY_RESULT_ROWS = _env_int("MAX_QUERY_RESULT_ROWS", 100)
MAX_QUERY_RESULT_CHARS = _env_int("MAX_QUERY_RESULT_CHARS", 12000)
MAX_SQL_CELL_CHARS = _env_int("MAX_SQL_CELL_CHARS", 1200)
MAX_LOG_QUERY_CHARS = _env_int("MAX_LOG_QUERY_CHARS", 500)
MAX_LOG_TOOL_RESULT_CHARS = _env_int("MAX_LOG_TOOL_RESULT_CHARS", 100)
MAX_SEARCH_SNIPPET_CHARS = _env_int("MAX_SEARCH_SNIPPET_CHARS", 500)


def _mask_connection_string(connection_string: str) -> str:
    redacted = re.sub(r"(?i)(password|pwd)\s*=\s*[^;]+", r"\1=***", connection_string)
    redacted = re.sub(r"(?i)(user id|uid)\s*=\s*[^;]+", r"\1=***", redacted)
    return redacted


def _compact_sql_for_logs(query: str) -> str:
    compacted = " ".join(query.strip().split())
    return _truncate_text(compacted, MAX_LOG_QUERY_CHARS, "SQL LOG")


def _summarize_params_for_logs(params: Any | None) -> str:
    if params is None:
        return "none"
    if isinstance(params, tuple):
        return f"tuple(len={len(params)})"
    if isinstance(params, list):
        return f"list(len={len(params)})"
    if isinstance(params, dict):
        return f"dict(keys={list(params.keys())})"
    return type(params).__name__


def _preview_tool_result_for_logs(value: Any) -> str:
    raw = str(value)
    compact = " ".join(raw.split())
    if len(compact) <= MAX_LOG_TOOL_RESULT_CHARS:
        return compact
    return f"{compact[:MAX_LOG_TOOL_RESULT_CHARS]}..."


def _get_token_struct(token: str) -> bytes:
    """Convert access token to the format required by pyodbc for SQL Server."""
    token_bytes = token.encode("utf-16-le")
    return struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)


def _truncate_text(value: str, max_chars: int, label: str) -> str:
    if len(value) <= max_chars:
        return value
    omitted = len(value) - max_chars
    return f"{value[:max_chars]}\n...[TRUNCATED {label}: omitted {omitted} chars]"


def _sanitize_cell_value(value: Any) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, MAX_SQL_CELL_CHARS, "SQL CELL")
    return value


class SqlDatabase:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self._credential = None
        self._last_query_truncated = False
        self._last_output_truncated = False
        self._query_counter = 0
        self._init_credential()
        logger.info(
            "SqlDatabase init: max_rows=%s max_result_chars=%s max_cell_chars=%s",
            MAX_QUERY_RESULT_ROWS,
            MAX_QUERY_RESULT_CHARS,
            MAX_SQL_CELL_CHARS,
        )
        self.get_conn()
        self.view_metadata: dict[str, Any] = {}

    def discover_view_metadata(self, schema_name: str = "ai", sample_size: int = 3) -> dict[str, Any]:
        """Iterate over all views in a schema and collect compact metadata for each.

        For every view, gathers:
        - Column names mapped to their data types
        - Source tables the view references (deduplicated)
        - A few sample values per column (pivoted from sample rows)

        Results are stored on ``self.view_metadata`` keyed by fully-qualified
        view name (e.g. ``ai.my_view``) and also returned.
        """
        sample_size = max(1, min(int(sample_size), 10))
        logger.info(
            "discover_view_metadata: schema=%s sample_size=%s", schema_name, sample_size
        )

        metadata: dict[str, Any] = {}

        with closing(self.get_conn()) as conn:
            def _run(query, params=None):
                with closing(conn.cursor()) as cur:
                    if params:
                        cur.execute(query, params)
                    else:
                        cur.execute(query)
                    cols = [c[0] for c in cur.description]
                    return [dict(zip(cols, row)) for row in cur.fetchall()]

            views = _run(
                "SELECT TABLE_SCHEMA, TABLE_NAME "
                "FROM INFORMATION_SCHEMA.VIEWS "
                "WHERE TABLE_SCHEMA = ?",
                (schema_name,),
            )

            for view in views:
                view_name = view["TABLE_NAME"]
                full_name = f"{schema_name}.{view_name}"
                logger.debug("discover_view_metadata: processing %s", full_name)

                # -- columns as {name: type} ----------------------------------
                raw_columns = _run(
                    "SELECT COLUMN_NAME, DATA_TYPE "
                    "FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
                    "ORDER BY ORDINAL_POSITION",
                    (schema_name, view_name),
                )
                columns = {c["COLUMN_NAME"]: c["DATA_TYPE"] for c in raw_columns}

                # -- sample values per column (pivoted from TOP rows) ---------
                sample_values: dict[str, list[Any]] = {}
                try:
                    rows = _run(
                        f"SELECT TOP ({sample_size}) * FROM [{schema_name}].[{view_name}]"
                    )
                    for col_name in columns:
                        seen: list[Any] = []
                        for row in rows:
                            v = row.get(col_name)
                            if v is not None and v not in seen:
                                seen.append(v)
                        sample_values[col_name] = seen
                except Exception as e:
                    logger.warning(
                        "discover_view_metadata: sample query failed for %s: %s",
                        full_name, e,
                    )

                metadata[full_name] = {
                    "columns": columns,
                    "sample_values": sample_values,
                }

        self.view_metadata = metadata
        logger.info(
            "discover_view_metadata: completed — %s views catalogued", len(metadata)
        )
        self._inject_metadata_into_docstrings()
        return self.view_metadata

    @staticmethod
    def _serialize_metadata(metadata: dict[str, Any]) -> str:
        """Serialize view metadata to compact JSON for docstring injection."""
        def _default(obj: Any) -> str:
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            return str(obj)
        return json.dumps(metadata, default=_default, separators=(",", ":"))

    def _inject_metadata_into_docstrings(self) -> None:
        """Append serialized view_metadata to key tool docstrings."""
        if not self.view_metadata:
            return
        schema_block = (
            "\n\nAvailable view schemas and sample data:\n"
            + self._serialize_metadata(self.view_metadata)
        )
        func = self.sql_read_query.__func__
        base_doc = func.__doc__ or ""
        # Strip any previously injected block to avoid duplication
        marker = "\n\nAvailable view schemas and sample data:\n"
        if marker in base_doc:
            base_doc = base_doc[: base_doc.index(marker)]
        func.__doc__ = base_doc + schema_block
        logger.info(
            "_inject_metadata_into_docstrings: injected %d chars into tool docstrings",
            len(schema_block),
        )

    def _format_tool_output(self, payload: Any) -> str:
        rendered = str(payload)
        self._last_output_truncated = len(rendered) > MAX_QUERY_RESULT_CHARS
        if self._last_output_truncated:
            logger.warning(
                "Tool output truncated at %s chars (original=%s chars)",
                MAX_QUERY_RESULT_CHARS,
                len(rendered),
            )
        return _truncate_text(rendered, MAX_QUERY_RESULT_CHARS, "SQL RESULT")

    def _is_distinct_query(self, normalized_query: str) -> bool:
        return "SELECT DISTINCT" in normalized_query

    def _build_truncation_guidance(self, query: str, normalized_query: str) -> str:
        base_guidance = (
            "NOTE: Results are partial due to truncation limits. Do not conclude a value is missing from the database based on this response alone. "
            "Run additional SELECT queries to continue coverage until no new rows/values are returned."
        )

        if self._is_distinct_query(normalized_query):
            return (
                f"{base_guidance}\n"
                "For DISTINCT discovery, page the value space in multiple queries and merge findings before concluding presence/absence.\n"
                "Example paging pattern (replace placeholders):\n"
                "SELECT DISTINCT <column> FROM <schema.view_or_table> "
                "ORDER BY <column> OFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY;\n"
                "Then increment OFFSET (100, 200, 300, ...) until a page returns no new values."
            )

        return (
            f"{base_guidance}\n"
            "If this response is used for filtering or existence checks, re-query in smaller pages "
            "(e.g., ORDER BY + OFFSET/FETCH) and consolidate all pages first."
        )

    def _init_credential(self):
        """Initialize Azure credential for token-based auth if needed."""
        # Check if connection string uses Azure AD auth that needs token injection
        conn_lower = self.connection_string.lower()
        if "authentication=activedirectory" in conn_lower:
            # Remove the Authentication attribute - we'll use token instead
            import re
            self.connection_string = re.sub(
                r";?\s*Authentication=[^;]+", "", self.connection_string, flags=re.IGNORECASE
            )
            # Also remove Uid if present (not needed for token auth)
            self.connection_string = re.sub(
                r";?\s*Uid=[^;]+", "", self.connection_string, flags=re.IGNORECASE
            )
            # DefaultAzureCredential: managed identity on Azure, CLI locally
            self._credential = DefaultAzureCredential()
            logger.info("Using DefaultAzureCredential for SQL authentication")

    def get_conn(self):
        start = time.perf_counter()
        auth_mode = "token" if self._credential else "connection_string"
        logger.debug(
            "Opening SQL connection (auth_mode=%s, connection=%s)",
            auth_mode,
            _mask_connection_string(self.connection_string),
        )
        try:
            if self._credential:
                # Get token for Azure SQL / Synapse
                # Use the correct scope for Azure Government
                token = self._credential.get_token("https://database.usgovcloudapi.net/.default")
                token_struct = _get_token_struct(token.token)
                conn = pyodbc.connect(self.connection_string, attrs_before={1256: token_struct})
            else:
                conn = pyodbc.connect(self.connection_string)
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug("SQL connection opened in %.2f ms", elapsed_ms)
            return conn
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error("Database connection error after %.2f ms: %s", elapsed_ms, e)
            raise

    def _execute_query(
        self, query: str, params: Any | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SQL query and return results as a list of dictionaries"""
        self._query_counter += 1
        query_id = self._query_counter
        query_start = time.perf_counter()
        logger.info(
            "[SQL %s] Executing query (params=%s): %s",
            query_id,
            _summarize_params_for_logs(params),
            _compact_sql_for_logs(query),
        )
        self._last_query_truncated = False
        self._last_output_truncated = False
        try:
            with closing(self.get_conn()) as conn:
                with closing(conn.cursor()) as cursor:
                    if params:
                        cursor.execute(query, params)
                    else:
                        cursor.execute(query)

                    if (
                        query.strip()
                        .upper()
                        .startswith(
                            ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER")
                        )
                    ):
                        conn.commit()
                        affected = cursor.rowcount
                        elapsed_ms = (time.perf_counter() - query_start) * 1000
                        logger.info(
                            "[SQL %s] Write query complete in %.2f ms (affected_rows=%s, result_preview=%s)",
                            query_id,
                            elapsed_ms,
                            affected,
                            _preview_tool_result_for_logs({"affected_rows": affected}),
                        )
                        return [{"affected_rows": affected}]
                    columns = [column[0] for column in cursor.description]
                    rows = cursor.fetchmany(MAX_QUERY_RESULT_ROWS + 1)
                    if len(rows) > MAX_QUERY_RESULT_ROWS:
                        self._last_query_truncated = True
                        logger.warning(
                            "[SQL %s] Row truncation applied at max_rows=%s",
                            query_id,
                            MAX_QUERY_RESULT_ROWS,
                        )
                        rows = rows[:MAX_QUERY_RESULT_ROWS]
                    results = [
                        dict(zip(columns, (_sanitize_cell_value(cell) for cell in row)))
                        for row in rows
                    ]
                    elapsed_ms = (time.perf_counter() - query_start) * 1000
                    logger.info(
                        "[SQL %s] Read query complete in %.2f ms (rows=%s, columns=%s, result_preview=%s)",
                        query_id,
                        elapsed_ms,
                        len(results),
                        len(columns),
                        _preview_tool_result_for_logs(results),
                    )
                    return results
        except Exception as e:
            elapsed_ms = (time.perf_counter() - query_start) * 1000
            logger.error("[SQL %s] Query failed after %.2f ms: %s", query_id, elapsed_ms, e)
            raise

    def sql_read_query(
        self, query: str = Field(description="T-SQL SELECT query to execute on Azure Synapse")
    ) -> str:
        """Execute read-only T-SQL SELECT queries against an Azure Synapse Analytics dedicated SQL pool.

        Database dialect: T-SQL (Synapse). Use Synapse-compatible syntax only.
        - Use TOP instead of LIMIT.
        - Use CAST/CONVERT for type conversions.
        - Use ISNULL instead of IFNULL/COALESCE where appropriate.
        - String concatenation uses + operator.
        - Date functions: GETDATE(), DATEADD(), DATEDIFF(), FORMAT().

        All available views with their column schemas and sample values are appended below.
        Use ONLY the views and columns listed there. Do not guess or fabricate table/column names.
        Only SELECT statements are allowed. No data or schema mutation.

        Query construction rules:
        - Always qualify view names with their schema (e.g. ai.vw_aircraft_profile).
        - For filtering/aggregation: first run SELECT DISTINCT on filter columns to verify actual values, then build WHERE/GROUP BY using only verified values.
        - Treat truncated results as partial — continue with paged follow-on queries (OFFSET/FETCH or TOP with WHERE).
        - Never claim a value is absent based on truncated results.
        """

        # Normalize the query for checking
        normalized_query = query.strip().upper()

        # Only allow SELECT statements
        if not normalized_query.startswith("SELECT"):
            logger.warning("read_query rejected non-SELECT query: %s", _compact_sql_for_logs(query))
            raise ValueError("Only SELECT queries are allowed for read_query")

        # Check if this is a filtered/aggregation query without having checked distinct values first
        has_where = "WHERE" in normalized_query
        has_count = "COUNT(" in normalized_query
        has_sum = "SUM(" in normalized_query
        has_avg = "AVG(" in normalized_query
        has_group_by = "GROUP BY" in normalized_query

        # Block dangerous keywords that could modify data or schema
        dangerous_keywords = [
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "CREATE",
            "ALTER",
            "TRUNCATE",
            "MERGE",
            "EXEC",
            "EXECUTE",
            "CALL",
            "GRANT",
            "REVOKE",
            "COMMIT",
            "ROLLBACK",
            "SAVEPOINT",
        ]

        for keyword in dangerous_keywords:
            if keyword in normalized_query:
                logger.warning("read_query rejected query containing blocked keyword '%s'", keyword)
                raise ValueError(
                    f"Keyword '{keyword}' is not allowed in read-only queries"
                )

        try:
            results = self._execute_query(query)
        except Exception as e:
            return (
                "Query failed to execute.\n"
                f"Database error: {str(e)}\n\n"
                "Check the view schemas and column names in the tool description and retry."
            )

        rendered_results = self._format_tool_output(results)
        has_marker_truncation = (
            "[TRUNCATED SQL RESULT" in rendered_results
            or "[TRUNCATED SQL CELL" in rendered_results
        )
        is_truncated = (
            self._last_query_truncated
            or self._last_output_truncated
            or has_marker_truncation
        )
        truncation_note = (
            f"\n\n{self._build_truncation_guidance(query, normalized_query)}"
            if is_truncated
            else ""
        )

        if has_where or has_count or has_sum or has_avg or has_group_by:
            return (
                f"Your results are: {rendered_results}{truncation_note}\n"
                "NOTE: You are attempting to filter or aggregate data"
                "Although this query completed, please make sure you have:\n"
                "1. Run SELECT DISTINCT queries on any columns you filter on\n"
                "2. Verify the actual values that exist in the database\n"
                "3. Then construct your filtered/aggregated query using only those verified values\n\n"
                "If you have not performed these steps, you will need to reattempt your query. "
                "Do NOT proceed without checking distinct values first."
            )
        else:
            return f"{rendered_results}{truncation_note}"


class UserProfileStore:
    """Per-session in-memory store for user profile data.

    The frontend sends the profile (from localStorage) when creating a session.
    Tools exposed: get_user_profile, save_user_profile.
    """

    def __init__(self, profile: dict[str, str] | None = None):
        self._profile: dict[str, str] | None = profile

    def get_user_profile(self) -> str:
        """Return the stored user profile as a JSON string, or a message indicating no profile was found."""
        if self._profile:
            return json.dumps(self._profile)
        return (
            "No user profile found. Please ask the user for their name "
            "and any preferences or interests they'd like you to remember."
        )

    def save_user_profile(self, name: str, preferences: str = "", notes: str = "") -> str:
        """Save or update the user profile. Returns confirmation or a validation error.

        Args:
            name: The user's display name (e.g. "Alex").
            preferences: Comma-separated list of things the user likes or prefers (e.g. "concise answers, dark mode, Python").
            notes: Any additional notes about the user to remember across sessions.
        """
        if not name or not name.strip():
            return "Error: name must not be empty."
        self._profile = {
            "name": name.strip(),
            "preferences": preferences.strip(),
            "notes": notes.strip(),
        }
        return f"User profile saved successfully: {json.dumps(self._profile)}"
