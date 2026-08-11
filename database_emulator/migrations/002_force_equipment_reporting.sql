SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'reporting')
    EXEC(N'CREATE SCHEMA [reporting] AUTHORIZATION [dbo]');
GO

IF OBJECT_ID(N'[emulator].[CONTEXT]', N'U') IS NULL
BEGIN
    CREATE TABLE [emulator].[CONTEXT] (
        [CONTEXT_ID] tinyint NOT NULL,
        [MANDT] char(3) NOT NULL,
        [PLVAR] nvarchar(2) NOT NULL,
        [OTYPE] nvarchar(2) NOT NULL,
        [LANGUAGE] char(1) NOT NULL,
        [AS_OF_DATE] date NOT NULL,
        CONSTRAINT [PK_EMULATOR_CONTEXT] PRIMARY KEY ([CONTEXT_ID]),
        CONSTRAINT [CK_EMULATOR_CONTEXT_SINGLETON] CHECK ([CONTEXT_ID] = 1)
    );
END;
GO

IF OBJECT_ID(N'[emulator].[RELATIONSHIP_RULE]', N'U') IS NULL
BEGIN
    CREATE TABLE [emulator].[RELATIONSHIP_RULE] (
        [RULE_NAME] sysname NOT NULL,
        [OTYPE] nvarchar(2) NOT NULL,
        [RSIGN] nvarchar(1) NOT NULL,
        [RELAT] nvarchar(3) NOT NULL,
        [SCLAS] nvarchar(2) NOT NULL,
        CONSTRAINT [PK_EMULATOR_RELATIONSHIP_RULE] PRIMARY KEY ([RULE_NAME])
    );
END;
GO

IF OBJECT_ID(N'[sap].[JSTO]', N'U') IS NULL
BEGIN
    CREATE TABLE [sap].[JSTO] (
        [MANDT] char(3) NOT NULL,
        [OBJNR] nvarchar(22) NOT NULL,
        [STSMA] nvarchar(8) NOT NULL,
        CONSTRAINT [PK_JSTO] PRIMARY KEY ([MANDT], [OBJNR])
    );
END;
GO

IF OBJECT_ID(N'[sap].[ZDFPS_DODAC]', N'U') IS NULL
BEGIN
    CREATE TABLE [sap].[ZDFPS_DODAC] (
        [MANDT] char(3) NOT NULL,
        [MATNR] nvarchar(40) NOT NULL,
        [DODAC] nvarchar(10) NOT NULL,
        CONSTRAINT [PK_ZDFPS_DODAC] PRIMARY KEY ([MANDT], [MATNR])
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ISDFPS_FORCE_OBJID'
      AND object_id = OBJECT_ID(N'[sap].[ISDFPS_FORCE]')
)
BEGIN
    CREATE INDEX [IX_ISDFPS_FORCE_OBJID]
        ON [sap].[ISDFPS_FORCE] ([MANDT], [PLVAR], [OTYPE], [OBJID]);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_IFLOT_PARENT'
      AND object_id = OBJECT_ID(N'[sap].[IFLOT]')
)
BEGIN
    CREATE INDEX [IX_IFLOT_PARENT]
        ON [sap].[IFLOT] ([MANDT], [TPLMA], [TPLNR]);
END;
GO

CREATE OR ALTER FUNCTION [emulator].[ALPHA_EQUNR] (@value nvarchar(45))
RETURNS nvarchar(18)
AS
BEGIN
    DECLARE @trimmed nvarchar(45) = LTRIM(RTRIM(@value));
    RETURN CASE
        WHEN @trimmed IS NULL OR @trimmed = N'' THEN NULL
        ELSE RIGHT(REPLICATE(N'0', 18) + @trimmed, 18)
    END;
END;
GO

CREATE OR ALTER FUNCTION [emulator].[DATS_TO_DATE] (@value char(8))
RETURNS date
AS
BEGIN
    RETURN TRY_CONVERT(date, NULLIF(LTRIM(RTRIM(@value)), ''), 112);
END;
GO

