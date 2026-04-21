"""MCP server for Cost Explorer tools — standalone wrapper for demo/CLI use.

Architecture (ADR-001): All business logic lives in agent/tools/cost_explorer.py.
This server re-exposes those functions over the MCP protocol for use with
``mcp dev`` or ``mcp-cli`` during live demos. The LangGraph agent NEVER calls
this server at runtime.

Usage:
    mcp dev src/mcp_servers/cost_explorer/server.py
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from agent.tools import cost_explorer

mcp = FastMCP("finops-cost-explorer")


@mcp.tool()
def get_cost_by_service(
    start_date: str,
    end_date: str,
    granularity: str = "MONTHLY",
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Return AWS costs grouped by service for the given date range.

    Use this tool to identify which AWS services are spending the most
    money. Results are broken down by service with unblended costs.

    Args:
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        granularity: DAILY or MONTHLY aggregation. Defaults to MONTHLY.
        region: AWS region for the API call. Defaults to us-east-1.

    Returns:
        ResultsByTime from Cost Explorer with per-service cost breakdown.
    """
    return cost_explorer.get_cost_by_service(start_date, end_date, granularity, region)


@mcp.tool()
def get_cost_anomalies(
    threshold_usd: float = 5.0,
    lookback_days: int = 30,
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Return cost anomalies detected by AWS Cost Anomaly Detection.

    Use this tool to find unexpected cost spikes above a given USD threshold.
    Anomalies are detected automatically by AWS and surfaced here for review.

    Args:
        threshold_usd: Minimum anomaly impact in USD to include. Defaults to 5.0.
        lookback_days: Days back from today to search. Defaults to 30.
        region: AWS region for the API call. Defaults to us-east-1.

    Returns:
        List of anomalies with root cause and impact data.
    """
    return cost_explorer.get_cost_anomalies(threshold_usd, lookback_days, region)


@mcp.tool()
def get_cost_forecast(
    start_date: str,
    end_date: str,
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Return the AWS cost forecast for a future date range.

    Use this tool to project whether costs are trending upward unexpectedly.
    Forecasts are based on historical usage patterns.

    Args:
        start_date: Forecast start date in YYYY-MM-DD format.
        end_date: Forecast end date in YYYY-MM-DD format.
        region: AWS region for the API call. Defaults to us-east-1.

    Returns:
        Forecast total and ResultsByTime with projected costs.
    """
    return cost_explorer.get_cost_forecast(start_date, end_date, region)


if __name__ == "__main__":
    mcp.run()
