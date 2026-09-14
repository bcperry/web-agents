output "AZURE_LOCATION" {
  description = "The location of the resources"
  value       = local.resource_group_location
}

output "AZURE_TENANT_ID" {
  description = "The Azure tenant ID"
  value       = data.azurerm_client_config.current.tenant_id
}

output "RESOURCE_GROUP_ID" {
  description = "The ID of the resource group"
  value       = var.existing_resource_group_name != "" ? data.azurerm_resource_group.existing[0].id : azurerm_resource_group.rg[0].id
}

output "RESOURCE_GROUP_NAME" {
  description = "The name of the resource group"
  value       = local.resource_group_name
}

# This is the magic output name that azd deploy uses to find the resource group
output "AZURE_RESOURCE_GROUP" {
  description = "The name of the resource group (for azd deploy)"
  value       = local.resource_group_name
}

output "WEB_APP_NAME" {
  description = "The name of the web app"
  value       = module.app_service.app_service_name
}

output "WEB_APP_URL" {
  description = "The URL of the web app"
  value       = module.app_service.app_service_url
}

output "AZURE_COSMOS_ENDPOINT" {
  description = "The Cosmos DB account endpoint"
  value       = module.cosmos.endpoint
}

output "AZURE_COSMOS_ACCOUNT_NAME" {
  description = "The Cosmos DB account name"
  value       = module.cosmos.account_name
}

output "MANAGED_IDENTITY_PRINCIPAL_ID" {
  description = "The principal ID of the App Service system-assigned managed identity"
  value       = module.app_service.system_assigned_principal_id
}

# Persist commonly used application configuration inputs via outputs
output "AZURE_OPENAI_ENDPOINT" {
  description = "Azure OpenAI endpoint URL"
  value       = var.azure_openai_endpoint
}

output "AZURE_OPENAI_MODEL" {
  description = "Azure OpenAI model deployment name"
  value       = var.azure_openai_model
}

output "AZURE_OPENAI_RESOURCE_ID" {
  description = "Azure OpenAI account resource ID"
  value       = var.azure_openai_resource_id
}

output "AZURE_OPENAI_API_VERSION" {
  description = "Azure OpenAI API version"
  value       = var.azure_openai_api_version
}

output "AZURE_SQL_CONNECTIONSTRING" {
  description = "Azure SQL connection string (empty indicates managed identity)"
  value       = var.azure_sql_connectionstring
  sensitive   = true
}

# Emitted under its own name: azd writes outputs back into the environment, so
# aliasing a computed value onto a user-set input would feed it back to Terraform.
output "SAP_EMULATOR_CONNECTIONSTRING" {
  description = "Passwordless ODBC connection string for the SAP emulator; null when disabled"
  value       = local.sap_emulator_enabled ? module.sap_emulator[0].connection_string : null
  sensitive   = true
}

output "SAP_EMULATOR_SERVER_FQDN" {
  description = "Azure SQL SAP emulator server FQDN; null when disabled"
  value       = local.sap_emulator_enabled ? module.sap_emulator[0].server_fqdn : null
}

output "SAP_EMULATOR_DATABASE_NAME" {
  description = "Azure SQL SAP emulator database name; null when disabled"
  value       = local.sap_emulator_enabled ? module.sap_emulator[0].database_name : null
}

output "SEARCH_SERVICE_ENDPOINT" {
  description = "Azure AI Search service endpoint"
  value       = var.search_service_endpoint
}

output "SEARCH_INDEX_NAME" {
  description = "Azure AI Search index name"
  value       = var.search_index_name
}

output "SEARCH_API_KEY" {
  description = "Azure AI Search API key (empty indicates managed identity)"
  value       = var.search_api_key
  sensitive   = true
}
