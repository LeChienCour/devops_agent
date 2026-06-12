"""AWS Lambda entry point for the FinOps agent."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from aws_lambda_powertools.utilities.typing import LambdaContext

from agent.graph import build_graph
from agent.guardrails import GuardrailsState
from agent.state import AgentState
from common.config import get_config
from common.logger import get_logger
from common.metrics import MetricsPublisher

logger = get_logger(__name__)

_AGENT_CONFIG = get_config()
_GRAPH = build_graph(_AGENT_CONFIG)


def _build_initial_state(
    investigation_id: str, trigger: str, model_id: str | None = None
) -> AgentState:
    """Construct the initial AgentState for a new investigation.

    Args:
        investigation_id: UUID4 string for this run.
        trigger: Source of the investigation — "scheduled" or "on_demand".
        model_id: Optional Bedrock model ID override for this run.

    Returns:
        A freshly initialised AgentState TypedDict.
    """
    return AgentState(
        investigation_id=investigation_id,
        trigger=trigger,
        model_id=model_id,
        messages=[],
        plan=None,
        gathered_data=[],
        analyzed_data_count=0,
        findings=[],
        recommendation=None,
        needs_more_data=False,
        guardrails=GuardrailsState(model_id=model_id or _AGENT_CONFIG.bedrock_model_id),
        error=None,
    )


async def _run_investigation(event: dict[str, Any]) -> dict[str, Any]:
    """Core async investigation logic extracted for testability.

    Args:
        event: Lambda event dict.

    Returns:
        Result dict with investigation_id, findings_count, total_savings_usd,
        bedrock_cost_usd, and optional error fields.
    """
    detail: dict[str, Any] = event.get("detail") or {}
    trigger: str = str(event.get("trigger") or detail.get("trigger") or "scheduled")
    model_id_raw = event.get("model_id") or detail.get("model_id")
    model_id: str | None = str(model_id_raw) if model_id_raw else None
    investigation_id = str(uuid.uuid4())

    log = logger.bind(investigation_id=investigation_id, trigger=trigger)
    log.info("investigation_started", model_id=model_id or _AGENT_CONFIG.bedrock_model_id)

    initial_state = _build_initial_state(investigation_id, trigger, model_id)

    final_state: AgentState = await asyncio.wait_for(
        _GRAPH.ainvoke(initial_state),  # type: ignore[arg-type]
        timeout=_AGENT_CONFIG.investigation_timeout_sec,
    )

    recommendation = final_state.get("recommendation")
    guardrails = final_state["guardrails"]

    findings_count = len(recommendation.findings) if recommendation else 0
    total_savings = recommendation.total_estimated_monthly_usd if recommendation else 0.0

    log.info(
        "investigation_complete",
        findings_count=findings_count,
        total_savings_usd=total_savings,
        bedrock_cost_usd=guardrails.estimated_cost_usd,
        iterations=guardrails.iterations,
        guardrail_violations=len(guardrails.violations),
    )

    MetricsPublisher(_AGENT_CONFIG).record_investigation(
        investigation_id=investigation_id,
        findings_count=findings_count,
        total_savings_usd=total_savings,
        bedrock_cost_usd=guardrails.estimated_cost_usd,
        violations_count=len(guardrails.violations),
    )

    return {
        "investigation_id": investigation_id,
        "findings_count": findings_count,
        "total_savings_usd": total_savings,
        "bedrock_cost_usd": guardrails.estimated_cost_usd,
        "status": "COMPLETED",
    }


def lambda_handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:  # noqa: ARG001
    """AWS Lambda handler — entry point for scheduled and on-demand invocations.

    Args:
        event: Lambda event dict; may contain ``trigger`` field.
        context: Lambda runtime context (unused, required by interface).

    Returns:
        Dict with investigation results or an error response.  Never raises.
    """
    try:
        return asyncio.run(_run_investigation(event))
    except TimeoutError:
        logger.error("investigation_timeout")
        return {
            "investigation_id": "unknown",
            "status": "FAILED",
            "error": "Investigation timed out",
            "findings_count": 0,
            "total_savings_usd": 0.0,
            "bedrock_cost_usd": 0.0,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("investigation_unhandled_error", error=str(exc), exc_info=True)
        return {
            "investigation_id": "unknown",
            "status": "FAILED",
            "error": str(exc),
            "findings_count": 0,
            "total_savings_usd": 0.0,
            "bedrock_cost_usd": 0.0,
        }
