# Feature Specification: SAP HANA Private Connectivity

**Feature Branch**: `015-sap-hana-private-connectivity`  
**Created**: 2026-07-27  
**Status**: Planning Draft  
**Input**: Connect the existing read-only database-agent experience used for the Azure Synapse database to a privately hosted SAP HANA database in Google Cloud, from both local WSL development and the Azure-hosted application.

## Scope

### In Scope

- A reusable read-only database tool contract that can target SAP HANA without exposing credentials or vendor-specific details to the model.
- Continued availability of the existing Azure Synapse integration alongside SAP HANA.
- Private network access from the Azure-hosted backend to the Google Cloud VPC that contains SAP HANA through the offered site-to-site IPsec VPN.
- Private network access from the developer's Windows/WSL workstation to the same HANA endpoint using an OpenVPN client profile.
- SAP HANA client/driver packaging, TLS, authentication, schema discovery, query validation, bounded results, diagnostics, and operational verification.
- Terraform-managed Azure networking and an explicitly owned Google Cloud networking workstream.
- A phased rollout that proves routing and database access before enabling HANA tools on an agent.

### Out of Scope

- Publicly exposing SAP HANA or allowlisting the Azure application's public egress IP.
- Database writes, DDL, stored-procedure execution, or broad catalog access.
- Migrating data between Azure Synapse and SAP HANA.
- Building a general-purpose database administration interface.
- Assuming Azure managed identity can authenticate directly to SAP HANA; HANA authentication is a separate credential boundary.

## Clarifications

### Session 2026-07-27

- Q: What OpenVPN connectivity does the Google Cloud environment provide? → A: Not yet confirmed with the network owner.
- Q: Which existing database integration should the plan reference? → A: Azure Synapse.
- Q: Should SAP HANA supplement or replace the existing Azure Synapse integration? → A: Add SAP HANA and retain Azure Synapse.
- Q: How should the Azure application authenticate to SAP HANA? → A: Not yet confirmed with the HANA owner.
- Q: What HANA data surface should agents be allowed to query? → A: All objects readable by the HANA identity by default; an approved-schema allowlist can restrict access.

### Session 2026-08-06

- Q: What VPN access methods are available? → A: Workstations use a confidential user-locked OpenVPN profile; Azure may connect site-to-site using IPsec.

## User Scenarios & Testing

### User Story 1 - Query HANA Through Existing Agent Tools (Priority: P1)

As an authorized user, I want the database-enabled agent to inspect approved HANA schemas and run read-only queries using the same interaction pattern as the Azure Synapse database tools.

**Independent Test**: From a test agent with only the HANA database tools enabled, discover one object readable by the HANA identity and execute a bounded `SELECT` against it; then configure an approved-schema override and verify discovery/query access is narrowed while no write-capable statement can execute.

**Acceptance Scenarios**:

1. **Given** a configured HANA connection without a schema override, **When** the schema tool runs, **Then** it returns bounded metadata only for objects readable by the HANA identity.
2. **Given** an approved-schema allowlist override, **When** discovery or query runs, **Then** only readable objects in the configured schemas are accessible.
3. **Given** a valid `SELECT` against an accessible object, **When** the query tool runs, **Then** it returns bounded rows with explicit truncation guidance.
4. **Given** a mutation, DDL, multi-statement payload, procedure call, or schema excluded by the configured allowlist, **When** the query tool receives it, **Then** validation rejects it before database execution.
5. **Given** an agent without the database tools configured, **When** a session starts, **Then** no HANA query capability is available.

---

### User Story 2 - Develop Locally Over Private Networking (Priority: P1)

As a developer using Windows with WSL, I want to connect privately to HANA without exposing the database to the internet or storing production credentials in the repository.

**Independent Test**: Connect the workstation with the approved OpenVPN client/profile, confirm the HANA private name resolves from WSL, open a TCP/TLS connection to the HANA SQL port, and run a read-only smoke query with a developer-scoped HANA identity.

**Acceptance Scenarios**:

1. **Given** an authenticated VPN client, **When** it connects, **Then** routes for the required Google Cloud subnet and DNS suffix are available to Windows and WSL.
2. **Given** a disconnected VPN client, **When** the developer attempts the same connection, **Then** the private HANA endpoint is unreachable.
3. **Given** local configuration, **When** the app starts, **Then** credentials come from ignored environment configuration or an approved local secret store and are never logged.