CREATE OR ALTER VIEW [reporting].[FORCE_EQUIPMENT]
AS
WITH [FL_HIERARCHY] AS (
    SELECT
        [location].[MANDT],
        [location].[TPLNR],
        CAST(1 AS int) AS [FL_LEVEL],
        CAST(N'|' + RTRIM([location].[TPLNR]) + N'|' AS nvarchar(max)) AS [VISITED]
    FROM [sap].[IFLOT] AS [location]
    INNER JOIN [emulator].[CONTEXT] AS [context]
        ON [context].[CONTEXT_ID] = 1
       AND [context].[MANDT] = [location].[MANDT]
    WHERE NULLIF(LTRIM(RTRIM([location].[TPLMA])), N'') IS NULL

    UNION ALL

    SELECT
        [child].[MANDT],
        [child].[TPLNR],
        [parent].[FL_LEVEL] + 1,
        CAST([parent].[VISITED] + RTRIM([child].[TPLNR]) + N'|' AS nvarchar(max))
    FROM [sap].[IFLOT] AS [child]
    INNER JOIN [FL_HIERARCHY] AS [parent]
        ON [parent].[MANDT] = [child].[MANDT]
       AND [parent].[TPLNR] = [child].[TPLMA]
    WHERE [parent].[FL_LEVEL] < 32
      AND CHARINDEX(N'|' + RTRIM([child].[TPLNR]) + N'|', [parent].[VISITED]) = 0
)
SELECT
    [force].[OBJID] AS [FORCE_ID],
    [force_text].[SHORT] AS [FE_SHORT],
    [force_text].[STEXT] AS [FE_STEXT],
    [emulator].[DATS_TO_DATE]([relationship].[BEGDA]) AS [BEGDA],
    [emulator].[DATS_TO_DATE]([relationship].[ENDDA]) AS [ENDDA],
    [equipment].[EQUNR] AS [EQUNR],
    [equipment].[EQTYP] AS [EQTYP],
    [equipment].[SERNR] AS [SERNR],
    [usage].[HEQUI] AS [HEQUI],
    [functional_location].[TPLMA] AS [TPLMA],
    [equipment_text].[EQKTX] AS [EQKTX],
    [equipment].[MATNR] AS [MATNR],
    [dodac].[DODAC] AS [DODAC],
    [material].[EXTWG] AS [EXTWG],
    [material].[MTART] AS [MTART],
    [material].[MATKL] AS [MATKL],
    [location_assignment].[TPLNR] AS [TPLNR],
    [hierarchy].[FL_LEVEL] AS [FL_LEVEL],
    [location_assignment].[SWERK] AS [SWERK],
    COALESCE([system_status].[STATUS_TEXT], N'') AS [SYS_STATUS],
    COALESCE([user_status].[STATUS_TEXT], N'') AS [USR_STATUS]
FROM [emulator].[CONTEXT] AS [context]
INNER JOIN [sap].[ISDFPS_FORCE] AS [force]
    ON [force].[MANDT] = [context].[MANDT]
   AND [force].[PLVAR] = [context].[PLVAR]
   AND [force].[OTYPE] = [context].[OTYPE]
INNER JOIN [sap].[HRP1000] AS [force_text]
    ON [force_text].[MANDT] = [force].[MANDT]
   AND [force_text].[PLVAR] = [force].[PLVAR]
   AND [force_text].[OTYPE] = [force].[OTYPE]
   AND [force_text].[OBJID] = [force].[OBJID]
   AND [force_text].[ISTAT] = N'1'
   AND [force_text].[LANGU] = [context].[LANGUAGE]
   AND [context].[AS_OF_DATE] BETWEEN
       [emulator].[DATS_TO_DATE]([force_text].[BEGDA])
       AND [emulator].[DATS_TO_DATE]([force_text].[ENDDA])
INNER JOIN [emulator].[RELATIONSHIP_RULE] AS [rule]
    ON [rule].[RULE_NAME] = N'force_to_equipment'
   AND [rule].[OTYPE] = [force].[OTYPE]
INNER JOIN [sap].[HRP1001] AS [relationship]
    ON [relationship].[MANDT] = [force].[MANDT]
   AND [relationship].[PLVAR] = [force].[PLVAR]
   AND [relationship].[OTYPE] = [force].[OTYPE]
   AND [relationship].[OBJID] = [force].[OBJID]
   AND [relationship].[RSIGN] = [rule].[RSIGN]
   AND [relationship].[RELAT] = [rule].[RELAT]
   AND [relationship].[SCLAS] = [rule].[SCLAS]
   AND [relationship].[ISTAT] = N'1'
   AND [context].[AS_OF_DATE] BETWEEN
       [emulator].[DATS_TO_DATE]([relationship].[BEGDA])
       AND [emulator].[DATS_TO_DATE]([relationship].[ENDDA])
