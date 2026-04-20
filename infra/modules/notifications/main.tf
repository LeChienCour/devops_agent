# ---------------------------------------------------------------------------
# Notifications module — SNS topic + optional Slack HTTPS subscription
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  topic_name = "${var.project_name}-alerts-${var.environment}"
}

# ---------------------------------------------------------------------------
# SNS Topic
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "alerts" {
  name = local.topic_name
  tags = var.tags
}

# ---------------------------------------------------------------------------
# SNS Topic Policy — allow Lambda (via IAM role) to publish
#
# The aws_sns_topic_policy replaces the default topic policy entirely,
# so we must include the owner's admin statement to avoid locking ourselves out.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "sns_topic_policy" {
  # Statement 1: account owner retains full admin access
  statement {
    sid    = "AllowAccountAdmin"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions   = ["SNS:*"]
    resources = [aws_sns_topic.alerts.arn]
  }

  # Statement 2: any Lambda execution role in this account can publish
  # (scoped to the account; the Lambda module further restricts via its own IAM policy)
  statement {
    sid    = "AllowLambdaPublish"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions   = ["SNS:Publish"]
    resources = [aws_sns_topic.alerts.arn]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.sns_topic_policy.json
}

# ---------------------------------------------------------------------------
# Slack HTTPS subscription — created only when a webhook URL is provided
# ---------------------------------------------------------------------------
resource "aws_sns_topic_subscription" "slack" {
  # count = 0 when slack_webhook_url is empty; no subscription is provisioned
  count = var.slack_webhook_url != "" ? 1 : 0

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "https"
  endpoint  = var.slack_webhook_url

  # Delivery policy: retry up to 3 times with exponential backoff before giving up
  delivery_policy = jsonencode({
    healthyRetryPolicy = {
      numRetries         = 3
      minDelayTarget     = 20
      maxDelayTarget     = 60
      numMaxDelayRetries = 1
      backoffFunction    = "exponential"
    }
  })
}