---

### User Story 3 - Reach HANA From Azure Hosting (Priority: P1)

As an operator, I want the deployed Azure backend to reach SAP HANA over private cross-cloud networking with deterministic routing and no public database exposure.

**Independent Test**: From the deployed backend's VNet-integrated runtime, resolve the private HANA name, connect over TLS to the SQL endpoint, and execute a health query while the public route remains closed.

**Acceptance Scenarios**:

1. **Given** the Azure-to-Google Cloud site-to-site IPsec VPN is healthy, **When** the backend connects, **Then** HANA traffic traverses App Service VNet integration, Azure VPN Gateway, and the private IPsec connection.
2. **Given** the deployed application, **When** it starts or scales, **Then** it does not run a workstation OpenVPN profile or require TUN-device privileges.
3. **Given** the site-to-site VPN is unavailable, **When** a query is attempted, **Then** the app returns a sanitized transient connectivity failure and does not fall back to public routing.

---

### User Story 4 - Operate and Audit the Integration (Priority: P2)

As an operator, I want health, latency, tunnel, and query diagnostics that distinguish network, TLS, authentication, authorization, and SQL failures without leaking sensitive data.

**Independent Test**: Exercise one failure from each boundary and verify logs/metrics identify the boundary, preserve a correlation id and duration, and redact host credentials, SQL parameters, and returned data.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST restore the historical Azure Synapse integration from the T004-approved compatibility fixtures and migration mapping, then keep Azure Synapse available while adding SAP HANA as a concurrently available provider. No currently exposed runtime database tool is assumed.
- **FR-002**: The database implementation MUST isolate provider-specific connection, quoting, metadata, pagination, and error behavior behind a provider boundary.
- **FR-003**: By default, the HANA provider MUST support discovery and bounded read-only queries for all objects readable by the configured HANA identity. An operator MUST be able to configure an approved-schema allowlist that narrows both discovery and query access; the override MUST NOT broaden database permissions.
- **FR-004**: Query validation MUST allow only one read-only query and MUST reject SQL comments or syntax that can conceal additional statements, mutation, DDL, session changes, anonymous blocks, or procedure execution.
- **FR-005**: The HANA database identity MUST be read-only and granted only the data surface approved by the HANA owner so database permissions remain the final control if application validation fails.
- **FR-006**: Results MUST honor `MAX_QUERY_RESULT_ROWS`, `MAX_QUERY_RESULT_CHARS`, and `MAX_SQL_CELL_CHARS`, and MUST clearly identify truncation.
- **FR-007**: The production HANA endpoint MUST be reachable only through private networking; no public fallback is permitted.
- **FR-008**: Azure hosting MUST use regional VNet integration and route HANA destination prefixes through a highly available Azure VPN Gateway and the offered site-to-site IPsec connection; the App Service runtime MUST NOT host a VPN client.
- **FR-009**: The workstation MUST use OpenVPN Connect with the confidential user-locked profile. The profile uses a `tun` interface, TLS 1.2 or newer, UDP `1194` with TCP `443` fallback, and interactive username/password authentication in addition to embedded client key material; Windows and WSL routing/DNS MUST both be verified.
- **FR-010**: Private DNS MUST resolve the HANA name consistently from Azure hosting and WSL without hard-coded production IPs in application configuration.
- **FR-011**: Routes and firewall rules MUST be least-privilege: only required Azure/workstation source prefixes, HANA destination addresses, SQL/TLS ports, DNS, OpenVPN UDP `1194`/TCP `443` for workstation access, and negotiated IPsec control/data traffic for Azure may pass.
- **FR-012**: Credentials and connection material MUST be stored outside source control, redacted from logs, and independently rotatable for local and deployed environments.
- **FR-013**: Terraform MUST manage all Azure resources. Google Cloud resources MUST be managed by the owning team's approved IaC repository or documented as a blocking external deliverable; no untracked portal-only production setup is acceptable.
- **FR-014**: Production deployment MUST include connection health, query duration, sanitized failure classification, VPN tunnel monitoring, and an operational rollback/disable switch.
- **FR-015**: HANA tools MUST remain opt-in per agent and disabled until network, TLS, authentication, authorization, and read-only negative tests pass in the target environment.
- **FR-016**: A HANA tool MUST be available only when the authenticated user belongs to an environment-specific entitled Entra group and the selected agent has the corresponding provider-bound grant. A shared HANA technical identity MUST NOT be treated as user authorization.
- **FR-017**: Each HANA invocation MUST audit the application user, agent, provider, environment, correlation id, duration, row count, truncation, and outcome without recording SQL parameter values, result cells, credentials, or unrestricted SQL text.
- **FR-018**: Truncated results MUST identify which limit was reached and MUST NOT imply absence or completeness. When no explicit ordering was supplied, the result MUST additionally state that the omitted rows are arbitrary and require a narrower ordered query.
- **FR-019**: Initial defaults MUST be a 10-second connection timeout and 30-second query timeout. Initial production targets are: p95 health and bounded schema-discovery completion in 10 seconds or less, p95 completion of the owner-approved representative bounded-query set in 15 seconds or less, production tunnel recovery within 5 minutes, and no unbounded fetch/materialization. Owners MUST define expected result volumes and approve or replace these values before implementation.
- **FR-020**: Environment acceptance MUST fail when HANA integration configuration is absent, all HANA integration tests skip, private routing is not proven, or required external-network/security approvals are missing.

