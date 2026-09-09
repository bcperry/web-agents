SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET XACT_ABORT ON;

IF OBJECT_ID(N'[sap].[FM_FUND_MASTER]', N'U') IS NULL
BEGIN
    CREATE TABLE [sap].[FM_FUND_MASTER] (
        [MANDT] char(3) NOT NULL,
        [FUND_CODE] nvarchar(10) NOT NULL,
        [APPROPRIATION] nvarchar(80) NOT NULL,
        [FUNDING_AUTHORITY] nvarchar(20) NOT NULL,
        CONSTRAINT [PK_FM_FUND_MASTER] PRIMARY KEY ([MANDT], [FUND_CODE])
    );
END;

IF COL_LENGTH(N'[sap].[FM_FUND_MASTER]', N'APPROPRIATION') < 160
    ALTER TABLE [sap].[FM_FUND_MASTER]
        ALTER COLUMN [APPROPRIATION] nvarchar(80) NOT NULL;

IF OBJECT_ID(N'[sap].[FM_FUNDS_CENTER_MASTER]', N'U') IS NULL
BEGIN
    CREATE TABLE [sap].[FM_FUNDS_CENTER_MASTER] (
        [MANDT] char(3) NOT NULL,
        [FUNDS_CENTER] nvarchar(16) NOT NULL,
        [FUNDS_CENTER_NAME] nvarchar(80) NOT NULL,
        [COMMAND_NAME] nvarchar(40) NOT NULL,
        CONSTRAINT [PK_FM_FUNDS_CENTER_MASTER] PRIMARY KEY ([MANDT], [FUNDS_CENTER])
    );
END;

IF OBJECT_ID(N'[sap].[FM_COMMITMENT_ITEM_MASTER]', N'U') IS NULL
BEGIN
    CREATE TABLE [sap].[FM_COMMITMENT_ITEM_MASTER] (
        [MANDT] char(3) NOT NULL,
        [COMMITMENT_ITEM] nvarchar(12) NOT NULL,
        [COMMITMENT_ITEM_NAME] nvarchar(80) NOT NULL,
        CONSTRAINT [PK_FM_COMMITMENT_ITEM_MASTER]
            PRIMARY KEY ([MANDT], [COMMITMENT_ITEM])
    );
END;

IF OBJECT_ID(N'[sap].[FM_BUDGET_LINE]', N'U') IS NULL
BEGIN
    CREATE TABLE [sap].[FM_BUDGET_LINE] (
        [MANDT] char(3) NOT NULL,
        [BUDGET_LINE_ID] nvarchar(16) NOT NULL,
        [FISCAL_YEAR] smallint NOT NULL,
        [FUND_CODE] nvarchar(10) NOT NULL,
        [FUNDS_CENTER] nvarchar(16) NOT NULL,
        [COMMITMENT_ITEM] nvarchar(12) NOT NULL,
        [PROGRAM_ELEMENT] nvarchar(16) NOT NULL,
        [BUDGET_AMOUNT] decimal(19, 2) NOT NULL,
        [VALID_FROM] date NOT NULL,
        [VALID_TO] date NOT NULL,
        CONSTRAINT [PK_FM_BUDGET_LINE] PRIMARY KEY ([MANDT], [BUDGET_LINE_ID]),
        CONSTRAINT [CK_FM_BUDGET_LINE_AMOUNT] CHECK ([BUDGET_AMOUNT] >= 0)
    );
END;

