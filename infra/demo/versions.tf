terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }

  # Separate local state file — completely independent from the agent infra state.
  # This is intentional: seed_leaks can be destroyed without touching agent resources.
  backend "local" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "finops-agent"
      ManagedBy   = "terraform-seed-leaks"
      Purpose     = "demo-finops-agent"
      Environment = "demo"
    }
  }
}
