output "lambda_function_name" {
  description = "Name of the FinOps Agent Lambda function."
  value       = aws_lambda_function.agent.function_name
}

output "lambda_function_arn" {
  description = "ARN of the FinOps Agent Lambda function."
  value       = aws_lambda_function.agent.arn
}

output "lambda_invoke_arn" {
  description = "Invoke ARN of the Lambda function (used by API Gateway in Phase 2)."
  value       = aws_lambda_function.agent.invoke_arn
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution IAM role."
  value       = aws_iam_role.lambda_exec.arn
}

output "lambda_role_name" {
  description = "Name of the Lambda execution IAM role."
  value       = aws_iam_role.lambda_exec.name
}

output "dlq_arn" {
  description = "ARN of the Lambda Dead Letter Queue."
  value       = aws_sqs_queue.dlq.arn
}

output "dlq_url" {
  description = "URL of the Lambda Dead Letter Queue."
  value       = aws_sqs_queue.dlq.id
}

output "log_group_name" {
  description = "CloudWatch Log Group name for Lambda logs."
  value       = aws_cloudwatch_log_group.lambda.name
}
