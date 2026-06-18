variable "account_name" {
  description = "Cosmos DB account name (globally unique, lowercase letters/numbers/hyphens, 3-44 chars)."
  type        = string
}

variable "location" {
  description = "Azure region for the Cosmos DB account."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group that holds the Cosmos DB account."
  type        = string
}

variable "tags" {
  description = "Tags applied to the Cosmos DB account."
  type        = map(string)
  default     = {}
}

variable "database_name" {
  description = "Cosmos DB SQL database name."
  type        = string
  default     = "agent-memory"
}

variable "messages_container_name" {
  description = "Container for chat messages (partition key /session_id)."
  type        = string
  default     = "chat-history"
}

variable "conversations_container_name" {
  description = "Container for the per-user conversation index (partition key /user_id)."
  type        = string
  default     = "conversations"
}

variable "principal_id" {
  description = "Principal ID of the app's managed identity, granted data-plane access."
  type        = string
}

variable "dev_principal_id" {
  description = "Optional developer/user principal ID granted Cosmos data-plane access for local development (empty = none granted)."
  type        = string
  default     = ""
}
