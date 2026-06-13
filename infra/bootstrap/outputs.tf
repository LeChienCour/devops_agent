output "state_bucket_name" {
  description = "Name of the S3 bucket for Terraform remote state."
  value       = aws_s3_bucket.state.id
}

output "backend_config_snippet" {
  description = "Paste into infra/backend.tf (and infra/demo/backend.tf) after applying this root."
  value       = <<-EOT
    terraform {
      backend "s3" {
        bucket       = "${aws_s3_bucket.state.id}"
        key          = "infra/terraform.tfstate"
        region       = "${var.aws_region}"
        encrypt      = true
        use_lockfile = true
      }
    }
  EOT
}
