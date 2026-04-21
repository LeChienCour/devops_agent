# ---------------------------------------------------------------------------
# Root outputs — expose key resource identifiers for downstream consumption
# (CI/CD, scripts, other Terraform roots via remote_state, etc.)
# ---------------------------------------------------------------------------

output "lambda_function_name" {
  description = "Name of the FinOps Agent Lambda function."
  value       = module.agent_lambda.lambda_function_name
}

output "lambda_function_arn" {
  description = "ARN of the FinOps Agent Lambda function."
  value       = module.agent_lambda.lambda_function_arn
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB findings table."
  value       = module.storage.dynamodb_table_name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB findings table."
  value       = module.storage.dynamodb_table_arn
}

output "sns_topic_arn" {
  description = "ARN of the SNS alert topic."
  value       = module.notifications.sns_topic_arn
}

output "eventbridge_rule_arn_weekly" {
  description = "ARN of the weekly EventBridge schedule rule."
  value       = module.eventbridge.eventbridge_rule_arn_weekly
}

output "eventbridge_rule_arn_ondemand" {
  description = "ARN of the on-demand EventBridge event rule."
  value       = module.eventbridge.eventbridge_rule_arn_ondemand
}

output "reports_bucket_name" {
  description = "Name of the S3 bucket used for investigation report storage."
  value       = module.storage.reports_bucket_name
}

output "dlq_url" {
  description = "URL of the Lambda Dead Letter Queue (SQS)."
  value       = module.agent_lambda.dlq_url
}

# ---------------------------------------------------------------------------
# Placeholder — populated in Phase 2 when API Gateway is added
# ---------------------------------------------------------------------------
output "api_gateway_invoke_url" {
  description = "API Gateway invoke URL for on-demand agent invocations. Populated in Phase 2."
  value       = "NOT_DEPLOYED_YET — API Gateway will be added in Phase 2"
}
