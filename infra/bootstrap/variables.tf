variable "aws_region" {
  description = "AWS region for the state bucket and lock table."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short project identifier used in resource names and tags."
  type        = string
  default     = "finops-agent"
}

variable "tags" {
  description = "Common tags merged into every resource."
  type        = map(string)
  default = {
    Project      = "finops-agent"
    ManagedBy    = "terraform"
    Repository   = "devops_agent"
    Presentation = "AWS Community Day 2026"
  }
}
