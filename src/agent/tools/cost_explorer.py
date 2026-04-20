"""Cost Explorer tool — in-process wrapper used by the LangGraph agent.

MCP-compatible schema kept in src/mcp_servers/cost_explorer/ for standalone demo use.
"""

from __future__ import annotations

import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="finops-agent")

# Tool schemas exposed to Bedrock via tool_use
TOOLS: list[dict] = [
    {
        "name": "get_cost_by_service",
        "description": (
            "Returns AWS costs grouped by service for a given date range. "
            "Use to identify which services are spending the most."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "granularity": {
                    "type": "string",
                    "enum": ["DAILY", "MONTHLY"],
                    "description": "Time granularity of results",
                    "default": "MONTHLY",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "get_cost_anomalies",
        "description": (
            "Lists cost anomalies detected by AWS Cost Anomaly Detection. "
            "Returns anomalies above a given impact threshold."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "threshold_usd": {
                    "type": "number",
                    "description": "Minimum anomaly impact in USD to include",
                    "default": 5.0,
                },
                "lookback_days": {
                    "type": "integer",
                    "description": "How many days back to search",
                    "default": 30,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_cost_forecast",
        "description": (
            "Returns AWS cost forecast for the current or next month. "
            "Use to project whether costs are trending up unexpectedly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Forecast start date in YYYY-MM-DD",
                },
                "end_date": {
                    "type": "string",
                    "description": "Forecast end date in YYYY-MM-DD",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
]


def get_cost_by_service(
    start_date: str,
    end_date: str,
    granularity: str = "MONTHLY",
    region: str = "us-east-1",
) -> dict:
    """Return costs grouped by service for the given date range.

    Args:
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        granularity: DAILY or MONTHLY.
        region: AWS region for the boto3 client.

    Returns:
        Dict with ResultsByTime from Cost Explorer API.
    """
    client = boto3.client("ce", region_name=region)
    response = client.get_cost_and_usage(
        TimePeriod={"Start": start_date, "End": end_date},
        Granularity=granularity,
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    return response


def get_cost_anomalies(
    threshold_usd: float = 5.0,
    lookback_days: int = 30,
    region: str = "us-east-1",
) -> dict:
    """Return cost anomalies above the given USD threshold.

    Args:
        threshold_usd: Minimum anomaly total impact in USD.
        lookback_days: Days back from today to search.
        region: AWS region for the boto3 client.

    Returns:
        Dict with Anomalies list from Cost Explorer API.
    """
    from datetime import date, timedelta

    end = date.today()
    start = end - timedelta(days=lookback_days)
    client = boto3.client("ce", region_name=region)
    response = client.get_anomalies(
        DateInterval={
            "StartDate": start.isoformat(),
            "EndDate": end.isoformat(),
        },
        TotalImpact={"NumericOperator": "GREATER_THAN", "StartValue": threshold_usd},
    )
    return response


def get_cost_forecast(
    start_date: str,
    end_date: str,
    region: str = "us-east-1",
) -> dict:
    """Return cost forecast for the given date range.

    Args:
        start_date: Forecast start date in YYYY-MM-DD format.
        end_date: Forecast end date in YYYY-MM-DD format.
        region: AWS region for the boto3 client.

    Returns:
        Dict with forecast Total and ResultsByTime.
    """
    client = boto3.client("ce", region_name=region)
    response = client.get_cost_forecast(
        TimePeriod={"Start": start_date, "End": end_date},
        Metric="UNBLENDED_COST",
        Granularity="MONTHLY",
    )
    return response
