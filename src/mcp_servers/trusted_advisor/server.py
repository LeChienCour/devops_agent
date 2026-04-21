"""MCP server for Trusted Advisor tools — standalone wrapper for demo/CLI use.

Architecture (ADR-001): All business logic lives in agent/tools/trusted_advisor.py.
This server re-exposes those functions over the MCP protocol for use with
``mcp dev`` or ``mcp-cli`` during live demos. The LangGraph agent NEVER calls
this server at runtime.

Note: Trusted Advisor requires an AWS Business or Enterprise support plan.
The Support API is global and only available via the us-east-1 endpoint.

Usage:
    mcp dev src/mcp_servers/trusted_advisor/server.py
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from agent.tools import trusted_advisor

mcp = FastMCP("finops-trusted-advisor")


@mcp.tool()
def list_cost_optimization_checks(region: str = "us-east-1") -> dict[str, Any]:
    """List all Trusted Advisor cost optimisation checks with current status and savings.

    Trusted Advisor analyses your AWS account and flags cost optimisation
    opportunities such as idle load balancers, underutilised EC2 instances,
    and reserved instance purchase recommendations. Each check includes an
    estimated monthly savings amount.

    Requires an AWS Business or Enterprise support plan. Returns an empty
    list with a warning message if the account does not qualify.

    The ``region`` parameter is accepted for interface consistency but is
    ignored — the Trusted Advisor API is always called against us-east-1.

    Args:
        region: Ignored. Included for interface consistency with other tools.

    Returns:
        Dict with 'checks' list (checkId, name, status, estimated_monthly_savings)
        and optionally a 'warning' key if the support plan is insufficient.
    """
    return trusted_advisor.list_cost_optimization_checks(region)


if __name__ == "__main__":
    mcp.run()
