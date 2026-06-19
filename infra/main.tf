data "azurerm_client_config" "current" {}

# Data source for existing resource group (when existing_resource_group_name is provided)
data "azurerm_resource_group" "existing" {
  count = var.existing_resource_group_name != "" ? 1 : 0
  name  = var.existing_resource_group_name
}

locals {
  tags = {
    "azd-env-name" = var.environment_name
  }

  # Use existing resource group if name is provided, otherwise use the created one
  use_existing            = var.existing_resource_group_name != ""
  resource_group_name     = local.use_existing ? data.azurerm_resource_group.existing[0].name : azurerm_resource_group.rg[0].name
  resource_group_location = local.use_existing ? data.azurerm_resource_group.existing[0].location : azurerm_resource_group.rg[0].location
}

# Resource group (only created if not using existing)
resource "azurerm_resource_group" "rg" {
  count    = local.use_existing ? 0 : 1
  name     = "rg-${var.environment_name}"
  location = var.location
  tags     = local.tags
}

# User-assigned managed identity
module "managed_identity" {
  source = "./modules/managed-identity"

  name     = "id-${var.environment_name}"
  location = local.resource_group_location
  tags     = local.tags

  resource_group_name = local.resource_group_name
}

# Azure Cosmos DB (durable agent memory + per-user chat history)
module "cosmos" {
  source = "./modules/cosmos"

  account_name        = lower("cosmos-${var.environment_name}")
  location            = local.resource_group_location
  tags                = local.tags
  resource_group_name = local.resource_group_name
  principal_id        = module.managed_identity.managed_identity_principal_id

  # Optional: grant the deploying user (AZURE_PRINCIPAL_ID) Cosmos data-plane
  # access so you can run the app locally against this live account. Toggle with
  # the ENABLE_DEV_COSMOS_ACCESS deployment env var (empty/false = not granted).
  dev_principal_id = lower(trimspace(var.enable_dev_cosmos_access)) == "true" ? var.principal_id : ""
}

# App Service Plan and App Service
module "app_service" {
  source = "./modules/app-service"

  name                       = "app-${var.environment_name}"
  location                   = local.resource_group_location
  app_service_tags           = merge(local.tags, { "azd-service-name" = "web" })
  app_service_plan_tags      = local.tags
  app_service_plan_name      = "asp-${var.environment_name}"
  app_service_plan_sku       = var.app_service_plan_sku
  python_version             = var.python_version
  managed_identity_id        = module.managed_identity.managed_identity_id
  managed_identity_client_id = module.managed_identity.managed_identity_client_id

  resource_group_name = local.resource_group_name

  # Application environment variables
  azure_openai_endpoint      = var.azure_openai_endpoint
  azure_openai_model         = var.azure_openai_model
  azure_openai_api_key       = var.azure_openai_api_key
  azure_openai_api_version   = var.azure_openai_api_version
  azure_sql_connectionstring = var.azure_sql_connectionstring
  search_service_endpoint    = var.search_service_endpoint
  search_index_name          = var.search_index_name
  search_api_key             = var.search_api_key

  # Azure Cosmos DB (durable agent memory)
  azure_cosmos_endpoint                = module.cosmos.endpoint
  azure_cosmos_database_name           = module.cosmos.database_name
  azure_cosmos_container_name          = module.cosmos.messages_container_name
  azure_cosmos_conversations_container = module.cosmos.conversations_container_name
  azure_cosmos_skills_container        = module.cosmos.skills_container_name

  # Autonomous Mode (in-process scheduler + Duty Officer audit/lease containers)
  azure_cosmos_autonomous_container = module.cosmos.autonomous_container_name
  azure_cosmos_leases_container     = module.cosmos.leases_container_name
  azure_cosmos_directives_container = module.cosmos.directives_container_name
  autonomous_scheduler_enabled      = var.autonomous_scheduler_enabled

  # Entra ID / Azure AD authentication
  entra_tenant_id     = var.entra_tenant_id
  entra_client_id     = var.entra_client_id
  entra_client_secret = var.entra_client_secret

  # Branding / application configuration
  classification_banner = var.classification_banner
  app_name              = var.app_name
  app_tagline           = var.app_tagline
  app_logo              = var.app_logo
}
