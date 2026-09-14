# Azure SQL SAP Force-Equipment Emulator Data Contract

## Purpose

The Azure SQL emulator reproduces the SAP force-equipment relational model and the expected ALV
result shape from `SAP_Force_Equipment_Table_Relationship_Complete.xlsx`. It supports schema
discovery, agent-query development, deterministic fixtures, and contract tests before private SAP
HANA access is available. It does not replace HANA driver, dialect, TLS, authorization, or private
network acceptance tests.

The workbook is authoritative for supplied physical fields, SAP data types, lengths, keys, and
descriptions. The rules below resolve contradictions or missing inputs explicitly so they can be
changed without reverse-engineering generated SQL.

## Canonical Source Objects

The workbook defines twelve physical SAP source tables:

- `/ISDFPS/FORCE`, `HRP1000`, `HRP1001`
- `EQUI`, `EQUZ`, `EQKT`, `MARA`
- `ILOA`, `IFLOT`
- `JEST`, `TJ02T`, `TJ30T`

`/ISDFPS/FORCE_ID` is a data element, not a table. `IFLO` and `TJO2T` in workbook labels are treated
as spelling errors for `IFLOT` and `TJ02T`.

Two supplemental objects fill information required by the advertised ALV result but absent from
the supplied dictionaries:

- `JSTO` supplies the status profile needed to resolve user statuses through `TJ30T`.
- `ZDFPS_DODAC` supplies the custom DODAC value by material number.

These names are emulator contracts until the SAP owner provides the actual source objects.

## Join and Selection Assumptions

1. `/ISDFPS/FORCE.OBJID`, not the 32-character `FORCE_ID`, joins to `HRP1000.OBJID` and
   `HRP1001.OBJID`. Joins also include `MANDT`, `PLVAR`, and `OTYPE` where those fields exist.
2. The default force-to-equipment relationship is `OTYPE = 'O'`, `RSIGN = 'B'`, `RELAT = '003'`,
   and `SCLAS = 'EQ'`. The values live in `emulator.RELATIONSHIP_RULE`, so confirmed SAP values can
   replace them without changing the reporting view.
3. `HRP1001.SOBID` is normalized to an 18-character equipment number using SAP ALPHA-style
   left-zero padding before joining to `EQUI.EQUNR`.
4. Validity intervals are inclusive. A current row satisfies `BEGDA <= as_of_date <= ENDDA` for
   HRP records and `DATAB <= as_of_date <= DATBI` for `EQUZ`.
5. The default context is client `100`, plan version `01`, object type `O`, language `E`, and a
   configurable UTC `as_of_date`. These values live in the single-row `emulator.CONTEXT` table so
   fixtures remain deterministic.
6. The ALV `BEGDA` and `ENDDA` columns represent the force-to-equipment relationship validity from
   `HRP1001`. Equipment usage validity remains available from the raw `EQUZ` table.
7. Equipment location follows `EQUI -> EQUZ -> ILOA -> IFLOT`. `HEQUI` comes from `EQUZ`; `TPLNR`
   and `SWERK` come from `ILOA`.
8. `FL_LEVEL` is derived recursively from `IFLOT.TPLMA`; a root functional location is level 1.
   Cycles are excluded by a bounded recursion guard.
9. Active statuses have blank `JEST.INACT`. Statuses beginning with `I` are system statuses resolved
   through `TJ02T`; statuses beginning with `E` are user statuses resolved through
   `JSTO.STSMA + TJ30T.ESTAT`. Text is aggregated in status-code order.
10. Optional descriptive, material, location, and status data use left joins so missing enrichment
    does not remove an otherwise valid force-equipment assignment.

## ALV Compatibility Decisions

- The reporting view exposes 21 columns in the workbook's stated order.
- `FORCE_ID` is the eight-character OM `OBJID`, matching the workbook's `NUMC(8)` result type. The
  raw 32-character `/ISDFPS/FORCE.FORCE_ID` remains available in the source table.
- `MATNR` is 40 characters, matching the supplied S/4HANA dictionaries rather than the ALV sheet's
  obsolete 18-character label.
- `DODAC` comes from `ZDFPS_DODAC`, not `MARA`, because no `DODAC` field exists in the supplied
  `MARA` dictionary.
- Date-like SAP source fields remain fixed `char(8)` values in `YYYYMMDD` form, including the
  `99991231` high-date sentinel. The reporting view converts valid values to SQL `date`.

## Synthetic Fixture Coverage

The seed data must include current and historical assignments, multiple equipment per force,
equipment hierarchy, functional-location hierarchy, multilingual text, active and inactive
statuses, system and user statuses, a material without optional DODAC data, missing optional
location data, and an unrelated HR relationship excluded by the configured relationship rule.

The scale fixture adds 500 deterministic, current force-equipment assignments with representative
Army unit naming, installations, equipment nomenclature, supply classifications, and coherent
maintenance-readiness states. Matching materials, locations, texts, status profiles, and
system/user statuses preserve all joins. Every SAP-facing emulator table contains at least 500
rows while the smaller edge-case fixture remains independently assertable.

All identifiers, serials, assignments, and readiness records are synthetic and unclassified.
Recognizable public Army nomenclature is used only to make the emulator credible; no production
records or workbook-supplied secrets are used.