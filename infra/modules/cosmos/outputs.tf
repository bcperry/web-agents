output "endpoint" {
  description = "Cosmos DB account endpoint (e.g. https://<account>.documents.azure.us:443/)."
  value       = azurerm_cosmosdb_account.cosmos.endpoint
}

output "account_name" {
  description = "Cosmos DB account name."
  value       = azurerm_cosmosdb_account.cosmos.name
}

output "database_name" {
  description = "Cosmos DB SQL database name."
  value       = azurerm_cosmosdb_sql_database.db.name
}

output "messages_container_name" {
  description = "Messages container name."
  value       = azurerm_cosmosdb_sql_container.messages.name
}

output "conversations_container_name" {
  description = "Conversation index container name."
  value       = azurerm_cosmosdb_sql_container.conversations.name
}

output "autonomous_container_name" {
  description = "Autonomous run audit container name."
  value       = azurerm_cosmosdb_sql_container.autonomous_runs.name
}

output "leases_container_name" {
  description = "Autonomous scheduler lease container name."
  value       = azurerm_cosmosdb_sql_container.autonomous_leases.name
}
