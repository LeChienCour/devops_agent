"""MCP server for EC2 inventory tools — standalone wrapper for demo/CLI use.

Architecture (ADR-001): All business logic lives in agent/tools/ec2_inventory.py.
This server re-exposes those functions over the MCP protocol for use with
``mcp dev`` or ``mcp-cli`` during live demos. The LangGraph agent NEVER calls
this server at runtime.

Usage:
    mcp dev src/mcp_servers/ec2_inventory/server.py
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from agent.tools import ec2_inventory

mcp = FastMCP("finops-ec2-inventory")


@mcp.tool()
def list_unattached_ebs_volumes(region: str = "us-east-1") -> dict:
    """List all EBS volumes that are unattached (in 'available' state).

    Unattached volumes incur storage costs — $0.08–$0.10/GB/month — with no
    workload benefiting from them. Use this tool to identify volumes safe to
    snapshot-and-delete or simply delete.

    Args:
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        List of volumes with VolumeId, Size, VolumeType, CreateTime,
        AvailabilityZone, Tags, and estimated_monthly_cost.
    """
    return ec2_inventory.list_unattached_ebs_volumes(region)


@mcp.tool()
def list_idle_nat_gateways(region: str = "us-east-1") -> dict:
    """List NAT Gateways with negligible outbound traffic over the last 7 days.

    A NAT Gateway with less than 1 MB of outbound traffic in 7 days is considered
    idle. Each idle NAT Gateway costs ~$32/month in fixed charges plus any data
    transfer fees. Use this tool to flag candidates for deletion.

    Args:
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        List of NAT Gateways with nat_gateway_id, vpc_id, subnet_id,
        total_bytes_7d, and is_idle flag.
    """
    return ec2_inventory.list_idle_nat_gateways(region)


@mcp.tool()
def list_unassociated_eips(region: str = "us-east-1") -> dict:
    """List Elastic IP addresses that are not associated with any resource.

    AWS charges $3.60/month per unassociated Elastic IP. These are safe to
    release if no longer needed. Use this tool to enumerate all chargeable
    idle EIPs in the account.

    Args:
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        List of EIPs with AllocationId, PublicIp, and estimated_monthly_cost.
    """
    return ec2_inventory.list_unassociated_eips(region)


@mcp.tool()
def list_old_snapshots(
    min_age_days: int = 90,
    region: str = "us-east-1",
) -> dict:
    """List EBS snapshots older than a minimum age in days.

    Old snapshots cost $0.05/GB/month. Snapshots whose source volume no longer
    exists are the safest to delete. Use this tool to identify snapshot cleanup
    candidates and estimate the potential storage cost reduction.

    Args:
        min_age_days: Minimum snapshot age in days to include. Defaults to 90.
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        List of snapshots with SnapshotId, VolumeId, StartTime, VolumeSize,
        source_volume_exists, and estimated_monthly_cost.
    """
    return ec2_inventory.list_old_snapshots(min_age_days, region)


@mcp.tool()
def list_stopped_instances(
    min_stopped_days: int = 30,
    region: str = "us-east-1",
) -> dict:
    """List EC2 instances that have been stopped for longer than a minimum period.

    Stopped instances do not incur compute charges, but any attached EBS volumes
    still accumulate costs. Long-stopped instances are candidates for termination
    or at minimum volume cleanup. Use this tool to surface stale stopped instances.

    Args:
        min_stopped_days: Minimum days since launch to include. Defaults to 30.
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        List of instances with InstanceId, InstanceType, LaunchTime,
        attached_volume_count, and Tags.
    """
    return ec2_inventory.list_stopped_instances(min_stopped_days, region)


if __name__ == "__main__":
    mcp.run()
