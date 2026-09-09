# SAP Force-Equipment Azure SQL Emulator

This directory builds the synthetic relational database defined by the feature 015 workbook and
the assumptions in
`specs/015-sap-hana-private-connectivity/emulator-data-contract.md`.

## Contents

- `generate_schema.py` parses all twelve DDIC sheets and generates 693 physical Azure SQL columns.
- `migrations/001_sap_schema.sql` contains the generated `sap` tables and queryable DDIC metadata.
- `migrations/002_force_equipment_reporting.sql` adds supplemental sources and the corrected
  21-column `reporting.FORCE_EQUIPMENT` view.
- `migrations/003_synthetic_seed.sql` adds deterministic synthetic records and asserts that the
  view returns three current force-equipment rows.
- `migrations/004_bulk_synthetic_seed.sql` adds 500 linked, representative Army force, equipment,
  installation, material, and readiness fixtures while preserving the three edge-case records.
- `migrations/005_financial_execution.sql` adds SAP-style fund, funds-center, commitment-item,
  budget-line, and posting sources; a 500-row FY2026 `reporting.FINANCIAL_EXECUTION` view; and
  deterministic execution-risk fixtures.
- `apply_migrations.py` validates or applies migrations using ODBC Driver 18 and Entra credentials.

## Regenerate and Validate

```bash
uv run --group dev python -m database_emulator.generate_schema
uv run --group dev python -m database_emulator.generate_schema --check
uv run python -m database_emulator.apply_migrations --validate-only
uv run --group dev pytest -q \
  tests/test_sap_emulator_schema.py \
  tests/test_sap_emulator_migrations.py
```

Regeneration fails on missing sheets, formulas, malformed rows, duplicate fields, unknown SAP
types, missing keys, or unsupported decimal shapes. Do not edit the generated migration manually.

## Provision Azure SQL

The Terraform module is disabled by default. Set these azd environment values before provisioning:

```bash
azd env set SAP_EMULATOR_ENABLED true
azd env set SAP_EMULATOR_ADMIN_OBJECT_ID <entra-object-id>
azd env set SAP_EMULATOR_ADMIN_LOGIN <entra-display-name>
```

`SAP_EMULATOR_SQL_SERVER_NAME` can override the derived globally unique server name.
`SAP_EMULATOR_DATABASE_SKU` defaults to `Basic` when empty.

Public connectivity remains disabled by default. Until Private Endpoint and VNet integration are
available, an explicitly trusted developer client can be restricted to one exact address:

```bash
azd env set SAP_EMULATOR_PUBLIC_NETWORK_ACCESS_ENABLED true
azd env set SAP_EMULATOR_ALLOWED_IP_START <public-ipv4-address>
azd env set SAP_EMULATOR_APP_OUTBOUND_IPS <comma-separated-app-service-possible-outbound-ipv4-addresses>
azd provision
```

Do not use the Azure SQL `0.0.0.0` "Allow Azure services" firewall rule. Keep
`SAP_EMULATOR_ALLOWED_IP_START` and `SAP_EMULATOR_ALLOWED_IP_END` set while persistent developer
access is required; Terraform manages that exact-IP rule. The target state is Private Endpoint
access through the feature 015 VNet with public network access disabled.

## Register the Application Provider

The application registers the emulator as the distinct `sap_emulator` provider when
`SAP_EMULATOR_ENABLED=true`. A built-in profile earns the read-only `database_schema` and
`database_query` tools by declaring them in `config/agents.yaml`; user-created custom agents cannot
select them. SQL is restricted to the `reporting` schema and every call requires membership in one
of the configured Entra security groups. An incomplete configuration disables the tools and logs an
error rather than stopping the app.

```bash
azd env set SAP_EMULATOR_ENTITLED_GROUP_IDS <entra-security-group-object-id>
azd provision
azd deploy web
```

Configure the app registration with `groupMembershipClaims=SecurityGroup` so validated access
tokens contain the user's group IDs. Users must acquire a new token after group membership or app
claim settings change. A token whose group claim is absent or overflowed fails closed because no
Graph membership resolver is currently configured.

## Apply and Verify

The connection string is configuration, not a password. The runner strips its authentication
attribute and obtains an Azure Government SQL token with `DefaultAzureCredential`.

```bash
export SAP_EMULATOR_CONNECTIONSTRING="$(terraform -chdir=infra output -raw SAP_EMULATOR_CONNECTIONSTRING)"
export SAP_EMULATOR_READER_PRINCIPAL_NAME=<app-managed-identity-name>
uv run python -m database_emulator.apply_migrations
```

The optional reader principal receives only `SELECT` and `VIEW DEFINITION` on the `reporting`
schema. The runner removes legacy `db_datareader` membership if present. The deploying Entra
administrator retains migration ownership.

Verify the semantic result:

```sql
SELECT *
FROM [reporting].[FORCE_EQUIPMENT]
ORDER BY [FORCE_ID], [EQUNR];
```

The force-equipment seed returns 503 rows: the original Alpha and Bravo edge cases plus 500
generated current assignments. Every force-equipment SAP table contains at least 500 rows. The
unrelated relationship and expired assignment must not appear. The finance seed separately returns
500 FY2026 budget lines backed by 1,500 synthetic posting rows across five appropriations,
50 funds centers, and ten commitment items.

Verify the finance semantic result:

```sql
SELECT [APPROPRIATION], SUM([BUDGET_AMOUNT]) AS [BUDGET_AMOUNT],
       SUM([CONSUMED_AMOUNT]) AS [CONSUMED_AMOUNT],
       SUM([AVAILABLE_AMOUNT]) AS [AVAILABLE_AMOUNT]
FROM [reporting].[FINANCIAL_EXECUTION]
GROUP BY [APPROPRIATION]
ORDER BY [APPROPRIATION];
```

To repeat the complete engine-level assertion against a disposable SQL Server or Azure SQL
database, point the dedicated test setting at that database:

```bash
export SAP_EMULATOR_TEST_CONNECTIONSTRING="$SAP_EMULATOR_CONNECTIONSTRING"
uv run --group dev pytest -q -m sqlserver_integration \
  tests/test_sap_emulator_integration.py
```

This database validates relational semantics, schema discovery, agent behavior, and expected
answers. It is not evidence for SAP HANA networking, TLS, authentication, driver, catalog, dialect,
permissions, performance, or required-target acceptance.