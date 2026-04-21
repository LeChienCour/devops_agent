# ---------------------------------------------------------------------------
# FinOps Agent — Root Module
#
# Composes the four core agent modules. The seed_leaks demo module is
# intentionally NOT wired here; it lives in infra/demo/ and is deployed
# independently to avoid any hard dependency on agent infrastructure.
# ---------------------------------------------------------------------------

locals {
  common_tags = merge(var.tags, {
    Environment = var.environment
  })
}

# ---------------------------------------------------------------------------
# Storage: DynamoDB (findings) + S3 (reports)
# ---------------------------------------------------------------------------
module "storage" {
  source = "./modules/storage"

  project_name = var.project_name
  environment  = var.environment
  tags         = local.common_tags
}

# ---------------------------------------------------------------------------
# Notifications: SNS topic + optional Slack subscription
# ---------------------------------------------------------------------------
module "notifications" {
  source = "./modules/notifications"

  project_name      = var.project_name
  environment       = var.environment
  slack_webhook_url = var.slack_webhook_url
  tags              = local.common_tags
}

# ---------------------------------------------------------------------------
# Agent Lambda: function, IAM role, DLQ, log group
# ---------------------------------------------------------------------------
module "agent_lambda" {
  source = "./modules/agent_lambda"

  project_name              = var.project_name
  environment               = var.environment
  aws_region                = var.aws_region
  dynamodb_table_name       = module.storage.dynamodb_table_name
  dynamodb_table_arn        = module.storage.dynamodb_table_arn
  dynamodb_table_gsi_arn    = module.storage.dynamodb_table_gsi_arn
  sns_topic_arn             = module.notifications.sns_topic_arn
  bedrock_model_id          = var.bedrock_model_id
  lambda_memory_mb          = var.lambda_memory_mb
  lambda_timeout_sec        = var.lambda_timeout_sec
  cost_threshold_usd        = var.cost_threshold_usd
  investigation_timeout_sec = var.investigation_timeout_sec
  log_level                 = var.log_level
  tags                      = local.common_tags
}

# ---------------------------------------------------------------------------
# EventBridge: weekly cron + on-demand event rule
# ---------------------------------------------------------------------------
module "eventbridge" {
  source = "./modules/eventbridge"

  project_name         = var.project_name
  environment          = var.environment
  lambda_function_arn  = module.agent_lambda.lambda_function_arn
  lambda_function_name = module.agent_lambda.lambda_function_name
  tags                 = local.common_tags
}
