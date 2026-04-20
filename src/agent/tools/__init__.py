"""Tool registry — maps every tool name to its (module, callable) pair.

The LangGraph gather node imports ``TOOL_REGISTRY`` to dispatch tool calls
dynamically. ``ALL_TOOLS`` is the combined Bedrock-compatible schema list
passed to the plan node so the LLM knows which tools are available.

Architecture (ADR-001):
    Tools live here as plain Python functions.
    MCP servers in src/mcp_servers/ import from these modules for demo use.
    The agent NEVER calls MCP servers at runtime.
"""

from __future__ import annotations

from agent.tools import cloudwatch, cost_explorer, ec2_inventory, trusted_advisor

# Maps tool name → (module, callable).
# The gather node uses this to dispatch calls without a long if/elif chain.
TOOL_REGISTRY: dict[str, tuple] = {
    # cost_explorer
    "get_cost_by_service": (cost_explorer, cost_explorer.get_cost_by_service),
    "get_cost_anomalies": (cost_explorer, cost_explorer.get_cost_anomalies),
    "get_cost_forecast": (cost_explorer, cost_explorer.get_cost_forecast),
    # cloudwatch
    "get_metric_statistics": (cloudwatch, cloudwatch.get_metric_statistics),
    "get_cloudwatch_insights": (cloudwatch, cloudwatch.get_cloudwatch_insights),
    "list_log_groups_without_retention": (
        cloudwatch,
        cloudwatch.list_log_groups_without_retention,
    ),
    # ec2_inventory
    "list_unattached_ebs_volumes": (
        ec2_inventory,
        ec2_inventory.list_unattached_ebs_volumes,
    ),
    "list_idle_nat_gateways": (ec2_inventory, ec2_inventory.list_idle_nat_gateways),
    "list_unassociated_eips": (ec2_inventory, ec2_inventory.list_unassociated_eips),
    "list_old_snapshots": (ec2_inventory, ec2_inventory.list_old_snapshots),
    "list_stopped_instances": (ec2_inventory, ec2_inventory.list_stopped_instances),
    # trusted_advisor
    "list_cost_optimization_checks": (
        trusted_advisor,
        trusted_advisor.list_cost_optimization_checks,
    ),
}

# Combined Bedrock tool_use schema list passed to the plan node prompt.
ALL_TOOLS: list[dict] = (
    cost_explorer.TOOLS + cloudwatch.TOOLS + ec2_inventory.TOOLS + trusted_advisor.TOOLS
)

__all__ = ["ALL_TOOLS", "TOOL_REGISTRY"]
