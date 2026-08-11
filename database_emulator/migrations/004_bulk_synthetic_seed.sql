SET XACT_ABORT ON;
GO

BEGIN TRANSACTION;

DECLARE @client char(3) = '900';
DECLARE @bulk_count int = 500;
DECLARE @unit_count int = 50;
DECLARE @unit_mean float = 10.0;
DECLARE @unit_sigma float = 4.0;

CREATE TABLE [#BULK_ROWS] (
    [ROW_ID] int NOT NULL PRIMARY KEY,
    [FORCE_ID] nvarchar(32) COLLATE DATABASE_DEFAULT NOT NULL,
    [OBJID] char(8) COLLATE DATABASE_DEFAULT NOT NULL,
    [EQUNR] nvarchar(18) COLLATE DATABASE_DEFAULT NOT NULL,
    [EQUNR_EXTERNAL] nvarchar(45) COLLATE DATABASE_DEFAULT NOT NULL,
    [MATNR] nvarchar(40) COLLATE DATABASE_DEFAULT NOT NULL,
    [ILOAN] nvarchar(12) COLLATE DATABASE_DEFAULT NOT NULL,
    [TPLNR] nvarchar(30) COLLATE DATABASE_DEFAULT NOT NULL,
    [TPLMA] nvarchar(30) COLLATE DATABASE_DEFAULT NULL,
    [OBJNR] nvarchar(22) COLLATE DATABASE_DEFAULT NOT NULL,
    [SYSTEM_STATUS] nvarchar(5) COLLATE DATABASE_DEFAULT NOT NULL,
    [USER_STATUS] nvarchar(5) COLLATE DATABASE_DEFAULT NOT NULL,
    [UNIT_SHORT] nvarchar(12) COLLATE DATABASE_DEFAULT NOT NULL,
    [UNIT_NAME] nvarchar(40) COLLATE DATABASE_DEFAULT NOT NULL,
    [INSTALLATION] nvarchar(20) COLLATE DATABASE_DEFAULT NOT NULL,
    [EQUIPMENT_NAME] nvarchar(40) COLLATE DATABASE_DEFAULT NOT NULL,
    [EQTYP] nvarchar(1) COLLATE DATABASE_DEFAULT NOT NULL,
    [MATERIAL_GROUP] nvarchar(9) COLLATE DATABASE_DEFAULT NOT NULL,
    [SUPPLY_CLASS] nvarchar(18) COLLATE DATABASE_DEFAULT NOT NULL,
    [DODAC] nvarchar(10) COLLATE DATABASE_DEFAULT NOT NULL,
    [SYSTEM_STATUS_TEXT] nvarchar(30) COLLATE DATABASE_DEFAULT NOT NULL,
    [USER_STATUS_TEXT] nvarchar(30) COLLATE DATABASE_DEFAULT NOT NULL
);

