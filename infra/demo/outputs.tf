# ---------------------------------------------------------------------------
# Demo root outputs — useful for verifying what was seeded and targeting
# specific resources during cleanup or agent testing.
# ---------------------------------------------------------------------------

output "unattached_ebs_volume_ids" {
  description = "IDs of the 2 unattached gp2 EBS volumes (Leak 1)."
  value       = module.seed_leaks.unattached_ebs_volume_ids
}

output "unassociated_eip_id" {
  description = "Allocation ID of the unassociated EIP (Leak 2)."
  value       = module.seed_leaks.unassociated_eip_id
}

output "oversized_lambda_name" {
  description = "Name of the 3008 MB oversized Lambda function (Leak 3)."
  value       = module.seed_leaks.oversized_lambda_name
}

output "no_retention_log_group_name" {
  description = "Name of the CloudWatch Log Group with no retention policy (Leak 4)."
  value       = module.seed_leaks.no_retention_log_group_name
}

output "snapshot_ids" {
  description = "IDs of the 3 demo old EBS snapshots (Leak 5)."
  value       = module.seed_leaks.snapshot_ids
}

output "snapshot_source_volume_id" {
  description = "ID of the source EBS volume used to generate the demo snapshots."
  value       = module.seed_leaks.snapshot_source_volume_id
}
