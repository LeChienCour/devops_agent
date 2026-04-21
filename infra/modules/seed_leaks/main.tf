# ---------------------------------------------------------------------------
# seed_leaks module
#
# Intentionally creates "leaky" AWS resources so the FinOps Agent has real
# targets to detect during live demos. Every resource is tagged for easy
# identification and bulk cleanup.
#
# COST WARNING: If left running, these resources cost approximately:
#   - NAT Gateway:  ~$32/month (hourly fee + $0.045/GB data)
#   - 2x EBS gp2:   ~$4/month  ($0.10/GB × 20 GB × 2)
#   - 1x EIP:       ~$3.60/month (unassociated)
#   - 3x Snapshots: ~$0.15/month ($0.05/GB, ~1 GB each)
#   - Lambda:       near-zero (only billed on invocations)
#   TOTAL:          ~$40/month — run only during demo preparation!
#
# Deploy: cd infra/demo && terraform apply
# Destroy: cd infra/demo && terraform destroy
# ---------------------------------------------------------------------------

locals {
  demo_tags = merge(var.tags, {
    Purpose     = "demo-finops-agent"
    Environment = "demo"
    ManagedBy   = "terraform-seed-leaks"
  })
}

# ---------------------------------------------------------------------------
# Networking — VPC + subnet for the idle NAT Gateway
#
# We create a minimal VPC + public subnet solely to host the NAT Gateway.
# No instances, no workload — the NAT Gateway just sits here burning money.
# ---------------------------------------------------------------------------
resource "aws_vpc" "demo" {
  cidr_block           = "10.99.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.demo_tags, {
    Name = "${var.project_name}-demo-vpc"
  })
}

# Public subnet (NAT Gateway requires a public subnet with an IGW)
resource "aws_subnet" "demo_public" {
  vpc_id            = aws_vpc.demo.id
  cidr_block        = "10.99.1.0/24"
  availability_zone = var.availability_zone

  tags = merge(local.demo_tags, {
    Name = "${var.project_name}-demo-public-subnet"
  })
}

resource "aws_internet_gateway" "demo" {
  vpc_id = aws_vpc.demo.id

  tags = merge(local.demo_tags, {
    Name = "${var.project_name}-demo-igw"
  })
}

# ---------------------------------------------------------------------------
# Leak 1: NAT Gateway — idle, no workload, ~$32/month
# ---------------------------------------------------------------------------
resource "aws_eip" "nat_gateway" {
  domain = "vpc"

  tags = merge(local.demo_tags, {
    Name     = "${var.project_name}-demo-nat-eip"
    LeakType = "idle-nat-gateway"
  })
}

resource "aws_nat_gateway" "demo" {
  allocation_id = aws_eip.nat_gateway.id
  subnet_id     = aws_subnet.demo_public.id

  tags = merge(local.demo_tags, {
    Name     = "${var.project_name}-demo-nat-gw"
    LeakType = "idle-nat-gateway"
  })

  depends_on = [aws_internet_gateway.demo]
}

# ---------------------------------------------------------------------------
# Leak 2: Unattached EBS gp2 volumes — 2x 20 GB, state=available
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
# Leak 3: Unassociated Elastic IP — $3.60/month
# ---------------------------------------------------------------------------
resource "aws_eip" "unassociated" {
  domain = "vpc"
  # Intentionally NOT associated with any instance or NAT gateway

  tags = merge(local.demo_tags, {
    Name     = "${var.project_name}-demo-orphan-eip"
    LeakType = "unassociated-eip"
  })
}

# ---------------------------------------------------------------------------
# Leak 4: Snapshots from a transient EBS volume
#
# We create a small EBS volume, snapshot it 3 times, then the volume persists
# (also as a leak) but the snapshots represent "orphaned" snapshots whose
# source volume will appear unrelated to any active workload.
# ---------------------------------------------------------------------------
resource "aws_ebs_volume" "snapshot_source" {
  availability_zone = var.availability_zone
  size              = 1 # 1 GB — minimal cost for the source volume
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
    Name     = "${var.project_name}-demo-old-snapshot-${count.index + 1}"
    LeakType = "orphaned-snapshot"
  })
}

# ---------------------------------------------------------------------------
# Leak 5: Oversized Lambda — 3008 MB allocation for a trivial handler
#
# The agent should detect that max_memory_used << memory_allocated.
# We use archive_file to create the handler inline.
# ---------------------------------------------------------------------------
data "archive_file" "oversized_lambda_zip" {
  type        = "zip"
  output_path = "${path.module}/oversized_handler.zip"

  source {
    content  = <<-PYTHON
      import json

      def handler(event, context):
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

# Attach the AWS managed basic execution policy (only needs CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "oversized_lambda_basic" {
  role       = aws_iam_role.oversized_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "oversized" {
  function_name    = "${var.project_name}-demo-oversized-${var.environment}"
  description      = "Demo leak: Lambda with 3008 MB allocated but uses <200 MB. Detected by FinOps Agent."
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
# Leak 6: CloudWatch Log Group with no retention policy
#
# retention_in_days = 0 means logs are kept indefinitely.
# Storage costs grow without bound as the agent generates logs.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "no_retention" {
  name              = "/demo/${var.project_name}/no-retention-log-group"
  retention_in_days = 0 # intentionally no retention — this is the leak

  tags = merge(local.demo_tags, {
    LeakType = "log-group-no-retention"
  })
}
