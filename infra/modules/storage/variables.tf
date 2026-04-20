variable "project_name" {
  description = "Short project identifier used in resource names."
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod, demo)."
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources in this module."
  type        = map(string)
  default     = {}
}

variable "ttl_attribute" {
  description = "DynamoDB TTL attribute name. Items set this to a Unix epoch timestamp for auto-expiry."
  type        = string
  default     = "ttl"
}

variable "report_retention_days" {
  description = "Number of days before objects in the reports S3 bucket are automatically expired."
  type        = number
  default     = 90
}
