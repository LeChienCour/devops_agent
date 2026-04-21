"""CloudWatch tool — in-process wrapper used by the LangGraph agent.

MCP-compatible schema kept in src/mcp_servers/cloudwatch/ for standalone demo use.
"""

from __future__ import annotations

import time
from typing import Any, cast

from aws_lambda_powertools import Logger

from common.aws_clients import get_client

logger = Logger(service="finops-agent")

# Tool schemas exposed to Bedrock via tool_use
TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_metric_statistics",
        "description": (
            "Returns CloudWatch metric statistics for a given namespace and metric. "
            "Use to check resource utilisation over a time window, e.g. NAT Gateway "
            "throughput or EC2 CPU to identify idle resources."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "CloudWatch namespace, e.g. 'AWS/EC2' or 'AWS/NATGateway'",
                },
                "metric_name": {
                    "type": "string",
                    "description": "Metric name, e.g. 'BytesOutToDestination'",
                },
                "dimensions": {
                    "type": "array",
                    "description": "List of dimension objects {Name: str, Value: str}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "Name": {"type": "string"},
                            "Value": {"type": "string"},
                        },
                        "required": ["Name", "Value"],
                    },
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time in ISO 8601 format, e.g. '2026-04-01T00:00:00Z'",
                },
                "end_time": {
                    "type": "string",
                    "description": "End time in ISO 8601 format, e.g. '2026-04-08T00:00:00Z'",
                },
                "period_seconds": {
                    "type": "integer",
                    "description": "Aggregation period in seconds. Defaults to 3600 (1 hour).",
                    "default": 3600,
                },
                "statistics": {
                    "type": "array",
                    "description": "Statistics to retrieve, e.g. ['Average', 'Sum']",
                    "items": {"type": "string"},
                    "default": ["Average"],
                },
            },
            "required": ["namespace", "metric_name", "dimensions", "start_time", "end_time"],
        },
    },
    {
        "name": "get_cloudwatch_insights",
        "description": (
            "Runs a CloudWatch Logs Insights query and returns the results. "
            "Use to analyse Lambda memory utilisation, error rates, or custom log patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "log_group_name": {
                    "type": "string",
                    "description": "CloudWatch Log Group name to query",
                },
                "query_string": {
                    "type": "string",
                    "description": "Logs Insights query string",
                },
                "start_time_epoch": {
                    "type": "integer",
                    "description": "Query start time as Unix epoch seconds",
                },
                "end_time_epoch": {
                    "type": "integer",
                    "description": "Query end time as Unix epoch seconds",
                },
            },
            "required": [
                "log_group_name",
                "query_string",
                "start_time_epoch",
                "end_time_epoch",
            ],
        },
    },
    {
        "name": "list_log_groups_without_retention",
        "description": (
            "Lists all CloudWatch Log Groups that have no retention policy set. "
            "Logs without retention grow indefinitely, incurring $0.03/GB/month storage costs. "
            "Use to identify log groups that should have a retention policy applied."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "AWS region to query. Defaults to us-east-1.",
                    "default": "us-east-1",
                },
            },
            "required": [],
        },
    },
]


def get_metric_statistics(
    namespace: str,
    metric_name: str,
    dimensions: list[dict[str, str]],
    start_time: str,
    end_time: str,
    period_seconds: int = 3600,
    statistics: list[str] | None = None,
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Return CloudWatch metric statistics for the specified metric.

    Args:
        namespace: CloudWatch namespace, e.g. ``"AWS/NATGateway"``.
        metric_name: Metric name, e.g. ``"BytesOutToDestination"``.
        dimensions: List of ``{Name: str, Value: str}`` dicts.
        start_time: Start of the period in ISO 8601 format.
        end_time: End of the period in ISO 8601 format.
        period_seconds: Aggregation period in seconds. Defaults to 3600.
        statistics: Statistics to retrieve. Defaults to ``["Average"]``.
        region: AWS region for the boto3 client.

    Returns:
        Dict with ``Datapoints`` list from CloudWatch GetMetricStatistics.
    """
    if statistics is None:
        statistics = ["Average"]

    client = get_client("cloudwatch", region)
    response = client.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=dimensions,
        StartTime=start_time,
        EndTime=end_time,
        Period=period_seconds,
        Statistics=statistics,
    )
    return cast(dict[str, Any], response)


def get_cloudwatch_insights(
    log_group_name: str,
    query_string: str,
    start_time_epoch: int,
    end_time_epoch: int,
    region: str = "us-east-1",
    _max_poll_seconds: int = 30,
    _poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    """Run a CloudWatch Logs Insights query and poll until complete.

    Starts the query, then polls ``get_query_results`` every 2 seconds
    for up to 30 seconds.

    Args:
        log_group_name: Log Group to query.
        query_string: Logs Insights query string.
        start_time_epoch: Query start time as Unix epoch seconds.
        end_time_epoch: Query end time as Unix epoch seconds.
        region: AWS region for the boto3 client.
        _max_poll_seconds: Maximum time to poll before returning partial results.
        _poll_interval_seconds: Seconds to sleep between poll attempts.

    Returns:
        Dict with ``results`` list and ``status`` from the query.
    """
    logs_client = get_client("logs", region)

    start_resp = logs_client.start_query(
        logGroupName=log_group_name,
        startTime=start_time_epoch,
        endTime=end_time_epoch,
        queryString=query_string,
    )
    query_id: str = start_resp["queryId"]

    deadline = time.monotonic() + _max_poll_seconds
    while time.monotonic() < deadline:
        result_resp = logs_client.get_query_results(queryId=query_id)
        status: str = result_resp.get("status", "Running")
        if status in ("Complete", "Failed", "Cancelled", "Timeout", "Unknown"):
            return {
                "queryId": query_id,
                "status": status,
                "results": result_resp.get("results", []),
                "statistics": result_resp.get("statistics", {}),
            }
        time.sleep(_poll_interval_seconds)

    # Return whatever we have after timeout
    result_resp = logs_client.get_query_results(queryId=query_id)
    return {
        "queryId": query_id,
        "status": result_resp.get("status", "Timeout"),
        "results": result_resp.get("results", []),
        "statistics": result_resp.get("statistics", {}),
    }


def list_log_groups_without_retention(
    region: str = "us-east-1",
) -> dict[str, Any]:
    """List all CloudWatch Log Groups that have no retention policy configured.

    Paginates through all log groups in the account/region and filters
    those where ``retentionInDays`` is absent from the API response.

    Args:
        region: AWS region to query.

    Returns:
        Dict with ``log_groups`` list, each entry containing ``name``,
        ``stored_bytes``, and ``creation_time``.
    """
    logs_client = get_client("logs", region)
    paginator = logs_client.get_paginator("describe_log_groups")

    groups_without_retention: list[dict[str, object]] = []
    for page in paginator.paginate():
        for group in page.get("logGroups", []):
            if "retentionInDays" not in group:
                groups_without_retention.append(
                    {
                        "name": group.get("logGroupName", ""),
                        "stored_bytes": group.get("storedBytes", 0),
                        "creation_time": group.get("creationTime"),
                    }
                )

    logger.info(
        "list_log_groups_without_retention_complete",
        region=region,
        count=len(groups_without_retention),
    )
    return {"log_groups": groups_without_retention}
