# ---------------------------------------------------------------------------
# Demo root outputs — useful for verifying what was seeded
# ---------------------------------------------------------------------------

output "nat_gateway_id" {
  description = "ID of the demo idle NAT Gateway (Leak 1)."
  value       = module.seed_leaks.nat_gateway_id
}

output "unattached_ebs_volume_ids" {
  description = "IDs of the 2 unattached gp2 EBS volumes (Leak 2)."
  value       = module.seed_leaks.unattached_ebs_volume_ids
}

output "unassociated_eip_id" {
  description = "Allocation ID of the unassociated EIP (Leak 3)."
  value       = module.seed_leaks.unassociated_eip_id
}

output "snapshot_ids" {
  description = "IDs of the 3 demo orphaned EBS snapshots (Leak 4)."
  value       = module.seed_leaks.snapshot_ids
}

output "oversized_lambda_name" {
  description = "Name of the 3008 MB oversized Lambda function (Leak 5)."
  value       = module.seed_leaks.oversized_lambda_name
}

output "no_retention_log_group_name" {
  description = "Name of the CloudWatch Log Group with no retention (Leak 6)."
  value       = module.seed_leaks.no_retention_log_group_name
}

output "demo_vpc_id" {
  description = "VPC created for the demo environment."
  value       = module.seed_leaks.demo_vpc_id
}
