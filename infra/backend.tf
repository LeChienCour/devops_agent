# ---------------------------------------------------------------------------
# Backend Configuration
#
# By default, Terraform uses a LOCAL backend (state stored in terraform.tfstate
# in this directory). This is fine for solo development but unsuitable for teams
# or CI/CD pipelines.
#
# TO ENABLE THE S3 REMOTE BACKEND:
#   1. Create an S3 bucket:
#        aws s3api create-bucket --bucket <your-bucket-name> --region us-east-1
#        aws s3api put-bucket-versioning \
#          --bucket <your-bucket-name> \
#          --versioning-configuration Status=Enabled
#   2. Create a DynamoDB table for state locking:
#        aws dynamodb create-table \
#          --table-name terraform-state-lock \
#          --attribute-definitions AttributeName=LockID,AttributeType=S \
#          --key-schema AttributeName=LockID,KeyType=HASH \
#          --billing-mode PAY_PER_REQUEST
#   3. Uncomment the block below and fill in your values.
#   4. Run: terraform init -reconfigure
#
# ---------------------------------------------------------------------------

# terraform {
#   backend "s3" {
#     bucket         = "finops-agent-terraform-state-<account_id>"
#     key            = "infra/terraform.tfstate"
#     region         = "us-east-1"
#     encrypt        = true
#     dynamodb_table = "terraform-state-lock"
#   }
# }

# ---------------------------------------------------------------------------
# LOCAL BACKEND (default — remove this comment block when switching to S3)
# ---------------------------------------------------------------------------
terraform {
  backend "local" {}
}
