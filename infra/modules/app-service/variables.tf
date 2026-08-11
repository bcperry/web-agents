variable "name" {
  description = "The name of the App Service"
  type        = string
}

variable "location" {
  description = "The location of the App Service"
  type        = string
}

variable "tags" {
  description = "Tags to apply to the App Service (deprecated, use app_service_tags)"
  type        = map(string)
  default     = {}
}

variable "app_service_tags" {
  description = "Tags to apply to the App Service"
  type        = map(string)
  default     = null
}

variable "app_service_plan_tags" {
  description = "Tags to apply to the App Service Plan"
  type        = map(string)
  default     = null
}

variable "app_service_plan_name" {
  description = "The name of the App Service Plan"
  type        = string
}

variable "app_service_plan_sku" {
  description = "The SKU of the App Service Plan"
  type        = string
  default     = "B1"
}

variable "python_version" {
  description = "The Python version to use"
  type        = string
  default     = "3.12"
}

variable "managed_identity_id" {
  description = "The managed identity resource ID"
  type        = string
}

variable "managed_identity_client_id" {
  description = "The managed identity client ID"
  type        = string
}

variable "resource_group_name" {
  description = "The name of the resource group"
  type        = string
}

variable "azure_openai_endpoint" {
  description = "Azure OpenAI endpoint URL"
  type        = string
}

variable "azure_openai_model" {
  description = "Azure OpenAI model deployment name"
  type        = string
}

variable "azure_openai_api_key" {
  description = "Azure OpenAI API key"
  type        = string
  sensitive   = true
}

variable "azure_openai_api_version" {
  description = "Azure OpenAI API version"
  type        = string
}

variable "azure_sql_connectionstring" {
  description = "Azure SQL connection string"
  type        = string
  sensitive   = true
}

variable "sap_emulator_enabled" {
  description = "Whether the native SAP emulator database provider is enabled"
  type        = bool
  default     = false
}

variable "sap_emulator_server_fqdn" {
  description = "Azure SQL server FQDN for the SAP emulator provider"
  type        = string
  default     = ""
}

variable "sap_emulator_database_name" {
  description = "Azure SQL database name for the SAP emulator provider"
  type        = string
  default     = ""
}

variable "sap_emulator_entitled_group_ids" {
  description = "Comma-separated Entra group object IDs entitled to the SAP emulator agent"
  type        = string
  default     = ""
}

variable "search_service_endpoint" {
  description = "Azure AI Search service endpoint"
  type        = string
}

variable "search_index_name" {
  description = "Azure AI Search index name"
  type        = string
}

variable "search_api_key" {
  description = "Azure AI Search API key"
  type        = string
  sensitive   = true
}

# Azure Cosmos DB (durable agent memory + per-user chat history)
variable "azure_cosmos_endpoint" {
  description = "Cosmos DB account endpoint"
  type        = string
  default     = ""
}

variable "azure_cosmos_database_name" {
  description = "Cosmos DB database name"
  type        = string
  default     = "agent-memory"
}

variable "azure_cosmos_container_name" {
  description = "Cosmos DB messages container name"
  type        = string
  default     = "chat-history"
}

variable "azure_cosmos_conversations_container" {
  description = "Cosmos DB conversation index container name"
  type        = string
  default     = "conversations"
}

variable "azure_cosmos_autonomous_container" {
  description = "Cosmos DB autonomous run audit container name"
  type        = string
  default     = "autonomous-runs"
}

variable "azure_cosmos_leases_container" {
  description = "Cosmos DB autonomous scheduler lease container name"
  type        = string
  default     = "autonomous-leases"
}

variable "azure_cosmos_directives_container" {
  description = "Cosmos DB autonomous directive store container name"
  type        = string
  default     = "autonomous-directives"
}

variable "azure_cosmos_skills_container" {
  description = "Cosmos DB global agent skills store container name"
  type        = string
  default     = "skills"
}

variable "azure_cosmos_user_skills_container" {
  description = "Cosmos DB user-owned agent skills container name"
  type        = string
  default     = "user-skills"
}

variable "autonomous_scheduler_enabled" {
  description = "Gate for the in-process autonomous scheduler. Empty string = enabled in Azure (the deployed default); 'false' disables it."
  type        = string
  default     = ""
}

# Entra ID / Azure AD authentication
variable "entra_tenant_id" {
  description = "Entra ID (Azure AD) tenant ID for authentication"
  type        = string
  default     = ""
}

variable "entra_client_id" {
  description = "Entra ID (Azure AD) client/application ID for authentication"
  type        = string
  default     = ""
}

variable "entra_client_secret" {
  description = "Entra ID (Azure AD) client secret (leave empty to use managed identity)"
  type        = string
  sensitive   = true
  default     = ""
}

# Branding / application configuration
variable "classification_banner" {
  description = "Classification banner text displayed in the UI"
  type        = string
  default     = "UNCLASSIFIED"
}

variable "app_name" {
  description = "Application display name"
  type        = string
  default     = "Web-Agents"
}

variable "app_tagline" {
  description = "Application tagline"
  type        = string
  default     = "AI Agent Framework"
}

variable "app_logo" {
  description = "Application logo path"
  type        = string
  default     = "/Microsoft.png"
}
