output "eventbridge_rule_arn_weekly" {
  description = "ARN of the weekly EventBridge schedule rule."
  value       = aws_cloudwatch_event_rule.weekly.arn
}

output "eventbridge_rule_arn_ondemand" {
  description = "ARN of the on-demand EventBridge event rule."
  value       = aws_cloudwatch_event_rule.on_demand.arn
}

output "eventbridge_rule_name_weekly" {
  description = "Name of the weekly EventBridge schedule rule."
  value       = aws_cloudwatch_event_rule.weekly.name
}

output "eventbridge_rule_name_ondemand" {
  description = "Name of the on-demand EventBridge event rule."
  value       = aws_cloudwatch_event_rule.on_demand.name
}
