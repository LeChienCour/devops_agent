# ---------------------------------------------------------------------------
# Storage module — DynamoDB findings table + S3 reports bucket
#
# DynamoDB key design (ADR-002):
#   PK: investigation_id (String)
#   SK: "finding#<ulid>"  — for individual findings
#       "meta#summary"    — for per-run summary records
#
# GSI-1 (finding_type-created_at-index):
#   PK: finding_type  (String) — cross-investigation queries by type
#   SK: created_at    (String) — ISO-8601 for range queries
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

locals {
  table_name  = "${var.project_name}-findings-${var.environment}"
  bucket_name = "${var.project_name}-reports-${data.aws_caller_identity.current.account_id}"
}

# ---------------------------------------------------------------------------
# DynamoDB — investigation findings table
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "findings" {
  name         = local.table_name
  billing_mode = "PAY_PER_REQUEST" # serverless; free-tier friendly, no capacity planning

  # Primary key
  hash_key  = "investigation_id"
  range_key = "sk"

  # All projected attributes must be declared here if used in LSI/GSI definitions
  attribute {
    name = "investigation_id"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # GSI attributes
  attribute {
    name = "finding_type"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  # GSI-1: query all findings of a given type across investigations, sorted by time
  global_secondary_index {
    name            = "finding_type-created_at-index"
    hash_key        = "finding_type"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  # TTL — items can self-expire by setting the `ttl` attribute to a Unix timestamp
  ttl {
    attribute_name = var.ttl_attribute
    enabled        = true
  }

  # Point-in-time recovery keeps a rolling 35-day backup at no extra query cost
  point_in_time_recovery {
    enabled = true
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# S3 — investigation reports bucket
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "reports" {
  bucket = local.bucket_name

  tags = var.tags
}

resource "aws_s3_bucket_versioning" "reports" {
  bucket = aws_s3_bucket.reports.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "reports" {
  bucket = aws_s3_bucket.reports.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id

  rule {
    id     = "expire-old-reports"
    status = "Enabled"

    expiration {
      days = var.report_retention_days
    }

    # Also clean up incomplete multipart uploads to avoid hidden storage costs
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
