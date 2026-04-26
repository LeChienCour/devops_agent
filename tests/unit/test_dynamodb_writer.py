"""Unit tests for notifications.dynamodb_writer.DynamoDBWriter.

All DynamoDB calls are intercepted by moto; no real AWS credentials required.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from agent.guardrails import GuardrailsState
from agent.models.finding import Finding, Recommendation, Severity
from notifications.dynamodb_writer import DynamoDBWriter, _make_ttl

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TABLE_NAME = "finops-test-findings"
_REGION = "us-east-1"
_INVESTIGATION_ID = "inv-test-0001"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_finding(**overrides: Any) -> Finding:
    """Return a minimal valid Finding with optional field overrides."""
    base: dict[str, Any] = {
        "finding_type": "unattached_ebs",
        "severity": Severity.HIGH,
        "title": "Unattached EBS volume",
        "description": "EBS volume vol-0abc123 is unattached.",
        "resource_id": "vol-0abc123",
        "estimated_monthly_usd": 45.0,
        "confidence": 0.95,
        "remediation_command": "aws ec2 delete-volume --volume-id vol-0abc123",
        "evidence": {"region": "us-east-1"},
    }
    base.update(overrides)
    return Finding(**base)


def _make_recommendation(findings: list[Finding] | None = None) -> Recommendation:
    """Return a Recommendation wrapping the given findings list."""
    if findings is None:
        findings = [_make_finding()]
    total_usd = sum(f.estimated_monthly_usd for f in findings)
    return Recommendation(
        findings=findings,
        total_estimated_monthly_usd=total_usd,
        summary="Test summary",
        investigation_id=_INVESTIGATION_ID,
    )


def _make_writer() -> DynamoDBWriter:
    """Return a DynamoDBWriter pointed at the test table and region."""
    config = MagicMock()
    config.dynamodb_table_name = _TABLE_NAME
    config.aws_region = _REGION
    return DynamoDBWriter(config=config)


@pytest.fixture()
def ddb_client() -> Any:
    """Pytest fixture: spin up a moto-backed DynamoDB table and return the client."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name=_REGION)
        client.create_table(
            TableName=_TABLE_NAME,
            KeySchema=[
                {"AttributeName": "investigation_id", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "investigation_id", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield client


def _scan(client: Any) -> list[dict[str, Any]]:
    """Return all items currently in the test table."""
    return list(client.scan(TableName=_TABLE_NAME).get("Items", []))


# ---------------------------------------------------------------------------
# TTL helper tests
# ---------------------------------------------------------------------------


class TestMakeTtl:
    """Tests for the _make_ttl helper function."""

    def test_make_ttl_returns_integer(self) -> None:
        """TTL value must be an integer for DynamoDB numeric attribute."""
        ttl = _make_ttl()
        assert isinstance(ttl, int)

    def test_make_ttl_approximately_90_days_from_now(self) -> None:
        """TTL must be within ±5 seconds of now + 90 days."""
        from datetime import timedelta

        expected_min = int((datetime.now(UTC) + timedelta(days=90)).timestamp()) - 5
        expected_max = int((datetime.now(UTC) + timedelta(days=90)).timestamp()) + 5
        ttl = _make_ttl()
        assert expected_min <= ttl <= expected_max

    def test_make_ttl_greater_than_now(self) -> None:
        """TTL epoch must always be in the future."""
        assert _make_ttl() > int(time.time())


# ---------------------------------------------------------------------------
# DynamoDBWriter — happy path tests
# ---------------------------------------------------------------------------


class TestDynamoDBWriterWriteInvestigation:
    """Tests for DynamoDBWriter.write_investigation backed by moto."""

    def test_write_investigation_creates_meta_item(self, ddb_client: Any) -> None:
        """write_investigation must create exactly one meta#summary item."""
        writer = _make_writer()
        writer.write_investigation(_INVESTIGATION_ID, _make_recommendation(), GuardrailsState())

        meta_items = [i for i in _scan(ddb_client) if i["sk"]["S"] == "meta#summary"]
        assert len(meta_items) == 1

    def test_write_investigation_meta_item_pk_sk_correct(self, ddb_client: Any) -> None:
        """Meta item must carry the correct PK (investigation_id) and SK."""
        writer = _make_writer()
        writer.write_investigation(_INVESTIGATION_ID, _make_recommendation(), GuardrailsState())

        meta = next(i for i in _scan(ddb_client) if i["sk"]["S"] == "meta#summary")
        assert meta["investigation_id"]["S"] == _INVESTIGATION_ID
        assert meta["sk"]["S"] == "meta#summary"

    def test_write_investigation_finding_item_sk_format(self, ddb_client: Any) -> None:
        """Finding SK must start with 'finding#' followed by the finding_id UUID."""
        finding = _make_finding()
        writer = _make_writer()
        writer.write_investigation(
            _INVESTIGATION_ID, _make_recommendation([finding]), GuardrailsState()
        )

        finding_items = [i for i in _scan(ddb_client) if i["sk"]["S"].startswith("finding#")]
        assert len(finding_items) == 1
        sk_suffix = finding_items[0]["sk"]["S"][len("finding#") :]
        assert sk_suffix == finding.finding_id

    def test_write_investigation_finding_item_fields(self, ddb_client: Any) -> None:
        """Finding item must carry finding_type, severity, estimated_monthly_usd."""
        finding = _make_finding(finding_type="nat_gateway_idle", severity=Severity.MEDIUM)
        writer = _make_writer()
        writer.write_investigation(
            _INVESTIGATION_ID, _make_recommendation([finding]), GuardrailsState()
        )

        item = next(i for i in _scan(ddb_client) if i["sk"]["S"].startswith("finding#"))
        assert item["finding_type"]["S"] == "nat_gateway_idle"
        assert item["severity"]["S"] == "MEDIUM"
        assert float(item["estimated_monthly_usd"]["N"]) == 45.0

    def test_write_investigation_ttl_is_set_and_in_future(self, ddb_client: Any) -> None:
        """Every item must have a TTL attribute that is greater than now."""
        writer = _make_writer()
        writer.write_investigation(_INVESTIGATION_ID, _make_recommendation(), GuardrailsState())

        for item in _scan(ddb_client):
            assert "ttl" in item, f"Missing ttl on item: {item.get('sk')}"
            assert int(item["ttl"]["N"]) > int(time.time())

    def test_write_investigation_multiple_findings_all_written(self, ddb_client: Any) -> None:
        """All findings in a recommendation are persisted as separate items."""
        findings = [
            _make_finding(resource_id="vol-001", estimated_monthly_usd=10.0),
            _make_finding(
                finding_type="rds_idle",
                resource_id="db-prod",
                estimated_monthly_usd=62.0,
            ),
            _make_finding(
                finding_type="nat_gateway_idle",
                resource_id="nat-abc",
                estimated_monthly_usd=150.0,
            ),
        ]
        writer = _make_writer()
        writer.write_investigation(
            _INVESTIGATION_ID, _make_recommendation(findings), GuardrailsState()
        )

        finding_items = [i for i in _scan(ddb_client) if i["sk"]["S"].startswith("finding#")]
        assert len(finding_items) == 3

    def test_write_investigation_empty_findings_only_meta_written(self, ddb_client: Any) -> None:
        """When there are no findings only the meta#summary item is written."""
        writer = _make_writer()
        writer.write_investigation(_INVESTIGATION_ID, _make_recommendation([]), GuardrailsState())

        items = _scan(ddb_client)
        assert len(items) == 1
        assert items[0]["sk"]["S"] == "meta#summary"

    def test_write_investigation_meta_total_savings_correct(self, ddb_client: Any) -> None:
        """meta#summary item must reflect total_estimated_monthly_usd correctly."""
        findings = [
            _make_finding(resource_id="vol-a", estimated_monthly_usd=30.0),
            _make_finding(resource_id="vol-b", estimated_monthly_usd=20.0),
        ]
        writer = _make_writer()
        writer.write_investigation(
            _INVESTIGATION_ID, _make_recommendation(findings), GuardrailsState()
        )

        meta = next(i for i in _scan(ddb_client) if i["sk"]["S"] == "meta#summary")
        assert float(meta["total_savings_usd"]["N"]) == pytest.approx(50.0)

    def test_write_investigation_meta_records_guardrail_violation_count(
        self, ddb_client: Any
    ) -> None:
        """meta#summary must store the number of guardrail violations."""
        writer = _make_writer()
        guardrails = GuardrailsState(violations=["iteration limit exceeded"])
        writer.write_investigation(_INVESTIGATION_ID, _make_recommendation(), guardrails)

        meta = next(i for i in _scan(ddb_client) if i["sk"]["S"] == "meta#summary")
        assert int(meta["guardrail_violations"]["N"]) == 1

    def test_write_investigation_finding_with_no_remediation_command(self, ddb_client: Any) -> None:
        """Findings without remediation_command must not cause a KeyError."""
        finding = _make_finding(remediation_command=None)
        writer = _make_writer()
        writer.write_investigation(
            _INVESTIGATION_ID, _make_recommendation([finding]), GuardrailsState()
        )

        finding_item = next(i for i in _scan(ddb_client) if i["sk"]["S"].startswith("finding#"))
        assert "remediation_command" not in finding_item

    def test_write_investigation_finding_with_no_resource_id(self, ddb_client: Any) -> None:
        """Finding with resource_id=None must omit the resource_ids attribute."""
        finding = _make_finding(resource_id=None)
        writer = _make_writer()
        writer.write_investigation(
            _INVESTIGATION_ID, _make_recommendation([finding]), GuardrailsState()
        )

        finding_item = next(i for i in _scan(ddb_client) if i["sk"]["S"].startswith("finding#"))
        assert "resource_ids" not in finding_item


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestDynamoDBWriterErrorHandling:
    """Tests that ClientError is logged and re-raised."""

    def test_write_investigation_client_error_is_reraised(self) -> None:
        """ClientError from put_item must propagate out of write_investigation."""
        writer = _make_writer()
        error_response = {
            "Error": {"Code": "ResourceNotFoundException", "Message": "Table not found"}
        }
        mock_client = MagicMock()
        mock_client.put_item.side_effect = ClientError(error_response, "PutItem")

        with (
            patch("notifications.dynamodb_writer.get_client", return_value=mock_client),
            pytest.raises(ClientError) as exc_info,
        ):
            writer.write_investigation(_INVESTIGATION_ID, _make_recommendation(), GuardrailsState())

        assert exc_info.value.response["Error"]["Code"] == "ResourceNotFoundException"

    def test_write_investigation_client_error_logged_before_reraise(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The error event must appear in structlog output before ClientError propagates.

        structlog writes JSON to stdout; we verify the event key is present
        in the captured output rather than patching the logger internals.
        """
        writer = _make_writer()
        error_response = {
            "Error": {
                "Code": "ProvisionedThroughputExceededException",
                "Message": "Rate exceeded",
            }
        }
        mock_client = MagicMock()
        mock_client.put_item.side_effect = ClientError(error_response, "PutItem")

        with (
            patch("notifications.dynamodb_writer.get_client", return_value=mock_client),
            pytest.raises(ClientError),
        ):
            writer.write_investigation(_INVESTIGATION_ID, _make_recommendation(), GuardrailsState())

        captured = capsys.readouterr().out
        assert "dynamodb_writer_put_item_failed" in captured
