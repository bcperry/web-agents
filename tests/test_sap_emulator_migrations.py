from pathlib import Path

import pytest

from database_emulator.apply_migrations import (
    MigrationConfigurationError,
    _execute_batch,
    _grant_reader,
    migration_files,
    split_batches,
    validate_migrations,
)

MIGRATIONS = Path(__file__).resolve().parents[1] / "database_emulator" / "migrations"


class RecordingConnection:
    def __init__(self) -> None:
        self.sql = ""

    def cursor(self):
        return self

    def execute(self, sql: str):
        self.sql = sql


class DelayedErrorCursor:
    def execute(self, sql: str):
        return self

    def nextset(self):
        raise RuntimeError("delayed batch error")


class DelayedErrorConnection:
    def cursor(self):
        return DelayedErrorCursor()


def test_migrations_are_contiguous_and_have_executable_batches():
    files = migration_files(MIGRATIONS)

    assert [path.name for path in files] == [
        "001_sap_schema.sql",
        "002_force_equipment_reporting.sql",
        "003_synthetic_seed.sql",
        "004_bulk_synthetic_seed.sql",
        "005_financial_execution.sql",
    ]
    assert validate_migrations(files) == {
        "001_sap_schema.sql": 17,
        "002_force_equipment_reporting.sql": 11,
        "003_synthetic_seed.sql": 3,
        "004_bulk_synthetic_seed.sql": 3,
        "005_financial_execution.sql": 4,
    }


def test_split_batches_accepts_only_standalone_go_lines():
    sql = "SELECT 'GO';\nGO\nSELECT 2; -- GO is not a separator\ngo -- next batch\n"

    assert split_batches(sql) == ("SELECT 'GO';", "SELECT 2; -- GO is not a separator")


def test_migration_sequence_gaps_fail_closed(tmp_path: Path):
    (tmp_path / "001_first.sql").write_text("SELECT 1", encoding="utf-8")
    (tmp_path / "003_third.sql").write_text("SELECT 3", encoding="utf-8")

    with pytest.raises(MigrationConfigurationError, match="contiguous"):
        migration_files(tmp_path)


def test_reader_grant_is_limited_to_reporting_schema():
    connection = RecordingConnection()

    _grant_reader(connection, "app-reader")

    assert "ALTER ROLE [db_datareader] DROP MEMBER [app-reader]" in connection.sql
    assert "ALTER ROLE [db_datareader] ADD MEMBER" not in connection.sql
    assert "REVOKE VIEW DEFINITION TO [app-reader]" in connection.sql
    assert "GRANT SELECT ON SCHEMA::[reporting] TO [app-reader]" in connection.sql
    assert "GRANT VIEW DEFINITION ON SCHEMA::[reporting] TO [app-reader]" in connection.sql


def test_execute_batch_surfaces_delayed_driver_errors():
    with pytest.raises(RuntimeError, match="delayed batch error"):
        _execute_batch(DelayedErrorConnection(), "SELECT 1")