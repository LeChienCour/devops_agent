# ---------------------------------------------------------------------------
# Demo root — independent Terraform root for seed_leaks resources
#
# This root has NO dependency on the agent infra root (infra/).
# It can be applied and destroyed freely without affecting Lambda, DynamoDB,
# SNS, or EventBridge resources.
#
# Usage:
#   cd infra/demo
#   terraform init
#   terraform plan
#   terraform apply     # seed demo leaks for live demo
#   terraform destroy   # clean up after the demo
#
# Or use the Makefile shortcuts:
#   make seed-demo
#   make cleanup-demo
# ---------------------------------------------------------------------------

module "seed_leaks" {
  source = "../modules/seed_leaks"

  project_name       = var.project_name
  environment        = "demo"
  aws_region         = var.aws_region
  availability_zone  = var.availability_zone
  ebs_volume_size_gb = var.ebs_volume_size_gb

  tags = {
    Project     = var.project_name
    ManagedBy   = "terraform-seed-leaks"
    Purpose     = "demo-finops-agent"
    Environment = "demo"
  }
}
