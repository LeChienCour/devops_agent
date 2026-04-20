"""SSM Parameter Store fetcher for runtime secrets.

Secrets are NEVER stored in environment variables in Lambda.
This module is the single access point for sensitive values.
"""

from __future__ import annotations

import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="finops-agent")

_cache: dict[str, str] = {}


def get_secret(parameter_name: str, region: str = "us-east-1") -> str:
    """Fetch a SecureString parameter from SSM, with in-memory cache.

    Args:
        parameter_name: Full SSM parameter path, e.g. /finops-agent/slack-webhook-url.
        region: AWS region where the parameter is stored.

    Returns:
        Decrypted parameter value as a string.

    Raises:
        boto3.exceptions.Boto3Error: On SSM API failure.
    """
    if parameter_name in _cache:
        return _cache[parameter_name]

    client = boto3.client("ssm", region_name=region)
    response = client.get_parameter(Name=parameter_name, WithDecryption=True)
    value: str = response["Parameter"]["Value"]
    _cache[parameter_name] = value
    logger.info("SSM parameter loaded", parameter=parameter_name)
    return value


def get_slack_webhook_url(region: str = "us-east-1") -> str:
    """Convenience wrapper for the Slack webhook URL secret."""
    return get_secret("/finops-agent/slack-webhook-url", region=region)


def get_github_token(region: str = "us-east-1") -> str:
    """Convenience wrapper for the GitHub read-only token secret."""
    return get_secret("/finops-agent/github-token", region=region)
