# ---------------------------------------------------------------------------
# Demo root variables
#
# Agent outputs are passed in as plain variables (not terraform_remote_state)
# to avoid hard state coupling. The demo root can be deployed and destroyed
# independently without any knowledge of the agent infrastructure state file.
# ---------------------------------------------------------------------------

variable "aws_region" {
  description = "AWS region for demo resources."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used in resource naming."
  type        = string
  default     = "finops-agent"
}

variable "availability_zone" {
  description = "Availability zone for EBS volumes and snapshots."
  type        = string
  default     = "us-east-1a"
}

variable "ebs_volume_size_gb" {
  description = "Size of each unattached demo EBS volume in GB."
  type        = number
  default     = 50
}
