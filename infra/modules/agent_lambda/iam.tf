# ---------------------------------------------------------------------------
# IAM — Lambda execution role and least-privilege policy documents
#
# Security principle: READ-ONLY access to all discovery APIs.
# The agent never modifies resources; it only surfaces recommendations.
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# Trust policy — only Lambda service can assume this role
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    sid    = "AllowLambdaAssumeRole"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

# ---------------------------------------------------------------------------
# Policy document: Cost Explorer (read)
#
# NOTE: Cost Explorer does NOT support resource-level ARN constraints.
# The AWS documentation explicitly states that all ce:* actions require
# Resource: "*". Using "*" here is unavoidable — not a security gap.
# Reference: https://docs.aws.amazon.com/cost-management/latest/userguide/
#            security_iam_service-with-iam.html
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "cost_explorer" {
  statement {
    sid    = "CostExplorerReadOnly"
    effect = "Allow"

    actions = [
      "ce:GetCostAndUsage",
      "ce:GetCostForecast",
      "ce:GetAnomalies",
      "ce:GetDimensionValues",
    ]

    # Cost Explorer has no resource-level permissions — "*" is required by the service
    resources = ["*"] # tfsec:ignore:aws-iam-no-policy-wildcards
  }
}

# ---------------------------------------------------------------------------
# Policy document: CloudWatch & Logs (read + custom metrics write)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "cloudwatch_read" {
  statement {
    sid    = "CloudWatchMetricsRead"
    effect = "Allow"

    actions = [
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:GetMetricData",
      "cloudwatch:ListMetrics",
    ]

    resources = ["*"] # CloudWatch metric actions have no resource-level support
  }

  statement {
    sid    = "CloudWatchLogsRead"
    effect = "Allow"

    actions = [
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
      "logs:FilterLogEvents",
      "logs:StartQuery",
      "logs:GetQueryResults",
    ]

    resources = ["*"] # Logs Insights query actions do not support resource scoping
  }

  statement {
    sid    = "CloudWatchMetricsWrite"
    effect = "Allow"

    actions = ["cloudwatch:PutMetricData"]

    # Scoped to the FinOpsAgent namespace via condition
    resources = ["*"] # PutMetricData does not support resource-level ARNs

    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["FinOpsAgent"]
    }
  }
}

# ---------------------------------------------------------------------------
# Policy document: EC2 read-only inventory
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "ec2_read" {
  statement {
    sid    = "EC2InventoryReadOnly"
    effect = "Allow"

    actions = [
      "ec2:DescribeVolumes",
      "ec2:DescribeSnapshots",
      "ec2:DescribeAddresses",
      "ec2:DescribeNatGateways",
      "ec2:DescribeInstances",
      "ec2:DescribeVpcs",
      "ec2:DescribeSubnets",
      "ec2:DescribeSecurityGroups",
    ]

    resources = ["*"] # All ec2:Describe* actions require "*" — no resource-level support
  }
}

# ---------------------------------------------------------------------------
# Policy document: Trusted Advisor (read)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "trusted_advisor" {
  statement {
    sid    = "TrustedAdvisorRead"
    effect = "Allow"

    actions = [
      "support:DescribeTrustedAdvisorChecks",
      "support:DescribeTrustedAdvisorCheckResult",
      "support:RefreshTrustedAdvisorCheck",
    ]

    resources = ["*"] # Support API does not support resource-level ARNs
  }
}

# ---------------------------------------------------------------------------
# Policy document: Bedrock model invocation (scoped to project model pattern)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid    = "BedrockModelInvoke"
    effect = "Allow"

    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]

    # Scoped to Anthropic Claude models in this region only — not a wildcard on all models
    resources = [
      "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-*",
    ]
  }
}

