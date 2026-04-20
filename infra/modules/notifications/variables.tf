variable "project_name" {
  description = "Short project identifier used in resource names."
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod, demo)."
  type        = string
}

variable "slack_webhook_url" {
  description = "Slack incoming webhook URL. When empty (default) no HTTPS subscription is created."
  type        = string
  default     = ""
  sensitive   = true
}

variable "tags" {
  description = "Tags to apply to all resources in this module."
  type        = map(string)
  default     = {}
}

variable "lambda_role_arn" {
  description = "IAM role ARN for the Lambda function that is allowed to publish to the SNS topic. Optional — used to add an explicit publish permission in the topic policy."
  type        = string
  default     = ""
}
