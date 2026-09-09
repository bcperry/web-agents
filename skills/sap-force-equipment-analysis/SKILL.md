---
name: sap-force-equipment-analysis
description: "Use when querying or analyzing SAP force-equipment assignments, Army equipment readiness, maintenance status, materials, or functional locations."
---

# SAP Force-Equipment Analysis

Use this skill to answer factual questions and make data-grounded forecasts about the current Army
force-equipment model. The database is read-only. Use `database_schema` and `database_query`; do not
infer records from the skill text.

## Data Source

Query only `[reporting].[FORCE_EQUIPMENT]`. It is the approved semantic view and already resolves
the SAP joins, current relationship dates, current equipment usage segment, functional-location
hierarchy, material details, and active status text.

The view reflects SAP context client `900`, plan version `01`, English, and an as-of date of
`2026-08-10`.

Call `database_schema(schema="reporting", object_name="FORCE_EQUIPMENT")` when column metadata is
needed. Do not query the raw `sap` or `emulator` schemas.

## Column Dictionary

| Column | Meaning |
| --- | --- |
| `FORCE_ID` | Eight-character SAP organizational object identifier; preserve leading zeros. This is the stable key to filter on once a unit is resolved. |
| `FE_SHORT` | Terse SAP unit code such as `B09/4-10CAV`. Users rarely type this exactly; never guess it. |
| `FE_STEXT` | Long force-element or unit name such as `Bravo Company, TF 09, 4-10CAV`. User phrasing usually resembles this. |
| `BEGDA` | Start date of the force-to-equipment assignment. |
| `ENDDA` | End date of the force-to-equipment assignment. |
| `EQUNR` | Eighteen-character SAP equipment number; preserve leading zeros. |
| `EQTYP` | Equipment category code. In this fixture, `V` is vehicle, `C` is communications, and `P` is power equipment. |
| `SERNR` | Equipment serial number. |
| `HEQUI` | Parent equipment number when this item is installed below another item; blank means no parent recorded. |
| `TPLMA` | Parent functional location; null for a root location. |
| `EQKTX` | English equipment description or nomenclature. |
| `MATNR` | SAP material identifier. |
| `DODAC` | DODAC-style commodity code; null means the optional mapping is absent. Do not call it a DODAAC. |
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
2. If the user names a unit, resolve it to a `FORCE_ID` first. See "Resolving a Named Unit".
3. Aggregate first. For a broad question, return counts or top-N groups rather than assignment rows.
4. Query the semantic view with only the columns needed and use selective predicates when available.
5. Retrieve detail only when explicitly requested and scoped to a unit, status, location, or equipment.
6. Bound detail with `TOP (20)` by default and use an explicit `ORDER BY`, normally `FORCE_ID, EQUNR`.
7. Check tool status, warnings, and `truncated`. Never treat omitted rows as absent.
8. State the as-of date when presenting readiness or assignment findings.
9. Translate column names into operational language unless the user asks for technical details.
10. For predictive analytics, retrieve the relevant current records and make a best-effort estimate
  of the future status using the available readiness, assignment, material, and maintenance signals.

## Resolving a Named Unit

Never filter on a guessed `FE_SHORT` with `=`. The short code is a terse SAP label such as
`B09/4-10CAV`, while users normally type something closer to `FE_STEXT`
(`Bravo Company, TF 09, 4-10CAV`) or an informal variant of it. An exact match on an invented code
returns zero rows, and zero rows here means "my guess was wrong", not "the unit does not exist".

Resolve in one bounded lookup, then query by the returned `FORCE_ID`:

1. Split the user's phrase into its most distinctive tokens. Prefer the parent unit designator
   (`4-10CAV`), the task-force or company number (`TF 09`, `B09`), and the company word (`BRAVO`).
   Drop filler such as "company", "co", "unit", "the".
2. Match two tokens with `AND`, each tested against both `FE_STEXT` and `FE_SHORT`, wrapping the
   column and the parameter in `UPPER(...)` and binding `%TOKEN%` values.
