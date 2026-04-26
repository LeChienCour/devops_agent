variable "project_name" {
  description = "Short project identifier used in resource names."
  type        = string
  default     = "finops-agent"
}

variable "environment" {
  description = "Deployment environment tag value."
  type        = string
  default     = "demo"
}

variable "aws_region" {
  description = "AWS region where demo resources are created."
  type        = string
  default     = "us-east-1"
}

variable "availability_zone" {
  description = "AZ for the demo EBS volumes and snapshots."
  type        = string
  default     = "us-east-1a"
}

variable "ebs_volume_size_gb" {
  description = "Size (GB) of each unattached gp2 demo EBS volume."
  type        = number
  default     = 50
}

variable "tags" {
  description = "Base tags merged into all demo resources."
  type        = map(string)
  default     = {}
}
