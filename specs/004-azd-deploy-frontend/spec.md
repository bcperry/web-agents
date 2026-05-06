# Feature Spec: AZD Deploy with Correct Infra & Env Variables

**ID**: 004 | **Branch**: `004-azd-deploy-frontend` | **Date**: 2026-04-24

## Problem Statement

The application needs to deploy via `azd up` to Azure App Service. The existing
Terraform infrastructure is close but has gaps:

1. **Missing auth env variables**: The App Service `app_settings` in Terraform do
   not include the Entra ID / Azure AD authentication variables that the backend
   (`auth.py`, `main.py`) requires: `OAUTH_AZURE_GOV_AD_TENANT_ID`,
   `OAUTH_AZURE_GOV_AD_CLIENT_ID`, `AZURE_AD_AUTHORITY`.
2. **Missing frontend build-time env variables injected at runtime**: The frontend
   build (Vite) bakes in `AUTH_DISABLED`, `OAUTH_AZURE_GOV_AD_TENANT_ID`,
   `OAUTH_AZURE_GOV_AD_CLIENT_ID`, `CLASSIFICATION_BANNER` at build time. In
   production the backend `/api/auth/config` endpoint serves these at runtime, but
   the App Service still needs the env vars set so the backend can serve them.
3. **Missing cosmetic/branding env vars**: `APP_NAME`, `APP_TAGLINE`, `APP_LOGO`,
   `CLASSIFICATION_BANNER` are read by the backend but not in Terraform.
4. **`azure.yaml` parameter mapping**: The `azure.yaml` needs to pass the new
   Entra ID variables through to Terraform.
5. **tfvars examples out of date**: The example files don't include the auth variables.
6. **Minimal infra**: Only App Service + Managed Identity are needed (already the case).

## Requirements

### Must Have
- App Service `app_settings` include all env vars the app reads at runtime
- `azure.yaml` maps all required env vars to Terraform variables
- `variables.tf` declares the new variables
- `azd up` successfully provisions and deploys the app
- Env vars for auth: `OAUTH_AZURE_GOV_AD_TENANT_ID`, `OAUTH_AZURE_GOV_AD_CLIENT_ID`
- Env vars for branding: `CLASSIFICATION_BANNER`, `APP_NAME`, `APP_TAGLINE`, `APP_LOGO`

### Should Have
- Updated tfvars example files
- Variables have sensible defaults where appropriate

### Won't Have
- Additional Azure resources beyond App Service + Managed Identity
- Changes to application code (only infra/config changes)
