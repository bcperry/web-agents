# Data Model: SAP HANA Private Connectivity

This feature adds configuration and runtime result models. It does not persist business data or
copy HANA rows into Cosmos DB.

## Database Provider Configuration

One configuration exists per provider and environment.

| Field | Type | Rules |
|-------|------|-------|
| `provider_id` | enum | `synapse` or `hana`; stable and unique. |
| `enabled` | boolean | Defaults to false for HANA until its environment gate passes. |
| `host` | string | Non-secret FQDN; IP literals are prohibited in production unless explicitly approved for a temporary network proof. |
| `port` | integer | `1..65535`; HANA value supplied by its owner. |
| `database` | string | Synapse database or HANA tenant/database identifier. |
| `tls_required` | boolean | Must be true for HANA outside isolated tests. |
| `tls_server_name` | string | Must match the validated server certificate identity. |
| `ca_secret_uri` | URI/null | Key Vault certificate/secret URI when the platform trust store is insufficient. Never contains certificate material. |
| `credential_secret_uri` | URI/null | Key Vault URI for the selected HANA credential. Terraform receives only the URI/reference, not the secret value. |
| `approved_schemas` | list[string]/null | Null or empty means all objects readable by the database identity. A non-empty list narrows discovery and query access and can never broaden database grants. |
| `connect_timeout_seconds` | integer | Positive; initial default 10, finalized by target testing. |
| `query_timeout_seconds` | integer | Positive; initial default 30, finalized by target testing. |
| `max_rows` | integer | Defaults to `MAX_QUERY_RESULT_ROWS`; server-side fetch must stop at limit + 1 to detect continuation. |
| `max_result_chars` | integer | Defaults to `MAX_QUERY_RESULT_CHARS`. |
| `max_cell_chars` | integer | Defaults to `MAX_SQL_CELL_CHARS`. |

### Validation

- HANA cannot be enabled without host, port, database, TLS server name, credential configuration,
  and a passed environment acceptance record.
- Schema names are normalized only for comparison; emitted SQL preserves provider-correct quoting.
- Provider configuration is selected by an agent grant, never by free-form model input.
- Secret values, PSKs, and private certificate material are not fields in this model.

## Agent Database Grant

| Field | Type | Rules |
|-------|------|-------|
| `provider_id` | enum | Explicitly binds the grant to `synapse` or `hana`. |
| `capabilities` | set | `database_schema` and/or `database_query`. |
| `entitled_groups` | list[string] | Entra group object IDs allowed to start a session with the HANA grant. Empty means no users for HANA, not everyone. |
| `environment` | enum | `local`, `development`, `staging`, or `production`. |

The grant is resolved server-side from the authenticated user and agent definition. Neither tool
accepts provider, user, group, environment, credential, host, or schema-override inputs from the
model.

## Query Request

| Field | Type | Rules |
|-------|------|-------|
| `sql` | string | Exactly one read query in the accepted grammar. Bounded by the existing tool-input limit. |
| `parameters` | list[scalar]/null | Optional positional bound values; never interpolated into SQL or logged. Named parameters are out of scope until both providers share an approved syntax. |
| `continuation` | object/null | Exact unmodified continuation object returned by a previous result. |

## Query Result

| Field | Type | Rules |
|-------|------|-------|
| `status` | enum | `success`, `validation_error`, `authentication_error`, `authorization_error`, `trust_error`, `configuration_error`, `transient_error`, or `query_error`. |
| `provider` | enum | `synapse` or `hana`. |
| `columns` | list[object] | Ordered names and normalized type labels. |
| `rows` | list[list] | Values are JSON-safe and each string/cell is bounded. |
| `row_count` | integer | Number of rows returned in this page. |
| `truncated` | boolean | True when row, cell, or total-output limits were reached. |
| `continuation` | object/null | Versioned signed token plus expiry and safe guidance, bound to provider, normalized query/parameters, proven unique ordering, limits, and configuration fingerprint. Never claims complete coverage when stable ordering cannot be proven. |
| `warnings` | list[string] | Includes explicit partial-result/absence guidance. |
| `correlation_id` | string | Safe opaque identifier for server-side diagnostics. |

## Schema Discovery Result

| Field | Type | Rules |
|-------|------|-------|
| `provider` | enum | Bound provider. |
| `objects` | list[object] | Schema, object, kind, ordered columns, normalized types. No source SQL/definition text. |
| `truncated` | boolean | Indicates incomplete catalog coverage. |
| `continuation` | object/null | Deterministic catalog continuation. |

## Environment Acceptance Record

This is a versioned deployment artifact, not an application database record.

| Field | Type | Rules |
|-------|------|-------|
| `schema_version` | integer | Starts at `1`; unknown versions fail closed. |
| `status` | enum | `passed`, `expired`, or `revoked`; only `passed` is enableable. |
| `environment` | enum | Development, staging, or production. |
| `network_tested_at` | timestamp | DNS/TCP/TLS proof from the deployed route domain. |
| `identity_tested_at` | timestamp | HANA login and direct negative-grant proof. |
| `contract_tested_at` | timestamp | Mandatory, non-skipped provider integration suite. |
| `vpn_failover_tested_at` | timestamp/null | Required for production; nullable only in nonproduction environments that intentionally use one test peer. |
| `evidence` | list[object] | Each entry has `type` (`network_plan`, `route`, `tunnel`, `dns_tls`, `identity_denial`, `integration`, `evaluation`, `rotation`, or `failover`), protected `uri`, SHA-256 digest, and `observed_at`. Production requires every type. |
| `approvers` | list[object] | Exactly one or more entries for each `network`, `hana`, `security`, and `application` role; each has immutable principal ID, display name, `approved` decision, and `decided_at`. |
| `issued_at` / `expires_at` | timestamp | Production validity is time-bounded; owner-approved maximum age is recorded in the handoff. |
| `config_fingerprint` | string | SHA-256 over canonical non-secret provider/network/DNS/TLS settings, code revision, driver/version, grant definitions, and entitled group IDs. |

The signed non-secret manifest is a JSON envelope stored at
`specs/015-sap-hana-private-connectivity/acceptance/<environment>.json` with `payload` containing the
fields above and `signature` containing `algorithm` (`RS256`), full versioned Key Vault `key_id`,
and base64url `value`. The signature covers the RFC 8785 JSON Canonicalization Scheme bytes of
`payload`. The verifier accepts only configured versioned key IDs, retrieves the public key through
managed identity, and fails closed on unknown algorithms/keys, noncanonical or altered payloads,
invalid signatures, status/freshness/environment/fingerprint mismatch, missing evidence types, or
missing role approvals. Detailed evidence remains in the protected systems referenced by `uri`.

## State Transitions

```text
unconfigured
  -> network-ready
  -> driver-auth-ready
  -> contract-verified
  -> enabled-nonprod
  -> enabled-production

Any code, driver, provider/network/DNS/TLS setting, grant, or entitled-group fingerprint change -> contract-verified is invalidated.
Credential rotation -> identity test required.
Network/routing/IKE change -> network and failover tests required.
Acceptance expiry or signature failure -> HANA tools disabled for new and existing sessions.
Disable switch -> disabled immediately; infrastructure remains deployed.
```
