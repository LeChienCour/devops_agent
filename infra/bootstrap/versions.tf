terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # This root creates the S3 bucket + DynamoDB table that the other roots
  # (infra/, infra/demo/) use as their remote backend. It cannot depend on
  # that backend itself, so it stays local.
  backend "local" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.tags
  }
}
