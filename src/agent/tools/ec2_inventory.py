"""EC2 inventory tool — in-process wrapper used by the LangGraph agent.

MCP-compatible schema kept in src/mcp_servers/ec2_inventory/ for standalone demo use.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aws_lambda_powertools import Logger

from common.aws_clients import get_client

logger = Logger(service="finops-agent")

# EBS monthly cost per GB by volume type
_EBS_COST_PER_GB: dict[str, float] = {
    "gp2": 0.10,
    "gp3": 0.08,
    "io1": 0.125,
    "io2": 0.125,
    "st1": 0.045,
    "sc1": 0.025,
    "standard": 0.05,
}
_EBS_COST_DEFAULT = 0.10  # fallback for unknown types

# Snapshot storage cost per GB/month
_SNAPSHOT_COST_PER_GB = 0.05

# EIP hourly cost when unassociated: $0.005/hr ≈ $3.60/month
_EIP_MONTHLY_COST = 3.60

# NAT Gateway idle threshold: 1 MB over 7 days
_NAT_IDLE_BYTES_THRESHOLD = 1_048_576

TOOLS: list[dict] = [
    {
        "name": "list_unattached_ebs_volumes",
        "description": (
            "Lists all EBS volumes in 'available' state (not attached to any instance). "
            "Unattached volumes incur storage costs with no value. "
            "Returns size, type, age, and estimated monthly cost for each volume."
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
    {
        "name": "list_idle_nat_gateways",
        "description": (
            "Lists NAT Gateways with less than 1 MB of outbound traffic over the last 7 days. "
            "Idle NAT Gateways cost ~$32/month plus data transfer. "
            "Returns throughput data and idle flag for each gateway."
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
    {
        "name": "list_unassociated_eips",
        "description": (
            "Lists Elastic IP addresses in VPC scope that are not associated with any resource. "
            "Each unassociated EIP costs $3.60/month. "
            "Returns allocation IDs and public IPs."
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
    {
        "name": "list_old_snapshots",
        "description": (
            "Lists EBS snapshots owned by the account that are older than a minimum age "
            "and checks whether the source volume still exists. "
            "Old snapshots from deleted volumes are safe to remove. "
            "Each GB costs $0.05/month in snapshot storage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "min_age_days": {
                    "type": "integer",
                    "description": "Minimum snapshot age in days to include. Defaults to 90.",
                    "default": 90,
                },
                "region": {
                    "type": "string",
                    "description": "AWS region to query. Defaults to us-east-1.",
                    "default": "us-east-1",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_stopped_instances",
        "description": (
            "Lists EC2 instances that have been in stopped state for longer than a minimum "
            "number of days. Stopped instances still incur EBS volume costs. "
            "Returns instance type, launch time, and attached volume count."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "min_stopped_days": {
                    "type": "integer",
                    "description": "Minimum days an instance must have been stopped. Defaults to 30.",
                    "default": 30,
                },
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


def list_unattached_ebs_volumes(
    region: str = "us-east-1",
) -> dict:
    """Return all EBS volumes in 'available' (unattached) state.

    Args:
        region: AWS region to query.

    Returns:
        Dict with ``volumes`` list. Each entry contains ``VolumeId``, ``Size``,
        ``VolumeType``, ``CreateTime``, ``AvailabilityZone``, ``Tags``, and
        ``estimated_monthly_cost``.
    """
    ec2 = get_client("ec2", region)
    response = ec2.describe_volumes(
        Filters=[{"Name": "status", "Values": ["available"]}]
    )

    volumes = []
    for vol in response.get("Volumes", []):
        size_gb: int = vol.get("Size", 0)
        vol_type: str = vol.get("VolumeType", "gp2")
        cost_per_gb = _EBS_COST_PER_GB.get(vol_type, _EBS_COST_DEFAULT)
        estimated_monthly_cost = round(size_gb * cost_per_gb, 2)

        create_time = vol.get("CreateTime")
        volumes.append(
            {
                "VolumeId": vol.get("VolumeId"),
                "Size": size_gb,
                "VolumeType": vol_type,
                "CreateTime": create_time.isoformat() if isinstance(create_time, datetime) else str(create_time),
                "AvailabilityZone": vol.get("AvailabilityZone"),
                "Tags": vol.get("Tags", []),
                "estimated_monthly_cost": estimated_monthly_cost,
            }
        )

    logger.info("list_unattached_ebs_volumes_complete", region=region, count=len(volumes))
    return {"volumes": volumes}


def list_idle_nat_gateways(
    region: str = "us-east-1",
) -> dict:
    """Return NAT Gateways with fewer than 1 MB of outbound traffic in the last 7 days.

    Queries CloudWatch ``NatGateway`` namespace ``BytesOutToDestination`` metric
    (Sum over 7 days) for each available NAT Gateway.

    Args:
        region: AWS region to query.

    Returns:
        Dict with ``nat_gateways`` list. Each entry contains ``nat_gateway_id``,
        ``vpc_id``, ``subnet_id``, ``total_bytes_7d``, and ``is_idle``.
    """
    ec2 = get_client("ec2", region)
    cw = get_client("cloudwatch", region)

    ngw_response = ec2.describe_nat_gateways(
        Filter=[{"Name": "state", "Values": ["available"]}]
    )

    now = datetime.now(tz=timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    results = []
    for ngw in ngw_response.get("NatGateways", []):
        ngw_id: str = ngw["NatGatewayId"]
        vpc_id: str = ngw.get("VpcId", "")
        subnet_id: str = ngw.get("SubnetId", "")

        cw_response = cw.get_metric_statistics(
            Namespace="AWS/NATGateway",
            MetricName="BytesOutToDestination",
            Dimensions=[{"Name": "NatGatewayId", "Value": ngw_id}],
            StartTime=seven_days_ago,
            EndTime=now,
            Period=604800,  # 7 days in seconds
            Statistics=["Sum"],
        )

        datapoints = cw_response.get("Datapoints", [])
        total_bytes = sum(dp.get("Sum", 0.0) for dp in datapoints)
        is_idle = total_bytes < _NAT_IDLE_BYTES_THRESHOLD

        results.append(
            {
                "nat_gateway_id": ngw_id,
                "vpc_id": vpc_id,
                "subnet_id": subnet_id,
                "total_bytes_7d": total_bytes,
                "is_idle": is_idle,
            }
        )

    idle_count = sum(1 for r in results if r["is_idle"])
    logger.info(
        "list_idle_nat_gateways_complete",
        region=region,
        total=len(results),
        idle=idle_count,
    )
    return {"nat_gateways": results}


def list_unassociated_eips(
    region: str = "us-east-1",
) -> dict:
    """Return Elastic IP addresses not associated with any resource.

    Filters to VPC-domain EIPs where ``AssociationId`` is absent.

    Args:
        region: AWS region to query.

    Returns:
        Dict with ``eips`` list. Each entry contains ``AllocationId``,
        ``PublicIp``, and ``estimated_monthly_cost``.
    """
    ec2 = get_client("ec2", region)
    response = ec2.describe_addresses()

    unassociated = []
    for addr in response.get("Addresses", []):
        if addr.get("AssociationId") is None and addr.get("Domain") == "vpc":
            unassociated.append(
                {
                    "AllocationId": addr.get("AllocationId"),
                    "PublicIp": addr.get("PublicIp"),
                    "estimated_monthly_cost": _EIP_MONTHLY_COST,
                }
            )

    logger.info(
        "list_unassociated_eips_complete",
        region=region,
        count=len(unassociated),
    )
    return {"eips": unassociated}


def list_old_snapshots(
    min_age_days: int = 90,
    region: str = "us-east-1",
) -> dict:
    """Return EBS snapshots older than ``min_age_days`` days.

    Uses a paginator to retrieve all self-owned snapshots, filters by age,
    then checks if the source volume still exists.

    Args:
        min_age_days: Minimum snapshot age in days. Defaults to 90.
        region: AWS region to query.

    Returns:
        Dict with ``snapshots`` list. Each entry contains ``SnapshotId``,
        ``VolumeId``, ``StartTime``, ``VolumeSize``, ``source_volume_exists``,
        and ``estimated_monthly_cost``.
    """
    ec2 = get_client("ec2", region)
    paginator = ec2.get_paginator("describe_snapshots")

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=min_age_days)

    old_snapshots = []
    for page in paginator.paginate(OwnerIds=["self"]):
        for snap in page.get("Snapshots", []):
            start_time = snap.get("StartTime")
            if start_time is None:
                continue
            # boto3 returns aware datetimes; ensure comparison is valid
            if not isinstance(start_time, datetime):
                continue
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            if start_time >= cutoff:
                continue

            volume_id: str = snap.get("VolumeId", "")
            volume_size: int = snap.get("VolumeSize", 0)

            # Check if source volume still exists
            source_volume_exists = False
            if volume_id:
                try:
                    vol_resp = ec2.describe_volumes(VolumeIds=[volume_id])
                    source_volume_exists = len(vol_resp.get("Volumes", [])) > 0
                except Exception:
                    # InvalidVolume.NotFound or similar — volume is gone
                    source_volume_exists = False

            old_snapshots.append(
                {
                    "SnapshotId": snap.get("SnapshotId"),
                    "VolumeId": volume_id,
                    "StartTime": start_time.isoformat(),
                    "VolumeSize": volume_size,
                    "source_volume_exists": source_volume_exists,
                    "estimated_monthly_cost": round(volume_size * _SNAPSHOT_COST_PER_GB, 2),
                }
            )

    logger.info(
        "list_old_snapshots_complete",
        region=region,
        min_age_days=min_age_days,
        count=len(old_snapshots),
    )
    return {"snapshots": old_snapshots}


def list_stopped_instances(
    min_stopped_days: int = 30,
    region: str = "us-east-1",
) -> dict:
    """Return EC2 instances in stopped state older than ``min_stopped_days``.

    Filters to instances whose ``LaunchTime`` is older than the threshold.
    Stopped instances still incur costs for any attached EBS volumes.

    Args:
        min_stopped_days: Minimum days since launch to include. Defaults to 30.
        region: AWS region to query.

    Returns:
        Dict with ``instances`` list. Each entry contains ``InstanceId``,
        ``InstanceType``, ``LaunchTime``, ``attached_volume_count``, and ``Tags``.
    """
    ec2 = get_client("ec2", region)
    response = ec2.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
    )

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=min_stopped_days)
    instances = []

    for reservation in response.get("Reservations", []):
        for inst in reservation.get("Instances", []):
            launch_time = inst.get("LaunchTime")
            if launch_time is None:
                continue
            if not isinstance(launch_time, datetime):
                continue
            if launch_time.tzinfo is None:
                launch_time = launch_time.replace(tzinfo=timezone.utc)
            if launch_time >= cutoff:
                continue

            block_devices = inst.get("BlockDeviceMappings", [])
            attached_volume_count = len(block_devices)

            instances.append(
                {
                    "InstanceId": inst.get("InstanceId"),
                    "InstanceType": inst.get("InstanceType"),
                    "LaunchTime": launch_time.isoformat(),
                    "attached_volume_count": attached_volume_count,
                    "Tags": inst.get("Tags", []),
                }
            )

    logger.info(
        "list_stopped_instances_complete",
        region=region,
        min_stopped_days=min_stopped_days,
        count=len(instances),
    )
    return {"instances": instances}
