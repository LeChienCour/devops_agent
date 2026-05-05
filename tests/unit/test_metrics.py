"""Unit tests for MetricsPublisher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from common.config import AgentConfig
from common.metrics import _NAMESPACE, MetricsPublisher


@pytest.fixture()
def config() -> AgentConfig:
    return AgentConfig(aws_region="us-east-1")


@pytest.fixture()
def mock_cw() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def publisher(config: AgentConfig, mock_cw: MagicMock) -> MetricsPublisher:
    with patch("common.metrics.get_client", return_value=mock_cw):
        return MetricsPublisher(config)


class TestRecordInvestigation:
    def test_record_investigation_publishes_four_base_metrics(
        self, publisher: MetricsPublisher, mock_cw: MagicMock
    ) -> None:
        publisher.record_investigation(
            investigation_id="inv-123",
            findings_count=3,
            total_savings_usd=45.00,
            bedrock_cost_usd=0.18,
        )

        mock_cw.put_metric_data.assert_called_once()
        call_kwargs = mock_cw.put_metric_data.call_args.kwargs
        assert call_kwargs["Namespace"] == _NAMESPACE
        metric_names = [m["MetricName"] for m in call_kwargs["MetricData"]]
        assert "investigations_run" in metric_names
        assert "findings_total" in metric_names
        assert "total_savings_usd" in metric_names
        assert "bedrock_cost_usd" in metric_names
        assert "guardrail_violations" not in metric_names

    def test_record_investigation_includes_violations_when_nonzero(
        self, publisher: MetricsPublisher, mock_cw: MagicMock
    ) -> None:
        publisher.record_investigation(
            investigation_id="inv-456",
            findings_count=1,
            total_savings_usd=10.00,
            bedrock_cost_usd=0.05,
            violations_count=2,
        )

        call_kwargs = mock_cw.put_metric_data.call_args.kwargs
        metric_names = [m["MetricName"] for m in call_kwargs["MetricData"]]
        assert "guardrail_violations" in metric_names
        violations_metric = next(
            m for m in call_kwargs["MetricData"] if m["MetricName"] == "guardrail_violations"
        )
        assert violations_metric["Value"] == 2.0

    def test_record_investigation_investigations_run_always_one(
        self, publisher: MetricsPublisher, mock_cw: MagicMock
    ) -> None:
        publisher.record_investigation(
            investigation_id="inv-789",
            findings_count=0,
            total_savings_usd=0.0,
            bedrock_cost_usd=0.02,
        )

        call_kwargs = mock_cw.put_metric_data.call_args.kwargs
        run_metric = next(
            m for m in call_kwargs["MetricData"] if m["MetricName"] == "investigations_run"
        )
        assert run_metric["Value"] == 1.0

    def test_record_investigation_swallows_client_error(
        self, publisher: MetricsPublisher, mock_cw: MagicMock
    ) -> None:
        mock_cw.put_metric_data.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "PutMetricData",
        )

        # Must not raise — metrics failures cannot break investigations
        publisher.record_investigation(
            investigation_id="inv-err",
            findings_count=1,
            total_savings_usd=5.0,
            bedrock_cost_usd=0.10,
        )

    def test_record_investigation_swallows_any_exception(
        self, publisher: MetricsPublisher, mock_cw: MagicMock
    ) -> None:
        mock_cw.put_metric_data.side_effect = RuntimeError("unexpected")

        publisher.record_investigation(
            investigation_id="inv-rt",
            findings_count=0,
            total_savings_usd=0.0,
            bedrock_cost_usd=0.0,
        )

    def test_record_investigation_findings_value_matches_count(
        self, publisher: MetricsPublisher, mock_cw: MagicMock
    ) -> None:
        publisher.record_investigation(
            investigation_id="inv-cnt",
            findings_count=7,
            total_savings_usd=120.50,
            bedrock_cost_usd=0.35,
        )

        call_kwargs = mock_cw.put_metric_data.call_args.kwargs
        findings_metric = next(
            m for m in call_kwargs["MetricData"] if m["MetricName"] == "findings_total"
        )
        assert findings_metric["Value"] == 7.0