# ---------------------------------------------------------------------------
# Policy document: Lambda self-logging (CloudWatch Logs)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_logging" {
  statement {
    sid    = "LambdaCloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    # Scoped to log groups under /aws/lambda/ in this account/region
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/*",
    ]
  }
}

# ---------------------------------------------------------------------------
# Policy document: DynamoDB (write findings + read)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "dynamodb_write" {
  statement {
    sid    = "DynamoDBFindingsReadWrite"
    effect = "Allow"

    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:UpdateItem",
    ]

    # Scoped to specific table ARN and its GSI only
    resources = [
      var.dynamodb_table_arn,
      var.dynamodb_table_gsi_arn,
    ]
  }
}

# ---------------------------------------------------------------------------
# Policy document: SNS (publish alerts)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "sns_publish" {
  statement {
    sid    = "SNSPublishAlerts"
    effect = "Allow"

    actions = ["sns:Publish"]

    # Scoped to the specific alerts topic only
    resources = [var.sns_topic_arn]
  }
}

# ---------------------------------------------------------------------------
# Policy document: SSM Parameter Store (read agent config / secrets)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "ssm_read" {
  statement {
    sid    = "SSMParameterRead"
    effect = "Allow"

    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
    ]

    # Scoped to the finops-agent namespace only
    resources = [
      "arn:aws:ssm:*:*:parameter/finops-agent/*",
    ]
  }
}

# ---------------------------------------------------------------------------
# Policy document: GuardDuty (read)
#
# NOTE: guardduty:ListDetectors, ListFindings, and GetFindings do not support
# resource-level ARN scoping.
# Reference: https://docs.aws.amazon.com/guardduty/latest/ug/security_iam_service-with-iam.html
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "guardduty_read" {
  statement {
    sid    = "GuardDutyReadOnly"
    effect = "Allow"

    actions = [
      "guardduty:ListDetectors",
      "guardduty:ListFindings",
      "guardduty:GetFindings",
    ]

    resources = ["*"] # tfsec:ignore:aws-iam-no-policy-wildcards
  }
}

# ---------------------------------------------------------------------------
# Policy document: AWS Config (read)
#
# NOTE: config:DescribeComplianceByConfigRule and GetComplianceDetailsByConfigRule
# do not support resource-level ARN scoping.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "config_read" {
  statement {
    sid    = "ConfigReadOnly"
    effect = "Allow"

    actions = [
      "config:DescribeComplianceByConfigRule",
      "config:GetComplianceDetailsByConfigRule",
      "config:DescribeConfigRules",
      "config:DescribeConfigurationRecorders",
      "config:DescribeConfigurationRecorderStatus",
    ]

    resources = ["*"] # tfsec:ignore:aws-iam-no-policy-wildcards
  }
}

# ---------------------------------------------------------------------------
# Policy document: IAM Access Analyzer (read)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "access_analyzer_read" {
  statement {
    sid    = "AccessAnalyzerReadOnly"
    effect = "Allow"

    actions = [
      "access-analyzer:ListAnalyzers",
      "access-analyzer:ListFindings",
      "access-analyzer:GetFinding",
    ]

    resources = ["*"] # tfsec:ignore:aws-iam-no-policy-wildcards
  }
}

# ---------------------------------------------------------------------------
# Policy document: Security Hub (read)
#
# NOTE: securityhub:GetFindings does not support resource-level ARN constraints.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "security_hub_read" {
  statement {
    sid    = "SecurityHubReadOnly"
    effect = "Allow"

    actions = [
      "securityhub:GetFindings",
      "securityhub:DescribeHub",
    ]

    resources = ["*"] # tfsec:ignore:aws-iam-no-policy-wildcards
  }
}

# ---------------------------------------------------------------------------
# Policy document: CloudTrail (read)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "cloudtrail_read" {
  statement {
    sid    = "CloudTrailReadOnly"
    effect = "Allow"

    actions = [
      "cloudtrail:DescribeTrails",
      "cloudtrail:GetTrailStatus",
      "cloudtrail:GetEventSelectors",
    ]

    resources = ["*"] # tfsec:ignore:aws-iam-no-policy-wildcards
  }
}

# ---------------------------------------------------------------------------
# Policy document: IAM credential audit (read)
#
# IAM is a global service. generate/get_credential_report and GetAccountSummary
# do not support resource-level ARN scoping.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "iam_audit_read" {
  statement {
    sid    = "IAMAuditReadOnly"
    effect = "Allow"

    actions = [
      "iam:GetAccountSummary",
      "iam:GenerateCredentialReport",
      "iam:GetCredentialReport",
      "iam:ListUsers",
      "iam:ListMFADevices",
      "iam:ListAccessKeys",
      "iam:GetAccessKeyLastUsed",
    ]

    resources = ["*"] # tfsec:ignore:aws-iam-no-policy-wildcards
  }
}

# ---------------------------------------------------------------------------
# SQS DLQ send message permission
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "sqs_dlq" {
  statement {
    sid    = "SQSDLQSendMessage"
    effect = "Allow"

    actions = ["sqs:SendMessage"]

    resources = [aws_sqs_queue.dlq.arn]
  }
}

# ---------------------------------------------------------------------------
# Merged policy document (all statements combined into a single policy)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_combined" {
  source_policy_documents = [
    data.aws_iam_policy_document.cost_explorer.json,
    data.aws_iam_policy_document.cloudwatch_read.json,
    data.aws_iam_policy_document.ec2_read.json,
    data.aws_iam_policy_document.trusted_advisor.json,
    data.aws_iam_policy_document.bedrock_invoke.json,
    data.aws_iam_policy_document.lambda_logging.json,
    data.aws_iam_policy_document.dynamodb_write.json,
    data.aws_iam_policy_document.sns_publish.json,
    data.aws_iam_policy_document.ssm_read.json,
    data.aws_iam_policy_document.sqs_dlq.json,
    data.aws_iam_policy_document.guardduty_read.json,
    data.aws_iam_policy_document.config_read.json,
    data.aws_iam_policy_document.access_analyzer_read.json,
    data.aws_iam_policy_document.security_hub_read.json,
    data.aws_iam_policy_document.cloudtrail_read.json,
    data.aws_iam_policy_document.iam_audit_read.json,
  ]
}

# ---------------------------------------------------------------------------
# IAM Role
# ---------------------------------------------------------------------------
resource "aws_iam_role" "lambda_exec" {
  name               = "${var.project_name}-lambda-exec-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  description        = "Execution role for the FinOps Agent Lambda. Read-only access to AWS discovery APIs."

  tags = var.tags
}

# ---------------------------------------------------------------------------
# IAM Policy (inline on the role for clarity and auditability)
# ---------------------------------------------------------------------------
resource "aws_iam_role_policy" "lambda_exec" {
  name   = "${var.project_name}-lambda-policy-${var.environment}"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_combined.json
}
