# Verification Runbook: SAP HANA Private Connectivity

This is a planning runbook. Commands use placeholders and must not be run with production secrets
in command history. The final implementation should provide `scripts/verify_hana_connectivity.py`
so checks do not require echoing credentials.

## 1. Collect Inputs

Record these in the approved secret/configuration systems, not in this document:

- HANA private FQDN, SQL port, database/tenant, version, TLS CA chain, and certificate hostname.
- Approved schema/view allowlist and read-only local/production identities.
- Entitled Entra group object IDs for each environment and confirmation that every row readable by
  the shared HANA identity is suitable for those groups.
- Azure VNet/integration/gateway CIDRs, OpenVPN client/tunnel pools, and Google Cloud VPC/HANA CIDRs.
- Confirmed workstation OpenVPN endpoint/profile details plus pushed routes/DNS, client pool,
  split-tunnel behavior, certificate/profile lifecycle, and concurrent-session policy.
- Site-to-site IPsec peer addresses, IKE/IPsec policy, authentication exchange process, local/remote
  prefixes, BGP/static routes, DPD/rekey settings, and redundancy.
- Azure and Google Cloud network owners, maintenance window, and escalation contacts.
- Confirmed Azure Synapse tool names, sample requests/results, and representative SQL.

## 2. Layered Local Check

1. Confirm the confidential profile is owner-readable only (`chmod 600` in WSL), import it into
  OpenVPN Connect on Windows, and connect with the separately supplied password.
2. Verify the expected GCP and DNS routes in Windows and WSL.
3. From WSL, resolve the HANA private FQDN.
4. Open TCP to the configured SQL port.
5. Validate the server certificate chain and hostname.
6. Use the selected client with the developer identity to run:

```sql
SELECT CURRENT_TIMESTAMP FROM DUMMY
```

7. Run one approved-view query with a small limit.
8. Disconnect the VPN and prove the endpoint is no longer reachable.

Do not use `ping` as the acceptance test; ICMP may be intentionally blocked. DNS, TCP, TLS, and a
read-only SQL query are the meaningful layers.

## 3. Layered Azure Check

Run the same DNS/TCP/TLS/query probe from the VNet-integrated application runtime or an approved
test workload in the same route domain. Confirm the observed source prefix is the App Service
integration subnet, not a public App Service egress address.

Verify:

- App Service VNet integration is healthy.
- The effective route for the HANA prefix points to Azure VPN Gateway.
- The site-to-site IPsec connection is established with the agreed policy.
- Google Cloud has deterministic return routes for the App integration subnet.
- Firewall logs show only the intended source prefixes and HANA destination/port.

## 4. Read-Only Negative Checks

With the exact application HANA identity, verify that direct attempts to perform each category fail:

- `INSERT`, `UPDATE`, `DELETE`, and `MERGE`.
- `CREATE`, `ALTER`, `DROP`, and `TRUNCATE`.
- Procedure execution and anonymous blocks.
- Reads outside the HANA identity's database grants.
- Access to unnecessary system/catalog details.

Then verify the application rejects these payloads before execution, including multi-statements and
comment-obfuscated variants. When an approved-schema override is configured, separately verify the
application rejects readable database objects outside that narrower override; direct database access
to those objects may still succeed because the override does not change HANA grants.

## 5. Failover and Failure Classification

In an approved maintenance window:

1. Disable one site-to-site tunnel and confirm routing converges to the redundant tunnel where redundancy is supported.
2. Restore it and confirm IPsec security associations and routes recover without application changes.
3. Test a bad DNS name, blocked route/port, untrusted certificate, expired/invalid credential,
   unauthorized object, query timeout, and result truncation.
4. Verify user-facing errors are sanitized and logs identify only the failure category, duration,
   provider, and correlation id.

## 6. Focused Test Commands

Expected implementation commands:

```bash
uv run pytest -q \
  tests/test_database_validation.py \
  tests/test_database_hana.py \
  tests/test_database_tools.py

# Developer convenience: may skip when no private target is configured.
uv run pytest -q -m hana_integration tests/test_hana_integration.py

# Environment acceptance: collection/session sentinel MUST report >0 executed target tests and
# fail if configuration is absent or every target test skips.
HANA_INTEGRATION_REQUIRED=true uv run pytest -q -m hana_integration \
  tests/test_hana_integration.py

terraform -chdir=infra init
terraform -chdir=infra fmt -check
terraform -chdir=infra validate
terraform -chdir=infra plan -var-file=<approved-environment.tfvars>
```

The integration marker must auto-skip unless an explicitly configured private HANA test endpoint is
available. It must never print environment values or secrets on skip/failure.

## 7. Release Gate

Do not grant HANA tools to a production agent until all of the following are attached to the change:

- Network diagram and non-overlapping address plan.
- Azure and Google Cloud Terraform plans or linked owned change records.
- Successful local and Azure layered probes.
- HANA role/grant review and negative-test evidence.
- Driver packaging/licensing decision.
- Tunnel failover evidence and monitoring alerts.
- Credential rotation and rollback runbooks.
- Representative Azure Synapse-to-HANA tool contract comparison.
- Approved constitution amendment and protected Terraform state evidence.
- Entitled-group authorization denial/allow tests and metadata-only audit-log checks.
- Mandatory HANA integration run showing target tests executed rather than skipped.
- Passing database-tool evaluation pipeline results; agent behavior changes make this mandatory.
- Signed, current acceptance manifest whose fingerprint matches the deployed environment.
