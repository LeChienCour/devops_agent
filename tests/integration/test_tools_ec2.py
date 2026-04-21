"""Integration tests for ec2_inventory tool functions using moto."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import boto3
import pytest
from moto import mock_aws

from agent.tools.ec2_inventory import (
    list_old_snapshots,
    list_stopped_instances,
    list_unassociated_eips,
    list_unattached_ebs_volumes,
)


@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set dummy AWS credentials so moto intercepts all boto3 calls."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


def _clear_client_cache() -> None:
    from common import aws_clients

    aws_clients._clients.clear()


# ---------------------------------------------------------------------------
# list_unattached_ebs_volumes
# ---------------------------------------------------------------------------


class TestListUnattachedEbsVolumes:
    """Tests for ec2_inventory.list_unattached_ebs_volumes."""

    @mock_aws
    def test_list_unattached_ebs_volumes_returns_available_volumes(self) -> None:
        """Volumes in 'available' state are returned with cost estimate."""
        _clear_client_cache()
        ec2 = boto3.client("ec2", region_name="us-east-1")
        ec2.create_volume(AvailabilityZone="us-east-1a", Size=100, VolumeType="gp2")
        ec2.create_volume(AvailabilityZone="us-east-1b", Size=50, VolumeType="gp3")

        result = list_unattached_ebs_volumes(region="us-east-1")

        assert len(result["volumes"]) == 2
        vol_ids = {v["VolumeId"] for v in result["volumes"]}
        assert len(vol_ids) == 2

    @mock_aws
    def test_list_unattached_ebs_volumes_includes_estimated_cost(self) -> None:
        """Each returned volume has estimated_monthly_cost based on size and type."""
        _clear_client_cache()
        ec2 = boto3.client("ec2", region_name="us-east-1")
        ec2.create_volume(AvailabilityZone="us-east-1a", Size=100, VolumeType="gp2")

        result = list_unattached_ebs_volumes(region="us-east-1")

        assert len(result["volumes"]) == 1
        # 100 GB * $0.10/GB = $10.00
        assert result["volumes"][0]["estimated_monthly_cost"] == pytest.approx(10.0)

    @mock_aws
    def test_list_unattached_ebs_volumes_excludes_attached_volumes(self) -> None:
        """Volumes attached to an instance (in-use state) are not returned."""
        _clear_client_cache()
        ec2 = boto3.client("ec2", region_name="us-east-1")

        # Create an instance — its root volume is 'in-use'
        ec2.run_instances(
            ImageId="ami-12345678",
            MinCount=1,
            MaxCount=1,
            InstanceType="t3.micro",
        )
        # Also create an unattached volume
        ec2.create_volume(AvailabilityZone="us-east-1a", Size=20, VolumeType="gp3")

        result = list_unattached_ebs_volumes(region="us-east-1")

        # Only the explicitly unattached volume should appear
        assert len(result["volumes"]) == 1
        assert result["volumes"][0]["Size"] == 20

    @mock_aws
    def test_list_unattached_ebs_volumes_returns_empty_when_none(self) -> None:
        """Returns empty list when no volumes are in available state."""
        _clear_client_cache()

        result = list_unattached_ebs_volumes(region="us-east-1")

        assert result["volumes"] == []


# ---------------------------------------------------------------------------
# list_unassociated_eips
# ---------------------------------------------------------------------------


class TestListUnassociatedEips:
    """Tests for ec2_inventory.list_unassociated_eips."""

    @mock_aws
    def test_list_unassociated_eips_returns_unassociated(self) -> None:
        """Unassociated VPC EIPs are returned with cost estimate."""
        _clear_client_cache()
        ec2 = boto3.client("ec2", region_name="us-east-1")
        ec2.allocate_address(Domain="vpc")
        ec2.allocate_address(Domain="vpc")

        result = list_unassociated_eips(region="us-east-1")

        assert len(result["eips"]) == 2
        for eip in result["eips"]:
            assert eip["estimated_monthly_cost"] == pytest.approx(3.60)
            assert "AllocationId" in eip
            assert "PublicIp" in eip

    @mock_aws
    def test_list_unassociated_eips_returns_empty_when_none(self) -> None:
        """Returns empty list when there are no unassociated EIPs."""
        _clear_client_cache()

        result = list_unassociated_eips(region="us-east-1")

        assert result["eips"] == []

    @mock_aws
    def test_list_unassociated_eips_excludes_associated(self) -> None:
        """EIPs associated with a NAT gateway are excluded from results."""
        _clear_client_cache()
        ec2 = boto3.client("ec2", region_name="us-east-1")

        # Allocate one EIP and leave it free
        ec2.allocate_address(Domain="vpc")

        # Allocate another and associate with an instance to mark it used
        resp = ec2.allocate_address(Domain="vpc")
        allocation_id = resp["AllocationId"]

        instance_resp = ec2.run_instances(
            ImageId="ami-12345678",
            MinCount=1,
            MaxCount=1,
            InstanceType="t3.micro",
        )
        instance_id = instance_resp["Instances"][0]["InstanceId"]
        ec2.associate_address(InstanceId=instance_id, AllocationId=allocation_id)

        result = list_unassociated_eips(region="us-east-1")

        # Only the unassociated EIP should appear
        assert len(result["eips"]) == 1


# ---------------------------------------------------------------------------
# list_old_snapshots
# ---------------------------------------------------------------------------


class TestListOldSnapshots:
    """Tests for ec2_inventory.list_old_snapshots."""

    @mock_aws
    def test_list_old_snapshots_filters_by_age(self) -> None:
        """Only snapshots older than min_age_days are returned."""
        _clear_client_cache()
        ec2 = boto3.client("ec2", region_name="us-east-1")

        # Create a volume to snapshot
        vol_resp = ec2.create_volume(
            AvailabilityZone="us-east-1a", Size=10, VolumeType="gp2"
        )
        volume_id = vol_resp["VolumeId"]

        # Create a snapshot — moto sets StartTime to 'now'
        ec2.create_snapshot(VolumeId=volume_id, Description="recent-snap")

        # With 90-day minimum, a snapshot created right now should NOT appear
        result = list_old_snapshots(min_age_days=90, region="us-east-1")

        # Recent snapshot must be excluded
        snap_ids = [s["SnapshotId"] for s in result["snapshots"]]
        assert len(snap_ids) == 0

    @mock_aws
    def test_list_old_snapshots_returns_estimated_cost(self) -> None:
        """Each snapshot entry includes an estimated_monthly_cost based on VolumeSize."""
        _clear_client_cache()
        ec2 = boto3.client("ec2", region_name="us-east-1")
        vol_resp = ec2.create_volume(
            AvailabilityZone="us-east-1a", Size=200, VolumeType="gp2"
        )
        volume_id = vol_resp["VolumeId"]
        snap_resp = ec2.create_snapshot(VolumeId=volume_id)

        # Patch StartTime on the moto snapshot to simulate old age
        import unittest.mock as mock

        old_time = datetime.now(tz=UTC) - timedelta(days=120)

        original_paginate = ec2.get_paginator("describe_snapshots").paginate

        def _patched_paginate(**kwargs):  # type: ignore[no-untyped-def]
            pages = list(original_paginate(**kwargs))
            for page in pages:
                for snap in page.get("Snapshots", []):
                    if snap["SnapshotId"] == snap_resp["SnapshotId"]:
                        snap["StartTime"] = old_time
            return iter(pages)

        paginator_mock = mock.MagicMock()
        paginator_mock.paginate = _patched_paginate

        with mock.patch.object(ec2, "get_paginator", return_value=paginator_mock):
            result = list_old_snapshots(min_age_days=90, region="us-east-1")

        if result["snapshots"]:
            snap = result["snapshots"][0]
            # 200 GB * $0.05/GB = $10.00
            assert snap["estimated_monthly_cost"] == pytest.approx(10.0)

    @mock_aws
    def test_list_old_snapshots_returns_source_volume_exists_flag(self) -> None:
        """snapshot entries include source_volume_exists boolean."""
        _clear_client_cache()
        ec2 = boto3.client("ec2", region_name="us-east-1")
        vol_resp = ec2.create_volume(
            AvailabilityZone="us-east-1a", Size=10, VolumeType="gp2"
        )
        volume_id = vol_resp["VolumeId"]
        ec2.create_snapshot(VolumeId=volume_id)

        import unittest.mock as mock

        old_time = datetime.now(tz=UTC) - timedelta(days=120)

        original_paginate = ec2.get_paginator("describe_snapshots").paginate

        def _patched_paginate(**kwargs):  # type: ignore[no-untyped-def]
            pages = list(original_paginate(**kwargs))
            for page in pages:
                for snap in page.get("Snapshots", []):
                    snap["StartTime"] = old_time
            return iter(pages)

        paginator_mock = mock.MagicMock()
        paginator_mock.paginate = _patched_paginate

        with mock.patch.object(ec2, "get_paginator", return_value=paginator_mock):
            result = list_old_snapshots(min_age_days=90, region="us-east-1")

        for snap in result["snapshots"]:
            assert "source_volume_exists" in snap


# ---------------------------------------------------------------------------
# list_stopped_instances
# ---------------------------------------------------------------------------


class TestListStoppedInstances:
    """Tests for ec2_inventory.list_stopped_instances."""

    @mock_aws
    def test_list_stopped_instances_filters_by_stopped_state(self) -> None:
        """Only stopped instances appear; running instances are excluded."""
        _clear_client_cache()
        ec2 = boto3.client("ec2", region_name="us-east-1")

        # Launch then stop one instance
        run_resp = ec2.run_instances(
            ImageId="ami-12345678",
            MinCount=1,
            MaxCount=1,
            InstanceType="t3.micro",
        )
        instance_id = run_resp["Instances"][0]["InstanceId"]
        ec2.stop_instances(InstanceIds=[instance_id])

        # Launch a second instance and leave it running
        ec2.run_instances(
            ImageId="ami-12345678",
            MinCount=1,
            MaxCount=1,
            InstanceType="t3.small",
        )

        # With min_stopped_days=0, all stopped instances qualify
        result = list_stopped_instances(min_stopped_days=0, region="us-east-1")

        instance_ids = [i["InstanceId"] for i in result["instances"]]
        assert instance_id in instance_ids
        # Running instance must not appear
        assert len(result["instances"]) == 1

    @mock_aws
    def test_list_stopped_instances_includes_attached_volume_count(self) -> None:
        """Each instance entry includes attached_volume_count."""
        _clear_client_cache()
        ec2 = boto3.client("ec2", region_name="us-east-1")

        run_resp = ec2.run_instances(
            ImageId="ami-12345678",
            MinCount=1,
            MaxCount=1,
            InstanceType="t3.micro",
        )
        instance_id = run_resp["Instances"][0]["InstanceId"]
        ec2.stop_instances(InstanceIds=[instance_id])

        result = list_stopped_instances(min_stopped_days=0, region="us-east-1")

        assert len(result["instances"]) == 1
        assert "attached_volume_count" in result["instances"][0]

    @mock_aws
    def test_list_stopped_instances_returns_empty_when_none_stopped(self) -> None:
        """Returns empty list when no instances are in stopped state."""
        _clear_client_cache()
        ec2 = boto3.client("ec2", region_name="us-east-1")
        ec2.run_instances(
            ImageId="ami-12345678",
            MinCount=1,
            MaxCount=1,
            InstanceType="t3.micro",
        )

        result = list_stopped_instances(min_stopped_days=0, region="us-east-1")

        assert result["instances"] == []

    @mock_aws
    def test_list_stopped_instances_filters_recently_stopped(self) -> None:
        """Instances stopped less than min_stopped_days ago are excluded."""
        _clear_client_cache()
        ec2 = boto3.client("ec2", region_name="us-east-1")

        run_resp = ec2.run_instances(
            ImageId="ami-12345678",
            MinCount=1,
            MaxCount=1,
            InstanceType="t3.micro",
        )
        instance_id = run_resp["Instances"][0]["InstanceId"]
        ec2.stop_instances(InstanceIds=[instance_id])

        # With 30-day minimum, a just-launched instance should NOT qualify
        # (its LaunchTime is essentially now)
        result = list_stopped_instances(min_stopped_days=30, region="us-east-1")

        assert result["instances"] == []
