variable "project_id" {
  type = string
}

variable "prefix" {
  type    = string
  default = "sentinel"
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "environment must be dev, test or prod"
  }
}

variable "region" {
  description = "europe-west2 (London) keeps data in the UK"
  type        = string
  default     = "europe-west2"
}

variable "subnet_cidr" {
  type    = string
  default = "10.50.0.0/24"
}

variable "access_policy_id" {
  description = "Organisation Access Context Manager policy id for VPC Service Controls"
  type        = string
}

variable "gateway_image" {
  description = "Container image of the Sentinel gateway, built and signed by CI"
  type        = string
}

variable "gemini_model_id" {
  description = "Pinned Gemini model id - changing it triggers re-validation"
  type        = string
}

variable "audit_retention_days" {
  type    = number
  default = 2557
}

variable "labels" {
  type    = map(string)
  default = { owner = "ai-engineering", cost_centre = "itsd-ai" }
}