IF OBJECT_ID(N'[sap].[FM_POSTING]', N'U') IS NULL
BEGIN
    CREATE TABLE [sap].[FM_POSTING] (
        [MANDT] char(3) NOT NULL,
        [DOCUMENT_NUMBER] nvarchar(16) NOT NULL,
        [LINE_ITEM] smallint NOT NULL,
        [BUDGET_LINE_ID] nvarchar(16) NOT NULL,
        [POSTING_DATE] date NOT NULL,
        [FISCAL_PERIOD] tinyint NOT NULL,
        [VALUE_TYPE] nvarchar(16) NOT NULL,
        [AMOUNT] decimal(19, 2) NOT NULL,
        [REFERENCE_TEXT] nvarchar(80) NOT NULL,
        CONSTRAINT [PK_FM_POSTING]
            PRIMARY KEY ([MANDT], [DOCUMENT_NUMBER], [LINE_ITEM]),
        CONSTRAINT [CK_FM_POSTING_PERIOD] CHECK ([FISCAL_PERIOD] BETWEEN 1 AND 12),
        CONSTRAINT [CK_FM_POSTING_VALUE_TYPE]
            CHECK ([VALUE_TYPE] IN (N'COMMITMENT', N'OBLIGATION', N'EXPENDITURE')),
        CONSTRAINT [CK_FM_POSTING_AMOUNT] CHECK ([AMOUNT] >= 0)
    );
END;
GO

CREATE OR ALTER VIEW [reporting].[FINANCIAL_EXECUTION]
AS
WITH [POSTING_SUMMARY] AS (
    SELECT
        [posting].[MANDT],
        [posting].[BUDGET_LINE_ID],
        SUM(CASE WHEN [posting].[VALUE_TYPE] = N'COMMITMENT'
            THEN [posting].[AMOUNT] ELSE 0 END) AS [COMMITTED_AMOUNT],
        SUM(CASE WHEN [posting].[VALUE_TYPE] = N'OBLIGATION'
            THEN [posting].[AMOUNT] ELSE 0 END) AS [OBLIGATED_AMOUNT],
        SUM(CASE WHEN [posting].[VALUE_TYPE] = N'EXPENDITURE'
            THEN [posting].[AMOUNT] ELSE 0 END) AS [EXPENDED_AMOUNT],
        MAX([posting].[POSTING_DATE]) AS [LAST_POSTING_DATE]
    FROM [sap].[FM_POSTING] AS [posting]
    GROUP BY [posting].[MANDT], [posting].[BUDGET_LINE_ID]
),
[EXECUTION] AS (
    SELECT
        [budget].[BUDGET_AMOUNT],
        COALESCE([posting].[COMMITTED_AMOUNT], 0) AS [COMMITTED_AMOUNT],
        COALESCE([posting].[OBLIGATED_AMOUNT], 0) AS [OBLIGATED_AMOUNT],
        COALESCE([posting].[EXPENDED_AMOUNT], 0) AS [EXPENDED_AMOUNT],
        COALESCE([posting].[COMMITTED_AMOUNT], 0)
            + COALESCE([posting].[OBLIGATED_AMOUNT], 0)
            + COALESCE([posting].[EXPENDED_AMOUNT], 0) AS [CONSUMED_AMOUNT],
        [budget].[BUDGET_LINE_ID],
        [budget].[FISCAL_YEAR],
        [budget].[FUND_CODE],
        [budget].[FUNDS_CENTER],
        [budget].[COMMITMENT_ITEM],
        [budget].[PROGRAM_ELEMENT],
        [posting].[LAST_POSTING_DATE],
        [budget].[MANDT]
    FROM [sap].[FM_BUDGET_LINE] AS [budget]
    LEFT JOIN [POSTING_SUMMARY] AS [posting]
        ON [posting].[MANDT] = [budget].[MANDT]
       AND [posting].[BUDGET_LINE_ID] = [budget].[BUDGET_LINE_ID]
)
SELECT
    [execution].[FISCAL_YEAR] AS [FISCAL_YEAR],
    [execution].[BUDGET_LINE_ID] AS [BUDGET_LINE_ID],
    [execution].[FUND_CODE] AS [FUND_CODE],
    [fund].[APPROPRIATION] AS [APPROPRIATION],
    [fund].[FUNDING_AUTHORITY] AS [FUNDING_AUTHORITY],
    [execution].[FUNDS_CENTER] AS [FUNDS_CENTER],
    [center].[FUNDS_CENTER_NAME] AS [FUNDS_CENTER_NAME],
    [center].[COMMAND_NAME] AS [COMMAND_NAME],
    [execution].[COMMITMENT_ITEM] AS [COMMITMENT_ITEM],
    [item].[COMMITMENT_ITEM_NAME] AS [COMMITMENT_ITEM_NAME],
    [execution].[PROGRAM_ELEMENT] AS [PROGRAM_ELEMENT],
    [execution].[BUDGET_AMOUNT] AS [BUDGET_AMOUNT],
    [execution].[COMMITTED_AMOUNT] AS [COMMITTED_AMOUNT],
    [execution].[OBLIGATED_AMOUNT] AS [OBLIGATED_AMOUNT],
    [execution].[EXPENDED_AMOUNT] AS [EXPENDED_AMOUNT],
    [execution].[CONSUMED_AMOUNT] AS [CONSUMED_AMOUNT],
    [execution].[BUDGET_AMOUNT] - [execution].[CONSUMED_AMOUNT] AS [AVAILABLE_AMOUNT],
    CAST(CASE WHEN [execution].[BUDGET_AMOUNT] = 0 THEN 0
        ELSE 100.0 * [execution].[CONSUMED_AMOUNT] / [execution].[BUDGET_AMOUNT]
        END AS decimal(9, 2)) AS [EXECUTION_PCT],
    CASE
        WHEN [execution].[CONSUMED_AMOUNT] > [execution].[BUDGET_AMOUNT]
            THEN N'OVER EXECUTED'
        WHEN [execution].[CONSUMED_AMOUNT] >= [execution].[BUDGET_AMOUNT] * 0.90
            THEN N'AT RISK'
        WHEN [execution].[CONSUMED_AMOUNT] >= [execution].[BUDGET_AMOUNT] * 0.75
            THEN N'WATCH'
        ELSE N'ON TRACK'
    END AS [EXECUTION_STATUS],
    [execution].[LAST_POSTING_DATE] AS [LAST_POSTING_DATE]
