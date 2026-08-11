# Phase 0 Research: SAP HANA Private Connectivity

## R1 - Preserve the Tool Contract, Separate the Provider

**Decision**: Recover the exact Azure Synapse model-facing database tool contract, retain it, then implement its
behavior through a provider interface with a HANA provider.

**Rationale**: Git history shows the former `SqlDatabase` combined the tool contract with SQL
Server-specific authentication and SQL. HANA differs in token/auth support, system catalogs,
identifier quoting, limiting, pagination, and errors. Keeping those differences below the tool
surface provides continuity without pretending the engines are interchangeable.

**Rejected**: Copy the former class and replace the connection string. `TOP`, bracket quoting,
Azure SQL token injection, and SQL Server paging make this incorrect.

## R2 - Driver Selection Requires a Target Spike

**Decision**: Perform an offline packaging/licensing comparison first. After private connectivity,
a disposable read-only identity, and secret delivery exist, test SAP's Python HANA client
(`hdbcli`) and SAP HANA Client ODBC through `pyodbc` against the same target and choose from measured
TLS, authentication, parameter, cancellation, fetch, packaging, and redistribution behavior.

**Rationale**: The repository already depends on `pyodbc`, but App Service does not currently
install the SAP ODBC driver. ODBC may force a custom container. A Python package may simplify
deployment, but it must be proven against the target and approved by the SAP/database owner.

**Rejected**: Choose ODBC solely because SQL Server used it; choose `hdbcli` solely to avoid a
container. Both optimize before testing the controlling constraints.

## R3 - Separate Workstation and Azure VPN Paths

**Decision**: Developers use OpenVPN Connect with the supplied user-locked profile. Azure uses the
separately offered site-to-site IPsec VPN through Azure VPN Gateway.

**Rationale**: The profile confirms `tun`, TLS 1.2+, UDP `1194` with TCP `443` fallback,
interactive credentials, and embedded user certificate/private-key material. It is explicitly
user-locked, so it must remain a confidential workstation credential. The network owner explicitly
offers site-to-site IPsec for Azure, avoiding a user profile and TUN client in App Service.

**Rejected**: Reusing the user-locked OpenVPN profile in Azure, running OpenVPN inside App Service,
or exposing HANA publicly.

## R4 - Azure App Service Egress

**Decision**: Add regional VNet integration on a dedicated delegated subnet and route only the HANA
prefixes through Azure VPN Gateway using UDRs or propagated routes. Enable route-all only if a focused review
shows it is required and safe for existing dependencies.

**Rationale**: App Service requires VNet integration for private outbound routing. The current
Terraform has no networking resources, so this must be declared before application connectivity.

**Rejected**: App Service public outbound IP allowlisting; it bypasses the private-network goal.

## R5 - Local Windows/WSL Access

**Decision**: Install/use the organization-approved OpenVPN client on Windows with its supplied
developer profile, then verify that Windows propagates the tunnel's routes and DNS behavior to WSL.

**Rationale**: This follows the network owner's required protocol and keeps developer authentication
separate from the Azure machine tunnel. WSL behavior still must be observed because DNS and route
propagation vary with WSL and OpenVPN client modes.

**Fallback**: If the Windows OpenVPN client cannot route WSL reliably, use the approved OpenVPN
client inside WSL only if the environment supplies TUN support and permits it, otherwise use a
controlled development jump host/private runner. Never expose HANA publicly for convenience.

## R6 - Azure Site-to-Site IPsec

**Decision**: Use a route-based, highly available Azure VPN Gateway with two matching production
Google Cloud peers. Finalize BGP versus static routing and active-active implementation details from
the network-owner parameter sheet.

**Rationale**: App Service traffic originates from its VNet integration subnet and requires private
routes plus deterministic return routing. Azure VPN Gateway provides the managed site-to-site IPsec
boundary that the network owner offered.

**Open questions**: Peer address(es), IKE version and proposals, PFS/DH groups, authentication,
local/remote prefixes, BGP ASNs/peer IPs or static routes, active-active support, DPD/rekey values,
and ownership of Google Cloud routes/firewalls.

## R7 - Private DNS

**Decision**: Prefer conditional forwarding from Azure DNS Private Resolver to a Google Cloud DNS
inbound forwarding path for the HANA private zone. Make the zone owner authoritative for changes.

**Rationale**: The same hostname and certificate identity should work from App Service and WSL.
Hard-coded IPs break HA and certificate validation. A copied Azure private-zone record is a viable
short-lived proof but creates dual ownership and stale-record risk.

## R8 - Authentication and Secrets

**Decision**: Use a dedicated HANA read-only technical identity or certificate approved by the
database owner. Store production material in Azure Key Vault and access Key Vault with the existing
App Service managed identity. Use a separate developer identity/material locally.

**Rationale**: Azure managed identity can authorize retrieval from Azure Key Vault but is not, by
itself, a HANA login mechanism. Separating local and deployed credentials supports least privilege,
attribution, and independent rotation.

