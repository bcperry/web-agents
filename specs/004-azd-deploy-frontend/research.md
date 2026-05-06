# Research: AZD Deploy with Correct Infra & Env Variables

**Feature**: 004-azd-deploy-frontend | **Date**: 2026-04-24

## 1. azd up with Terraform Provider

**Decision**: `azd` uses `infra/main.tfvars.json` as a template file for Terraform.

**Rationale**: When `infra.provider: terraform` is set in `azure.yaml`, azd:
1. Reads `infra/main.tfvars.json` as a template
2. Substitutes `${VARIABLE}` references from `.azure/<env>/.env`
3. Writes resolved file to `.azure/<env-name>/infra/main.tfvars.json`
4. Runs `terraform plan -var-file=<resolved>` → `terraform apply`
5. Reads `terraform output -json` and writes every output back to `.env`

The `infra.parameters` block in `azure.yaml` may be Bicep-specific — for Terraform,
`main.tfvars.json` is the actual source of truth. Keep the parameters block for
documentation but ensure `main.tfvars.json` matches.

**Required outputs for `azd deploy`**:
- Resource tagged `azd-service-name = "web"` (already present)
- `AZURE_RESOURCE_GROUP` output (already present)

**Alternatives considered**: Bicep (native azd support) — rejected, team uses Terraform.

## 2. App Service app_settings for Auth Variables

**Decision**: Pass Entra ID (tenant ID, client ID) as `app_settings`. Mark only
`client_secret` as `sensitive = true`.

**Rationale**: Tenant ID and client ID are public identifiers (visible in OIDC
metadata, OAuth redirects). Not sensitive. Client secret is a credential.
App Service stores all app_settings encrypted at rest.

**Gap found**: `main.tfvars.json.startexample` references `entra_client_id`,
`entra_tenant_id`, `entra_client_secret` but these are not defined in `variables.tf`
or passed to the app-service module.

**Alternatives considered**: Key Vault references for secrets — good practice but
adds complexity beyond current scope.

## 3. Frontend Build During Deploy

**Decision**: Use a `prepackage` service hook in `azure.yaml` to run
`cd frontend && npm install && npm run build` before packaging.

**Rationale**: `SCM_DO_BUILD_DURING_DEPLOYMENT` (Oryx) handles Python deps but does
NOT auto-detect or build frontend assets. Node.js is available in the container but
must be invoked explicitly.

The `prepackage` hook runs locally before zip creation, so:
- Errors caught early (not on remote server)
- Built `frontend/dist/` is included in the deployment zip
- Faster than remote build

**Alternatives considered**:
- Oryx `PRE_BUILD_COMMAND` app_setting — slower (remote build), longer deploy
- Root `predeploy` hook — too broad

## 4. azd Environment Variables

**Decision**: `${VARIABLE}` references resolve from `.azure/<env>/.env`. Users
populate via `azd env set`.

**Auto-set by azd**: `AZURE_ENV_NAME`, `AZURE_LOCATION`, `AZURE_SUBSCRIPTION_ID`,
`AZURE_PRINCIPAL_ID`, `AZURE_TENANT_ID`

**User setup flow**:
```bash
azd env new myenv
azd env set AZURE_LOCATION "usgovvirginia"
azd env set EXISTING_RESOURCE_GROUP_NAME "rg-my-group"
azd env set AZURE_OPENAI_ENDPOINT "https://..."
# ... etc for each variable
azd up
```

## 5. Gaps Identified

| Gap | File(s) | Resolution |
|-----|---------|------------|
| Missing Entra ID variables | `variables.tf`, app-service `variables.tf` | Add `entra_client_id`, `entra_tenant_id`, `entra_client_secret` |
| Missing auth app_settings | app-service `main.tf` | Add `OAUTH_AZURE_GOV_AD_TENANT_ID`, `OAUTH_AZURE_GOV_AD_CLIENT_ID` |
| Missing branding app_settings | app-service `main.tf` | Add `CLASSIFICATION_BANNER`, `APP_NAME`, `APP_TAGLINE`, `APP_LOGO` |
| No frontend build hook | `azure.yaml` | Add `prepackage` hook |
| Missing `main.tfvars.json` | `infra/` | Create from example template (required by azd) |
| tfvars examples outdated | `infra/*.example` | Add auth/branding vars |
| `infra.parameters` possibly ignored | `azure.yaml` | Keep for docs, ensure tfvars matches |
| Verify `uv.lock` committed | repo root | Check and commit if missing |
