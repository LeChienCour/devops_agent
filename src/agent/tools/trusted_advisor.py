"""Trusted Advisor tool — in-process wrapper used by the LangGraph agent.

MCP-compatible schema kept in src/mcp_servers/trusted_advisor/ for standalone demo use.

Note: Trusted Advisor requires an AWS Business or Enterprise support plan.
The Support API endpoint is global and only available in us-east-1.
"""

from __future__ import annotations

from typing import Any

from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

from common.aws_clients import get_client

logger = Logger(service="finops-agent")

# Trusted Advisor Support API is only available in us-east-1
_SUPPORT_REGION = "us-east-1"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_cost_optimization_checks",
        "description": (
            "Lists all Trusted Advisor checks in the 'cost_optimizing' category "
            "and their current results, including estimated monthly savings. "
            "Requires AWS Business or Enterprise support plan. "
            "Returns an empty list with a warning if the plan is insufficient."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": (
                        "Ignored — Trusted Advisor Support API is always global (us-east-1). "
                        "Included for interface consistency."
                    ),
                    "default": "us-east-1",
                },
            },
            "required": [],
        },
    },
]


def list_cost_optimization_checks(
    region: str = "us-east-1",  # noqa: ARG001 — kept for registry interface consistency
) -> dict[str, Any]:
    """Return Trusted Advisor cost optimisation checks with their current status.

    Fetches all checks in the ``cost_optimizing`` category and retrieves
    individual results including estimated monthly savings from the metadata.

    The ``region`` parameter is accepted for interface consistency with other
    tools but is ignored — the Support API is always called against
    ``us-east-1`` (global endpoint).

    Args:
        region: Ignored. Kept for uniform tool signature across the registry.

    Returns:
        Dict with ``checks`` list (each having ``checkId``, ``name``, ``status``,
        ``estimated_monthly_savings``) and optionally a ``warning`` key if the
        account does not have a qualifying support plan.
    """
    support = get_client("support", _SUPPORT_REGION)

    try:
        checks_response = support.describe_trusted_advisor_checks(language="en")
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code == "SubscriptionRequiredException":
            logger.warning(
                "trusted_advisor_subscription_required",
                message="Business or Enterprise support plan required for Trusted Advisor API.",
            )
            return {
                "checks": [],
                "warning": "Business/Enterprise support plan required",
            }
        raise

    cost_checks = [
        check
        for check in checks_response.get("checks", [])
        if check.get("category") == "cost_optimizing"
    ]

    results: list[dict[str, object]] = []
    for check in cost_checks:
        check_id: str = check["id"]
        check_name: str = check.get("name", "")

        try:
            result_response = support.describe_trusted_advisor_check_result(
                checkId=check_id,
                language="en",
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            logger.warning(
                "trusted_advisor_check_result_error",
                check_id=check_id,
                check_name=check_name,
                error_code=error_code,
            )
            continue

        result = result_response.get("result", {})
        status: str = result.get("status", "unknown")

        # Estimated savings live in result.categorySpecificSummary.costOptimizing
        category_summary = result.get("categorySpecificSummary", {})
        cost_optimizing = category_summary.get("costOptimizing", {})
        estimated_monthly_savings: float = float(
            cost_optimizing.get("estimatedMonthlySavings", 0.0)
        )

        results.append(
            {
                "checkId": check_id,
                "name": check_name,
                "status": status,
                "estimated_monthly_savings": estimated_monthly_savings,
            }
        )

    logger.info(
        "list_cost_optimization_checks_complete",
        check_count=len(results),
    )
    return {"checks": results}
