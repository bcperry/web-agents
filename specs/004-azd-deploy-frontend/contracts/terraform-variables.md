# Terraform Variable Contract

This documents the complete set of Terraform input variables required for `azd up`
deployment. Variables are supplied via `main.tfvars.json` (template with `${VAR}`
references resolved by azd from `.azure/<env>/.env`).

## Required Variables

| Variable | Type | Sensitive | Source |
|----------|------|-----------|--------|
| `environment_name` | string | no | `${AZURE_ENV_NAME}` (auto) |
| `location` | string | no | `${AZURE_LOCATION}` (auto) |
| `existing_resource_group_name` | string | no | `${EXISTING_RESOURCE_GROUP_NAME}` |
| `azure_openai_endpoint` | string | no | `${AZURE_OPENAI_ENDPOINT}` |
| `azure_openai_model` | string | no | `${AZURE_OPENAI_MODEL}` |
| `azure_openai_api_key` | string | yes | `${AZURE_OPENAI_API_KEY}` |
| `azure_openai_api_version` | string | no | `${AZURE_OPENAI_API_VERSION}` |
| `azure_sql_connectionstring` | string | yes | `${AZURE_SQL_CONNECTIONSTRING}` |
| `search_service_endpoint` | string | no | `${SEARCH_SERVICE_ENDPOINT}` |
| `search_index_name` | string | no | `${SEARCH_INDEX_NAME}` |
| `search_api_key` | string | yes | `${SEARCH_API_KEY}` |
| `entra_tenant_id` | string | no | `${ENTRA_TENANT_ID}` |
| `entra_client_id` | string | no | `${ENTRA_CLIENT_ID}` |
| `entra_client_secret` | string | yes | `${ENTRA_CLIENT_SECRET}` |

## Optional Variables (have defaults)

| Variable | Type | Default | Source |
|----------|------|---------|--------|
| `principal_id` | string | `""` | `${AZURE_PRINCIPAL_ID}` |
| `subscription_id` | string | `""` | `${AZURE_SUBSCRIPTION_ID}` |
| `app_service_plan_sku` | string | `"B1"` | hardcoded or override |
| `python_version` | string | `"3.12"` | hardcoded or override |
| `classification_banner` | string | `"UNCLASSIFIED"` | `${CLASSIFICATION_BANNER}` |
| `app_name` | string | `"Web-Agents"` | `${APP_NAME}` |
| `app_tagline` | string | `"AI Agent Framework"` | `${APP_TAGLINE}` |
| `app_logo` | string | `"/Microsoft.png"` | `${APP_LOGO}` |
