# Quickstart: AZD Deploy

**Feature**: 004-azd-deploy-frontend | **Date**: 2026-04-24

## Prerequisites

- [Azure Developer CLI (azd)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) installed
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.0 installed
- Node.js >= 18 (for frontend build)
- Python 3.12+ with `uv` (for backend)
- Azure Government subscription with appropriate permissions

## Deploy

### 1. Initialize azd environment

```bash
azd auth login --tenant-id <your-tenant-id>
azd env new <env-name>
```

### 2. Set required environment variables

```bash
# Location
azd env set AZURE_LOCATION "usgovvirginia"

# Resource group (empty string to create new, or name of existing)
azd env set EXISTING_RESOURCE_GROUP_NAME ""

# Azure OpenAI
azd env set AZURE_OPENAI_ENDPOINT "https://<your-endpoint>.openai.azure.us/"
azd env set AZURE_OPENAI_MODEL "<deployment-name>"
azd env set AZURE_OPENAI_API_KEY ""  # empty for managed identity
azd env set AZURE_OPENAI_API_VERSION "2024-02-15-preview"

# Azure SQL
azd env set AZURE_SQL_CONNECTIONSTRING "Driver={ODBC Driver 18 for SQL Server};Server=tcp:<server>.database.usgovcloudapi.net,1433;Database=<db>;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;Authentication=ActiveDirectoryMsi"

# Azure AI Search
azd env set SEARCH_SERVICE_ENDPOINT "https://<endpoint>.search.azure.us"
azd env set SEARCH_INDEX_NAME "<index-name>"
azd env set SEARCH_API_KEY ""  # empty for managed identity

# Entra ID Auth
azd env set ENTRA_TENANT_ID "<your-tenant-id>"
azd env set ENTRA_CLIENT_ID "<your-app-registration-client-id>"
azd env set ENTRA_CLIENT_SECRET ""  # optional

# Branding (optional, these have defaults)
# azd env set CLASSIFICATION_BANNER "UNCLASSIFIED"
# azd env set APP_NAME "Web-Agents"
# azd env set APP_TAGLINE "AI Agent Framework"
# azd env set APP_LOGO "/Microsoft.png"
```

### 3. Provision and deploy

```bash
azd up
```

This will:
1. Run `terraform plan` and `terraform apply` to provision App Service + Managed Identity
2. Build the frontend (`npm install && npm run build` via prepackage hook)
3. Package and deploy the app to Azure App Service

### 4. Verify

```bash
azd env get-values | grep WEB_APP_URL
# Open the URL in a browser
```

## Redeploy (code changes only)

```bash
azd deploy
```

## Teardown

```bash
azd down
```
