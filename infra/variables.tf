variable "environment" {
  description = "Deployment environment name. Used as a suffix/prefix in resource names."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod", "demo"], var.environment)
    error_message = "environment must be one of: dev, staging, prod, demo."
  }
}

variable "aws_region" {
  description = "AWS region for all resources. Bedrock has the latest models in us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short project identifier used in resource names and tags."
  type        = string
  default     = "finops-agent"
}

variable "tags" {
  description = "Common tags merged into every resource. Extend this map for cost allocation or compliance."
  type        = map(string)
  default = {
    Project      = "finops-agent"
    ManagedBy    = "terraform"
    Repository   = "devops_agent"
    Presentation = "AWS Community Day 2026"
  }
}

# ---------------------------------------------------------------------------
# Notification variables (passed down to the notifications module)
# ---------------------------------------------------------------------------
variable "slack_webhook_url" {
  description = "Slack incoming webhook URL for cost-alert notifications. Leave empty to skip subscription creation."
  type        = string
  default     = ""
  sensitive   = true
}

# ---------------------------------------------------------------------------
# Lambda tuning (optional overrides)
# ---------------------------------------------------------------------------
variable "lambda_memory_mb" {
  description = "Lambda memory allocation in MB. 512 MB is the conservative starting point."
  type        = number
  default     = 512
}

variable "lambda_timeout_sec" {
  description = "Lambda execution timeout in seconds. Max 900 (15 min); 300 is safe for long investigations."
  type        = number
  default     = 300
}

variable "bedrock_model_id" {
  description = "Amazon Bedrock model ID. Update when a newer Claude version is available."
  type        = string
  default     = "anthropic.claude-sonnet-4-5-20250929-v1:0"
}

variable "cost_threshold_usd" {
  description = "Minimum monthly savings (USD) for a finding to be reported. Reduces noise for tiny leaks."
  type        = number
  default     = 5.0
}

variable "investigation_timeout_sec" {
  description = "Soft timeout (seconds) passed to the agent graph to cap a single investigation run."
  type        = number
  default     = 180
}

variable "log_level" {
  description = "Python log level for the Lambda function (DEBUG, INFO, WARNING, ERROR)."
  type        = string
  default     = "INFO"
}
