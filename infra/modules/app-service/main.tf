# App Service Plan
resource "azurerm_service_plan" "app_service_plan" {
  name                = var.app_service_plan_name
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = coalesce(var.app_service_plan_tags, var.tags)

  os_type  = "Linux"
  sku_name = var.app_service_plan_sku
}

# App Service
resource "azurerm_linux_web_app" "app_service" {
  name                = var.name
  location            = var.location
  resource_group_name = var.resource_group_name
  service_plan_id     = azurerm_service_plan.app_service_plan.id
  tags                = coalesce(var.app_service_tags, var.tags)

  https_only = true

  identity {
    type = "UserAssigned"
    identity_ids = [
      var.managed_identity_id
    ]
  }

  site_config {
    always_on           = true
    websockets_enabled  = true
    ftps_state          = "Disabled"
    minimum_tls_version = "1.2"

    application_stack {
      python_version = var.python_version
    }

    app_command_line = "python -m uvicorn main:app --host 0.0.0.0 --port 8000"
  }

  app_settings = {
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
    AZURE_CLIENT_ID                = var.managed_identity_client_id
    WEBSITES_PORT                  = "8000"

    # Azure OpenAI settings
    AZURE_OPENAI_ENDPOINT    = var.azure_openai_endpoint
    AZURE_OPENAI_MODEL       = var.azure_openai_model
    AZURE_OPENAI_API_KEY     = var.azure_openai_api_key
    AZURE_OPENAI_API_VERSION = var.azure_openai_api_version

    # Azure SQL settings
    AZURE_SQL_CONNECTIONSTRING = var.azure_sql_connectionstring

    # Azure AI Search settings
    SEARCH_SERVICE_ENDPOINT = var.search_service_endpoint
    SEARCH_INDEX_NAME       = var.search_index_name
    SEARCH_API_KEY          = var.search_api_key

    # Azure Cosmos DB (durable agent memory + per-user chat history)
    AZURE_COSMOS_ENDPOINT                = var.azure_cosmos_endpoint
    AZURE_COSMOS_DATABASE_NAME           = var.azure_cosmos_database_name
    AZURE_COSMOS_CONTAINER_NAME          = var.azure_cosmos_container_name
    AZURE_COSMOS_CONVERSATIONS_CONTAINER = var.azure_cosmos_conversations_container
    AZURE_COSMOS_SKILLS_CONTAINER        = var.azure_cosmos_skills_container

    # Autonomous Mode (in-process scheduler + Duty Officer). An empty
    # AUTONOMOUS_SCHEDULER_ENABLED means "enabled" in the deployed App Service.
    AZURE_COSMOS_AUTONOMOUS_CONTAINER = var.azure_cosmos_autonomous_container
    AZURE_COSMOS_LEASES_CONTAINER     = var.azure_cosmos_leases_container
    AZURE_COSMOS_DIRECTIVES_CONTAINER = var.azure_cosmos_directives_container
    AUTONOMOUS_SCHEDULER_ENABLED      = var.autonomous_scheduler_enabled

    # Entra ID / Azure AD authentication
    OAUTH_AZURE_GOV_AD_TENANT_ID = var.entra_tenant_id
    OAUTH_AZURE_GOV_AD_CLIENT_ID = var.entra_client_id

    # Branding / application configuration
    CLASSIFICATION_BANNER = var.classification_banner
    APP_NAME              = var.app_name
    APP_TAGLINE           = var.app_tagline
    APP_LOGO              = var.app_logo
  }

  logs {
    detailed_error_messages = true
    failed_request_tracing  = true

    http_logs {
      file_system {
        retention_in_days = 1
        retention_in_mb   = 35
      }
    }

    application_logs {
      file_system_level = "Verbose"
    }
  }
}
