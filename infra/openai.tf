resource "azurerm_cognitive_account" "foundry" {
  name                          = "foundry-${var.environment_name}-luna"
  location                      = local.resource_group_location
  resource_group_name           = local.resource_group_name
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = "foundry-${var.environment_name}-luna"
  project_management_enabled    = true
  local_auth_enabled            = false
  public_network_access_enabled = true
  tags                          = local.tags

  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_cognitive_account_project" "agents" {
  depends_on = [azurerm_cognitive_deployment.foundry_luna]

  name                 = "web-agents"
  display_name         = "Web Agents"
  cognitive_account_id = azurerm_cognitive_account.foundry.id
  location             = local.resource_group_location

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_deployment" "foundry_luna" {
  name                 = "gpt-5.6-luna"
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = "gpt-5.6-luna"
    version = "2026-07-09"
  }

  sku {
    name     = "DataZoneStandard"
    capacity = 10
  }
}
