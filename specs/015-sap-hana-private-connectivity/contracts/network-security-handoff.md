# Contract: Network and Security Handoff

This artifact is the required input contract between the application/Azure team, Google Cloud
network owner, HANA owner, and security owner. Unknown values block the dependent phase.

## Workstation OpenVPN - Confirmed

| Field | Value/Status |
|-------|--------------|
| Client | OpenVPN Connect on Windows |
| Profile | Confidential, user-locked, workstation-only; ignored by Git and mode `0600` in WSL |
| Tunnel | `tun` |
| Minimum TLS | 1.2 |
| Transport | UDP `1194`, TCP `443` fallback |
| Authentication | User-locked inline client certificate/key plus interactive username/password |
| Observed client pool | `172.27.240.0/20` during the 2026-08-06 test; network owner must confirm stability |
| WSL traversal | Confirmed to a VPN-routed TCP endpoint through the Windows tunnel |

Still required: HANA route/prefix, pushed DNS behavior for its private zone, profile revocation and
rotation process, concurrent-session policy, and whether the observed client pool is contractual.

## Azure Site-to-Site IPsec - Required Inputs

| Field | Owner | Required Value |
|-------|-------|----------------|
| Google Cloud peer public IPs | Network owner | Two production static peers supporting required failover. |
| Azure VNet CIDR | Azure owner | Non-overlapping approved prefix. |
| App integration subnet | Azure owner | Dedicated `/26` planning default. |
| `GatewaySubnet` | Azure owner | Dedicated `/27` or larger. |
| Google Cloud/HANA prefixes | Network/HANA owner | Exact remote routes, not an unrestricted default route. |
| IKE version and lifetime | Network owner | Azure-compatible policy. |
| Encryption/integrity | Network owner | IKE and IPsec algorithms. |
| DH/PFS groups | Network owner | Azure-compatible groups. |
| Authentication | Network/security owner | PSK exchange workflow or approved certificate method. |
| Routing | Both network owners | BGP ASN/peer IPs or static prefixes. |
| DPD/rekey | Network owner | Timers and expected recovery behavior. |
| Redundancy | Both network owners | Production active-active peer/connection count and supported failure cases. |
| Return route | Google Cloud owner | Route to the App integration subnet through the VPN. |
| Firewall | Google Cloud owner | App integration subnet -> exact HANA IP/port only. |

### Terraform State Gate

The IPsec connection must not be applied until the Terraform state backend is documented and
verified for encryption at rest, least-privilege access, locking, versioning/retention, and audit.
If a PSK enters Terraform configuration, it remains in state even when marked sensitive. Never add
it to `azure.yaml`, `main.tfvars.json`, Terraform outputs, azd outputs, logs, or source control.

The approved apply workflow must inject the PSK from a protected secret store into an ephemeral
runner environment variable or provider-supported secure input, disable shell tracing, avoid saved
plan files unless encrypted and access-controlled, redact CI logs, prohibit plan/cache artifacts
from ordinary retention, clear the environment/workspace after apply, and restrict state backup and
recovery access. The owner must document rotation as coordinated replacement of both peer values,
Terraform apply/state verification, tunnel validation, old-key revocation, and rollback without
printing either key.

## HANA Endpoint and Identity - Required Inputs

| Field | Owner | Required Value |
|-------|-------|----------------|
| Product/version/topology | HANA owner | HANA version, tenant/system database, HA endpoints. |
| Private FQDN and SQL port | HANA owner | Certificate-valid endpoint reachable through private routes. |
| TLS | HANA/security owner | Required mode, server name, CA chain, protocol/cipher requirements. |
| Authentication | HANA/security owner | Technical password, X.509, LDAP/Kerberos, or approved alternative. |
| Identity grants | HANA owner | Read-only approved data surface and required catalog metadata. |
| Rotation | HANA/security owner | Issuance, storage, expiry monitoring, rotation, revocation, rollback. |
| Data classification | Data owner | Confirms all rows readable by the shared identity are suitable for the entitled Entra groups. |

## DNS

Preferred: Azure DNS Private Resolver outbound endpoint and conditional forwarding to Google Cloud
DNS inbound forwarders for the HANA private zone.

Required values: private zone suffix, Google Cloud inbound forwarder IPs, source prefixes accepted
by Google Cloud DNS, expected records/TTL, and DNS owner. An Azure private-zone record is permitted
only as a non-production temporary fallback with an owner, expiry, automated comparison to the
authoritative Google Cloud record, and a removal gate before production.

## Key Vault Contract

- Terraform creates or references the vault and grants the existing user-assigned managed identity
  only the secret/certificate read permissions required by the selected HANA auth method.
- An authorized out-of-band workflow writes and rotates the secret/certificate value.
- App Service receives only a Key Vault reference or secret URI, never a Terraform secret output.
- HANA secret names and URIs may be configuration; values must never be in Terraform outputs,
  `azure.yaml`, `main.tfvars.json`, application logs, or frontend responses.

## Acceptance Evidence

Each environment requires the RFC 8785-canonicalized, Key Vault `RS256`-signed JSON envelope defined
in `data-model.md` at `specs/015-sap-hana-private-connectivity/acceptance/<environment>.json`, with
status, issue/expiry, canonical configuration fingerprint, exact role-based decisions, and typed
protected evidence references/digests. Only configured versioned signing-key IDs are trusted.
The fingerprint covers non-secret provider/network/DNS/TLS settings, code revision, driver/version,
grant definitions, and entitled group IDs. Each environment also requires: approved parameter sheet, Terraform plans from both cloud owners,
effective-route evidence, tunnel/IKE status, DNS resolution, TCP/TLS proof, HANA auth/read proof,
direct write-denial proof, mandatory non-skipped integration results, and named approvers. Production
also requires credential-rotation and redundant-tunnel failover/recovery evidence. Code, driver,
configuration, grant, or group changes and artifact expiry revoke acceptance until applicable tests
and signatures are renewed.