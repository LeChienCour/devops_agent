"""CloudWatch custom metrics publisher for investigation observability."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from common.aws_clients import get_client
from common.config import AgentConfig
from common.logger import get_logger

logger = get_logger(__name__)

_NAMESPACE = "FinOpsAgent"


class MetricsPublisher:
    """Publishes investigation outcome metrics to CloudWatch.

    Failures are logged but never re-raised — metrics must not affect
    investigation results.

    Args:
        config: Runtime configuration (uses aws_region).
    """

    def __init__(self, config: AgentConfig) -> None:
        self._region = config.aws_region
        self._cw = get_client("cloudwatch", config.aws_region)

    def record_investigation(
        self,
        investigation_id: str,
        findings_count: int,
        total_savings_usd: float,
        bedrock_cost_usd: float,
        violations_count: int = 0,
    ) -> None:
        """Publish investigation outcome metrics to CloudWatch.

        Metrics published:
          - ``investigations_run`` (Count, always 1)
          - ``findings_total`` (Count)
          - ``total_savings_usd`` (None unit — USD float)
          - ``bedrock_cost_usd`` (None unit — USD float)
          - ``guardrail_violations`` (Count, only when > 0)

        Args:
            investigation_id: UUID of the investigation run.
            findings_count: Number of validated findings above threshold.
            total_savings_usd: Sum of estimated monthly savings in USD.
            bedrock_cost_usd: Estimated Bedrock spend for this run in USD.
            violations_count: Number of guardrail violations triggered.
        """
        now = datetime.now(tz=UTC)
        metric_data: list[dict[str, Any]] = [
            {
                "MetricName": "investigations_run",
                "Value": 1.0,
                "Unit": "Count",
                "Timestamp": now,
            },
            {
                "MetricName": "findings_total",
                "Value": float(findings_count),
                "Unit": "Count",
                "Timestamp": now,
            },
            {
                "MetricName": "total_savings_usd",
                "Value": total_savings_usd,
                "Unit": "None",
                "Timestamp": now,
            },
            {
                "MetricName": "bedrock_cost_usd",
                "Value": bedrock_cost_usd,
                "Unit": "None",
                "Timestamp": now,
            },
        ]
        if violations_count > 0:
            metric_data.append(
                {
                    "MetricName": "guardrail_violations",
                    "Value": float(violations_count),
                    "Unit": "Count",
                    "Timestamp": now,
                }
            )

        try:
            self._cw.put_metric_data(Namespace=_NAMESPACE, MetricData=metric_data)
            logger.info(
                "metrics_published",
                investigation_id=investigation_id,
                findings_count=findings_count,
                total_savings_usd=round(total_savings_usd, 2),
                bedrock_cost_usd=round(bedrock_cost_usd, 4),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("metrics_publish_failed", error=str(exc))
