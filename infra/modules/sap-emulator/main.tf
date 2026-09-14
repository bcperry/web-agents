resource "azurerm_mssql_server" "this" {
  name                = var.server_name
  resource_group_name = var.resource_group_name
  location            = var.location
  version             = "12.0"

  minimum_tls_version                  = "1.2"
  public_network_access_enabled        = var.public_network_access_enabled
  outbound_network_restriction_enabled = false
  express_vulnerability_assessment_enabled = true

  azuread_administrator {
    login_username              = var.azuread_admin_login
    object_id                   = var.azuread_admin_object_id
    tenant_id                   = var.tenant_id
    azuread_authentication_only = true
  }

  tags = var.tags

  lifecycle {
    precondition {
      condition     = trimspace(var.azuread_admin_object_id) != ""
      error_message = "An Entra administrator object ID is required when the SAP emulator is enabled."
    }
  }
}

resource "azurerm_mssql_database" "this" {
  name      = var.database_name
  server_id = azurerm_mssql_server.this.id

  sku_name                                     = var.sku_name
  max_size_gb                                  = var.max_size_gb
  collation                                    = "SQL_Latin1_General_CP1_CS_AS"
  geo_backup_enabled                           = true
  transparent_data_encryption_enabled          = true
  transparent_data_encryption_key_vault_key_id = null

  tags = var.tags
}

resource "azurerm_mssql_firewall_rule" "migration_client" {
  count = var.public_network_access_enabled && var.allowed_ip_start != "" ? 1 : 0

  name             = "migration-client"
  server_id        = azurerm_mssql_server.this.id
  start_ip_address = var.allowed_ip_start
  end_ip_address   = var.allowed_ip_end != "" ? var.allowed_ip_end : var.allowed_ip_start

  lifecycle {
    precondition {
      condition     = can(cidrnetmask("${var.allowed_ip_start}/32"))
      error_message = "allowed_ip_start must be a valid IPv4 address."
    }
    precondition {
      condition     = var.allowed_ip_end == "" || can(cidrnetmask("${var.allowed_ip_end}/32"))
      error_message = "allowed_ip_end must be empty or a valid IPv4 address."
    }
  }
}

resource "azurerm_mssql_firewall_rule" "app_service" {
  for_each = var.public_network_access_enabled ? var.app_service_outbound_ips : toset([])

  name             = "app-service-${replace(each.value, ".", "-")}"
  server_id        = azurerm_mssql_server.this.id
  start_ip_address = each.value
  end_ip_address   = each.value

  lifecycle {
    precondition {
      condition     = can(cidrnetmask("${each.value}/32"))
      error_message = "Every app_service_outbound_ips entry must be a valid IPv4 address."
    }
  }
}