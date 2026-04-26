"""DynamoDB persistence layer for FinOps agent findings and recommendations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from botocore.exceptions import ClientError

from agent.guardrails import GuardrailsState
from agent.models.finding import Finding, Recommendation
from common.aws_clients import get_client
from common.config import AgentConfig
from common.logger import get_logger

__all__ = ["DynamoDBWriter"]

_TTL_DAYS = 90


def _make_ttl() -> int:
    """Compute a Unix epoch TTL 90 days from now.

    Returns:
        Integer Unix timestamp for expiry.
    """
    return int((datetime.now(UTC) + timedelta(days=_TTL_DAYS)).timestamp())


def _finding_to_item(
    investigation_id: str,
    finding: Finding,
    ttl: int,
) -> dict[str, Any]:
    """Serialise a Finding into a DynamoDB-ready attribute map.

    Args:
        investigation_id: The PK value for this investigation.
        finding: Validated Finding object.
        ttl: Pre-computed TTL epoch integer.

    Returns:
        Dict suitable for ``put_item`` / ``batch_write_item``.
    """
    # Use finding_id (UUID4) as the ULID-like unique suffix so no extra dep needed
    sk = f"finding#{finding.finding_id}"

    item: dict[str, Any] = {
        "investigation_id": {"S": investigation_id},
        "sk": {"S": sk},
        "finding_type": {"S": finding.finding_type},
        "severity": {"S": str(finding.severity)},
        "title": {"S": finding.title},
        "description": {"S": finding.description},
        "estimated_monthly_usd": {"N": str(finding.estimated_monthly_usd)},
        "confidence": {"N": str(finding.confidence)},
        "created_at": {"S": finding.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")},
        "ttl": {"N": str(ttl)},
    }

    if finding.remediation_command is not None:
        item["remediation_command"] = {"S": finding.remediation_command}

    if finding.resource_id is not None:
        item["resource_ids"] = {"SS": [finding.resource_id]}

    region = finding.evidence.get("region")
    if isinstance(region, str) and region:
        item["region"] = {"S": region}

    return item


def _recommendation_to_meta_item(
    investigation_id: str,
    recommendation: Recommendation,
    guardrails_state: GuardrailsState,
    ttl: int,
) -> dict[str, Any]:
    """Serialise a Recommendation into the ``meta#summary`` DynamoDB item.

    Args:
        investigation_id: The PK value for this investigation.
        recommendation: Completed Recommendation object.
        guardrails_state: Guardrails counters from the same run.
        ttl: Pre-computed TTL epoch integer.

    Returns:
        Dict suitable for ``put_item``.
    """
    return {
        "investigation_id": {"S": investigation_id},
        "sk": {"S": "meta#summary"},
        "total_savings_usd": {"N": str(recommendation.total_estimated_monthly_usd)},
        "findings_count": {"N": str(len(recommendation.findings))},
        "created_at": {"S": recommendation.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")},
        "guardrail_violations": {"N": str(len(guardrails_state.violations))},
        "estimated_bedrock_cost_usd": {"N": str(round(guardrails_state.estimated_cost_usd, 6))},
        "ttl": {"N": str(ttl)},
    }


class DynamoDBWriter:
    """Persists investigation findings and recommendations to DynamoDB.

    Each investigation maps to a set of items under a shared PK
    (``investigation_id``).  One ``meta#summary`` item captures the
    recommendation header; one ``finding#<uuid>`` item is written per finding.

    Attributes:
        _table_name: DynamoDB table name read from AgentConfig.
        _region: AWS region used to build the boto3 client.
    """

    def __init__(self, config: AgentConfig | None = None) -> None:
        """Initialise the writer from agent configuration.

        Args:
            config: Optional AgentConfig instance.  A default instance is
                created from environment variables when not supplied.
        """
        _config = config or AgentConfig()
        self._table_name: str = _config.dynamodb_table_name
        self._region: str = _config.aws_region
        self._log = get_logger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write_investigation(
        self,
        investigation_id: str,
        recommendation: Recommendation,
        guardrails_state: GuardrailsState,
    ) -> None:
        """Write a complete investigation (meta + all findings) to DynamoDB.

        Writes are individual ``put_item`` calls rather than a batch so that a
        single-item failure does not silently skip remaining writes.

        Args:
            investigation_id: UUID4 string uniquely identifying this run.
            recommendation: Final Recommendation produced by the recommend node.
            guardrails_state: Guardrails state for the same run (violations, cost).

        Raises:
            ClientError: Re-raised after logging when any DynamoDB call fails.
        """
        log = self._log.bind(
            investigation_id=investigation_id,
            table=self._table_name,
            findings_count=len(recommendation.findings),
        )

        ttl = _make_ttl()
        client = get_client("dynamodb", self._region)

        # 1. Write the meta#summary item first
        meta_item = _recommendation_to_meta_item(
            investigation_id, recommendation, guardrails_state, ttl
        )
        self._put_item(client, meta_item, log)
        log.info("dynamodb_writer_meta_written", sk="meta#summary")

        # 2. Write one item per finding
        for finding in recommendation.findings:
            finding_item = _finding_to_item(investigation_id, finding, ttl)
            self._put_item(client, finding_item, log)
            log.info(
                "dynamodb_writer_finding_written",
                sk=finding_item["sk"]["S"],
                finding_type=finding.finding_type,
            )

        log.info(
            "dynamodb_writer_investigation_complete",
            items_written=1 + len(recommendation.findings),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _put_item(
        self,
        client: Any,
        item: dict[str, Any],
        log: Any,
    ) -> None:
        """Execute a single put_item call and re-raise ClientError on failure.

        Args:
            client: Boto3 DynamoDB client.
            item: Fully serialised DynamoDB attribute map.
            log: Bound structlog logger for this investigation.

        Raises:
            ClientError: Re-raised after logging the error code and message.
        """
        try:
            client.put_item(TableName=self._table_name, Item=item)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            error_msg = exc.response.get("Error", {}).get("Message", "")
            log.error(
                "dynamodb_writer_put_item_failed",
                error_code=error_code,
                error_message=error_msg,
                sk=item.get("sk", {}).get("S", "unknown"),
            )
            raise
