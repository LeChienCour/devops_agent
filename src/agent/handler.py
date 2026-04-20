"""AWS Lambda entry point for the FinOps agent."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from aws_lambda_powertools.utilities.typing import LambdaContext

from agent.graph import build_graph
from agent.guardrails import GuardrailsState
from agent.state import AgentState
from common.config import AgentConfig
from common.logger import get_logger

logger = get_logger(__name__)


def _build_initial_state(investigation_id: str, trigger: str) -> AgentState:
    """Construct the initial AgentState for a new investigation.

    Args:
        investigation_id: UUID4 string for this run.
        trigger: Source of the investigation — "scheduled" or "on_demand".

    Returns:
        A freshly initialised AgentState TypedDict.
    """
    return AgentState(
        investigation_id=investigation_id,
        trigger=trigger,
        messages=[],
        plan=None,
        gathered_data=[],
        findings=[],
        recommendation=None,
        needs_more_data=False,
        guardrails=GuardrailsState(),
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
    trigger: str = str(event.get("trigger", "scheduled"))
    investigation_id = str(uuid.uuid4())

    log = logger.bind(investigation_id=investigation_id, trigger=trigger)
    log.info("investigation_started")

    agent_config = AgentConfig()
    graph = build_graph(agent_config)
    initial_state = _build_initial_state(investigation_id, trigger)

    final_state: AgentState = await asyncio.wait_for(
        graph.ainvoke(initial_state),
        timeout=agent_config.investigation_timeout_sec,
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
