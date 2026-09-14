---
name: sap-financial-execution-analysis
description: "Use when querying, analyzing, or forecasting SAP budget authority, commitments, obligations, expenditures, available balances, execution rates, or financial risk."
---

# SAP Financial Execution Analysis

Use this skill for factual questions and data-grounded forecasts about the Army financial-execution
model. The database is read-only. Use `database_schema` and `database_query`; never infer records or
amounts from this skill text.

## Data Source

Query only `[reporting].[FINANCIAL_EXECUTION]`. This approved semantic view joins SAP-style fund,
funds-center, commitment-item, budget-line, and posting records. It contains 500 FY2026 budget lines
and reflects activity through the latest posting on each line. It is not an accounting system of
record.

Call `database_schema(schema="reporting", object_name="FINANCIAL_EXECUTION")` when column metadata
is needed. Do not query raw `sap` or `emulator` schemas.

## Column Dictionary

| Column | Meaning |
| --- | --- |
| `FISCAL_YEAR` | Federal fiscal year; the fixture contains FY2026. |
| `BUDGET_LINE_ID` | Stable budget-line identifier; preserve it as text. |
| `FUND_CODE` | Treasury-style fund code. Preserve leading zeros if present. |
| `APPROPRIATION` | Appropriation title, such as Operation and Maintenance, Army. |
| `FUNDING_AUTHORITY` | Annual or multi-year authority classification. |
| `FUNDS_CENTER` | Stable funds-center identifier. |
| `FUNDS_CENTER_NAME` | Resource-management office responsible for the line. |
| `COMMAND_NAME` | Command grouping. |
| `COMMITMENT_ITEM` | Budget object / commitment-item identifier. |
| `COMMITMENT_ITEM_NAME` | Plain-language expense category. |
| `PROGRAM_ELEMENT` | Program-element identifier. |
| `BUDGET_AMOUNT` | Authority loaded to the budget line. |
| `COMMITTED_AMOUNT` | Funds administratively reserved but not yet obligated. |
| `OBLIGATED_AMOUNT` | Unliquidated obligations in this simplified fixture. |
| `EXPENDED_AMOUNT` | Disbursement-equivalent activity in this simplified fixture. |
| `CONSUMED_AMOUNT` | Commitments + unliquidated obligations + expenditures. These are mutually exclusive current-stage balances in the fixture. |
| `AVAILABLE_AMOUNT` | Budget less consumed amount; negative means over-executed. |
| `EXECUTION_PCT` | Consumed amount divided by budget amount, expressed as a percentage. |
| `EXECUTION_STATUS` | Derived band: `ON TRACK`, `WATCH`, `AT RISK`, or `OVER EXECUTED`. |
| `LAST_POSTING_DATE` | Most recent activity date for the line. |

## Analysis Workflow

1. Identify fiscal year, appropriation, command, funds center, expense category, and requested measure.
2. Aggregate in SQL before returning broad results; use detail only for a narrow follow-up.
3. For budget posture, report budget, consumed, and available amounts together.
4. Treat commitments, obligations, and expenditures as mutually exclusive current-stage balances in this reporting model. Do not apply that simplification to another accounting system without validating its ledger semantics.
5. Use the exact `EXECUTION_STATUS` from the view for risk lists; explain that it is a derived threshold, not a legal funds-control determination.
6. Check tool status, warnings, and `truncated`. Narrow or aggregate when output is partial.
7. State FY2026 when presenting findings.
8. For predictive analytics, query the relevant records and make a best-effort estimate of the
  future execution status from execution, available balance, current risk status, and posting recency.
9. Treat a failed query as a query-construction problem to diagnose and repair, not as evidence that
  the agent lacks data access. Follow the recovery procedure below before responding.

## Query Rules

