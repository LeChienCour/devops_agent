"""Application config — loaded from environment variables or .env file."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    """All runtime configuration for the FinOps agent.

    Values are read from environment variables (uppercase) or a .env file.
    Secrets (Slack webhook, GitHub token) are fetched at runtime via SSM;
    see src/common/secrets.py.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # AWS
    aws_region: str = Field(default="us-east-1", description="AWS region")

    # Bedrock
    bedrock_model_id: str = Field(
        default="anthropic.claude-sonnet-4-5-20250929-v1:0",
        description="Bedrock model ID",
    )

    # DynamoDB
    dynamodb_table_name: str = Field(
        default="finops-agent-findings",
        description="DynamoDB table for persisting findings",
    )

    # SNS
    sns_topic_arn: str = Field(
        default="",
        description="SNS topic ARN for Slack notifications",
    )

    # Agent behavior
    log_level: str = Field(default="INFO", description="Structlog level")
    cost_threshold_usd: float = Field(
        default=5.0,
        description="Ignore findings with estimated monthly impact below this USD amount",
    )
    investigation_timeout_sec: int = Field(
        default=180,
        description="Max wall-clock seconds for a single investigation",
    )

    # Guardrails
    max_iterations: int = Field(
        default=5,
        description="Max gather→analyze loop iterations per investigation",
    )
    max_tokens_per_investigation: int = Field(
        default=50_000,
        description="Max total Bedrock tokens per investigation",
    )
    bedrock_cost_ceiling_usd: float = Field(
        default=0.50,
        description="Max estimated Bedrock spend per investigation in USD",
    )