FROM [EXECUTION] AS [execution]
INNER JOIN [sap].[FM_FUND_MASTER] AS [fund]
    ON [fund].[MANDT] = [execution].[MANDT]
   AND [fund].[FUND_CODE] = [execution].[FUND_CODE]
INNER JOIN [sap].[FM_FUNDS_CENTER_MASTER] AS [center]
    ON [center].[MANDT] = [execution].[MANDT]
   AND [center].[FUNDS_CENTER] = [execution].[FUNDS_CENTER]
INNER JOIN [sap].[FM_COMMITMENT_ITEM_MASTER] AS [item]
    ON [item].[MANDT] = [execution].[MANDT]
   AND [item].[COMMITMENT_ITEM] = [execution].[COMMITMENT_ITEM];
GO

BEGIN TRANSACTION;

DECLARE @client char(3) = '900';
DECLARE @fiscal_year smallint = 2026;
DECLARE @line_count int = 500;

DELETE FROM [sap].[FM_POSTING] WHERE [MANDT] = @client;
DELETE FROM [sap].[FM_BUDGET_LINE] WHERE [MANDT] = @client;
DELETE FROM [sap].[FM_COMMITMENT_ITEM_MASTER] WHERE [MANDT] = @client;
DELETE FROM [sap].[FM_FUNDS_CENTER_MASTER] WHERE [MANDT] = @client;
DELETE FROM [sap].[FM_FUND_MASTER] WHERE [MANDT] = @client;

INSERT INTO [sap].[FM_FUND_MASTER]
    ([MANDT], [FUND_CODE], [APPROPRIATION], [FUNDING_AUTHORITY])
