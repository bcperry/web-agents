variable "server_name" {
  description = "Globally unique Azure SQL logical server name"
  type        = string
}

variable "database_name" {
  description = "SAP force-equipment emulator database name"
  type        = string
  default     = "sap-force-emulator"
}

variable "resource_group_name" {
  description = "Resource group containing the Azure SQL resources"
  type        = string
}

variable "location" {
  description = "Azure region for the Azure SQL resources"
  type        = string
}

variable "tenant_id" {
  description = "Entra tenant containing the database administrator"
  type        = string
}

variable "azuread_admin_login" {
  description = "Display name used for the Entra database administrator"
  type        = string
}

variable "azuread_admin_object_id" {
  description = "Object ID of the Entra database administrator"
  type        = string
}

variable "sku_name" {
  description = "Azure SQL database SKU"
  type        = string
  default     = "Basic"
}

variable "max_size_gb" {
  description = "Maximum database size in GB"
  type        = number
  default     = 2
}

variable "public_network_access_enabled" {
  description = "Whether the logical server accepts exact-IP-restricted public connections"
  type        = bool
  default     = false
}

variable "allowed_ip_start" {
  description = "First exact trusted developer IPv4 address; empty creates no firewall rule"
  type        = string
  default     = ""
}

variable "allowed_ip_end" {
  description = "Last trusted developer IPv4 address; empty reuses allowed_ip_start"
  type        = string
  default     = ""
}

variable "app_service_outbound_ips" {
  description = "Exact App Service possible outbound IPv4 addresses allowed through the SQL firewall"
  type        = set(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to Azure SQL resources"
  type        = map(string)
  default     = {}
}