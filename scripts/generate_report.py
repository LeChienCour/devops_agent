#!/usr/bin/env python3
"""Generate a Markdown report for a completed FinOps investigation.

Reads findings from DynamoDB for a given ``investigation_id`` and writes
a formatted Markdown report to stdout or a file.  No LLM calls are made.

Usage::

    python scripts/generate_report.py \\
        --investigation-id INV_ID \\
        [--output report.md] \\
        [--region us-east-1]
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure src/ is importable when the script is executed directly.
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402 — must come after sys.path manipulation

load_dotenv(_REPO_ROOT / ".env")

from common.aws_clients import get_client  # noqa: E402
from common.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# DynamoDB query helpers
# ---------------------------------------------------------------------------


def _query_investigation(
    client: Any,
    table_name: str,
    investigation_id: str,
) -> list[dict[str, Any]]:
    """Return all DynamoDB items for an investigation sorted by SK.

    Uses a KeyConditionExpression to fetch the single partition and filters
    server-side for SK values beginning with ``"finding#"``.

    Args:
        client: Boto3 DynamoDB client.
        table_name: Name of the DynamoDB findings table.
        investigation_id: PK value (investigation UUID).

    Returns:
        List of raw DynamoDB attribute-map dicts for finding items only.
    """
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "TableName": table_name,
        "KeyConditionExpression": (
            "investigation_id = :pk AND begins_with(sk, :prefix)"
        ),
        "ExpressionAttributeValues": {
            ":pk": {"S": investigation_id},
            ":prefix": {"S": "finding#"},
        },
    }

    # Paginate in case there are many findings.
    while True:
        response: dict[str, Any] = client.query(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    return items


def _query_meta(
    client: Any,
    table_name: str,
    investigation_id: str,
) -> dict[str, Any] | None:
    """Fetch the ``meta#summary`` item for an investigation.

    Args:
        client: Boto3 DynamoDB client.
        table_name: Name of the DynamoDB findings table.
        investigation_id: PK value (investigation UUID).

    Returns:
        Raw DynamoDB attribute-map dict, or ``None`` if the item does not exist.
    """
    response: dict[str, Any] = client.get_item(
        TableName=table_name,
        Key={
            "investigation_id": {"S": investigation_id},
            "sk": {"S": "meta#summary"},
        },
    )
    return response.get("Item")  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _str(item: dict[str, Any], key: str, default: str = "") -> str:
    """Extract a string value from a DynamoDB attribute map.

    Args:
        item: DynamoDB item dict.
        key: Attribute name.
        default: Value returned when the attribute is absent.

    Returns:
        String attribute value or *default*.
    """
    attr = item.get(key, {})
    return str(attr.get("S", default))


def _num(item: dict[str, Any], key: str, default: float = 0.0) -> float:
    """Extract a numeric value from a DynamoDB attribute map.

    Args:
        item: DynamoDB item dict.
        key: Attribute name.
        default: Value returned when the attribute is absent.

    Returns:
        Float value or *default*.
    """
    attr = item.get(key, {})
    raw = attr.get("N")
    if raw is None:
        return default
    return float(raw)


def _render_markdown(
    investigation_id: str,
    meta: dict[str, Any] | None,
    finding_items: list[dict[str, Any]],
    generated_at: str,
) -> str:
    """Render a complete Markdown report from raw DynamoDB items.

    Args:
        investigation_id: Investigation UUID string.
        meta: Raw ``meta#summary`` DynamoDB item, or ``None`` if not found.
        finding_items: List of raw ``finding#…`` DynamoDB items.
        generated_at: ISO-8601 UTC timestamp string for the report header.

    Returns:
        Rendered Markdown string.
    """
    total_savings = _num(meta, "total_savings_usd") if meta else 0.0
    summary_from_meta = ""  # meta#summary does not store free-text summary

    # Sort findings descending by estimated monthly cost
    sorted_findings = sorted(
        finding_items,
        key=lambda i: _num(i, "estimated_monthly_usd"),
        reverse=True,
    )

    lines: list[str] = [
        "# FinOps Investigation Report",
        "",
        f"**Investigation ID:** {investigation_id}",
        f"**Generated:** {generated_at}",
        f"**Total estimated savings:** ${total_savings:.2f}/month",
        "",
    ]

    lines += [
        f"## Findings ({len(sorted_findings)})",
        "",
    ]

    for idx, item in enumerate(sorted_findings, start=1):
        severity = _str(item, "severity", "UNKNOWN")
        title = _str(item, "title", "Untitled")
        usd = _num(item, "estimated_monthly_usd")
        description = _str(item, "description")
        resource_ids_attr = item.get("resource_ids", {})
        resources = resource_ids_attr.get("SS", [])
        resource_str = ", ".join(resources) if resources else _str(item, "resource_ids", "N/A")
        confidence_pct = int(_num(item, "confidence") * 100)
        remediation = _str(item, "remediation_command")

        lines += [
            f"### {idx}. [{severity}] {title} (~${usd:.2f}/mo)",
            "",
            f"**Description:** {description}",
            f"**Resource:** {resource_str or 'N/A'}",
            f"**Confidence:** {confidence_pct}%",
        ]

        if remediation:
            lines += [
                "**Remediation:**",
                "```",
                remediation,
                "```",
            ]

        lines.append("")

    if summary_from_meta:
        lines += [
            "## Summary",
            "",
            summary_from_meta,
            "",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Markdown report from a FinOps investigation stored in DynamoDB."
    )
    parser.add_argument(
        "--investigation-id",
        required=True,
        help="Investigation ID (UUID) to generate the report for.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path.  Prints to stdout when not specified.",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region where the DynamoDB table resides (default: us-east-1).",
    )
    parser.add_argument(
        "--table",
        default="finops-agent-findings",
        help="DynamoDB table name (default: finops-agent-findings).",
    )
    return parser.parse_args()


def main() -> int:
    """Entry point for the report generator CLI.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    args = _parse_args()
    investigation_id: str = args.investigation_id
    region: str = args.region
    table_name: str = args.table
    output_path: str | None = args.output

    log = logger.bind(investigation_id=investigation_id, region=region, table=table_name)
    log.info("generate_report_started")

    try:
        client = get_client("dynamodb", region)
        meta = _query_meta(client, table_name, investigation_id)
        finding_items = _query_investigation(client, table_name, investigation_id)
    except Exception as exc:  # noqa: BLE001
        log.error("generate_report_dynamodb_error", error=str(exc))
        print(f"[ERROR] DynamoDB query failed: {exc}", file=sys.stderr)
        return 1

    if meta is None and not finding_items:
        print(
            f"[ERROR] No data found for investigation_id='{investigation_id}'",
            file=sys.stderr,
        )
        return 1

    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = _render_markdown(investigation_id, meta, finding_items, generated_at)

    if output_path:
        Path(output_path).write_text(report, encoding="utf-8")
        log.info("generate_report_written", output=output_path, findings=len(finding_items))
        print(f"Report written to {output_path}")
    else:
        print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
