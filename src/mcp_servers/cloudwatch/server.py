"""MCP server for CloudWatch tools — standalone wrapper for demo/CLI use.

Architecture (ADR-001): All business logic lives in agent/tools/cloudwatch.py.
This server re-exposes those functions over the MCP protocol for use with
``mcp dev`` or ``mcp-cli`` during live demos. The LangGraph agent NEVER calls
this server at runtime.

Usage:
    mcp dev src/mcp_servers/cloudwatch/server.py
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from agent.tools import cloudwatch

mcp = FastMCP("finops-cloudwatch")


@mcp.tool()
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
    """Return CloudWatch metric statistics for a given namespace and metric.

    Use this tool to check resource utilisation over a time window — for example
    NAT Gateway BytesOutToDestination to detect idle gateways, or EC2 CPUUtilization
    to find undersized or oversized instances.

    Args:
        namespace: CloudWatch namespace, e.g. 'AWS/NATGateway' or 'AWS/EC2'.
        metric_name: Metric name, e.g. 'BytesOutToDestination' or 'CPUUtilization'.
        dimensions: List of {Name: str, Value: str} dimension dicts.
        start_time: Start of the window in ISO 8601 format.
        end_time: End of the window in ISO 8601 format.
        period_seconds: Aggregation period in seconds. Defaults to 3600 (1 hour).
        statistics: Statistics to retrieve. Defaults to ['Average'].
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        Datapoints list with timestamps and metric values.
    """
    return cloudwatch.get_metric_statistics(
        namespace,
        metric_name,
        dimensions,
        start_time,
        end_time,
        period_seconds,
        statistics,
        region,
    )


@mcp.tool()
def get_cloudwatch_insights(
    log_group_name: str,
    query_string: str,
    start_time_epoch: int,
    end_time_epoch: int,
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Run a CloudWatch Logs Insights query and return the results.

    Use this tool to analyse Lambda memory utilisation, detect error patterns,
    or query any structured log data. Polls until the query completes (up to 30s).

    Example query for Lambda memory utilisation:
        filter @type = 'REPORT'
        | stats avg(@memorySize / 1000000) as avg_mb,
                max(@maxMemoryUsed / 1000000) as max_used_mb by functionVersion

    Args:
        log_group_name: CloudWatch Log Group to query, e.g. '/aws/lambda/my-function'.
        query_string: CloudWatch Logs Insights query string.
        start_time_epoch: Query start time as Unix epoch seconds.
        end_time_epoch: Query end time as Unix epoch seconds.
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        Query results list with status and statistics.
    """
    return cloudwatch.get_cloudwatch_insights(
        log_group_name,
        query_string,
        start_time_epoch,
        end_time_epoch,
        region,
    )


@mcp.tool()
def list_log_groups_without_retention(
    region: str = "us-east-1",
) -> dict[str, Any]:
    """List all CloudWatch Log Groups with no retention policy.

    Log Groups without a retention policy grow indefinitely, accumulating
    storage costs at $0.03/GB/month. Use this tool to identify groups that
    need a retention policy applied to control costs.

    Args:
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        List of log groups with name, stored_bytes, and creation_time.
    """
    return cloudwatch.list_log_groups_without_retention(region)


if __name__ == "__main__":
    mcp.run()
