---
name: sap-force-equipment-analysis
description: "Use when querying or analyzing SAP force-equipment assignments, Army equipment readiness, maintenance status, materials, or functional locations."
---

# SAP Force-Equipment Analysis

Use this skill to answer factual questions about the current synthetic Army force-equipment model.
The database is read-only. Use `database_schema` and `database_query`; do not infer records from the
skill text.

## Data Source

Query only `[reporting].[FORCE_EQUIPMENT]`. It is the approved semantic view and already resolves
the SAP joins, current relationship dates, current equipment usage segment, functional-location
hierarchy, material details, and active status text.

The view reflects emulator context client `900`, plan version `01`, English, and as-of date
`2026-08-10`. All identifiers, serials, assignments, and readiness records are synthetic and
unclassified. Public Army nomenclature is representative, not an operational data claim.

Call `database_schema(schema="reporting", object_name="FORCE_EQUIPMENT")` when column metadata is
needed. Do not query the raw `sap` or `emulator` schemas.

## Column Dictionary

| Column | Meaning |
| --- | --- |
| `FORCE_ID` | Eight-character SAP organizational object identifier; preserve leading zeros. |
| `FE_SHORT` | Short force-element or unit label. |
| `FE_STEXT` | Long force-element or unit name. |
| `BEGDA` | Start date of the force-to-equipment assignment. |
| `ENDDA` | End date of the force-to-equipment assignment. |
| `EQUNR` | Eighteen-character SAP equipment number; preserve leading zeros. |
| `EQTYP` | Equipment category code. In this fixture, `V` is vehicle, `C` is communications, and `P` is power equipment. |
| `SERNR` | Synthetic equipment serial number. |
| `HEQUI` | Parent equipment number when this item is installed below another item; blank means no parent recorded. |
| `TPLMA` | Parent functional location; null for a root location. |
| `EQKTX` | English equipment description or nomenclature. |
| `MATNR` | SAP material identifier. |
| `DODAC` | Synthetic DODAC-style commodity code; null means the optional mapping is absent. Do not call it a DODAAC. |
| `EXTWG` | External material group; the fixture uses values such as `CLASS-VII`. |
| `MTART` | SAP material type, such as `FERT` or `HAWA`. |
| `MATKL` | Material group, such as `COMBATVEH`, `ARTILLERY`, `TACTVEH`, `SIGNAL`, or `POWER`. |
| `TPLNR` | Current functional location or maintenance-position identifier. Null means no current location assignment. |
| `FL_LEVEL` | Functional-location hierarchy depth, where a root is level 1. Null when no location resolves. |
| `SWERK` | Maintenance plant. |
| `SYS_STATUS` | Active SAP system status text; multiple statuses are comma-separated in status-code order. |
| `USR_STATUS` | Active user/readiness status text; multiple statuses are comma-separated in status-code order. |

## Analysis Workflow

1. Identify the requested population, grouping, timeframe, and measure.
2. Aggregate first. For a broad question, return counts or top-N groups rather than assignment rows.
3. Query the semantic view with only the columns needed and use selective predicates when available.
4. Retrieve detail only when explicitly requested and scoped to a unit, status, location, or equipment.
5. Bound detail with `TOP (20)` by default and use an explicit `ORDER BY`, normally `FORCE_ID, EQUNR`.
6. Check tool status, warnings, and `truncated`. Never treat omitted rows as absent.
7. State the as-of date when presenting readiness or assignment findings.
8. Translate column names into operational language unless the user asks for technical details.

## Scale-Safe Defaults

- Treat broad requests such as "equipment by unit," "where is equipment," or "what needs
  maintenance" as summary requests. Group and count in SQL before returning data.
- Default to at most 10 ranked groups and at most 20 detail rows. Increase that only when the user
  explicitly asks and the result remains operationally useful.
- Avoid grouping by high-cardinality identifiers such as `EQUNR`, `SERNR`, or a force/location
  combination unless the user specifically requests that grain.
- Do not attempt to enumerate an entire fleet. Give a compact summary, then offer to drill into a
  named unit, readiness status, material group, or location.
- Prefer one low-cardinality dimension per summary. Add a second dimension only when needed to
  answer the question and keep the output compact.
- Apply user-supplied filters before aggregation. On production-scale data, an aggregate can still
  be expensive if it scans an unnecessarily broad population.

## Query Rules

- Submit exactly one `SELECT` statement, optionally with read-only CTEs.
- Use fully qualified `[reporting].[FORCE_EQUIPMENT]` and T-SQL bracket identifiers.
- Do not include SQL comments, DML, DDL, procedures, temp tables, or multiple statements.
- Bind user-provided filters with `?` placeholders and positional parameters. Do not concatenate
  user text into SQL.
