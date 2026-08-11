SET XACT_ABORT ON;
GO

BEGIN TRANSACTION;

DECLARE @client char(3) = '900';
DECLARE @eq1 nvarchar(18) = RIGHT(REPLICATE(N'0', 18) + N'1001', 18);
DECLARE @eq2 nvarchar(18) = RIGHT(REPLICATE(N'0', 18) + N'1002', 18);
DECLARE @eq3 nvarchar(18) = RIGHT(REPLICATE(N'0', 18) + N'1003', 18);
DECLARE @eq4 nvarchar(18) = RIGHT(REPLICATE(N'0', 18) + N'1004', 18);
DECLARE @eq5 nvarchar(18) = RIGHT(REPLICATE(N'0', 18) + N'1005', 18);

DELETE FROM [emulator].[CONTEXT] WHERE [CONTEXT_ID] = 1;
INSERT INTO [emulator].[CONTEXT]
    ([CONTEXT_ID], [MANDT], [PLVAR], [OTYPE], [LANGUAGE], [AS_OF_DATE])
VALUES
    (1, @client, N'01', N'O', 'E', CONVERT(date, '20260810', 112));

DELETE FROM [emulator].[RELATIONSHIP_RULE] WHERE [RULE_NAME] = N'force_to_equipment';
INSERT INTO [emulator].[RELATIONSHIP_RULE]
    ([RULE_NAME], [OTYPE], [RSIGN], [RELAT], [SCLAS])
VALUES
    (N'force_to_equipment', N'O', N'B', N'003', N'EQ');

DELETE FROM [sap].[JEST] WHERE [MANDT] = @client;
DELETE FROM [sap].[JSTO] WHERE [MANDT] = @client;
DELETE FROM [sap].[ZDFPS_DODAC] WHERE [MANDT] = @client;
DELETE FROM [sap].[EQKT] WHERE [MANDT] = @client;
DELETE FROM [sap].[EQUZ] WHERE [MANDT] = @client;
DELETE FROM [sap].[ILOA] WHERE [MANDT] = @client;
DELETE FROM [sap].[IFLOT] WHERE [MANDT] = @client;
DELETE FROM [sap].[EQUI] WHERE [MANDT] = @client;
DELETE FROM [sap].[MARA] WHERE [MANDT] = @client;
DELETE FROM [sap].[HRP1001] WHERE [MANDT] = @client;
DELETE FROM [sap].[HRP1000] WHERE [MANDT] = @client;
DELETE FROM [sap].[ISDFPS_FORCE] WHERE [MANDT] = @client;
DELETE FROM [sap].[TJ30T] WHERE [MANDT] = @client;
DELETE FROM [sap].[TJ02T]
WHERE [SPRAS] = 'E' AND [ISTAT] IN (N'I0001', N'I0002', N'I0076');

INSERT INTO [sap].[ISDFPS_FORCE]
    ([MANDT], [FORCE_ID], [FORCE_CNT], [PLVAR], [OTYPE], [OBJID])
VALUES
    (@client, N'FORCE-SYN-1-66-AR', '000001', N'01', N'O', '00001000'),
    (@client, N'FORCE-SYN-4-10-CAV', '000001', N'01', N'O', '00001100');

INSERT INTO [sap].[HRP1000]
    ([MANDT], [PLVAR], [OTYPE], [OBJID], [ISTAT], [BEGDA], [ENDDA], [LANGU],
     [SEQNR], [SHORT], [STEXT])
VALUES
    (@client, N'01', N'O', '00001000', N'1', '20200101', '99991231', 'E',
    '000', N'1-66 AR', N'1st Battalion, 66th Armor'),
    (@client, N'01', N'O', '00001000', N'1', '20200101', '99991231', 'D',
    '000', N'1-66 AR-DE', N'1. Bataillon, 66. Panzerregiment'),
    (@client, N'01', N'O', '00001100', N'1', '20200101', '99991231', 'E',
    '000', N'4-10 CAV', N'4th Squadron, 10th Cavalry');

INSERT INTO [sap].[HRP1001]
    ([MANDT], [OTYPE], [OBJID], [PLVAR], [RSIGN], [RELAT], [ISTAT], [PRIOX],
     [BEGDA], [ENDDA], [VARYF], [SEQNR], [SCLAS], [SOBID])
VALUES
    (@client, N'O', '00001000', N'01', N'B', N'003', N'1', N'00',
     '20200101', '99991231', N'', '001', N'EQ', N'1001'),
    (@client, N'O', '00001000', N'01', N'B', N'003', N'1', N'00',
     '20200101', '99991231', N'', '002', N'EQ', N'1002'),
    (@client, N'O', '00001100', N'01', N'B', N'003', N'1', N'00',
     '20200101', '99991231', N'', '001', N'EQ', N'1003'),
    (@client, N'O', '00001000', N'01', N'B', N'999', N'1', N'00',
     '20200101', '99991231', N'', '001', N'EQ', N'1004'),
    (@client, N'O', '00001000', N'01', N'B', N'003', N'1', N'00',
     '20200101', '20211231', N'', '003', N'EQ', N'1005');

INSERT INTO [sap].[EQUI]
    ([MANDT], [EQUNR], [EQTYP], [SERNR], [MATNR], [OBJNR])
