from pathlib import Path

from database_emulator.generate_schema import (
    DEFAULT_OUTPUT,
    DEFAULT_WORKBOOK,
    load_contract,
    render_schema,
)

MIGRATIONS = Path(__file__).resolve().parents[1] / "database_emulator" / "migrations"


def test_workbook_contract_contains_every_supplied_source_field():
    tables = load_contract(DEFAULT_WORKBOOK)

    assert [table.source_name for table in tables] == [
        "/ISDFPS/FORCE",
        "HRP1000",
        "HRP1001",
        "EQUI",
        "EQUZ",
        "EQKT",
        "MARA",
        "ILOA",
        "IFLOT",
        "JEST",
        "TJ02T",
        "TJ30T",
    ]
    assert sum(len(table.fields) for table in tables) == 693
    assert all(table.key_fields for table in tables)


def test_workbook_contract_preserves_fields_that_control_relationships():
    tables = {table.source_name: table for table in load_contract(DEFAULT_WORKBOOK)}

    force_fields = {field.name: field for field in tables["/ISDFPS/FORCE"].fields}
    assert force_fields["FORCE_ID"].data_type == "CHAR"
    assert force_fields["FORCE_ID"].length == 32
    assert force_fields["OBJID"].data_type == "NUMC"
    assert force_fields["OBJID"].length == 8

    equz_fields = {field.name for field in tables["EQUZ"].fields}
    assert {"EQUNR", "DATAB", "DATBI", "HEQUI", "ILOAN"} <= equz_fields
    assert "TPLNR" not in equz_fields
    assert "SWERK" not in equz_fields

    mara_fields = {field.name: field for field in tables["MARA"].fields}
    assert mara_fields["MATNR"].length == 40
    assert "DODAC" not in mara_fields


def test_rendered_schema_is_azure_sql_ddl_with_ddic_metadata():
    sql = render_schema(DEFAULT_WORKBOOK)

    assert "CREATE TABLE [sap].[ISDFPS_FORCE]" in sql
    assert "[FORCE_ID] nvarchar(32) NOT NULL" in sql
    assert "[OBJID] char(8) NULL" in sql
    assert "CREATE TABLE [sap].[MARA]" in sql
    assert "[MATNR] nvarchar(40) NOT NULL" in sql
    assert "CREATE TABLE [emulator].[DDIC_FIELD]" in sql
    assert "Unsupported SAP type" not in sql


def test_generated_schema_migration_matches_workbook():
    assert DEFAULT_OUTPUT.read_text(encoding="utf-8") == render_schema(DEFAULT_WORKBOOK)


def test_reporting_view_uses_corrected_relationship_contract():
    sql = (MIGRATIONS / "002_force_equipment_reporting.sql").read_text(encoding="utf-8")

    assert "[force].[OBJID] AS [FORCE_ID]" in sql
    assert "[equipment].[EQUNR] = [emulator].[ALPHA_EQUNR]([relationship].[SOBID])" in sql
    assert "[location_assignment].[ILOAN] = [usage].[ILOAN]" in sql
    assert "[functional_location].[TPLNR] = [location_assignment].[TPLNR]" in sql
    assert "[status_text].[STSMA] = [status_profile].[STSMA]" in sql
    assert "[dodac].[MATNR] = [equipment].[MATNR]" in sql

    expected_columns = [
        "FORCE_ID",
        "FE_SHORT",
        "FE_STEXT",
        "BEGDA",
        "ENDDA",
        "EQUNR",
        "EQTYP",
        "SERNR",
        "HEQUI",
        "TPLMA",
        "EQKTX",
        "MATNR",
        "DODAC",
        "EXTWG",
        "MTART",
        "MATKL",
        "TPLNR",
        "FL_LEVEL",
        "SWERK",
        "SYS_STATUS",
        "USR_STATUS",
    ]
    aliases = [f"AS [{column}]" for column in expected_columns]
    projection = sql.split("SELECT\n    [force].[OBJID]", 1)[1].split(
        "FROM [emulator].[CONTEXT]", 1
    )[0]
    assert all(alias in projection for alias in aliases)
    assert [projection.index(alias) for alias in aliases] == sorted(
        projection.index(alias) for alias in aliases
    )


def test_synthetic_seed_covers_positive_and_negative_relationships():
    sql = (MIGRATIONS / "003_synthetic_seed.sql").read_text(encoding="utf-8")

    assert "N'003'" in sql
    assert "N'999'" in sql
    assert "'20211231'" in sql
    assert "N'M1A2 SEPv3 Kampfpanzer'" in sql
    assert "N'I0076', N'X'" in sql
    assert "N'MAT-MEP-805B'" in sql
    assert "N'1st Battalion, 66th Armor'" in sql
    assert "N'FORT-CAVAZOS-MP-12'" in sql
    assert "Synthetic force-equipment fixture did not produce three current rows." in sql


def test_bulk_seed_populates_linked_sap_tables_at_scale():
    sql = (MIGRATIONS / "004_bulk_synthetic_seed.sql").read_text(encoding="utf-8")

    assert "DECLARE @bulk_count int = 500;" in sql
    assert "DECLARE @unit_count int = 50;" in sql
    assert "SQRT(-2.0 * LOG([UNIT_U1]))" in sql
    assert "Bulk fixture did not produce 500 current reporting rows." in sql
    assert "Bulk fixture did not populate every SAP emulator table." in sql
    assert "Bulk fixture did not produce varied Gaussian unit holdings." in sql
    assert "INSERT INTO [sap].[ISDFPS_FORCE]" in sql
    assert "INSERT INTO [sap].[JEST]" in sql
    assert "INSERT INTO [sap].[TJ30T]" in sql
    assert "N'M1A2 SEPv3 Abrams'" in sql
    assert "N'FORT-BRAGG'" in sql
    assert "N'Non-Mission Capable Supply'" in sql