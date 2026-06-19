resource "azurerm_cosmosdb_account" "cosmos" {
  name                = var.account_name
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  offer_type = "Standard"
  kind       = "GlobalDocumentDB"

  # Serverless throughput — bills per request unit, ideal for spiky,
  # user-driven interactive chat memory workloads (see research.md R5).
  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }

  # Production authenticates via managed identity (RBAC). Disable account-key
  # (local) auth so no shared secret exists for the cloud account.
  local_authentication_disabled = true
}

resource "azurerm_cosmosdb_sql_database" "db" {
  name                = var.database_name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos.name
}

# Messages container — owned by the Agent Framework CosmosHistoryProvider.
resource "azurerm_cosmosdb_sql_container" "messages" {
  name                = var.messages_container_name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  database_name       = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths = ["/session_id"]
}

# Per-user conversation index — powers the left chat pane and enforces ownership.
resource "azurerm_cosmosdb_sql_container" "conversations" {
  name                = var.conversations_container_name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  database_name       = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths = ["/user_id"]
}

# Per-user custom agents (admin-built). Names match the backend defaults in user_data.py.
resource "azurerm_cosmosdb_sql_container" "custom_agents" {
  name                = "custom-agents"
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  database_name       = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths = ["/user_id"]
}

# Per-user built-in agent customizations (overrides).
resource "azurerm_cosmosdb_sql_container" "agent_customizations" {
  name                = "agent-customizations"
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  database_name       = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths = ["/user_id"]
}

# Per-user memory profile (one document per user).
resource "azurerm_cosmosdb_sql_container" "user_profiles" {
  name                = "user-profiles"
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  database_name       = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths = ["/user_id"]
}

# Autonomous Mode run audit log (partition key /directive_id). One durable record
# per autonomous cycle; the dominant query is "runs for a directive" + recency.
resource "azurerm_cosmosdb_sql_container" "autonomous_runs" {
  name                = var.autonomous_container_name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  database_name       = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths = ["/directive_id"]
}

# Autonomous Mode scheduler leases (partition key /directive_id). The atomic
# create of "{directive_id}:{slot}" guarantees at-most-once execution per slot
# across instances. default_ttl = -1 enables per-item TTL so leases self-expire.
resource "azurerm_cosmosdb_sql_container" "autonomous_leases" {
  name                = var.leases_container_name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  database_name       = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths = ["/directive_id"]
  default_ttl         = -1
}

# Autonomous Mode directive store (partition key /id). Seeded from the YAML
# defaults at startup; holds runtime edits (enable/disable, schedule, new ones).
resource "azurerm_cosmosdb_sql_container" "autonomous_directives" {
  name                = var.directives_container_name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  database_name       = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths = ["/id"]
}

# Grant the app's managed identity data-plane access via the built-in
# "Cosmos DB Built-in Data Contributor" role (id ...0002).
resource "azurerm_cosmosdb_sql_role_assignment" "data_contributor" {
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  role_definition_id  = "${azurerm_cosmosdb_account.cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = var.principal_id
  scope               = azurerm_cosmosdb_account.cosmos.id
}

# Optional developer/user data-plane access for running the app locally against
# this live account (Cosmos data-plane RBAC is separate from control-plane RBAC).
# Gated by the ENABLE_DEV_COSMOS_ACCESS deployment env var; empty = not granted.
resource "azurerm_cosmosdb_sql_role_assignment" "dev_data_contributor" {
  count               = var.dev_principal_id != "" ? 1 : 0
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  role_definition_id  = "${azurerm_cosmosdb_account.cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = var.dev_principal_id
  scope               = azurerm_cosmosdb_account.cosmos.id
}