VALUES
    (@client, N'2020', N'Operation and Maintenance, Army', N'ANNUAL'),
    (@client, N'2010', N'Military Personnel, Army', N'ANNUAL'),
    (@client, N'2035', N'Other Procurement, Army', N'MULTI-YEAR'),
    (@client, N'2040', N'Research, Development, Test and Evaluation, Army', N'MULTI-YEAR'),
    (@client, N'2050', N'Military Construction, Army', N'MULTI-YEAR');

INSERT INTO [sap].[FM_COMMITMENT_ITEM_MASTER]
    ([MANDT], [COMMITMENT_ITEM], [COMMITMENT_ITEM_NAME])
VALUES
    (@client, N'CI-2100', N'Civilian Personnel'),
    (@client, N'CI-2200', N'Travel and Transportation'),
    (@client, N'CI-2300', N'Rent, Communications, and Utilities'),
    (@client, N'CI-2400', N'Printing and Reproduction'),
    (@client, N'CI-2500', N'Other Contractual Services'),
    (@client, N'CI-2600', N'Supplies and Materials'),
    (@client, N'CI-3100', N'Equipment'),
    (@client, N'CI-3200', N'Land and Structures'),
    (@client, N'CI-4100', N'Grants, Subsidies, and Contributions'),
    (@client, N'CI-4200', N'Insurance Claims and Indemnities');

;WITH [DIGITS] AS (
    SELECT [DIGIT]
    FROM (VALUES (0), (1), (2), (3), (4), (5), (6), (7), (8), (9))
        AS [values]([DIGIT])
),
[NUMBERS] AS (
    SELECT TOP (50)
        ROW_NUMBER() OVER (ORDER BY [tens].[DIGIT], [ones].[DIGIT]) AS [CENTER_ID]
    FROM [DIGITS] AS [tens]
    CROSS JOIN [DIGITS] AS [ones]
)
INSERT INTO [sap].[FM_FUNDS_CENTER_MASTER]
    ([MANDT], [FUNDS_CENTER], [FUNDS_CENTER_NAME], [COMMAND_NAME])
SELECT
    @client,
    N'FC-' + RIGHT(REPLICATE(N'0', 4) + CONVERT(nvarchar(4), [CENTER_ID]), 4),
    CASE (([CENTER_ID] - 1) % 10) + 1
        WHEN 1 THEN N'Fort Bragg Resource Management Office'
        WHEN 2 THEN N'Fort Cavazos Resource Management Office'
        WHEN 3 THEN N'Fort Campbell Resource Management Office'
        WHEN 4 THEN N'Fort Stewart Resource Management Office'
        WHEN 5 THEN N'Fort Bliss Resource Management Office'
        WHEN 6 THEN N'JBLM Resource Management Office'
        WHEN 7 THEN N'Fort Carson Resource Management Office'
        WHEN 8 THEN N'Fort Riley Resource Management Office'
        WHEN 9 THEN N'Fort Drum Resource Management Office'
        ELSE N'Fort Johnson Resource Management Office'
    END + N' ' + CONVERT(nvarchar(2), (([CENTER_ID] - 1) / 10) + 1),
    CASE (([CENTER_ID] - 1) % 5) + 1
        WHEN 1 THEN N'FORSCOM'
        WHEN 2 THEN N'AMC'
        WHEN 3 THEN N'TRADOC'
        WHEN 4 THEN N'USACE'
        ELSE N'NETCOM'
    END
FROM [NUMBERS];

CREATE TABLE [#FINANCE_LINES] (
    [ROW_ID] int NOT NULL PRIMARY KEY,
    [BUDGET_LINE_ID] nvarchar(16) NOT NULL,
    [FUND_CODE] nvarchar(10) NOT NULL,
    [FUNDS_CENTER] nvarchar(16) NOT NULL,
    [COMMITMENT_ITEM] nvarchar(12) NOT NULL,
    [PROGRAM_ELEMENT] nvarchar(16) NOT NULL,
    [BUDGET_AMOUNT] decimal(19, 2) NOT NULL,
    [COMMITMENT_PCT] int NOT NULL,
    [OBLIGATION_PCT] int NOT NULL,
    [EXPENDITURE_PCT] int NOT NULL
);

