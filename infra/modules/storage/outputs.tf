output "dynamodb_table_name" {
  description = "Name of the DynamoDB findings table."
  value       = aws_dynamodb_table.findings.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB findings table."
  value       = aws_dynamodb_table.findings.arn
}

output "dynamodb_table_gsi_arn" {
  description = "ARN of the finding_type-created_at GSI (needed for scoped IAM policy)."
  value       = "${aws_dynamodb_table.findings.arn}/index/finding_type-created_at-index"
}

output "reports_bucket_name" {
  description = "Name of the S3 reports bucket."
  value       = aws_s3_bucket.reports.bucket
}

output "reports_bucket_arn" {
  description = "ARN of the S3 reports bucket."
  value       = aws_s3_bucket.reports.arn
}