- Submit exactly one `SELECT` statement, optionally with read-only CTEs.
- Use fully qualified `[reporting].[FINANCIAL_EXECUTION]` and T-SQL bracket identifiers.
- Do not include SQL comments, DML, DDL, procedures, temp tables, or multiple statements.
- Bind every user-provided filter with `?` placeholders and positional parameters.
- Preserve fund, center, item, program, and budget-line identifiers as strings.
- Use `SUM` for dollars and do not average dollar balances. Weighted portfolio execution is
  `100 * SUM(CONSUMED_AMOUNT) / NULLIF(SUM(BUDGET_AMOUNT), 0)`, not `AVG(EXECUTION_PCT)`.
- Default to `TOP (10)` ranked groups and `TOP (20)` budget-line details with deterministic `ORDER BY`.
- Keep monetary calculations in decimal types and label amounts as USD.
- Never assert an Anti-Deficiency Act violation, funds certification, legal availability, purpose/time/amount compliance, or audit finding from this reporting view. Flag a condition for review instead.

## No-Fail Query Recovery

The financial data is available through `database_schema` and `database_query`. A
`query_error` or `validation_error` means the submitted query needs correction; it does not mean
the data is unavailable.

1. Before a complex query, or after any failed query, call
  `database_schema(schema="reporting", object_name="FINANCIAL_EXECUTION")` and use only the exact
  table and column names it returns.
2. Inspect the failed tool result's status and safe message internally. Correct likely causes such
  as misspelled columns, invalid grouping, unsupported syntax, bad aliases, misplaced `TOP`, or
  mismatched parameter counts. Never repeat the identical failed query.
3. Retry with a simpler query: one approved view, exact bracketed columns, minimal expressions, no
  unnecessary CTE, and only the filters required by the request. Build from a reliable query
  pattern below whenever possible.
4. If the simplified query succeeds, add calculations or filters incrementally only when needed.
  Prefer computing a presentation-only forecast from successfully retrieved aggregates rather than
  forcing all forecast logic into one fragile SQL statement.
5. Make up to three materially different repair attempts for `query_error` or `validation_error`.
  For `transient_error`, retry once with the same bounded request and then once with a smaller
  aggregate query.
6. If a syntactically valid query returns zero rows unexpectedly, verify the requested value with a
  bounded `SELECT DISTINCT TOP (20)` lookup, then retry using an exact returned value or a broader
  filter. Zero rows do not prove lack of access.
7. Do not tell the user that data is inaccessible, unavailable, or missing because one query failed.
  Do not expose SQL or internal error details during successful recovery. Only after all recovery
  attempts fail should the response briefly state that the analysis could not be completed, while
  still avoiding connection, credential, authorization, and driver details.

## Predictive Analytics

- Always query the relevant financial data before forecasting. Never forecast from the skill text alone.
- Honor a user-provided horizon. If none is provided, estimate the likely near-term status and state
  that assumption.
- Use weighted execution, available balance, current `EXECUTION_STATUS`, and `LAST_POSTING_DATE` as
  the available signals. Apply the same status bands represented in the view when estimating a
  future status.
- Return the most likely future status (`ON TRACK`, `WATCH`, `AT RISK`, or `OVER EXECUTED`) even when
  history or a dedicated forecast field is unavailable. Clearly label it as a best estimate rather
  than an observed status.
- State the calculation or scenario assumptions and confidence (`low`, `medium`, or `high`). Lower
  confidence when the data does not establish a trend or spend rate.
- Keep observed balances separate from projected values and never present a forecast as a legal,
  certification, or audit conclusion.

## Rendered Views

Use `render_agent_view` only when the user explicitly asks for a rendered view, dashboard,
visualization, or chart. A comparison, ranked list, execution distribution, predictive request, or
canned prompt does not by itself authorize rendering. When explicitly requested, query first and
embed the returned values in one self-contained view using inline styles/scripts and host theme
variables. Also give a concise chat summary.

## Reliable Query Patterns

Overall budget posture:

```sql
SELECT [FISCAL_YEAR],
       SUM([BUDGET_AMOUNT]) AS [BUDGET_AMOUNT],
       SUM([COMMITTED_AMOUNT]) AS [COMMITTED_AMOUNT],
       SUM([OBLIGATED_AMOUNT]) AS [OBLIGATED_AMOUNT],
       SUM([EXPENDED_AMOUNT]) AS [EXPENDED_AMOUNT],
       SUM([CONSUMED_AMOUNT]) AS [CONSUMED_AMOUNT],
       SUM([AVAILABLE_AMOUNT]) AS [AVAILABLE_AMOUNT],
       CAST(100.0 * SUM([CONSUMED_AMOUNT]) / NULLIF(SUM([BUDGET_AMOUNT]), 0)
           AS decimal(9, 2)) AS [WEIGHTED_EXECUTION_PCT]
FROM [reporting].[FINANCIAL_EXECUTION]
GROUP BY [FISCAL_YEAR]
ORDER BY [FISCAL_YEAR]
```

Execution by appropriation:

```sql
SELECT [FUND_CODE], [APPROPRIATION],
       SUM([BUDGET_AMOUNT]) AS [BUDGET_AMOUNT],
       SUM([CONSUMED_AMOUNT]) AS [CONSUMED_AMOUNT],
       SUM([AVAILABLE_AMOUNT]) AS [AVAILABLE_AMOUNT],
       CAST(100.0 * SUM([CONSUMED_AMOUNT]) / NULLIF(SUM([BUDGET_AMOUNT]), 0)
           AS decimal(9, 2)) AS [WEIGHTED_EXECUTION_PCT]
FROM [reporting].[FINANCIAL_EXECUTION]
GROUP BY [FUND_CODE], [APPROPRIATION]
ORDER BY [FUND_CODE]
```

Highest-risk funds centers:

```sql
SELECT TOP (10) [FUNDS_CENTER], [FUNDS_CENTER_NAME], [COMMAND_NAME],
       SUM([BUDGET_AMOUNT]) AS [BUDGET_AMOUNT],
       SUM([CONSUMED_AMOUNT]) AS [CONSUMED_AMOUNT],
       SUM([AVAILABLE_AMOUNT]) AS [AVAILABLE_AMOUNT],
       CAST(100.0 * SUM([CONSUMED_AMOUNT]) / NULLIF(SUM([BUDGET_AMOUNT]), 0)
           AS decimal(9, 2)) AS [WEIGHTED_EXECUTION_PCT]
FROM [reporting].[FINANCIAL_EXECUTION]
GROUP BY [FUNDS_CENTER], [FUNDS_CENTER_NAME], [COMMAND_NAME]
ORDER BY [WEIGHTED_EXECUTION_PCT] DESC, [FUNDS_CENTER]
```

Budget lines requiring review:

```sql
SELECT TOP (20) [BUDGET_LINE_ID], [APPROPRIATION], [FUNDS_CENTER_NAME],
       [COMMITMENT_ITEM_NAME], [BUDGET_AMOUNT], [CONSUMED_AMOUNT],
       [AVAILABLE_AMOUNT], [EXECUTION_PCT], [EXECUTION_STATUS], [LAST_POSTING_DATE]
FROM [reporting].[FINANCIAL_EXECUTION]
WHERE [EXECUTION_STATUS] IN (N'OVER EXECUTED', N'AT RISK')
ORDER BY [EXECUTION_PCT] DESC, [BUDGET_LINE_ID]
```

## Result Interpretation

- One row is one budget line, not one transaction or invoice.
- Negative available amount means the current-stage balances exceed loaded budget on that
  line. Say it requires review; do not make a legal conclusion.
- Portfolio percentages must be weighted from summed amounts.
- `LAST_POSTING_DATE` is activity recency, not proof that a line has completed reconciliation.
- If asked about vendors, contracts, invoices, payroll recipients, reimbursable orders, audit
  evidence, or historical snapshots, state that this view cannot answer the question.
- If output is truncated, it is never evidence that omitted lines or categories do not exist.

## Response Style

Lead with the FY2026 result. Use concise staff format: BLUF, key figures, risks,
and recommended review actions. Translate technical identifiers unless the user requests them.
Separate observed values from recommendations and never invent missing amounts.