INNER JOIN [sap].[EQUI] AS [equipment]
    ON [equipment].[MANDT] = [force].[MANDT]
   AND [equipment].[EQUNR] = [emulator].[ALPHA_EQUNR]([relationship].[SOBID])
OUTER APPLY (
    SELECT TOP (1)
        [segment].[HEQUI],
        [segment].[ILOAN]
    FROM [sap].[EQUZ] AS [segment]
    WHERE [segment].[MANDT] = [equipment].[MANDT]
      AND [segment].[EQUNR] = [equipment].[EQUNR]
      AND [context].[AS_OF_DATE] BETWEEN
          [emulator].[DATS_TO_DATE]([segment].[DATAB])
          AND [emulator].[DATS_TO_DATE]([segment].[DATBI])
    ORDER BY [segment].[DATAB] DESC, [segment].[DATBI], [segment].[EQLFN] DESC
) AS [usage]
LEFT JOIN [sap].[ILOA] AS [location_assignment]
    ON [location_assignment].[MANDT] = [equipment].[MANDT]
   AND [location_assignment].[ILOAN] = [usage].[ILOAN]
LEFT JOIN [sap].[IFLOT] AS [functional_location]
    ON [functional_location].[MANDT] = [location_assignment].[MANDT]
   AND [functional_location].[TPLNR] = [location_assignment].[TPLNR]
LEFT JOIN [FL_HIERARCHY] AS [hierarchy]
    ON [hierarchy].[MANDT] = [functional_location].[MANDT]
   AND [hierarchy].[TPLNR] = [functional_location].[TPLNR]
LEFT JOIN [sap].[EQKT] AS [equipment_text]
    ON [equipment_text].[MANDT] = [equipment].[MANDT]
   AND [equipment_text].[EQUNR] = [equipment].[EQUNR]
   AND [equipment_text].[SPRAS] = [context].[LANGUAGE]
LEFT JOIN [sap].[MARA] AS [material]
    ON [material].[MANDT] = [equipment].[MANDT]
   AND [material].[MATNR] = [equipment].[MATNR]
LEFT JOIN [sap].[ZDFPS_DODAC] AS [dodac]
    ON [dodac].[MANDT] = [equipment].[MANDT]
   AND [dodac].[MATNR] = [equipment].[MATNR]
OUTER APPLY (
    SELECT STRING_AGG(CONVERT(nvarchar(max), [status_text].[TXT30]), N', ')
        WITHIN GROUP (ORDER BY [status].[STAT]) AS [STATUS_TEXT]
    FROM [sap].[JEST] AS [status]
    INNER JOIN [sap].[TJ02T] AS [status_text]
        ON [status_text].[ISTAT] = [status].[STAT]
       AND [status_text].[SPRAS] = [context].[LANGUAGE]
    WHERE [status].[MANDT] = [equipment].[MANDT]
      AND [status].[OBJNR] = [equipment].[OBJNR]
      AND LEFT([status].[STAT], 1) = N'I'
      AND ISNULL(LTRIM(RTRIM([status].[INACT])), N'') = N''
) AS [system_status]
OUTER APPLY (
    SELECT STRING_AGG(CONVERT(nvarchar(max), [status_text].[TXT30]), N', ')
        WITHIN GROUP (ORDER BY [status].[STAT]) AS [STATUS_TEXT]
    FROM [sap].[JEST] AS [status]
    INNER JOIN [sap].[JSTO] AS [status_profile]
        ON [status_profile].[MANDT] = [status].[MANDT]
       AND [status_profile].[OBJNR] = [status].[OBJNR]
    INNER JOIN [sap].[TJ30T] AS [status_text]
        ON [status_text].[MANDT] = [status].[MANDT]
       AND [status_text].[STSMA] = [status_profile].[STSMA]
       AND [status_text].[ESTAT] = [status].[STAT]
       AND [status_text].[SPRAS] = [context].[LANGUAGE]
    WHERE [status].[MANDT] = [equipment].[MANDT]
      AND [status].[OBJNR] = [equipment].[OBJNR]
      AND LEFT([status].[STAT], 1) = N'E'
      AND ISNULL(LTRIM(RTRIM([status].[INACT])), N'') = N''
) AS [user_status];
GO