;WITH [DIGITS] AS (
    SELECT [DIGIT]
    FROM (VALUES (0), (1), (2), (3), (4), (5), (6), (7), (8), (9)) AS [values]([DIGIT])
),
[NUMBERS] AS (
    SELECT TOP (@bulk_count)
        ROW_NUMBER() OVER (ORDER BY [hundreds].[DIGIT], [tens].[DIGIT], [ones].[DIGIT]) AS [ROW_ID]
    FROM [DIGITS] AS [hundreds]
    CROSS JOIN [DIGITS] AS [tens]
    CROSS JOIN [DIGITS] AS [ones]
),
[UNIT_RANDOM] AS (
    SELECT
        [ROW_ID] AS [UNIT_ID],
        CONVERT(float, (ABS(CONVERT(bigint, CHECKSUM(HASHBYTES(
            'SHA2_256', CONCAT(N'unit-u1-', [ROW_ID]))))) % 999999) + 1)
            / 1000000.0 AS [UNIT_U1],
        CONVERT(float, (ABS(CONVERT(bigint, CHECKSUM(HASHBYTES(
            'SHA2_256', CONCAT(N'unit-u2-', [ROW_ID]))))) % 999999) + 1)
            / 1000000.0 AS [UNIT_U2]
    FROM [NUMBERS]
    WHERE [ROW_ID] <= @unit_count
),
[GAUSSIAN_SCORES] AS (
    SELECT
        [unit_random].*,
        SQRT(-2.0 * LOG([UNIT_U1])) * COS(2.0 * PI() * [UNIT_U2]) AS [UNIT_Z]
    FROM [UNIT_RANDOM] AS [unit_random]
),
[UNIT_WEIGHTS] AS (
    SELECT
        [gaussian_scores].*,
        CASE WHEN @unit_mean + @unit_sigma * [UNIT_Z] < 2.0 THEN 2.0
            WHEN @unit_mean + @unit_sigma * [UNIT_Z] > 20.0 THEN 20.0
            ELSE @unit_mean + @unit_sigma * [UNIT_Z] END AS [RAW_WEIGHT]
    FROM [GAUSSIAN_SCORES] AS [gaussian_scores]
),
[UNIT_QUOTAS] AS (
    SELECT
        [unit_weights].*,
        @bulk_count * [RAW_WEIGHT] / SUM([RAW_WEIGHT]) OVER () AS [RAW_QUOTA]
    FROM [UNIT_WEIGHTS] AS [unit_weights]
),
[UNIT_BASE_COUNTS] AS (
    SELECT
        [unit_quotas].*,
        CONVERT(int, FLOOR([RAW_QUOTA])) AS [BASE_COUNT],
        [RAW_QUOTA] - FLOOR([RAW_QUOTA]) AS [QUOTA_FRACTION]
    FROM [UNIT_QUOTAS] AS [unit_quotas]
),
[UNIT_RANKS] AS (
    SELECT
        [unit_base_counts].*,
        @bulk_count - SUM([BASE_COUNT]) OVER () AS [EXTRA_COUNT],
        ROW_NUMBER() OVER (ORDER BY [QUOTA_FRACTION] DESC, [UNIT_ID]) AS [EXTRA_RANK]
    FROM [UNIT_BASE_COUNTS] AS [unit_base_counts]
),
[UNIT_COUNTS] AS (
    SELECT
        [UNIT_ID],
        [BASE_COUNT] + CASE WHEN [EXTRA_RANK] <= [EXTRA_COUNT] THEN 1 ELSE 0 END
            AS [HOLDING_COUNT]
    FROM [UNIT_RANKS]
),
[UNIT_RANGES] AS (
    SELECT
        [UNIT_ID],
        COALESCE(SUM([HOLDING_COUNT]) OVER (
            ORDER BY [UNIT_ID] ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ), 0) + 1 AS [FIRST_ROW_ID],
        SUM([HOLDING_COUNT]) OVER (ORDER BY [UNIT_ID] ROWS UNBOUNDED PRECEDING)
            AS [LAST_ROW_ID]
    FROM [UNIT_COUNTS]
),
[ROW_VARIETY] AS (
    SELECT
        [ROW_ID],
        RIGHT(REPLICATE(N'0', 6) + CONVERT(nvarchar(6), [ROW_ID]), 6) AS [PADDED_ROW_ID],
        (ABS(CONVERT(bigint, CHECKSUM(HASHBYTES(
            'SHA2_256', CONCAT(N'equipment-', [ROW_ID]))))) % 20) + 1 AS [EQUIPMENT_ID],
        ABS(CONVERT(bigint, CHECKSUM(HASHBYTES(
            'SHA2_256', CONCAT(N'readiness-', [ROW_ID]))))) % 100 AS [READINESS_ROLL]
    FROM [NUMBERS]
),
[UNIT_ASSIGNMENTS] AS (
    SELECT [row_variety].*, [unit_ranges].[UNIT_ID]
    FROM [ROW_VARIETY] AS [row_variety]
    INNER JOIN [UNIT_RANGES] AS [unit_ranges]
        ON [row_variety].[ROW_ID] BETWEEN [unit_ranges].[FIRST_ROW_ID]
            AND [unit_ranges].[LAST_ROW_ID]
),
[IDENTIFIERS] AS (
    SELECT
        [assignments].*,
        RIGHT(REPLICATE(N'0', 2) + CONVERT(nvarchar(2), (([UNIT_ID] - 1) / 5) + 1), 2) AS [TASK_FORCE_ID],
        RIGHT(REPLICATE(N'0', 8) + CONVERT(nvarchar(8), 200000 + [UNIT_ID]), 8) AS [OBJID],
        RIGHT(REPLICATE(N'0', 18) + CONVERT(nvarchar(18), 300000 + [ROW_ID]), 18) AS [EQUNR],
        (([UNIT_ID] - 1) % 10) + 1 AS [INSTALLATION_ID],
        ROW_NUMBER() OVER (
            PARTITION BY (([UNIT_ID] - 1) % 10) + 1 ORDER BY [ROW_ID]
        ) AS [INSTALLATION_ROW_NUMBER],
        (([UNIT_ID] - 1) % 5) + 1 AS [COMPANY_ID],
        (([UNIT_ID] - 1) % 10) + 1 AS [UNIT_TYPE_ID],
        CASE WHEN [READINESS_ROLL] < 55 THEN 1
            WHEN [READINESS_ROLL] < 70 THEN 2
            WHEN [READINESS_ROLL] < 82 THEN 3
            WHEN [READINESS_ROLL] < 92 THEN 4
            ELSE 5 END AS [READINESS_ID]
    FROM [UNIT_ASSIGNMENTS] AS [assignments]
),
[ARMY_ROWS] AS (
    SELECT
        [identifiers].*,
        CASE [INSTALLATION_ID]
            WHEN 1 THEN N'FORT-BRAGG'
            WHEN 2 THEN N'FORT-CAVAZOS'
            WHEN 3 THEN N'FORT-CAMPBELL'
            WHEN 4 THEN N'FORT-STEWART'
            WHEN 5 THEN N'FORT-BLISS'
            WHEN 6 THEN N'JBLM'
            WHEN 7 THEN N'FORT-CARSON'
            WHEN 8 THEN N'FORT-RILEY'
            WHEN 9 THEN N'FORT-DRUM'
            ELSE N'FORT-JOHNSON'
        END AS [INSTALLATION],
        CASE [UNIT_TYPE_ID]
            WHEN 1 THEN N'1-66AR'
            WHEN 2 THEN N'1-22IN'
            WHEN 3 THEN N'4-10CAV'
            WHEN 4 THEN N'2-12CAV'
            WHEN 5 THEN N'101BSB'
            WHEN 6 THEN N'115BSB'
            WHEN 7 THEN N'1-14FA'
            WHEN 8 THEN N'8ENBN'
            WHEN 9 THEN N'51ESB'
            ELSE N'39ENBN'
        END AS [UNIT_CODE],
        CASE [EQUIPMENT_ID]
            WHEN 1 THEN N'M1A2 SEPv3 Abrams'
            WHEN 2 THEN N'M2A4 Bradley IFV'
            WHEN 3 THEN N'M3A4 Bradley CFV'
            WHEN 4 THEN N'M1126 Stryker ICV'
            WHEN 5 THEN N'M1280 JLTV General Purpose'
            WHEN 6 THEN N'M1165A1 HMMWV'
            WHEN 7 THEN N'M109A7 Paladin'
            WHEN 8 THEN N'M270A2 MLRS'
            WHEN 9 THEN N'M142 HIMARS'
            WHEN 10 THEN N'M88A2 Hercules'
            WHEN 11 THEN N'M1078A1P2 LMTV'
            WHEN 12 THEN N'M1083A1P2 MTV'
            WHEN 13 THEN N'M978A4 HEMTT Tanker'
            WHEN 14 THEN N'M1120A4 HEMTT LHS'
            WHEN 15 THEN N'M1075A1 PLS'
            WHEN 16 THEN N'M1150 Assault Breacher Vehicle'
            WHEN 17 THEN N'M9 Armored Combat Earthmover'
            WHEN 18 THEN N'M1200 Armored Knight'
            WHEN 19 THEN N'AN/VRC-114 Mounted Radio'
            ELSE N'MEP-805B Generator Set'
        END AS [EQUIPMENT_NAME]
    FROM [IDENTIFIERS] AS [identifiers]
)
INSERT INTO [#BULK_ROWS]
    ([ROW_ID], [FORCE_ID], [OBJID], [EQUNR], [EQUNR_EXTERNAL], [MATNR], [ILOAN],
     [TPLNR], [TPLMA], [OBJNR], [SYSTEM_STATUS], [USER_STATUS], [UNIT_SHORT],
     [UNIT_NAME], [INSTALLATION], [EQUIPMENT_NAME], [EQTYP], [MATERIAL_GROUP],
     [SUPPLY_CLASS], [DODAC], [SYSTEM_STATUS_TEXT], [USER_STATUS_TEXT])
SELECT
    [ROW_ID],
    N'FORCE-SYN-' + RIGHT(REPLICATE(N'0', 6) + CONVERT(nvarchar(6), [UNIT_ID]), 6),
    [OBJID],
    [EQUNR],
    CONVERT(nvarchar(45), 300000 + [ROW_ID]),
    N'MAT-ARMY-' + RIGHT(REPLICATE(N'0', 2) + CONVERT(nvarchar(2), [EQUIPMENT_ID]), 2)
        + N'-' + [PADDED_ROW_ID],
    RIGHT(REPLICATE(N'0', 12) + CONVERT(nvarchar(12), 400000 + [ROW_ID]), 12),
    CASE WHEN [INSTALLATION_ROW_NUMBER] = 1 THEN [INSTALLATION]
        ELSE [INSTALLATION] + N'-MP-' + [PADDED_ROW_ID] END,
    CASE WHEN [INSTALLATION_ROW_NUMBER] = 1 THEN NULL ELSE [INSTALLATION] END,
    N'IE' + [EQUNR],
    N'I' + CONVERT(nvarchar(4), 1000 + [ROW_ID]),
    N'E' + CONVERT(nvarchar(4), 1000 + [ROW_ID]),
    CASE [COMPANY_ID] WHEN 1 THEN N'HQ' WHEN 2 THEN N'A' WHEN 3 THEN N'B'
        WHEN 4 THEN N'C' ELSE N'D' END + [TASK_FORCE_ID] + N'/' + [UNIT_CODE],
    CASE [COMPANY_ID] WHEN 1 THEN N'HHC' WHEN 2 THEN N'Alpha Company'
        WHEN 3 THEN N'Bravo Company' WHEN 4 THEN N'Charlie Company'
        ELSE N'Delta Company' END + N', TF ' + [TASK_FORCE_ID] + N', ' + [UNIT_CODE],
    [INSTALLATION],
    [EQUIPMENT_NAME],
    CASE WHEN [EQUIPMENT_ID] = 19 THEN N'C' WHEN [EQUIPMENT_ID] = 20 THEN N'P' ELSE N'V' END,
    CASE WHEN [EQUIPMENT_ID] IN (1, 2, 3, 4, 10, 16, 17, 18) THEN N'COMBATVEH'
        WHEN [EQUIPMENT_ID] IN (7, 8, 9) THEN N'ARTILLERY'
        WHEN [EQUIPMENT_ID] = 19 THEN N'SIGNAL'
        WHEN [EQUIPMENT_ID] = 20 THEN N'POWER'
        ELSE N'TACTVEH' END,
    N'CLASS-VII',
    CASE WHEN [EQUIPMENT_ID] IN (1, 2, 3, 4, 10, 16, 17, 18) THEN N'2350A'
        WHEN [EQUIPMENT_ID] IN (5, 6, 11, 12, 13, 14, 15) THEN N'2320B'
        WHEN [EQUIPMENT_ID] IN (7, 8, 9) THEN N'2350C'
        WHEN [EQUIPMENT_ID] = 19 THEN N'5820D'
        ELSE N'6115E' END
        + RIGHT(REPLICATE(N'0', 3) + CONVERT(nvarchar(3), [EQUIPMENT_ID]), 3),
    CASE [READINESS_ID] WHEN 1 THEN N'Installed' WHEN 2 THEN N'Available'
        WHEN 3 THEN N'In Maintenance' WHEN 4 THEN N'Inspection Due'
        ELSE N'Awaiting Parts' END,
    CASE [READINESS_ID] WHEN 1 THEN N'Fully Mission Capable'
        WHEN 2 THEN N'Ready for Issue'
        WHEN 3 THEN N'Non-Mission Capable Maint'
        WHEN 4 THEN N'Partially Mission Capable'
        ELSE N'Non-Mission Capable Supply' END
FROM [ARMY_ROWS];

DELETE [status]
FROM [sap].[JEST] AS [status]
INNER JOIN [#BULK_ROWS] AS [bulk] ON [bulk].[OBJNR] = [status].[OBJNR]
WHERE [status].[MANDT] = @client;

DELETE [profile]
FROM [sap].[JSTO] AS [profile]
INNER JOIN [#BULK_ROWS] AS [bulk] ON [bulk].[OBJNR] = [profile].[OBJNR]
WHERE [profile].[MANDT] = @client;

DELETE [dodac]
FROM [sap].[ZDFPS_DODAC] AS [dodac]
INNER JOIN [#BULK_ROWS] AS [bulk] ON [bulk].[MATNR] = [dodac].[MATNR]
WHERE [dodac].[MANDT] = @client;

DELETE [text]
FROM [sap].[EQKT] AS [text]
INNER JOIN [#BULK_ROWS] AS [bulk] ON [bulk].[EQUNR] = [text].[EQUNR]
WHERE [text].[MANDT] = @client;

DELETE [usage]
FROM [sap].[EQUZ] AS [usage]
INNER JOIN [#BULK_ROWS] AS [bulk] ON [bulk].[EQUNR] = [usage].[EQUNR]
WHERE [usage].[MANDT] = @client;

DELETE [assignment]
FROM [sap].[ILOA] AS [assignment]
INNER JOIN [#BULK_ROWS] AS [bulk] ON [bulk].[ILOAN] = [assignment].[ILOAN]
WHERE [assignment].[MANDT] = @client;

DELETE [location]
FROM [sap].[IFLOT] AS [location]
INNER JOIN [#BULK_ROWS] AS [bulk] ON [bulk].[TPLNR] = [location].[TPLNR]
WHERE [location].[MANDT] = @client;

DELETE [equipment]
FROM [sap].[EQUI] AS [equipment]
INNER JOIN [#BULK_ROWS] AS [bulk] ON [bulk].[EQUNR] = [equipment].[EQUNR]
WHERE [equipment].[MANDT] = @client;

DELETE [material]
FROM [sap].[MARA] AS [material]
INNER JOIN [#BULK_ROWS] AS [bulk] ON [bulk].[MATNR] = [material].[MATNR]
WHERE [material].[MANDT] = @client;

DELETE FROM [sap].[HRP1001]
WHERE [MANDT] = @client AND [OBJID] BETWEEN '00200001' AND '00200500';

DELETE FROM [sap].[HRP1000]
WHERE [MANDT] = @client AND [OBJID] BETWEEN '00200001' AND '00200500';

DELETE FROM [sap].[ISDFPS_FORCE]
WHERE [MANDT] = @client AND [FORCE_ID] LIKE N'FORCE-SYN-0%';

DELETE [status_text]
FROM [sap].[TJ30T] AS [status_text]
INNER JOIN [#BULK_ROWS] AS [bulk] ON [bulk].[USER_STATUS] = [status_text].[ESTAT]
WHERE [status_text].[MANDT] = @client AND [status_text].[STSMA] = N'EQUIP';

DELETE [status_text]
FROM [sap].[TJ02T] AS [status_text]
INNER JOIN [#BULK_ROWS] AS [bulk] ON [bulk].[SYSTEM_STATUS] = [status_text].[ISTAT]
WHERE [status_text].[SPRAS] = 'E';

INSERT INTO [sap].[ISDFPS_FORCE]
    ([MANDT], [FORCE_ID], [FORCE_CNT], [PLVAR], [OTYPE], [OBJID], [WERKS_S],
     [MATSTAT], [READINESS_MAT], [CREADAT], [CREABY])
SELECT
    @client, [FORCE_ID], '000001', N'01', N'O', [OBJID], N'A100',
    N'A', CASE MIN([ROW_ID]) % 5 WHEN 0 THEN '050' WHEN 1 THEN '090'
        WHEN 2 THEN '075' WHEN 3 THEN '040' ELSE '060' END,
    '20200101', N'EMULATOR'
FROM [#BULK_ROWS]
GROUP BY [FORCE_ID], [OBJID];

INSERT INTO [sap].[HRP1000]
    ([MANDT], [PLVAR], [OTYPE], [OBJID], [ISTAT], [BEGDA], [ENDDA], [LANGU],
     [SEQNR], [SHORT], [STEXT])
SELECT
    @client, N'01', N'O', [OBJID], N'1', '20200101', '99991231', 'E', '000',
    [UNIT_SHORT], [UNIT_NAME]
FROM [#BULK_ROWS]
GROUP BY [OBJID], [UNIT_SHORT], [UNIT_NAME];

INSERT INTO [sap].[HRP1001]
    ([MANDT], [OTYPE], [OBJID], [PLVAR], [RSIGN], [RELAT], [ISTAT], [PRIOX],
     [BEGDA], [ENDDA], [VARYF], [SEQNR], [SCLAS], [SOBID])
SELECT
    @client, N'O', [OBJID], N'01', N'B', N'003', N'1', N'00',
    '20200101', '99991231', N'',
    RIGHT(REPLICATE(N'0', 3) + CONVERT(nvarchar(3),
        ROW_NUMBER() OVER (PARTITION BY [OBJID] ORDER BY [ROW_ID])), 3),
    N'EQ', [EQUNR_EXTERNAL]
FROM [#BULK_ROWS];

INSERT INTO [sap].[EQUI]
    ([MANDT], [EQUNR], [ERDAT], [ERNAM], [EQTYP], [HERST], [TYPBZ], [BAUJJ],
     [OBJNR], [MATNR], [SERNR], [WERK])
SELECT
    @client, [EQUNR], '20200101', N'EMULATOR', [EQTYP],
    N'Synthetic OEM', LEFT([EQUIPMENT_NAME], 20), N'2026', [OBJNR], [MATNR],
    N'SYN-26-' + RIGHT(REPLICATE(N'0', 6) + CONVERT(nvarchar(6), [ROW_ID]), 6),
    N'A100'
FROM [#BULK_ROWS];

INSERT INTO [sap].[EQUZ]
    ([MANDT], [EQUNR], [DATBI], [EQLFN], [DATAB], [HEQUI], [ILOAN], [IWERK])
SELECT
    @client, [EQUNR], '99991231', '001', '20200101',
    CASE
        WHEN [ROW_ID] > 1 AND [ROW_ID] % 5 = 0 AND EXISTS (
            SELECT 1
            FROM [#BULK_ROWS] AS [parent]
            WHERE [parent].[ROW_ID] = [bulk].[ROW_ID] - 1
              AND [parent].[OBJID] = [bulk].[OBJID]
        )
            THEN RIGHT(REPLICATE(N'0', 18) + CONVERT(nvarchar(18), 300000 + [ROW_ID] - 1), 18)
        ELSE N''
    END,
    [ILOAN], N'A100'
FROM [#BULK_ROWS] AS [bulk];

INSERT INTO [sap].[ILOA]
    ([MANDT], [ILOAN], [TPLNR], [SWERK], [STORT], [BEBER], [KOSTL])
SELECT
    @client, [ILOAN], [TPLNR], N'A100',
    N'MP-' + RIGHT(REPLICATE(N'0', 6) + CONVERT(nvarchar(6), [ROW_ID]), 6),
    N'OPS',
    N'CC-' + RIGHT(REPLICATE(N'0', 6) + CONVERT(nvarchar(6), [ROW_ID]), 6)
FROM [#BULK_ROWS];

INSERT INTO [sap].[IFLOT]
    ([MANDT], [TPLNR], [MLANG], [TPLKZ], [FLTYP], [TPLMA], [DATAB], [IWERK], [OBJNR])
SELECT
    @client, [TPLNR], 'E', N'ARMY', N'F', [TPLMA], '20200101', N'A100',
    N'IF' + RIGHT(REPLICATE(N'0', 8) + CONVERT(nvarchar(8), 500000 + [ROW_ID]), 8)
FROM [#BULK_ROWS];

INSERT INTO [sap].[EQKT]
    ([MANDT], [EQUNR], [SPRAS], [EQKTX], [TXASP])
SELECT
    @client, [EQUNR], 'E', [EQUIPMENT_NAME], N'X'
FROM [#BULK_ROWS];

INSERT INTO [sap].[MARA]
    ([MANDT], [MATNR], [ERSDA], [ERNAM], [MTART], [MATKL], [EXTWG])
SELECT
    @client, [MATNR], '20200101', N'EMULATOR',
    CASE WHEN [EQTYP] = N'V' THEN N'FERT' ELSE N'HAWA' END,
    [MATERIAL_GROUP], [SUPPLY_CLASS]
FROM [#BULK_ROWS];

INSERT INTO [sap].[ZDFPS_DODAC] ([MANDT], [MATNR], [DODAC])
SELECT
    @client, [MATNR], [DODAC]
FROM [#BULK_ROWS];

INSERT INTO [sap].[JSTO] ([MANDT], [OBJNR], [STSMA])
SELECT @client, [OBJNR], N'EQUIP'
FROM [#BULK_ROWS];

INSERT INTO [sap].[TJ02T] ([ISTAT], [SPRAS], [TXT04], [TXT30])
SELECT
    [SYSTEM_STATUS], 'E',
    CASE [ROW_ID] % 5 WHEN 0 THEN N'AWPT' WHEN 1 THEN N'INST'
        WHEN 2 THEN N'AVLB' WHEN 3 THEN N'MNT' ELSE N'INSP' END,
    [SYSTEM_STATUS_TEXT]
FROM [#BULK_ROWS];

INSERT INTO [sap].[TJ30T]
    ([MANDT], [STSMA], [ESTAT], [SPRAS], [TXT04], [TXT30], [LTEXT])
SELECT
    @client, N'EQUIP', [USER_STATUS], 'E',
    CASE [ROW_ID] % 5 WHEN 0 THEN N'NMCS' WHEN 1 THEN N'FMC'
        WHEN 2 THEN N'RFI' WHEN 3 THEN N'NMCM' ELSE N'PMC' END,
    [USER_STATUS_TEXT], N''
FROM [#BULK_ROWS];

INSERT INTO [sap].[JEST] ([MANDT], [OBJNR], [STAT], [INACT], [CHGNR])
SELECT @client, [OBJNR], [SYSTEM_STATUS], N'', '001'
FROM [#BULK_ROWS]
UNION ALL
SELECT @client, [OBJNR], [USER_STATUS], N'', '002'
FROM [#BULK_ROWS];

DROP TABLE [#BULK_ROWS];

COMMIT TRANSACTION;
GO

IF (SELECT COUNT(*) FROM [reporting].[FORCE_EQUIPMENT]
    WHERE [FORCE_ID] BETWEEN '00200001' AND '00200500') <> 500
    THROW 51001, 'Bulk fixture did not produce 500 current reporting rows.', 1;

IF (SELECT COUNT(*) FROM [sap].[ISDFPS_FORCE] WHERE [MANDT] = '900' AND [FORCE_ID] LIKE N'FORCE-SYN-%') <> 52
    OR (SELECT COUNT(*) FROM [sap].[HRP1000] WHERE [MANDT] = '900' AND [OBJID] BETWEEN '00200001' AND '00200500') <> 50
    OR (SELECT COUNT(*) FROM [sap].[HRP1001] WHERE [MANDT] = '900' AND [OBJID] BETWEEN '00200001' AND '00200500') <> 500
    OR (SELECT COUNT(*) FROM [sap].[EQUI] WHERE [MANDT] = '900' AND [EQUNR] BETWEEN N'000000000000300001' AND N'000000000000300500') <> 500
    OR (SELECT COUNT(*) FROM [sap].[EQUZ] WHERE [MANDT] = '900' AND [EQUNR] BETWEEN N'000000000000300001' AND N'000000000000300500') <> 500
    OR (SELECT COUNT(*) FROM [sap].[EQKT] WHERE [MANDT] = '900' AND [EQUNR] BETWEEN N'000000000000300001' AND N'000000000000300500') <> 500
    OR (SELECT COUNT(*) FROM [sap].[MARA] WHERE [MANDT] = '900' AND [MATNR] LIKE N'MAT-ARMY-%') <> 500
    OR (SELECT COUNT(*) FROM [sap].[ILOA] WHERE [MANDT] = '900' AND [ILOAN] BETWEEN N'000000400001' AND N'000000400500') <> 500
    OR (SELECT COUNT(*) FROM [sap].[IFLOT] WHERE [MANDT] = '900' AND ([TPLNR] LIKE N'FORT-%' OR [TPLNR] LIKE N'JBLM%')) < 500
    OR (SELECT COUNT(*) FROM [sap].[JEST] WHERE [MANDT] = '900' AND [OBJNR] BETWEEN N'IE000000000000300001' AND N'IE000000000000300500') <> 1000
    OR (SELECT COUNT(*) FROM [sap].[TJ02T] WHERE [SPRAS] = 'E' AND [ISTAT] BETWEEN N'I1001' AND N'I1500') <> 500
    OR (SELECT COUNT(*) FROM [sap].[TJ30T] WHERE [MANDT] = '900' AND [STSMA] = N'EQUIP' AND [ESTAT] BETWEEN N'E1001' AND N'E1500') <> 500
    OR (SELECT COUNT(*) FROM [sap].[JSTO] WHERE [MANDT] = '900' AND [OBJNR] BETWEEN N'IE000000000000300001' AND N'IE000000000000300500') <> 500
    OR (SELECT COUNT(*) FROM [sap].[ZDFPS_DODAC] WHERE [MANDT] = '900' AND [MATNR] LIKE N'MAT-ARMY-%') <> 500
    THROW 51002, 'Bulk fixture did not populate every SAP emulator table.', 1;

IF (SELECT COUNT(*) FROM (
        SELECT [FORCE_ID]
        FROM [reporting].[FORCE_EQUIPMENT]
        WHERE [FORCE_ID] BETWEEN '00200001' AND '00200050'
        GROUP BY [FORCE_ID]
    ) AS [units]) <> 50
    OR (SELECT COUNT(DISTINCT [distribution].[EQUIPMENT_COUNT]) FROM (
        SELECT [FORCE_ID], COUNT(*) AS [EQUIPMENT_COUNT]
        FROM [reporting].[FORCE_EQUIPMENT]
        WHERE [FORCE_ID] BETWEEN '00200001' AND '00200050'
        GROUP BY [FORCE_ID]
    ) AS [distribution]) < 8
    OR (SELECT STDEV(CONVERT(float, [distribution].[EQUIPMENT_COUNT])) FROM (
        SELECT [FORCE_ID], COUNT(*) AS [EQUIPMENT_COUNT]
        FROM [reporting].[FORCE_EQUIPMENT]
        WHERE [FORCE_ID] BETWEEN '00200001' AND '00200050'
        GROUP BY [FORCE_ID]
    ) AS [distribution]) < 2.5
    OR (SELECT MIN([distribution].[EQUIPMENT_COUNT]) FROM (
        SELECT [FORCE_ID], COUNT(*) AS [EQUIPMENT_COUNT]
        FROM [reporting].[FORCE_EQUIPMENT]
        WHERE [FORCE_ID] BETWEEN '00200001' AND '00200050'
        GROUP BY [FORCE_ID]
    ) AS [distribution]) < 2
    OR (SELECT MAX([distribution].[EQUIPMENT_COUNT]) FROM (
        SELECT [FORCE_ID], COUNT(*) AS [EQUIPMENT_COUNT]
        FROM [reporting].[FORCE_EQUIPMENT]
        WHERE [FORCE_ID] BETWEEN '00200001' AND '00200050'
        GROUP BY [FORCE_ID]
    ) AS [distribution]) > 25
    THROW 51003, 'Bulk fixture did not produce varied Gaussian unit holdings.', 1;
GO