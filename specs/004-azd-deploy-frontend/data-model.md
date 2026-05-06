# Data Model: AZD Deploy with Correct Infra & Env Variables

**Feature**: 004-azd-deploy-frontend | **Date**: 2026-04-24

This feature is infrastructure-only. No application data models are added or changed.
The "entities" here are Terraform variables and App Service app_settings.

## Entity: Terraform Variables (new additions)

These are new variables to add to the Terraform configuration. They map to environment
variables the application reads at runtime.

### Auth Variables

| Variable | Type | Sensitive | Default | Maps to App Setting |
|----------|------|-----------|---------|-------------------|
| `entra_tenant_id` | string | no | `""` | `OAUTH_AZURE_GOV_AD_TENANT_ID` |
| `entra_client_id` | string | no | `""` | `OAUTH_AZURE_GOV_AD_CLIENT_ID` |
| `entra_client_secret` | string | yes | `""` | `ENTRA_CLIENT_SECRET` (reserved, not currently used by app) |

### Branding/Config Variables

| Variable | Type | Sensitive | Default | Maps to App Setting |
|----------|------|-----------|---------|-------------------|
| `classification_banner` | string | no | `"UNCLASSIFIED"` | `CLASSIFICATION_BANNER` |
| `app_name` | string | no | `"Web-Agents"` | `APP_NAME` |
| `app_tagline` | string | no | `"AI Agent Framework"` | `APP_TAGLINE` |
| `app_logo` | string | no | `"/Microsoft.png"` | `APP_LOGO` |

## Entity: App Service app_settings (complete list)

The full set of `app_settings` the App Service should have after this change:

| Setting | Source | Already Present |
|---------|--------|----------------|
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | hardcoded `"true"` | yes |
| `AZURE_CLIENT_ID` | managed identity | yes |
| `WEBSITES_PORT` | hardcoded `"8000"` | yes |
| `AZURE_OPENAI_ENDPOINT` | variable | yes |
| `AZURE_OPENAI_MODEL` | variable | yes |
| `AZURE_OPENAI_API_KEY` | variable | yes |
| `AZURE_OPENAI_API_VERSION` | variable | yes |
| `AZURE_SQL_CONNECTIONSTRING` | variable | yes |
| `SEARCH_SERVICE_ENDPOINT` | variable | yes |
| `SEARCH_INDEX_NAME` | variable | yes |
| `SEARCH_API_KEY` | variable | yes |
| `OAUTH_AZURE_GOV_AD_TENANT_ID` | variable | **NO** |
| `OAUTH_AZURE_GOV_AD_CLIENT_ID` | variable | **NO** |
| `CLASSIFICATION_BANNER` | variable | **NO** |
| `APP_NAME` | variable | **NO** |
| `APP_TAGLINE` | variable | **NO** |
| `APP_LOGO` | variable | **NO** |

## Entity: azure.yaml Hooks

| Hook | Phase | Command |
|------|-------|---------|
| `prepackage` | Before zip packaging | `cd frontend && npm install && npm run build` |

## Entity: azd Environment Variables

Variables users must set via `azd env set` before running `azd up`:

| azd env var | Required | Notes |
|-------------|----------|-------|
| `AZURE_LOCATION` | yes | Auto-prompted by azd |
| `EXISTING_RESOURCE_GROUP_NAME` | yes | Empty string creates new RG |
| `AZURE_OPENAI_ENDPOINT` | yes | |
| `AZURE_OPENAI_MODEL` | yes | |
| `AZURE_OPENAI_API_KEY` | conditional | Empty = managed identity |
| `AZURE_OPENAI_API_VERSION` | yes | |
| `AZURE_SQL_CONNECTIONSTRING` | yes | |
| `SEARCH_SERVICE_ENDPOINT` | yes | |
| `SEARCH_INDEX_NAME` | yes | |
| `SEARCH_API_KEY` | conditional | Empty = managed identity |
| `ENTRA_TENANT_ID` | yes (for auth) | |
| `ENTRA_CLIENT_ID` | yes (for auth) | |
| `ENTRA_CLIENT_SECRET` | conditional | |
| `CLASSIFICATION_BANNER` | no | Defaults to "UNCLASSIFIED" |
| `APP_NAME` | no | Defaults to "Web-Agents" |
| `APP_TAGLINE` | no | Defaults to "AI Agent Framework" |
| `APP_LOGO` | no | Defaults to "/Microsoft.png" |