;WITH [DIGITS] AS (
    SELECT [DIGIT]
    FROM (VALUES (0), (1), (2), (3), (4), (5), (6), (7), (8), (9))
        AS [values]([DIGIT])
),
[NUMBERS] AS (
    SELECT TOP (@line_count)
        ROW_NUMBER() OVER (ORDER BY [hundreds].[DIGIT], [tens].[DIGIT], [ones].[DIGIT]) AS [ROW_ID]
    FROM [DIGITS] AS [hundreds]
    CROSS JOIN [DIGITS] AS [tens]
    CROSS JOIN [DIGITS] AS [ones]
)
INSERT INTO [#FINANCE_LINES]
    ([ROW_ID], [BUDGET_LINE_ID], [FUND_CODE], [FUNDS_CENTER], [COMMITMENT_ITEM],
     [PROGRAM_ELEMENT], [BUDGET_AMOUNT], [COMMITMENT_PCT], [OBLIGATION_PCT],
     [EXPENDITURE_PCT])
SELECT
    [ROW_ID],
    N'BL-2026-' + RIGHT(REPLICATE(N'0', 6) + CONVERT(nvarchar(6), [ROW_ID]), 6),
    CASE ([ROW_ID] - 1) % 5
        WHEN 0 THEN N'2020' WHEN 1 THEN N'2010' WHEN 2 THEN N'2035'
        WHEN 3 THEN N'2040' ELSE N'2050' END,
    N'FC-' + RIGHT(REPLICATE(N'0', 4)
        + CONVERT(nvarchar(4), (([ROW_ID] - 1) % 50) + 1), 4),
    N'CI-' + CASE ([ROW_ID] - 1) % 10
        WHEN 0 THEN N'2100' WHEN 1 THEN N'2200' WHEN 2 THEN N'2300'
        WHEN 3 THEN N'2400' WHEN 4 THEN N'2500' WHEN 5 THEN N'2600'
        WHEN 6 THEN N'3100' WHEN 7 THEN N'3200' WHEN 8 THEN N'4100'
        ELSE N'4200' END,
    N'PE-' + RIGHT(REPLICATE(N'0', 8)
        + CONVERT(nvarchar(8), 60000000 + (([ROW_ID] - 1) % 25) + 1), 8),
    CONVERT(decimal(19, 2), 100000 +
        (ABS(CONVERT(bigint, CHECKSUM(HASHBYTES(
            'SHA2_256', CONCAT(N'finance-budget-', [ROW_ID]))))) % 190) * 25000),
    CONVERT(int, ABS(CONVERT(bigint, CHECKSUM(HASHBYTES(
        'SHA2_256', CONCAT(N'finance-commitment-', [ROW_ID]))))) % 10),
    20 + CONVERT(int, ABS(CONVERT(bigint, CHECKSUM(HASHBYTES(
        'SHA2_256', CONCAT(N'finance-obligation-', [ROW_ID]))))) % 40),
    10 + CONVERT(int, ABS(CONVERT(bigint, CHECKSUM(HASHBYTES(
        'SHA2_256', CONCAT(N'finance-expenditure-', [ROW_ID]))))) % 35)
FROM [NUMBERS];

INSERT INTO [sap].[FM_BUDGET_LINE]
    ([MANDT], [BUDGET_LINE_ID], [FISCAL_YEAR], [FUND_CODE], [FUNDS_CENTER],
     [COMMITMENT_ITEM], [PROGRAM_ELEMENT], [BUDGET_AMOUNT], [VALID_FROM], [VALID_TO])
SELECT
    @client, [BUDGET_LINE_ID], @fiscal_year, [FUND_CODE], [FUNDS_CENTER],
    [COMMITMENT_ITEM], [PROGRAM_ELEMENT], [BUDGET_AMOUNT],
    CONVERT(date, '20251001', 112), CONVERT(date, '20260930', 112)
FROM [#FINANCE_LINES];

INSERT INTO [sap].[FM_POSTING]
    ([MANDT], [DOCUMENT_NUMBER], [LINE_ITEM], [BUDGET_LINE_ID], [POSTING_DATE],
     [FISCAL_PERIOD], [VALUE_TYPE], [AMOUNT], [REFERENCE_TEXT])
SELECT
    @client,
    N'FM-' + RIGHT(REPLICATE(N'0', 8) + CONVERT(nvarchar(8), [ROW_ID]), 8),
    [posting_type].[LINE_ITEM],
    [BUDGET_LINE_ID],
    [activity].[POSTING_DATE],
    CONVERT(tinyint, DATEDIFF(month, CONVERT(date, '20251001', 112),
        [activity].[POSTING_DATE]) + 1),
    [posting_type].[VALUE_TYPE],
    ROUND([BUDGET_AMOUNT] * [posting_type].[PERCENTAGE] / 100.0, 2),
    N'Synthetic FY26 ' + LOWER([posting_type].[VALUE_TYPE]) + N' activity'
FROM [#FINANCE_LINES]
CROSS APPLY (VALUES
    (CONVERT(smallint, 1), N'COMMITMENT', [COMMITMENT_PCT]),
    (CONVERT(smallint, 2), N'OBLIGATION', [OBLIGATION_PCT]),
    (CONVERT(smallint, 3), N'EXPENDITURE', [EXPENDITURE_PCT])
) AS [posting_type]([LINE_ITEM], [VALUE_TYPE], [PERCENTAGE])
CROSS APPLY (VALUES (
    DATEADD(day, ([ROW_ID] * (11 + [posting_type].[LINE_ITEM] * 3)) % 330,
        CONVERT(date, '20251001', 112))
)) AS [activity]([POSTING_DATE]);

DROP TABLE [#FINANCE_LINES];

COMMIT TRANSACTION;
GO

IF (SELECT COUNT(*) FROM [reporting].[FINANCIAL_EXECUTION]
    WHERE [FISCAL_YEAR] = 2026) <> 500
    THROW 51010, 'Finance fixture did not produce 500 execution rows.', 1;

IF (SELECT COUNT(*) FROM [sap].[FM_FUND_MASTER] WHERE [MANDT] = '900') <> 5
    OR (SELECT COUNT(*) FROM [sap].[FM_FUNDS_CENTER_MASTER] WHERE [MANDT] = '900') <> 50
    OR (SELECT COUNT(*) FROM [sap].[FM_COMMITMENT_ITEM_MASTER] WHERE [MANDT] = '900') <> 10
    OR (SELECT COUNT(*) FROM [sap].[FM_BUDGET_LINE] WHERE [MANDT] = '900') <> 500
    OR (SELECT COUNT(*) FROM [sap].[FM_POSTING] WHERE [MANDT] = '900') <> 1500
    THROW 51011, 'Finance fixture did not populate every finance source.', 1;

IF NOT EXISTS (
    SELECT 1 FROM [reporting].[FINANCIAL_EXECUTION]
    WHERE [EXECUTION_STATUS] = N'OVER EXECUTED'
) OR NOT EXISTS (
    SELECT 1 FROM [reporting].[FINANCIAL_EXECUTION]
    WHERE [EXECUTION_STATUS] = N'AT RISK'
) OR NOT EXISTS (
    SELECT 1 FROM [reporting].[FINANCIAL_EXECUTION]
    WHERE [EXECUTION_STATUS] = N'WATCH'
) OR NOT EXISTS (
    SELECT 1 FROM [reporting].[FINANCIAL_EXECUTION]
    WHERE [EXECUTION_STATUS] = N'ON TRACK'
)
    THROW 51012, 'Finance fixture did not produce varied execution statuses.', 1;
GO
