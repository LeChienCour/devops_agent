# ---------------------------------------------------------------------------
# Agent Lambda module
#
# Creates the FinOps Agent Lambda function along with its supporting resources:
#   - CloudWatch Log Group (created before the function to avoid a race condition)
#   - SQS Dead Letter Queue for failed async invocations
#   - The Lambda function itself
#
# The IAM role and policies live in iam.tf (same module, separate file).
#
# PLACEHOLDER ZIP NOTE:
#   A minimal Python handler is generated inline via archive_file so that
#   `terraform plan` and `terraform apply` succeed before Phase 2 code exists.
#   Replace var.lambda_source_path (or update the archive_file data source) when
#   the real src/agent/handler.py is ready.
# ---------------------------------------------------------------------------

locals {
  function_name  = "${var.project_name}-agent-${var.environment}"
  dlq_name       = "${var.project_name}-agent-dlq-${var.environment}"
  log_group_name = "/aws/lambda/${local.function_name}"
}

# ---------------------------------------------------------------------------
# Placeholder Lambda package
#
# Generates a minimal handler zip inline. This lets the module plan cleanly
# before Phase 2 source code exists. When the real handler is available,
# point archive_file at src/agent/ instead.
# ---------------------------------------------------------------------------
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/placeholder.zip"

  source {
    content  = <<-PYTHON
      """
      FinOps Agent — placeholder Lambda handler.
      This stub is replaced in Phase 2 by src/agent/handler.py.
      """
      import json
      import logging

      logger = logging.getLogger()
      logger.setLevel("INFO")


      def lambda_handler(event, context):
          logger.info("FinOps Agent placeholder handler invoked", extra={"event": event})
          return {
              "statusCode": 200,
              "body": json.dumps({
                  "status": "placeholder",
                  "message": "Phase 2 handler not yet deployed.",
              }),
          }
    PYTHON
    filename = "agent/handler.py"
  }
}

# ---------------------------------------------------------------------------
# CloudWatch Log Group — created BEFORE the Lambda function.
#
# If Lambda creates its own log group automatically (which it does on first
# invocation), Terraform loses track of retention settings. By declaring the
# log group explicitly here, we control retention from day one and avoid the
# race condition where Lambda creates the group before Terraform can.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "lambda" {
  name              = local.log_group_name
  retention_in_days = var.log_retention_days

  tags = var.tags
}

# ---------------------------------------------------------------------------
# SQS Dead Letter Queue
#
# Captures payloads of failed async Lambda invocations for post-mortem analysis.
# The Lambda service sends here after all retries are exhausted.
# No event source mapping is needed — DLQ for async invocations is configured
# directly on the Lambda function via dead_letter_config.
# ---------------------------------------------------------------------------
resource "aws_sqs_queue" "dlq" {
  name                      = local.dlq_name
  message_retention_seconds = var.dlq_message_retention_seconds

  # Encrypt at rest using the default SQS-managed key
  sqs_managed_sse_enabled = true

  tags = var.tags
}

# Allow the Lambda service to send messages to the DLQ
data "aws_iam_policy_document" "dlq_policy" {
  statement {
    sid    = "AllowLambdaSendMessage"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:lambda:*:${data.aws_caller_identity.current.account_id}:function:${local.function_name}"]
    }
  }
}

resource "aws_sqs_queue_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id
  policy    = data.aws_iam_policy_document.dlq_policy.json
}

# ---------------------------------------------------------------------------
# Lambda Function
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "agent" {
  function_name = local.function_name
  description   = "FinOps Agent — autonomous AWS cost waste detection using LangGraph + Bedrock."

  # Runtime
  runtime = "python3.12"
  handler = "agent.handler.lambda_handler"

  # Package — placeholder zip; replaced in Phase 2 with real source
  filename         = data.archive_file.lambda_placeholder.output_path
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256

  # Execution role (defined in iam.tf)
  role = aws_iam_role.lambda_exec.arn

  # Performance
  memory_size = var.lambda_memory_mb
  timeout     = var.lambda_timeout_sec

  # Concurrency cap — prevents runaway parallel investigations from inflating Bedrock costs
  reserved_concurrent_executions = var.reserved_concurrent_executions

  # Dead letter queue for failed async invocations
  dead_letter_config {
    target_arn = aws_sqs_queue.dlq.arn
  }

  # Environment variables — all values from variables, nothing hardcoded
  environment {
    variables = {
      DYNAMODB_TABLE_NAME       = var.dynamodb_table_name
      SNS_TOPIC_ARN             = var.sns_topic_arn
      BEDROCK_MODEL_ID          = var.bedrock_model_id
      LOG_LEVEL                 = var.log_level
      AWS_REGION_NAME           = var.aws_region # AWS_REGION is reserved by Lambda runtime
      COST_THRESHOLD_USD        = tostring(var.cost_threshold_usd)
      INVESTIGATION_TIMEOUT_SEC = tostring(var.investigation_timeout_sec)
    }
  }

  # Ensure the log group exists before the function, so retention is applied immediately
  depends_on = [aws_cloudwatch_log_group.lambda]

  tags = var.tags
}