- Preserve SAP identifiers as strings. Never cast `FORCE_ID`, `EQUNR`, or `HEQUI` to numbers.
- Use `COUNT(*)` for assignment rows and `COUNT(DISTINCT EQUNR)` for unique equipment. Name which
  measure is being reported.
- Use `TOP (10)` for ranked summaries and `TOP (20)` for detail by default. Pair `TOP` with an
  explicit, deterministic `ORDER BY`.
- Use `NULLIF(LTRIM(RTRIM(column)), N'')` when blank and null should both mean missing.
- Use `COALESCE` only for presentation. Do not convert missing DODAC or location values into facts.
- Use exact readiness values returned by the data. Do not infer FMC, PMC, NMCM, or NMCS from
  equipment type or location.
- The view is already current as of the emulator context date. `BEGDA` and `ENDDA` describe the
  assignment validity; they are not maintenance-event dates.

## Reliable Query Patterns

Largest force elements by assigned equipment:

```sql
SELECT TOP (10) [FORCE_ID], [FE_SHORT], [FE_STEXT],
       COUNT(DISTINCT [EQUNR]) AS [EQUIPMENT_COUNT]
FROM [reporting].[FORCE_EQUIPMENT]
GROUP BY [FORCE_ID], [FE_SHORT], [FE_STEXT]
ORDER BY [EQUIPMENT_COUNT] DESC, [FORCE_ID]
```

Readiness distribution:

```sql
SELECT [USR_STATUS], COUNT(*) AS [ASSIGNMENT_COUNT],
       COUNT(DISTINCT [EQUNR]) AS [EQUIPMENT_COUNT]
FROM [reporting].[FORCE_EQUIPMENT]
GROUP BY [USR_STATUS]
ORDER BY [USR_STATUS]
```

Units with the most equipment needing maintenance:

```sql
SELECT TOP (10) [FORCE_ID], [FE_SHORT],
       COUNT(DISTINCT [EQUNR]) AS [EQUIPMENT_COUNT]
FROM [reporting].[FORCE_EQUIPMENT]
WHERE [USR_STATUS] IN (
    N'Non-Mission Capable Maint',
    N'Non-Mission Capable Supply',
    N'Partially Mission Capable',
    N'PMCS Scheduled'
)
  GROUP BY [FORCE_ID], [FE_SHORT]
  ORDER BY [EQUIPMENT_COUNT] DESC, [FORCE_ID]
```

Equipment for one unit using a bound parameter:

```sql
SELECT TOP (20) [FORCE_ID], [FE_SHORT], [EQUNR], [EQKTX], [MATKL], [TPLNR],
       [USR_STATUS]
FROM [reporting].[FORCE_EQUIPMENT]
WHERE [FE_SHORT] = ?
ORDER BY [FORCE_ID], [EQUNR]
```

Material summary:

```sql
SELECT TOP (10) [MATKL], COUNT(DISTINCT [EQUNR]) AS [EQUIPMENT_COUNT]
FROM [reporting].[FORCE_EQUIPMENT]
GROUP BY [MATKL]
ORDER BY [EQUIPMENT_COUNT] DESC, [MATKL]
```

Installed equipment hierarchy:

```sql
SELECT TOP (20) [HEQUI] AS [PARENT_EQUNR], [EQUNR] AS [CHILD_EQUNR], [EQKTX],
       [FE_SHORT]
FROM [reporting].[FORCE_EQUIPMENT]
WHERE NULLIF(LTRIM(RTRIM([HEQUI])), N'') IS NOT NULL
ORDER BY [HEQUI], [EQUNR]
```

## Result Interpretation

- One row represents one current force-to-equipment assignment, not a maintenance work order or
  historical event.
- A blank `HEQUI` is a top-level equipment assignment, not evidence that hierarchy data is broken.
- Null `DODAC`, `TPLNR`, `TPLMA`, `FL_LEVEL`, or `SWERK` is allowed by the semantic model.
- Status fields can contain multiple comma-separated active statuses. For exact membership across
  such values, avoid naive substring conclusions; retrieve the row and explain the combined text.
- If the result is truncated, narrow the query or aggregate it. Only reuse a continuation object
  unchanged when the tool supplies one and the SQL and parameters are identical.
- If a question asks for history, work orders, faults, parts demand, quantities, costs, personnel,
  or operational locations beyond this view, state that the available data cannot answer it.

## Response Style

Lead with the result and the `2026-08-10` as-of date when relevant. Distinguish counts of assignment
rows from counts of unique equipment. Mention material, location, or status gaps only when they
affect the requested conclusion. Do not expose SQL, schema names, tool names, connection details,
or internal authorization behavior unless the user explicitly asks for technical implementation.
Keep the initial response compact: normally one short conclusion plus a table of no more than 10
summary rows. Do not print raw fleet records merely because they are available.