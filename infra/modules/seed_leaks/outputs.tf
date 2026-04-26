output "unattached_ebs_volume_ids" {
  description = "IDs of the two unattached gp2 EBS volumes (Leak 1)."
  value       = aws_ebs_volume.unattached[*].id
}

output "unassociated_eip_id" {
  description = "Allocation ID of the unassociated Elastic IP (Leak 2)."
  value       = aws_eip.unassociated.id
}

output "oversized_lambda_name" {
  description = "Name of the 3008 MB oversized Lambda function (Leak 3)."
  value       = aws_lambda_function.oversized.function_name
}

output "no_retention_log_group_name" {
  description = "Name of the CloudWatch Log Group with no retention policy (Leak 4)."
  value       = aws_cloudwatch_log_group.no_retention.name
}

output "snapshot_ids" {
  description = "IDs of the three demo old EBS snapshots (Leak 5)."
  value       = aws_ebs_snapshot.demo[*].id
}

output "snapshot_source_volume_id" {
  description = "ID of the source EBS volume used to generate the demo snapshots."
  value       = aws_ebs_volume.snapshot_source.id
}
