variable "prefix" {
  description = "Short name prefix for all resources"
  type        = string
  default     = "sentinel"
}

variable "environment" {
  description = "dev, test or prod - each has identical infrastructure"
  type        = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "environment must be dev, test or prod"
  }
}

variable "location" {
  description = "Azure region; UK South keeps data in the UK"
  type        = string
  default     = "uksouth"
}

variable "vnet_cidr" {
  type    = string
  default = "10.40.0.0/20"
}

variable "corporate_cidr" {
  description = "Corporate network range allowed to reach the gateway"
  type        = string
}

variable "chat_deployment_name" {
  type    = string
  default = "chat-prod"
}

variable "chat_model_name" {
  description = "Model name as offered in your tenancy"
  type        = string
}

variable "chat_model_version" {
  description = "Pinned model version - changing it triggers re-validation"
  type        = string
}

variable "chat_capacity_k_tpm" {
  description = "Provisioned capacity in thousands of tokens per minute"
  type        = number
  default     = 50
}

variable "cmk_expiry" {
  description = "Expiry date of the customer-managed key (RFC3339)"
  type        = string
}

variable "audit_retention_days" {
  description = "Immutable retention for AI audit records (e.g. 7 years for MiFID II record keeping)"
  type        = number
  default     = 2557
}

variable "tags" {
  type    = map(string)
  default = { owner = "ai-engineering", cost_centre = "ITSD-AI" }
}
