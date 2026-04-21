# ---------------------------------------------------------------------------
# EventBridge module
#
# Two rules:
#   1. weekly — cron-based schedule (Monday 09:00 UTC) for automated investigations
#   2. on_demand — event pattern rule for manual/programmatic trigger via PutEvents
#
# Both rules grant Lambda permission via aws_lambda_permission (resource-based policy).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rule 1: Weekly scheduled investigation
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "weekly" {
  name                = "${var.project_name}-weekly-${var.environment}"
  description         = "Triggers the FinOps Agent weekly investigation every Monday at 09:00 UTC."
  schedule_expression = var.weekly_schedule_expression
  state               = "ENABLED"

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "weekly_lambda" {
  rule      = aws_cloudwatch_event_rule.weekly.name
  target_id = "FinOpsAgentWeekly"
  arn       = var.lambda_function_arn

  input = jsonencode({
    source      = "finops.agent"
    detail-type = "ScheduledInvestigation"
    detail = {
      trigger = "weekly-schedule"
    }
  })
}

resource "aws_lambda_permission" "allow_eventbridge_weekly" {
  statement_id  = "AllowEventBridgeWeekly"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly.arn
}

# ---------------------------------------------------------------------------
# Rule 2: On-demand — triggered by a custom event from API Gateway or CLI
#
# To invoke manually:
#   aws events put-events --entries '[{
#     "Source": "finops.agent",
#     "DetailType": "InvestigationRequest",
#     "Detail": "{\"requested_by\": \"manual\"}"
#   }]'
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "on_demand" {
  name        = "${var.project_name}-on-demand-${var.environment}"
  description = "Triggers the FinOps Agent on an explicit InvestigationRequest event."
  state       = "ENABLED"

  event_pattern = jsonencode({
    source      = ["finops.agent"]
    detail-type = ["InvestigationRequest"]
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "on_demand_lambda" {
  rule      = aws_cloudwatch_event_rule.on_demand.name
  target_id = "FinOpsAgentOnDemand"
  arn       = var.lambda_function_arn
}

resource "aws_lambda_permission" "allow_eventbridge_on_demand" {
  statement_id  = "AllowEventBridgeOnDemand"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.on_demand.arn
}
