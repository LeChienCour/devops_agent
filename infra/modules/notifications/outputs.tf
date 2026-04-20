output "sns_topic_arn" {
  description = "ARN of the SNS alerts topic."
  value       = aws_sns_topic.alerts.arn
}

output "sns_topic_name" {
  description = "Name of the SNS alerts topic."
  value       = aws_sns_topic.alerts.name
}

output "slack_subscription_arn" {
  description = "ARN of the Slack HTTPS subscription, or empty string if not created."
  value       = var.slack_webhook_url != "" ? aws_sns_topic_subscription.slack[0].arn : ""
}
