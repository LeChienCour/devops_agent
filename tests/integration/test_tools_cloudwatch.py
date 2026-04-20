"""Integration tests for cloudwatch tool functions using moto."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from agent.tools.cloudwatch import (
    get_metric_statistics,
    list_log_groups_without_retention,
)


@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set dummy AWS credentials so moto intercepts all boto3 calls."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


# ---------------------------------------------------------------------------
# list_log_groups_without_retention
# ---------------------------------------------------------------------------


class TestListLogGroupsWithoutRetention:
    """Tests for cloudwatch.list_log_groups_without_retention."""

    @mock_aws
    def test_list_log_groups_without_retention_returns_groups_missing_retention(
        self,
    ) -> None:
        """Log groups with no retention policy are included in the result."""
        # Arrange — clear the client cache so moto intercepts fresh
        from common import aws_clients

        aws_clients._clients.clear()

        logs = boto3.client("logs", region_name="us-east-1")
        logs.create_log_group(logGroupName="/no-retention/app")
        logs.create_log_group(logGroupName="/no-retention/worker")

        # Act
        result = list_log_groups_without_retention(region="us-east-1")

        # Assert
        names = [g["name"] for g in result["log_groups"]]
        assert "/no-retention/app" in names
        assert "/no-retention/worker" in names

    @mock_aws
    def test_list_log_groups_without_retention_excludes_groups_with_retention(
        self,
    ) -> None:
        """Log groups that have a retention policy are excluded from the result."""
        from common import aws_clients

        aws_clients._clients.clear()

        logs = boto3.client("logs", region_name="us-east-1")
        logs.create_log_group(logGroupName="/has-retention/api")
        logs.put_retention_policy(logGroupName="/has-retention/api", retentionInDays=30)
        logs.create_log_group(logGroupName="/no-retention/api")

        result = list_log_groups_without_retention(region="us-east-1")

        names = [g["name"] for g in result["log_groups"]]
        assert "/has-retention/api" not in names
        assert "/no-retention/api" in names

    @mock_aws
    def test_list_log_groups_without_retention_returns_empty_when_all_have_retention(
        self,
    ) -> None:
        """Returns an empty list when every log group has a retention policy."""
        from common import aws_clients

        aws_clients._clients.clear()

        logs = boto3.client("logs", region_name="us-east-1")
        logs.create_log_group(logGroupName="/retained/svc")
        logs.put_retention_policy(logGroupName="/retained/svc", retentionInDays=7)

        result = list_log_groups_without_retention(region="us-east-1")

        assert result["log_groups"] == []

    @mock_aws
    def test_list_log_groups_without_retention_includes_stored_bytes(self) -> None:
        """Each returned entry exposes a stored_bytes field."""
        from common import aws_clients

        aws_clients._clients.clear()

        logs = boto3.client("logs", region_name="us-east-1")
        logs.create_log_group(logGroupName="/check-bytes/app")

        result = list_log_groups_without_retention(region="us-east-1")

        assert len(result["log_groups"]) == 1
        assert "stored_bytes" in result["log_groups"][0]


# ---------------------------------------------------------------------------
# get_metric_statistics
# ---------------------------------------------------------------------------


class TestGetMetricStatistics:
    """Tests for cloudwatch.get_metric_statistics."""

    @mock_aws
    def test_get_metric_statistics_returns_datapoints(self) -> None:
        """get_metric_statistics returns a dict with a Datapoints key."""
        from common import aws_clients

        aws_clients._clients.clear()

        result = get_metric_statistics(
            namespace="AWS/EC2",
            metric_name="CPUUtilization",
            dimensions=[{"Name": "InstanceId", "Value": "i-0abc1234567890"}],
            start_time="2026-04-01T00:00:00Z",
            end_time="2026-04-08T00:00:00Z",
            period_seconds=3600,
            statistics=["Average"],
            region="us-east-1",
        )

        # moto returns empty Datapoints for metrics with no published data
        assert "Datapoints" in result

    @mock_aws
    def test_get_metric_statistics_defaults_to_average_statistic(self) -> None:
        """Calling without statistics param defaults to Average and returns Datapoints."""
        from common import aws_clients

        aws_clients._clients.clear()

        result = get_metric_statistics(
            namespace="AWS/NATGateway",
            metric_name="BytesOutToDestination",
            dimensions=[{"Name": "NatGatewayId", "Value": "nat-0abc1234"}],
            start_time="2026-04-01T00:00:00Z",
            end_time="2026-04-08T00:00:00Z",
            region="us-east-1",
        )

        assert "Datapoints" in result

    @mock_aws
    def test_get_metric_statistics_accepts_sum_statistic(self) -> None:
        """statistics=['Sum'] is a valid request and returns Datapoints."""
        from common import aws_clients

        aws_clients._clients.clear()

        result = get_metric_statistics(
            namespace="AWS/NATGateway",
            metric_name="BytesOutToDestination",
            dimensions=[{"Name": "NatGatewayId", "Value": "nat-0abc1234"}],
            start_time="2026-04-01T00:00:00Z",
            end_time="2026-04-08T00:00:00Z",
            period_seconds=604800,
            statistics=["Sum"],
            region="us-east-1",
        )

        assert "Datapoints" in result
