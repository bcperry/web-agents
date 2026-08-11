output "server_fqdn" {
  description = "Azure SQL logical server FQDN"
  value       = azurerm_mssql_server.this.fully_qualified_domain_name
}

output "database_name" {
  description = "SAP force-equipment emulator database name"
  value       = azurerm_mssql_database.this.name
}

output "connection_string" {
  description = "Passwordless ODBC connection string for the emulator"
  value       = "Driver={ODBC Driver 18 for SQL Server};Server=tcp:${azurerm_mssql_server.this.fully_qualified_domain_name},1433;Database=${azurerm_mssql_database.this.name};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=10;Authentication=ActiveDirectoryMsi"
}

output "server_id" {
  description = "Azure SQL logical server resource ID"
  value       = azurerm_mssql_server.this.id
}