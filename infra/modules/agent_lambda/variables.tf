variable "project_name" {
  description = "Short project identifier used in resource names."
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod, demo)."
  type        = string
}

variable "aws_region" {
  description = "AWS region the Lambda runs in. Used in Bedrock ARN scoping."
  type        = string
}

variable "dynamodb_table_name" {
  description = "Name of the DynamoDB findings table. Injected as Lambda environment variable."
  type        = string
}

variable "dynamodb_table_arn" {
  description = "ARN of the DynamoDB findings table. Used in IAM policy resource scoping."
  type        = string
}

variable "dynamodb_table_gsi_arn" {
  description = "ARN of the DynamoDB GSI. Used in IAM policy resource scoping."
  type        = string
}

variable "sns_topic_arn" {
  description = "ARN of the SNS alerts topic. Injected as Lambda environment variable and used in IAM policy."
  type        = string
}

variable "bedrock_model_id" {
  description = "Amazon Bedrock model ID passed to the agent runtime."
  type        = string
  default     = "anthropic.claude-sonnet-4-5-20250929-v1:0"
}

variable "lambda_memory_mb" {
  description = "Lambda memory allocation in MB."
  type        = number
  default     = 512
}

variable "lambda_timeout_sec" {
  description = "Lambda execution timeout in seconds."
  type        = number
  default     = 300
}

variable "cost_threshold_usd" {
  description = "Minimum monthly saving (USD) for a finding to be surfaced."
  type        = number
  default     = 5.0
}

variable "investigation_timeout_sec" {
  description = "Soft agent graph timeout in seconds."
  type        = number
  default     = 180
}

variable "log_level" {
  description = "Python log level for the Lambda function."
  type        = string
  default     = "INFO"
}

variable "reserved_concurrent_executions" {
  description = "Maximum number of concurrent Lambda executions. Caps runaway parallel investigations."
  type        = number
  default     = 5
}

variable "dlq_message_retention_seconds" {
  description = "How long (seconds) failed invocation payloads are retained in the DLQ."
  type        = number
  default     = 1209600 # 14 days
}

variable "log_retention_days" {
  description = "CloudWatch Log Group retention in days."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Tags to apply to all resources in this module."
  type        = map(string)
  default     = {}
}