### Discovery Gates

The following facts are required before implementation choices are finalized:

- **DG-001**: Confirm the product is SAP HANA and record edition/version, single-tenant versus system database, hostname, SQL port, Google Cloud region/VPC/subnet, and high-availability topology.
- **DG-002**: Confirm the exact Azure Synapse tool names, result contract, approved schemas/views, and representative queries so SAP HANA can implement a compatible provider contract; both providers MUST remain available.
- **DG-003**: HANA authentication is not yet confirmed. The HANA owner MUST select a dedicated technical user, X.509, LDAP/Kerberos, or another supported mechanism and assign credential issuance and rotation ownership before driver selection is finalized.
- **DG-004**: Confirm TLS mode, server certificate chain, private DNS zone, and certificate hostname.
- **DG-005**: Confirm non-overlapping Azure VNet, OpenVPN client/tunnel pools, and Google Cloud VPC CIDRs, plus IPsec local/remote prefixes, return routes, and BGP/static-routing requirements.
- **DG-006**: Confirm whether Google Cloud networking will be delivered in this repository, a separate IaC repository, or by the Google Cloud network team.
- **DG-007**: The workstation profile is confirmed as user-locked and confidential, with inline private key material, `tun`, TLS 1.2+, UDP `1194`, TCP `443` fallback, and interactive credentials. The network owner MUST still confirm pushed routes/DNS, client address pool, split-tunnel behavior, certificate/profile rotation, and concurrent-session policy.
- **DG-008**: The network owner MUST provide the site-to-site IPsec parameters for Azure: peer address(es), IKE/IPsec policy, pre-shared-key exchange process or certificate method, local/remote prefixes, BGP ASNs/peer addresses or static routes, redundancy, DPD/rekey settings, and Google Cloud firewall/return-route ownership.
- **DG-009**: Application, network, and HANA owners MUST approve or replace the initial timeout, latency, and tunnel-recovery targets in FR-019 and identify the monitoring owner/escalation path.

## Success Criteria

- **SC-001**: Both WSL and the deployed Azure backend complete DNS, TCP, TLS, authentication, and `SELECT CURRENT_TIMESTAMP FROM DUMMY` smoke checks through private paths.
- **SC-002**: All mutation, DDL, multi-statement, procedure-call, and configured schema-override bypass tests are rejected; direct mutation/DDL/procedure attempts also fail under the HANA application identity.
- **SC-003**: Query output never exceeds configured row, cell, or total character limits and reports truncation accurately.
- **SC-004**: Production site-to-site IPsec tunnel failover and recovery across redundant peers, plus workstation OpenVPN disconnect/reconnect and restored DNS/TLS/query access, are demonstrated without changing application configuration.
- **SC-005**: Logs and telemetry contain no passwords, connection strings, certificate private keys, query parameter values, or result data.
- **SC-006**: Disabling the HANA tool grant or configuration switch removes database access from new agent sessions without redeploying network infrastructure.
- **SC-007**: Users outside the entitled Entra group cannot receive HANA tools even when selecting an otherwise HANA-enabled agent; authorized invocations remain attributable to the calling application user.
- **SC-008**: A required-target acceptance command exits nonzero if HANA configuration is missing, every HANA integration test skips, or private DNS/TCP/TLS/authentication/query checks do not run successfully.