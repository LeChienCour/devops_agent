# ---------------------------------------------------------------------------
# Backend Configuration
#
# By default, Terraform uses a LOCAL backend (state stored in terraform.tfstate
# in this directory). This is fine for solo development but unsuitable for teams
# or CI/CD pipelines.
#
# TO ENABLE THE S3 REMOTE BACKEND:
#   1. Run `make tf-bootstrap-apply` (infra/bootstrap/) to create the S3
#      state bucket — versioned, encrypted, private.
#   2. Uncomment the block below and fill in your values (the bootstrap's
#      `backend_config_snippet` output has the exact values to paste).
#   3. Run: terraform init -reconfigure
#
# State locking uses S3's native lock file (use_lockfile, Terraform >= 1.10)
# — no DynamoDB table required.
# ---------------------------------------------------------------------------

terraform {
  backend "s3" {
    bucket       = "finops-agent-terraform-state-187711854492"
    key          = "infra/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