VALUES
    (@client, @eq1, N'V', N'SYN-M1A2-001', N'MAT-M1A2-SEPV3', N'IE' + @eq1),
    (@client, @eq2, N'C', N'SYN-VRC114-001', N'MAT-AN-VRC-114', N'IE' + @eq2),
    (@client, @eq3, N'P', N'SYN-MEP805-001', N'MAT-MEP-805B', N'IE' + @eq3),
    (@client, @eq4, N'V', N'SYN-JLTV-004', N'MAT-M1280-JLTV', N'IE' + @eq4),
    (@client, @eq5, N'V', N'SYN-HMMWV-005', N'MAT-M1165-HMMWV', N'IE' + @eq5);

INSERT INTO [sap].[EQUZ]
    ([MANDT], [EQUNR], [DATBI], [EQLFN], [DATAB], [HEQUI], [ILOAN], [IWERK])
VALUES
    (@client, @eq1, '20191231', '001', '20100101', N'', N'000000000009', N'A100'),
    (@client, @eq1, '99991231', '001', '20200101', N'', N'000000000001', N'A100'),
    (@client, @eq2, '99991231', '001', '20210101', @eq1, N'000000000002', N'A100');

INSERT INTO [sap].[ILOA]
    ([MANDT], [ILOAN], [TPLNR], [SWERK], [STORT], [BEBER])
VALUES
    (@client, N'000000000001', N'FORT-CAVAZOS-MP-12', N'A100', N'MP-12', N'OPS'),
    (@client, N'000000000002', N'FORT-CAVAZOS-SIG-01', N'A100', N'SIG-01', N'SIG');

INSERT INTO [sap].[IFLOT]
    ([MANDT], [TPLNR], [TPLMA], [MLANG], [TPLKZ], [FLTYP], [IWERK], [OBJNR])
VALUES
    (@client, N'FORT-CAVAZOS', NULL, 'E', N'BASE', N'F', N'A100', N'IF-FORT-CAVAZOS'),
    (@client, N'FORT-CAVAZOS-MP-12', N'FORT-CAVAZOS', 'E', N'BASE', N'F', N'A100',
     N'IF-FCAV-MP-12'),
    (@client, N'FORT-CAVAZOS-SIG-01', N'FORT-CAVAZOS', 'E', N'BASE', N'F', N'A100',
     N'IF-FCAV-SIG-01');

INSERT INTO [sap].[EQKT]
    ([MANDT], [EQUNR], [SPRAS], [EQKTX], [TXASP])
VALUES
    (@client, @eq1, 'E', N'M1A2 SEPv3 Abrams', N'X'),
    (@client, @eq1, 'D', N'M1A2 SEPv3 Kampfpanzer', N''),
    (@client, @eq2, 'E', N'AN/VRC-114 Mounted Radio', N'X'),
    (@client, @eq3, 'E', N'MEP-805B Generator Set', N'X');

INSERT INTO [sap].[MARA]
    ([MANDT], [MATNR], [MTART], [MATKL], [EXTWG])
VALUES
    (@client, N'MAT-M1A2-SEPV3', N'FERT', N'COMBATVEH', N'CLASS-VII'),
    (@client, N'MAT-AN-VRC-114', N'FERT', N'SIGNAL', N'CLASS-VII'),
    (@client, N'MAT-MEP-805B', N'FERT', N'POWER', N'CLASS-VII'),
    (@client, N'MAT-M1280-JLTV', N'HAWA', N'TACTVEH', N'CLASS-VII'),
    (@client, N'MAT-M1165-HMMWV', N'HAWA', N'TACTVEH', N'CLASS-VII');

INSERT INTO [sap].[ZDFPS_DODAC] ([MANDT], [MATNR], [DODAC])
VALUES
    (@client, N'MAT-M1A2-SEPV3', N'2350A001'),
    (@client, N'MAT-AN-VRC-114', N'5820D001');

INSERT INTO [sap].[JSTO] ([MANDT], [OBJNR], [STSMA])
VALUES
    (@client, N'IE' + @eq1, N'EQUIP'),
    (@client, N'IE' + @eq2, N'EQUIP'),
    (@client, N'IE' + @eq3, N'EQUIP');

INSERT INTO [sap].[JEST] ([MANDT], [OBJNR], [STAT], [INACT], [CHGNR])
VALUES
    (@client, N'IE' + @eq1, N'I0001', N'', '001'),
    (@client, N'IE' + @eq1, N'I0076', N'X', '002'),
    (@client, N'IE' + @eq1, N'E0001', N'', '003'),
    (@client, N'IE' + @eq2, N'I0002', N'', '001'),
    (@client, N'IE' + @eq2, N'E0002', N'', '002'),
    (@client, N'IE' + @eq3, N'I0001', N'', '001');

INSERT INTO [sap].[TJ02T] ([ISTAT], [SPRAS], [TXT04], [TXT30])
VALUES
    (N'I0001', 'E', N'INST', N'Installed'),
    (N'I0002', 'E', N'AVLB', N'Available'),
    (N'I0076', 'E', N'INAC', N'Inactive');

INSERT INTO [sap].[TJ30T]
    ([MANDT], [STSMA], [ESTAT], [SPRAS], [TXT04], [TXT30], [LTEXT])
VALUES
    (@client, N'EQUIP', N'E0001', 'E', N'FMC', N'Fully Mission Capable', N''),
    (@client, N'EQUIP', N'E0002', 'E', N'PMCS', N'PMCS Scheduled', N'');

COMMIT TRANSACTION;
GO

IF (SELECT COUNT(*) FROM [reporting].[FORCE_EQUIPMENT]) <> 3
    THROW 51000, 'Synthetic force-equipment fixture did not produce three current rows.', 1;
GO