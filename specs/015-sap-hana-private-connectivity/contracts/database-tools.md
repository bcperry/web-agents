# Contract: Database Tools and Providers

## Contract Status

The current runtime exposes no database tools, and the previous implementation is available only in
Git history. Therefore the names below are the proposed stable contract and require approval before
implementation. Compatibility fixtures must capture representative Azure Synapse requests/results
before HANA code begins.

## Model-Facing Tools

### `database_schema`

Returns bounded metadata for the provider bound to the current agent grant.

```text
database_schema(
  schema: string | null = null,
  object_name: string | null = null
) -> SchemaDiscoveryResult
```

`schema` and `object_name` are each null or 1-127 Unicode characters after trimming; control
characters and unquoted separator/wildcard syntax are rejected. The provider applies its own
identifier quoting after validation.

- Provider, connection, environment, and credentials are not model inputs.
- A requested schema must be readable by the database identity and included in the configured
  approved-schema override when one exists.
- Source definitions, grants, credentials, connection metadata, and unrestricted system catalogs
  are never returned.

### `database_query`

Executes one bounded read query through the provider bound to the current agent grant.

```text
database_query(
  sql: string,
  parameters: list[scalar] | null = null
) -> QueryResult
```

`sql` is 1-20,000 Unicode characters. `parameters` contains at most 100 positional scalars and its
canonical JSON encoding is at most 16,384 UTF-8 bytes. A scalar is null, boolean, signed 64-bit integer,
finite IEEE-754 number, or an untyped Unicode string up to 4,096 characters. Strings receive no
decimal/date inference; callers use an explicit provider-valid SQL `CAST` when semantic typing is
required. Binary, nested collections/maps, NaN, and infinities are rejected.

The model cannot select `synapse` versus `hana`. Separate provider-bound tool instances may share
these public names because an agent/session receives only one binding for a given name. An agent
that truly needs both providers must receive unambiguous aliases approved in the contract review;
silent provider selection from SQL text is prohibited.

## Accepted SQL Grammar

Allowed:

- Exactly one `SELECT` statement.
- Read-only CTEs whose final statement is `SELECT` and whose bodies contain only allowed reads.
- Provider-supported joins, predicates, grouping, ordering, and scalar expressions.
- Bound scalar parameters through the driver's parameter API.
- Provider-correct quoted identifiers and Unicode string values.
- HANA read-only table functions only when explicitly allowlisted by fully qualified name; default
  is denied.

Rejected before execution:

- Multiple statements or a trailing non-whitespace statement delimiter followed by content.
- SQL comments. This conservative rule prevents hidden statement/control tokens in model output.
- DML, DDL, DCL, transaction/session statements, anonymous blocks, dynamic SQL, procedure calls,
  `DO`, `CALL`, `EXEC/EXECUTE`, imports/exports, and administrative/system commands.
- Queries referencing schemas excluded by the configured override.
- Driver-specific escape hatches that execute arbitrary statements.

Validation uses a HANA-aware parser/tokenizer selected by a focused spike. A keyword prefix or regex
alone is not an acceptable validator. Database grants remain the final write-prevention boundary.

## Truncation

The tools do not page. A truncated result is a prompt to narrow the query, never a cursor.

- The provider fetches at most `max_rows + 1` rows to detect additional data without materializing
  an unbounded result.
- Character-limit truncation can occur before the row limit. The result identifies which limit was
  reached and never interprets omitted values as absent.
- A truncated result from a query without an explicit `ORDER BY` additionally warns that the
  omitted rows are arbitrary, so the caller re-issues with an explicit ordering.
- Schema discovery is bounded by the same row limit and reports truncation the same way.

## Normalized Types and Serialization

- `null`, boolean, integer, decimal-as-string, float, string, date/time ISO 8601, binary metadata,
  and safe fallback string are the normalized categories.
- Decimal values are serialized as strings to avoid precision loss.
- Binary/LOB values are not returned by default; metadata reports their presence. Explicit support
  requires a later contract change.
- Timestamps preserve timezone information when supplied by the provider; otherwise the result
  identifies them as timezone-naive.

## Error Contract

| Status | Meaning | Retryable |
|--------|---------|-----------|
| `validation_error` | SQL shape, schema override, or parameter contract rejected before execution. | No |
| `authentication_error` | HANA/Synapse credential, token, or login was rejected. | No; rotate or repair identity. |
| `authorization_error` | User entitlement or database grant denied. | No |
| `trust_error` | Certificate chain, hostname, protocol, or trust policy validation failed. | No; repair configuration/certificate. |
| `configuration_error` | Provider disabled, acceptance invalid, or required non-secret/secret reference missing. | No |
| `transient_error` | DNS, route, TCP, TLS transport interruption, timeout, or temporary provider availability. | Yes, bounded |
| `query_error` | Valid read query rejected by HANA/Synapse syntax or object semantics. | Usually no |

Tool results contain a correlation id and sanitized category/message only. Raw driver errors,
hosts, connection strings, SQL parameters, result previews, and credentials remain server-side and
must also be redacted there.

## Authorization

Tool availability requires all of:

1. Authenticated application user.
2. Agent configured with the provider-bound capability.
3. User membership in an environment-specific entitled Entra group.
4. Provider enabled for that environment with a current acceptance record.

The shared HANA technical identity does not provide per-user row-level authorization. Per-user HANA
impersonation/analytic privileges are out of scope for this feature; every returned row must already
be suitable for all users in the entitled group. Only configured Entra tenants are accepted.
Transitive group membership is supported; when token group claims are incomplete/overage, the
trusted backend resolves membership through Microsoft Graph and fails closed if it cannot do so.
Membership is re-evaluated before each invocation with a maximum five-minute cache; wrong-tenant,
revoked, stale/unresolvable, or nonmember requests are denied, including existing sessions.

Every invocation attempt emits one metadata-only audit event with `timestamp`, application user id,
tenant id, agent id, provider, environment, capability, correlation id, duration, row count,
truncated, outcome/status, and sanitized error category. Denied or pre-execution requests use row
count `0` and `truncated=false`. SQL text/hashes, parameter values, result cells, credentials,
connection metadata, and raw driver errors are excluded from this audit event.

## Compatibility Gate

Before implementation, approve fixtures that define:

- Existing Azure Synapse tool names or the migration mapping to these proposed names.
- Representative schema and query inputs.
- Result columns/types and truncation behavior.
- Error categories and redaction expectations.
- Whether any agent needs simultaneous Synapse and HANA access; if yes, approve distinct aliases.
