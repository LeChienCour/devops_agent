# ---------------------------------------------------------------------------
# seed_leaks module
#
# Intentionally creates "leaky" AWS resources so the FinOps Agent has real
# targets to detect during live demos. Every resource is tagged for easy
# identification and bulk cleanup.
#
# NOTE — NAT Gateway is intentionally omitted.
# A NAT Gateway costs ~$32/month even when completely idle (hourly fee plus
# $0.045/GB data processed). That is too expensive to leave running as a demo
# resource. All other leaks stay well under $5/month combined.
#
# Approximate monthly cost if left running:
#   - 2x EBS gp2 50 GB each : ~$10/month  ($0.10/GB × 50 GB × 2)
#   - 1x Unassociated EIP   : ~$3.60/month
#   - 3x Snapshots (~1 GB)  : ~$0.15/month ($0.05/GB)
#   - Lambda (no invocations): ~$0.00/month
#   - CloudWatch Log Group  : ~$0.00/month (no data ingested)
#   TOTAL                   : < $15/month — acceptable for a demo account
#
# Deploy : cd infra/demo && terraform apply
# Destroy: cd infra/demo && terraform destroy
# ---------------------------------------------------------------------------

locals {
  demo_tags = merge(var.tags, {
    Purpose     = "demo-finops-agent"
    Environment = "demo"
    ManagedBy   = "terraform"
  })
}

# ---------------------------------------------------------------------------
# Leak 1: Unattached EBS gp2 volumes (×2) — 50 GB each, state=available
#
# gp2 is the older volume type. Two leak signals in one: unattached AND
# wrong volume type (gp3 is cheaper and faster at equal or lower cost).
# ---------------------------------------------------------------------------
resource "aws_ebs_volume" "unattached" {
  count             = 2
  availability_zone = var.availability_zone
  size              = var.ebs_volume_size_gb
  type              = "gp2" # intentionally gp2 (not gp3) — two leak types in one

  tags = merge(local.demo_tags, {
    Name     = "${var.project_name}-demo-orphan-vol-${count.index + 1}"
    LeakType = "unattached-ebs-gp2"
  })
}

# ---------------------------------------------------------------------------
# Leak 2: Unassociated Elastic IP — $3.60/month
#
# An EIP that is allocated but not associated with any running instance or
# NAT gateway is billed at $0.005/hour (~$3.60/month).
# ---------------------------------------------------------------------------
resource "aws_eip" "unassociated" {
  domain = "vpc"
  # Intentionally NOT associated with any instance or NAT Gateway

  tags = merge(local.demo_tags, {
    Name     = "${var.project_name}-demo-orphan-eip"
    LeakType = "unassociated-eip"
  })
}

# ---------------------------------------------------------------------------
# Leak 3: Oversized Lambda — 3008 MB allocation for a trivial no-op handler
#
# The agent detects that max_memory_used << memory_allocated.
# We use the archive provider to generate the deployment zip inline so no
# external files or build steps are required.
# ---------------------------------------------------------------------------
data "archive_file" "oversized_lambda_zip" {
  type        = "zip"
  output_path = "${path.module}/oversized_handler.zip"

  source {
    content  = <<-PYTHON
      import json

      def handler(event, context):
          print("demo")
          return {"statusCode": 200, "body": json.dumps("ok")}
    PYTHON
    filename = "handler.py"
  }
}

data "aws_iam_policy_document" "oversized_lambda_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "oversized_lambda" {
  name               = "${var.project_name}-demo-oversized-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.oversized_lambda_assume.json
  description        = "Minimal execution role for the demo oversized Lambda leak."

  tags = local.demo_tags
}

# Attach the AWS-managed basic execution policy (CloudWatch Logs only).
# Using aws_iam_role_policy_attachment — no inline policies.
resource "aws_iam_role_policy_attachment" "oversized_lambda_basic" {
  role       = aws_iam_role.oversized_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "oversized" {
  function_name    = "${var.project_name}-demo-oversized-${var.environment}"
  description      = "Demo leak: 3008 MB allocated but handler uses <200 MB. Detected by FinOps Agent."
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.oversized_lambda_zip.output_path
  source_code_hash = data.archive_file.oversized_lambda_zip.output_base64sha256
  role             = aws_iam_role.oversized_lambda.arn

  # Intentionally oversized — this is the leak we want the agent to detect
  memory_size = 3008
  timeout     = 10

  tags = merge(local.demo_tags, {
    LeakType = "oversized-lambda"
  })
}

# ---------------------------------------------------------------------------
# Leak 4: CloudWatch Log Group with no retention policy
#
# Omitting retention_in_days means logs are retained indefinitely.
# Storage costs grow without bound as the log group accumulates data.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "no_retention" {
  name = "/demo/${var.project_name}/no-retention-log-group"
  # retention_in_days is intentionally omitted — logs kept forever (the leak)

  tags = merge(local.demo_tags, {
    LeakType = "log-group-no-retention"
  })
}

# ---------------------------------------------------------------------------
# Leak 5: Old EBS snapshots (×3)
#
# We create a small source EBS volume (10 GB gp3) and take 3 snapshots of it.
# The snapshots represent old, orphaned snapshots no longer tied to an active
# workload — a common cost leak in long-running accounts.
# ---------------------------------------------------------------------------
resource "aws_ebs_volume" "snapshot_source" {
  availability_zone = var.availability_zone
  size              = 10 # 10 GB gp3 — minimal cost for the source volume
  type              = "gp3"

  tags = merge(local.demo_tags, {
    Name     = "${var.project_name}-demo-snapshot-source"
    LeakType = "snapshot-source-volume"
  })
}

resource "aws_ebs_snapshot" "demo" {
  count     = 3
  volume_id = aws_ebs_volume.snapshot_source.id

  tags = merge(local.demo_tags, {
    Name            = "${var.project_name}-demo-old-snapshot-${count.index + 1}"
    LeakType        = "orphaned-snapshot"
    CreatedForDemo  = "true"
  })
}