3. Act on the candidate count:
   - **Exactly one** — use its `FORCE_ID` and name the unit you resolved to.
   - **Several** — if one candidate matches every token the user supplied, use it and state the
     assumption in one clause. Otherwise list the candidates and ask which one.
   - **None** — retry once with only the single most distinctive token. If that is still empty,
     say the unit is not present and show the nearest candidates you did find.
4. Run the detail or summary query against `[FORCE_ID] = ?`. It is the stable key; labels are not.

Do not describe this lookup step to the user. Report the resolved unit, not the search.

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
- The view is already current as of the `2026-08-10` context date. `BEGDA` and `ENDDA` describe the
  assignment validity; they are not maintenance-event dates.

## Predictive Analytics

- Always query the relevant data before forecasting. Never forecast from the skill text alone.
- If the user provides no horizon, forecast the near-term status and state that assumption.
- Use current `USR_STATUS` and `SYS_STATUS` as the primary signals. Use assignment validity,
  material group, functional location, and maintenance plant only as supporting context.
- Produce the most likely future readiness status or risk band even when history or dedicated
  prediction fields are unavailable. Treat that result as a best estimate, not an observed fact.
- Explain the strongest supporting signals, material assumptions, and confidence (`low`, `medium`,
  or `high`). Lower confidence when the view lacks history, work orders, fault details, or parts data.
- For a population, aggregate current signals and forecast a compact distribution or top risk list;
  do not invent equipment-level precision unsupported by the records.

## Rendered Views

Use `render_agent_view` only when the user explicitly asks for a rendered view, dashboard,
visualization, or chart. A comparison, ranked list, readiness distribution, predictive request, or
canned prompt does not by itself authorize rendering. When explicitly requested, query first and
embed the returned values in one self-contained view using inline styles/scripts and host theme
variables. Also give a concise chat summary.

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

Resolve a unit the user named, using two distinctive tokens:

```sql
SELECT DISTINCT TOP (10) [FORCE_ID], [FE_SHORT], [FE_STEXT]
FROM [reporting].[FORCE_EQUIPMENT]
WHERE (UPPER([FE_STEXT]) LIKE UPPER(?) OR UPPER([FE_SHORT]) LIKE UPPER(?))
  AND (UPPER([FE_STEXT]) LIKE UPPER(?) OR UPPER([FE_SHORT]) LIKE UPPER(?))
ORDER BY [FE_SHORT]
```

For "tell me about Bravo Company, TF 09, 4-10CAV" bind `%BRAVO%`, `%BRAVO%`, `%TF 09%`, `%TF 09%`,
which resolves to a single `FORCE_ID`. Binding `%BRAVO%` with `%4-10CAV%` instead returns the whole
`B**/4-10CAV` family, so prefer the token that carries the company or task-force number.

Equipment for one resolved unit:

```sql
SELECT TOP (20) [FORCE_ID], [FE_SHORT], [EQUNR], [EQKTX], [MATKL], [TPLNR],
       [USR_STATUS]
FROM [reporting].[FORCE_EQUIPMENT]
WHERE [FORCE_ID] = ?
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
- If the result is truncated, narrow the query or aggregate it. The tools do not page, so a
  truncated result is never evidence that the omitted rows do not exist.
- If a question asks for history, work orders, faults, parts demand, quantities, costs, personnel,
  or operational locations beyond this view, state that the available data cannot answer it.
- Zero rows from an equality filter on a name or code means the filter value was wrong, not that the
  unit or equipment is absent. Re-resolve with the fuzzy lookup before reporting an absence.

## Response Style

Lead with the result and the `2026-08-10` as-of date when relevant. Distinguish counts of assignment
rows from counts of unique equipment. Mention material, location, or status gaps only when they
affect the requested conclusion. Do not expose SQL, schema names, tool names, connection details,
or internal authorization behavior unless the user explicitly asks for technical implementation.
Name the source as the force-equipment record, never as an emulator, fixture, test database, or
generated dataset. Write "as of 2026-08-10", not "as of the SAP emulator". If the user asks about
data provenance, explain only what the available source metadata establishes.
Keep the initial response compact: normally one short conclusion plus a table of no more than 10
summary rows. Do not print raw fleet records merely because they are available.