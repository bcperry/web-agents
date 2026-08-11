import os

import pytest

from database_emulator.apply_migrations import (
    apply_migrations,
    migration_files,
    open_connection,
)

EXPECTED_COLUMNS = [
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

EXPECTED_TABLE_MINIMUMS = {
    "EQKT": 500,
    "EQUI": 500,
    "EQUZ": 500,
    "HRP1000": 50,
    "HRP1001": 500,
    "IFLOT": 500,
    "ILOA": 500,
    "ISDFPS_FORCE": 50,
    "JEST": 1000,
    "JSTO": 500,
    "MARA": 500,
    "TJ02T": 500,
    "TJ30T": 500,
    "ZDFPS_DODAC": 500,
}


@pytest.mark.sqlserver_integration
def test_sap_emulator_migrations_and_reporting_contract():
    connection_string = os.getenv("SAP_EMULATOR_TEST_CONNECTIONSTRING", "")
    if not connection_string:
        pytest.skip("SAP_EMULATOR_TEST_CONNECTIONSTRING is not configured")

    apply_migrations(connection_string, migration_files())

    connection = open_connection(connection_string)
    try:
        cursor = connection.cursor()
        columns = [
            row[0]
            for row in cursor.execute(
                """
SELECT [COLUMN_NAME]
FROM [INFORMATION_SCHEMA].[COLUMNS]
WHERE [TABLE_SCHEMA] = 'reporting' AND [TABLE_NAME] = 'FORCE_EQUIPMENT'
ORDER BY [ORDINAL_POSITION]
"""
            )
        ]
        rows = [
            tuple(row)
            for row in cursor.execute(
                """
SELECT [FORCE_ID], [FE_SHORT], [EQUNR], [EQKTX], [DODAC], [TPLNR], [FL_LEVEL],
       [SYS_STATUS], [USR_STATUS]
FROM [reporting].[FORCE_EQUIPMENT]
WHERE [EQUNR] IN (
    N'000000000000001001', N'000000000000001002', N'000000000000001003'
)
ORDER BY [FORCE_ID], [EQUNR]
"""
            )
        ]
        bulk_rows = cursor.execute(
            """
SELECT COUNT(*)
FROM [reporting].[FORCE_EQUIPMENT]
WHERE [FORCE_ID] BETWEEN '00200001' AND '00200500'
"""
        ).fetchval()
        unit_distribution = tuple(
            cursor.execute(
                """
WITH [UNIT_COUNTS] AS (
    SELECT [FORCE_ID], COUNT(*) AS [EQUIPMENT_COUNT]
    FROM [reporting].[FORCE_EQUIPMENT]
    WHERE [FORCE_ID] BETWEEN '00200001' AND '00200050'
    GROUP BY [FORCE_ID]
)
SELECT COUNT(*), MIN([EQUIPMENT_COUNT]), MAX([EQUIPMENT_COUNT]),
       COUNT(DISTINCT [EQUIPMENT_COUNT]), STDEV(CONVERT(float, [EQUIPMENT_COUNT]))
FROM [UNIT_COUNTS]
"""
            ).fetchone()
        )
        populated_table_counts = {
            row[0]: row[1]
            for row in cursor.execute(
                """
SELECT [table].[name], SUM([partition].[rows])
FROM [sys].[tables] AS [table]
INNER JOIN [sys].[schemas] AS [schema]
    ON [schema].[schema_id] = [table].[schema_id]
INNER JOIN [sys].[partitions] AS [partition]
    ON [partition].[object_id] = [table].[object_id]
   AND [partition].[index_id] IN (0, 1)
WHERE [schema].[name] = N'sap'
GROUP BY [table].[name]
"""
            )
        }
        ddic_fields = cursor.execute(
            "SELECT COUNT(*) FROM [emulator].[DDIC_FIELD]"
        ).fetchval()
        excluded_rows = cursor.execute(
            """
SELECT COUNT(*)
FROM [reporting].[FORCE_EQUIPMENT]
WHERE [EQUNR] IN ('000000000000001004', '000000000000001005')
"""
        ).fetchval()
    finally:
        connection.close()

    assert columns == EXPECTED_COLUMNS
    assert ddic_fields == 693
    assert excluded_rows == 0
    assert bulk_rows == 500
    assert unit_distribution[0] == 50
    assert unit_distribution[1] >= 2
    assert unit_distribution[2] <= 25
    assert unit_distribution[2] > unit_distribution[1]
    assert unit_distribution[3] >= 8
    assert unit_distribution[4] >= 2.5
    assert EXPECTED_TABLE_MINIMUMS.keys() <= populated_table_counts.keys()
    assert all(
        populated_table_counts[table] >= minimum
        for table, minimum in EXPECTED_TABLE_MINIMUMS.items()
    )
    assert rows == [
        (
            "00001000",
            "1-66 AR",
            "000000000000001001",
            "M1A2 SEPv3 Abrams",
            "2350A001",
            "FORT-CAVAZOS-MP-12",
            2,
            "Installed",
            "Fully Mission Capable",
        ),
        (
            "00001000",
            "1-66 AR",
            "000000000000001002",
            "AN/VRC-114 Mounted Radio",
            "5820D001",
            "FORT-CAVAZOS-SIG-01",
            2,
            "Available",
            "PMCS Scheduled",
        ),
        (
            "00001100",
            "4-10 CAV",
            "000000000000001003",
            "MEP-805B Generator Set",
            None,
            None,
            None,
            "Installed",
            "",
        ),
    ]