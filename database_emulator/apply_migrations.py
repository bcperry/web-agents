"""Validate or apply the SAP emulator migrations without exposing credentials."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pyodbc
from azure.identity import DefaultAzureCredential

from tools import _get_token_struct

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
AZURE_GOVERNMENT_SQL_SCOPE = "https://database.usgovcloudapi.net/.default"
SQL_COPT_SS_ACCESS_TOKEN = 1256

_GO_LINE = re.compile(r"^\s*GO\s*(?:--.*)?$", flags=re.IGNORECASE)
_AUTHENTICATION_ATTRIBUTE = re.compile(
    r";?\s*Authentication=[^;]+", flags=re.IGNORECASE
)
_USER_ATTRIBUTE = re.compile(r";?\s*(?:Uid|User ID)=[^;]+", flags=re.IGNORECASE)


class MigrationConfigurationError(ValueError):
    """Raised for safe-to-display migration configuration failures."""


def migration_files(directory: Path = MIGRATIONS_DIR) -> tuple[Path, ...]:
    files = tuple(sorted(directory.glob("[0-9][0-9][0-9]_*.sql")))
    if not files:
        raise MigrationConfigurationError(f"No SQL migrations found in {directory}.")
    expected = list(range(1, len(files) + 1))
    actual = [int(path.name[:3]) for path in files]
    if actual != expected:
        raise MigrationConfigurationError(
            f"Migration sequence must be contiguous from 001; found {actual}."
        )
    return files


def split_batches(sql: str) -> tuple[str, ...]:
    batches: list[str] = []
    current: list[str] = []
    for line in sql.splitlines():
        if _GO_LINE.match(line):
            batch = "\n".join(current).strip()
            if batch:
                batches.append(batch)
            current = []
        else:
            current.append(line)
    batch = "\n".join(current).strip()
    if batch:
        batches.append(batch)
    return tuple(batches)


def validate_migrations(files: Iterable[Path]) -> dict[str, int]:
    result: dict[str, int] = {}
    for path in files:
        sql = path.read_text(encoding="utf-8")
        batches = split_batches(sql)
        if not batches:
            raise MigrationConfigurationError(f"{path.name} contains no executable batches.")
        result[path.name] = len(batches)
    return result


def open_connection(connection_string: str) -> Any:
    if not connection_string.strip():
        raise MigrationConfigurationError(
            "SAP_EMULATOR_CONNECTIONSTRING or AZURE_SQL_CONNECTIONSTRING is required."
        )
    uses_entra = "authentication=activedirectory" in connection_string.lower()
    kwargs: dict[str, Any] = {"autocommit": True}
    if uses_entra:
        sanitized = _AUTHENTICATION_ATTRIBUTE.sub("", connection_string)
        sanitized = _USER_ATTRIBUTE.sub("", sanitized).strip("; ")
        token = DefaultAzureCredential().get_token(AZURE_GOVERNMENT_SQL_SCOPE)
        kwargs["attrs_before"] = {
            SQL_COPT_SS_ACCESS_TOKEN: _get_token_struct(token.token)
        }
        connection_string = sanitized
    return pyodbc.connect(connection_string, **kwargs)


def _quoted_identifier(value: str) -> str:
    trimmed = value.strip()
    if not trimmed or len(trimmed) > 128 or any(ord(char) < 32 for char in trimmed):
        raise MigrationConfigurationError("Reader principal name is invalid.")
    return "[" + trimmed.replace("]", "]]" ) + "]"


def _grant_reader(connection: Any, principal_name: str) -> None:
    principal = _quoted_identifier(principal_name)
    escaped_name = principal_name.replace("'", "''")
    sql = f"""
IF DATABASE_PRINCIPAL_ID(N'{escaped_name}') IS NULL
    CREATE USER {principal} FROM EXTERNAL PROVIDER;
IF IS_ROLEMEMBER(N'db_datareader', N'{escaped_name}') = 1
    ALTER ROLE [db_datareader] DROP MEMBER {principal};
REVOKE VIEW DEFINITION TO {principal};
GRANT SELECT ON SCHEMA::[reporting] TO {principal};
GRANT VIEW DEFINITION ON SCHEMA::[reporting] TO {principal};
"""
    connection.cursor().execute(sql)


def _execute_batch(connection: Any, sql: str) -> None:
    cursor = connection.cursor()
    cursor.execute(sql)
    while cursor.nextset():
        pass


def apply_migrations(
    connection_string: str,
    files: Iterable[Path],
    *,
    reader_principal_name: str = "",
) -> None:
    connection = open_connection(connection_string)
    try:
        for path in files:
            for batch in split_batches(path.read_text(encoding="utf-8")):
                _execute_batch(connection, batch)
        if reader_principal_name.strip():
            _grant_reader(connection, reader_principal_name)
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate migration order and GO batches without connecting to a database.",
    )
    args = parser.parse_args()

    try:
        files = migration_files()
        counts = validate_migrations(files)
        if args.validate_only:
            for name, count in counts.items():
                print(f"{name}: {count} batches")
            return 0

        connection_string = os.getenv("SAP_EMULATOR_CONNECTIONSTRING") or os.getenv(
            "AZURE_SQL_CONNECTIONSTRING", ""
        )
        apply_migrations(
            connection_string,
            files,
            reader_principal_name=os.getenv("SAP_EMULATOR_READER_PRINCIPAL_NAME", ""),
        )
        print(f"Applied {len(files)} SAP emulator migrations.")
        return 0
    except MigrationConfigurationError as error:
        print(str(error), file=sys.stderr)
    except Exception:
        print("Azure SQL migration failed; sensitive driver details were suppressed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())