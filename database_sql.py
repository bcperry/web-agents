"""The read-only SQL grammar gate.

One parser-backed pass proves a statement is a single read: the root must be a
SELECT-shaped node, no denied node type may appear anywhere in the tree, table
functions must be allowlisted by fully qualified name, and every referenced
object must sit in an approved schema. Denied node types are imported by name so
a ``sqlglot`` upgrade that renames one breaks the build instead of the guarantee.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from database import ValidationError, sha256_hex, validate_sql_text

_DENIED_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Command,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Set,
    exp.Use,
    exp.Copy,
    exp.Pragma,
    exp.Analyze,
    exp.Into,
    exp.Export,
    exp.LoadData,
)

_TABLE_FUNCTION_NODES: tuple[type[exp.Expression], ...] = (
    exp.Lateral,
    exp.TableFromRows,
    exp.Unnest,
)

_READ_ROOT_NODES: tuple[type[exp.Expression], ...] = (
    exp.Select,
    exp.SetOperation,
    exp.Subquery,
)


@dataclass(frozen=True)
class ValidatedSql:
    expression: exp.Expression
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


def _reject_comments(sql: str) -> None:
    """Reject SQL comments outside string/identifier literals.

    Comments can smuggle instructions into anything that later reads the
    statement, so the contract bans them rather than trying to interpret them.
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
        elif sql.startswith("--", index) or sql.startswith("/*", index):
            raise ValidationError("SQL comments are not permitted.")
        index += 1
    if quote is not None:
        raise ValidationError("SQL contains an unterminated literal.")


def _table_function_name(table: exp.Table, func: exp.Func) -> str:
    name = str(func.this) if isinstance(func, exp.Anonymous) else func.sql_name()
    return ".".join(part for part in (table.catalog, table.db, name) if part).lower()


class SqlGlotValidator(SqlValidator):
    """Parser-backed validator.

    The dialect is injectable so a HANA-aware dialect can replace the default
    without changing any caller.
    """

    def __init__(self, dialect: str | None = None) -> None:
        self.dialect = dialect

    def validate(
        self,
        sql: str,
        *,
        approved_schemas: frozenset[str] | None = None,
        allowed_table_functions: frozenset[str] | None = None,
    ) -> ValidatedSql:
        validate_sql_text(sql)
        _reject_comments(sql)
        root = self._parse_single_read(sql)

        allowed_functions = frozenset(
            name.lower() for name in (allowed_table_functions or frozenset())
        )
        approved = frozenset(name.lower() for name in (approved_schemas or frozenset()))
        cte_names = {
            cte.alias_or_name.lower() for cte in root.find_all(exp.CTE) if cte.alias_or_name
        }

        schemas: set[str] = set()
        table_functions: set[str] = set()
        for node in root.walk():
            if isinstance(node, _DENIED_NODES):
                raise ValidationError("The statement contains a non-read operation.")
            if isinstance(node, _TABLE_FUNCTION_NODES):
                raise ValidationError("Table functions are not permitted by default.")
            if isinstance(node, exp.Table):
                self._collect_table(
                    node,
                    approved=approved,
                    allowed_functions=allowed_functions,
                    cte_names=cte_names,
                    schemas=schemas,
                    table_functions=table_functions,
                )

        normalized_sql = root.sql(dialect=self.dialect, comments=False, normalize=True)
        return ValidatedSql(
            expression=root,
            normalized_sql=normalized_sql,
            normalized_sql_hash=sha256_hex(normalized_sql.encode("utf-8")),
            referenced_schemas=frozenset(schemas),
            referenced_table_functions=frozenset(table_functions),
            has_explicit_order=root.args.get("order") is not None,
        )

    def _parse_single_read(self, sql: str) -> exp.Expression:
        try:
            statements = sqlglot.parse(sql, read=self.dialect)
        except SqlglotError as error:  # never echo the statement text
            raise ValidationError("SQL could not be parsed as a single read query.") from error
        if len(statements) != 1 or statements[0] is None:
            raise ValidationError("Exactly one read statement is allowed.")
        root = statements[0]
        if not isinstance(root, _READ_ROOT_NODES):
            raise ValidationError("Only a single read-only SELECT statement is allowed.")
        return root

    @staticmethod
    def _collect_table(
        table: exp.Table,
        *,
        approved: frozenset[str],
        allowed_functions: frozenset[str],
        cte_names: set[str],
        schemas: set[str],
        table_functions: set[str],
    ) -> None:
        inner: Any = table.this
        if isinstance(inner, exp.Func):
            name = _table_function_name(table, inner)
            if name not in allowed_functions:
                raise ValidationError(
                    "Table functions must be explicitly allowlisted by fully qualified name."
                )
            table_functions.add(name)
            return
        schema_name = (table.db or "").lower()
        if not schema_name:
            if approved and table.name.lower() not in cte_names:
                raise ValidationError(
                    "Every referenced object must be schema-qualified within the "
                    "approved schemas."
                )
            return
        if approved and schema_name not in approved:
            raise ValidationError("The statement references a schema that is not approved.")
        schemas.add(schema_name)


_DEFAULT_VALIDATOR = SqlGlotValidator()


def default_sql_validator() -> SqlValidator:
    return _DEFAULT_VALIDATOR