**Rejected**: Commit a connection string, pass a password through Terraform/azd outputs, or reuse a
personal HANA identity in production.

## R9 - Read-Only Defense in Depth

**Decision**: Enforce a single read statement and object allowlist in the application, while also
granting the HANA identity only catalog visibility and `SELECT` on approved views/schemas.

**Rationale**: Text validation is fallible. Database authorization is the final boundary. The
application still validates early to avoid unsafe attempts and produce useful tool feedback.

**Rejected**: `query.strip().upper().startswith("SELECT")`; comments, multi-statements, anonymous
blocks, and dialect features make prefix-only validation insufficient.

## R10 - Observability Without Data Leakage

**Decision**: Record provider, correlation id, duration, row count, truncation, and sanitized error
category. Do not log credentials, full connection strings, bound values, result cells, certificate
private material, or unrestricted SQL text.

**Rationale**: Operators need to distinguish DNS, route, TCP, TLS, authn, authz, timeout, and SQL
errors. They do not need sensitive data to do so.

## R11 - Application User Authorization

**Decision**: Require both membership in an environment-specific entitled Entra group and an
agent/provider grant before exposing a HANA tool. Audit the calling application user independently
of the shared HANA technical identity.

**Rationale**: The HANA identity controls database privileges but cannot express which application
users may invoke the tool. The two controls address different boundaries and both are required.

**Rejected**: Treat possession of the shared HANA credential or selection of a HANA-enabled agent
as sufficient user authorization.

## R12 - SQL Grammar and Result Continuation

**Decision**: Use a HANA-aware parser/token validator for one read-only `SELECT`, including
read-only CTEs. Reject comments, multiple statements, mutations, DDL/DCL, session commands,
anonymous blocks, procedures, dynamic SQL, and table functions unless explicitly approved.
Bound fetches with `max_rows + 1`; use stable keyset ordering for deterministic continuation and
label unordered truncation as partial rather than complete.

**Rationale**: Prefix checks and naïve semicolon handling are not a grammar. Offset paging can
duplicate or omit changing rows, while an unordered truncated result cannot support a truthful
continuation claim.

**Rejected**: `startswith("SELECT")`, regex-only validation, unbounded materialization, and generic
offset continuation without a stable order.

## R13 - Terraform State Is a Secret Boundary

**Decision**: Verify encrypted, access-controlled remote Terraform state with locking,
retention/versioning, audit, and a PSK rotation procedure before provisioning VPN connections.
Never output the PSK. Create HANA secret containers/references in Terraform but load values through
an approved out-of-band workflow.

**Rationale**: Terraform marks `shared_key` sensitive in output, but the value remains in state.
Output redaction alone does not protect it.

**Rejected**: Local state containing production PSKs, PSK output through azd, or Terraform-managed
HANA password values.

## R14 - Required-Target Acceptance

**Decision**: Keep optional local integration tests convenient, but require
`HANA_INTEGRATION_REQUIRED=true` for environment acceptance. A collection/session plugin plus a
required sentinel test must fail missing configuration and assert at least one target test executed,
so an all-skip run exits nonzero. Bind acceptance to a configuration fingerprint and owner approvals.

**Rationale**: A green suite that did not contact the required target is not evidence of private
routing, TLS, authentication, authorization, or query behavior.

**Rejected**: Treating skipped integration tests as a deployable acceptance result.

## R15 - Initial Operational Targets

**Decision**: Start with a 10-second connection timeout, 30-second query timeout, p95 health and
bounded schema discovery within 10 seconds, p95 owner-approved representative bounded queries
within 15 seconds, and production redundant-tunnel recovery within 5 minutes. Application,
network, and HANA owners must define expected volumes and approve or replace these before implementation.

**Rationale**: Concrete initial values make timeout behavior and alerting testable while preserving
owner authority to tune them against the target service and contracted network topology.

## Unresolved Inputs

1. SAP HANA edition/version, topology, endpoint, SQL port, region, and HA behavior.
2. Exact Azure Synapse tool names/contracts; Azure Synapse remains supported alongside SAP HANA.
3. Approved HANA authentication/TLS/rotation policy.
4. Azure, OpenVPN client, and Google Cloud CIDRs plus site-to-site local/remote prefix ownership.
5. OpenVPN pushed routes/DNS, client pool, split-tunnel behavior, profile rotation, and concurrent-session policy.
6. Site-to-site IPsec peer, cryptographic, authentication, routing, DPD/rekey, and redundancy parameters.
7. Google Cloud IaC repository and network owner.
8. App Service SKU/region compatibility with VNet integration and Azure VPN Gateway.
9. Required schemas/views, data classification, representative query volume, and owner approval or replacement of the initial latency/recovery targets.
10. Environment-specific entitled Entra group object IDs and confirmation that the shared identity's readable data is suitable for each group.
11. Protected Terraform state backend evidence and PSK rotation owner.
