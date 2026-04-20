variable "project_name" {
  description = "Short project identifier used in resource names."
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod, demo)."
  type        = string
}

variable "lambda_function_arn" {
  description = "ARN of the Lambda function to invoke as the EventBridge rule target."
  type        = string
}

variable "lambda_function_name" {
  description = "Name of the Lambda function. Used to create the resource-based invocation permission."
  type        = string
}

variable "weekly_schedule_expression" {
  description = "EventBridge cron expression for the scheduled weekly investigation run. Default: Monday 09:00 UTC."
  type        = string
  default     = "cron(0 9 ? * MON *)"
}

variable "tags" {
  description = "Tags to apply to all resources in this module."
  type        = map(string)
  default     = {}
}
