variable "environment_name" {
  description = "Name of the environment that can be used as part of naming resource convention"
  type        = string

  validation {
    condition     = length(var.environment_name) >= 1 && length(var.environment_name) <= 64
    error_message = "Environment name must be between 1 and 64 characters."
  }
}

variable "location" {
  description = "Primary location for all resources"
  type        = string

  validation {
    condition     = length(var.location) >= 1
    error_message = "Location must not be empty."
  }
}

variable "principal_id" {
  description = "Id of the user or app to assign application roles"
  type        = string
  default     = ""
}

variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
  default     = ""
}

variable "app_service_plan_sku" {
  description = "App Service Plan SKU"
  type        = string
  default     = "B1"
}

variable "python_version" {
  description = "Python version for the App Service"
  type        = string
  default     = "3.12"
}

variable "existing_resource_group_name" {
  description = "Name of an existing resource group to use (leave empty to create a new one)"
  type        = string
}

variable "azure_openai_endpoint" {
  description = "Azure OpenAI endpoint URL: 'https://{your-custom-endpoint}.openai.azure.com/'"
  type        = string
}

variable "azure_openai_model" {
  description = "Azure OpenAI model deployment name: 'your-deployment-name'"
  type        = string
}

variable "azure_openai_api_key" {
  description = "Azure OpenAI API key (leave empty to use managed identity)"
  type        = string
  sensitive   = true
}

variable "azure_openai_api_version" {
  description = "Azure OpenAI API version: '2024-02-15-preview'"
  type        = string
}

variable "azure_sql_connectionstring" {
  description = "Azure SQL connection string: 'Driver={ODBC Driver 18 for SQL Server};Server=tcp:<yourserver>.database.usgovcloudapi.net,1433;Database=<yourdatabase>;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;Authentication=ActiveDirectoryMsi'"
  type        = string
  sensitive   = true
}

variable "sap_emulator_enabled" {
  description = "Set to 'true' to provision the Azure SQL SAP force-equipment emulator"
  type        = string
  default     = "false"
}

variable "sap_emulator_sql_server_name" {
  description = "Optional globally unique Azure SQL server name; empty derives one from the environment"
  type        = string
  default     = ""
}

variable "sap_emulator_database_sku" {
  description = "Azure SQL database SKU; empty uses Basic"
  type        = string
  default     = ""
}

variable "sap_emulator_admin_object_id" {
  description = "Entra object ID for the Azure SQL administrator; empty uses principal_id"
  type        = string
  default     = ""
}

variable "sap_emulator_admin_login" {
  description = "Display name for the Azure SQL Entra administrator"
  type        = string
  default     = ""
}

variable "sap_emulator_public_network_access_enabled" {
  description = "Set to 'true' for exact-IP-restricted application or trusted developer access"
  type        = string
  default     = "false"
}

variable "sap_emulator_allowed_ip_start" {
  description = "First trusted developer IPv4 address allowed when public access is enabled"
  type        = string
  default     = ""
}

variable "sap_emulator_allowed_ip_end" {
  description = "Last trusted developer IPv4 address; empty reuses sap_emulator_allowed_ip_start"
  type        = string
  default     = ""
}

variable "sap_emulator_app_outbound_ips" {
  description = "Comma-separated App Service possible outbound IPv4 addresses allowed to reach the emulator"
  type        = string
  default     = ""
}

variable "sap_emulator_entitled_group_ids" {
  description = "Comma-separated Entra security group object IDs entitled to the SAP emulator agent"
  type        = string
  default     = ""
}

variable "search_service_endpoint" {
  description = "Azure AI Search service endpoint: 'https://{your-custom-endpoint}.search.azure.us'"
  type        = string
}

variable "search_index_name" {
  description = "Azure AI Search index name: 'your-index-name'"
  type        = string
}

variable "search_api_key" {
  description = "Azure AI Search API key (leave empty to use managed identity)"
  type        = string
  sensitive   = true
}

# Local development access to the live Cosmos account
variable "enable_dev_cosmos_access" {
  description = "When 'true', grant the deploying user (AZURE_PRINCIPAL_ID) the Cosmos data-plane 'Built-in Data Contributor' role so you can run the app locally against the live account. Leave 'false'/empty for normal deployments."
  type        = string
  default     = "false"
}

variable "autonomous_scheduler_enabled" {
  description = "Gate for the in-process Autonomous Mode scheduler in the App Service. Empty = enabled (the deployed default); 'false' disables the unattended schedule (run-now still works)."
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
