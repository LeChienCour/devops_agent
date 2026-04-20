output "nat_gateway_id" {
  description = "ID of the demo idle NAT Gateway."
  value       = aws_nat_gateway.demo.id
}

output "unattached_ebs_volume_ids" {
  description = "IDs of the two unattached gp2 EBS volumes."
  value       = aws_ebs_volume.unattached[*].id
}

output "unassociated_eip_id" {
  description = "Allocation ID of the unassociated Elastic IP."
  value       = aws_eip.unassociated.id
}

output "snapshot_ids" {
  description = "IDs of the three demo orphaned snapshots."
  value       = aws_ebs_snapshot.demo[*].id
}

output "oversized_lambda_name" {
  description = "Name of the demo oversized Lambda function."
  value       = aws_lambda_function.oversized.function_name
}

output "no_retention_log_group_name" {
  description = "Name of the CloudWatch Log Group with no retention policy."
  value       = aws_cloudwatch_log_group.no_retention.name
}

output "demo_vpc_id" {
  description = "VPC ID created for the demo NAT Gateway."
  value       = aws_vpc.demo.id
}
